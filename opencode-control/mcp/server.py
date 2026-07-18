#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0", "httpx>=0.27"]
# ///
"""opencode control MCP server.

Drives the OpenCode AI coding agent (sst/opencode) two ways:

  1. HTTP server  — `opencode serve` exposes ~162 REST operations (a legacy API
     and a parallel `/api/*` v2 API). This server talks to it.
       * Generic passthrough (oc_call / oc_discover / oc_schema) reaches EVERY route.
       * Curated tools wrap the common jobs (status, sessions, prompt, agents,
         commands, skills, models, config, mcp, files/find, vcs, tui control).
  2. ACP  — `opencode acp` speaks the Agent Client Protocol (JSON-RPC 2.0 over
     stdio). oc_acp_prompt spawns it, runs the initialize handshake, creates a
     session, sends a prompt, and returns the streamed result. This is the
     "call opencode as an agent from anywhere" connector.

Config authoring (agents / commands / skills are FILES, not HTTP resources):
     oc_agent_write / oc_command_write / oc_skill_write create them on disk in
     the opencode config dir, and oc_config_update patches opencode.json.

Conventions (verified live against opencode 1.18.3):
  * Local server is unauthenticated on 127.0.0.1 unless OPENCODE_SERVER_PASSWORD
    is set, in which case requests need `Authorization: Bearer <password>`.
  * Plain JSON in/out. Legacy routes return bare arrays/objects.
  * Destructive/disruptive writes are confirm-gated. Logs to stderr; stdout=MCP.
"""

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
import acp_client as ACP  # noqa: E402

# ----------------------------------------------------------------- config

def _load_config() -> dict:
    cfg = {
        "base_url": "http://127.0.0.1:4096",
        "username": "opencode",         # OPENCODE_SERVER_USERNAME (Basic-auth user)
        "password": "",                 # OPENCODE_SERVER_PASSWORD, if the server is secured
        "opencode_bin": "opencode",     # binary for ACP / CLI helpers
        "config_dir": "",               # opencode config dir (auto-detected from /path if blank)
        "default_cwd": "",              # cwd for ACP sessions (defaults to $HOME)
        "timeout": 120,
    }
    path = os.environ.get("OPENCODE_CONFIG")
    if path and Path(path).expanduser().exists():
        try:
            cfg.update(json.loads(Path(path).expanduser().read_text()))
        except Exception as e:  # noqa: BLE001
            print(f"[opencode] bad config {path}: {e}", file=sys.stderr)
    if os.environ.get("OPENCODE_BASE_URL"):
        cfg["base_url"] = os.environ["OPENCODE_BASE_URL"]
    if os.environ.get("OPENCODE_SERVER_PASSWORD"):
        cfg["password"] = os.environ["OPENCODE_SERVER_PASSWORD"]
    if os.environ.get("OPENCODE_SERVER_USERNAME"):
        cfg["username"] = os.environ["OPENCODE_SERVER_USERNAME"]
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg

CFG = _load_config()
mcp = FastMCP("opencode")

_spec_cache: dict[str, Any] = {}


def _headers() -> dict:
    # opencode server auth is HTTP Basic (user defaults to "opencode") when
    # OPENCODE_SERVER_PASSWORD is set; open on localhost otherwise.
    h = {"Content-Type": "application/json"}
    if CFG.get("password"):
        import base64
        tok = base64.b64encode(
            f"{CFG.get('username', 'opencode')}:{CFG['password']}".encode()).decode()
        h["Authorization"] = f"Basic {tok}"
    return h


async def _req(method: str, path: str, *, params: dict | None = None,
               body: Any = None, timeout: float | None = None) -> Any:
    url = CFG["base_url"] + (path if path.startswith("/") else "/" + path)
    to = timeout if timeout is not None else CFG["timeout"]
    async with httpx.AsyncClient(timeout=to) as client:
        r = await client.request(method.upper(), url, params=params,
                                 json=body if body is not None else None,
                                 headers=_headers())
        r.raise_for_status()
        ct = r.headers.get("content-type", "")
        if "application/json" in ct:
            return r.json()
        return r.text


def _err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        detail = ""
        try:
            detail = json.dumps(e.response.json())[:400]
        except Exception:  # noqa: BLE001
            detail = e.response.text[:400]
        return f"HTTP {e.response.status_code} on {e.request.url}: {detail}"
    if isinstance(e, httpx.ConnectError):
        return (f"Cannot reach opencode server at {CFG['base_url']}. "
                f"Start one with `opencode serve --port <PORT>` and set base_url "
                f"in config.local.json (or OPENCODE_BASE_URL).")
    return f"{type(e).__name__}: {e}"


async def _spec() -> dict:
    if "doc" not in _spec_cache:
        _spec_cache["doc"] = await _req("GET", "/doc")
    return _spec_cache["doc"]


async def _config_dir() -> Path:
    if CFG.get("config_dir"):
        return Path(CFG["config_dir"]).expanduser()
    try:
        p = await _req("GET", "/path")
        if isinstance(p, dict) and p.get("config"):
            return Path(p["config"])
    except Exception:  # noqa: BLE001
        pass
    return Path("~/.config/opencode").expanduser()


def _dump(obj: Any, limit: int = 6000) -> str:
    s = json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj
    if len(s) > limit:
        s = s[:limit] + f"\n... [truncated, {len(s)} chars total]"
    return s

# ================================================================ GENERIC LAYER

@mcp.tool()
async def oc_status() -> str:
    """Health + identity snapshot of the opencode server: reachability, health,
    version, paths, current project, default model/agent, session count, and
    configured providers. Start here."""
    out: dict[str, Any] = {"base_url": CFG["base_url"]}
    try:
        out["health"] = await _req("GET", "/api/health")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    for label, path in [("path", "/path"), ("project", "/project/current"),
                        ("config", "/config")]:
        try:
            out[label] = await _req("GET", path)
        except Exception as e:  # noqa: BLE001
            out[label] = _err(e)
    cfg = out.get("config", {})
    if isinstance(cfg, dict):
        out["defaults"] = {"model": cfg.get("model"), "small_model": cfg.get("small_model"),
                           "username": cfg.get("username")}
        out.pop("config", None)
    try:
        sessions = await _req("GET", "/session")
        out["session_count"] = len(sessions) if isinstance(sessions, list) else None
    except Exception:  # noqa: BLE001
        pass
    try:
        prov = await _req("GET", "/config/providers")
        ids = [p.get("id") for p in prov.get("providers", [])] if isinstance(prov, dict) else None
        out["configured_providers"] = ids
    except Exception:  # noqa: BLE001
        pass
    return _dump(out)


@mcp.tool()
async def oc_discover(query: str = "", limit: int = 60) -> str:
    """Search the live OpenAPI surface (all ~162 operations pulled from the server's
    /doc). Returns matching METHOD path -> operationId : summary. Use this to find
    the right endpoint for oc_call. Empty query lists everything (grouped)."""
    try:
        spec = await _spec()
    except Exception as e:  # noqa: BLE001
        return _err(e)
    q = query.lower().strip()
    rows = []
    for path in sorted(spec.get("paths", {})):
        for m, op in spec["paths"][path].items():
            if m not in ("get", "post", "put", "delete", "patch"):
                continue
            oid = op.get("operationId", "")
            summ = op.get("summary", "") or (op.get("description", "") or "")[:60]
            hay = f"{m} {path} {oid} {summ}".lower()
            if not q or all(tok in hay for tok in q.split()):
                rows.append(f"{m.upper():6} {path:48} {oid:32} {summ}")
    head = f"{len(rows)} operation(s)" + (f" matching '{query}'" if q else " total")
    return head + ":\n" + "\n".join(rows[:limit]) + (
        f"\n... (+{len(rows)-limit} more; narrow the query)" if len(rows) > limit else "")


@mcp.tool()
async def oc_schema(operation: str) -> str:
    """Show the request-body + response schema for an operation, identified by
    operationId (e.g. 'session.prompt') or by path (e.g. '/session/{sessionID}/message').
    Use before oc_call to get params right."""
    try:
        spec = await _spec()
    except Exception as e:  # noqa: BLE001
        return _err(e)
    comps = spec.get("components", {}).get("schemas", {})

    def deref(sch: Any, depth: int = 0) -> Any:
        if depth > 5 or not isinstance(sch, dict):
            return sch if not isinstance(sch, dict) else "..."
        if "$ref" in sch:
            name = sch["$ref"].split("/")[-1]
            target = comps.get(name, {})
            return {f"<{name}>": deref(target, depth + 1)}
        if "anyOf" in sch:
            return {"anyOf": [deref(x, depth + 1) for x in sch["anyOf"][:6]]}
        t = sch.get("type")
        if t == "object" or "properties" in sch:
            props = sch.get("properties", {})
            req = set(sch.get("required", []))
            return {(f"{k}*" if k in req else k): deref(v, depth + 1)
                    for k, v in list(props.items())[:30]}
        if t == "array":
            return [deref(sch.get("items", {}), depth + 1)]
        return sch.get("type", sch.get("const", sch.get("enum", "any")))

    found = []
    for path, methods in spec.get("paths", {}).items():
        for m, op in methods.items():
            if m not in ("get", "post", "put", "delete", "patch"):
                continue
            if operation == op.get("operationId") or operation == path or operation in path:
                rb = (op.get("requestBody", {}).get("content", {})
                      .get("application/json", {}).get("schema"))
                resp = (op.get("responses", {}).get("200", {}).get("content", {})
                        .get("application/json", {}).get("schema"))
                params = [f"{p['name']} ({p.get('in')})" for p in op.get("parameters", [])]
                found.append({
                    "op": f"{m.upper()} {path}", "operationId": op.get("operationId"),
                    "summary": op.get("summary"), "path_query_params": params or None,
                    "request_body": deref(rb) if rb else None,
                    "response": deref(resp) if resp else None,
                })
    if not found:
        return f"No operation matching '{operation}'. Try oc_discover to find it."
    return _dump(found[:4])


@mcp.tool()
async def oc_call(method: str, path: str, params: Optional[dict] = None,
                  body: Optional[dict] = None, confirm: bool = False) -> str:
    """Generic passthrough to ANY opencode endpoint (the escape hatch for the long
    tail beyond the curated tools). method=GET/POST/PUT/DELETE/PATCH, path e.g.
    '/session' or '/api/session/{id}/prompt'. params=query string, body=JSON body.
    Non-GET calls require confirm=true (they can mutate state)."""
    if method.upper() != "GET" and not confirm:
        return (f"Refusing {method.upper()} {path} without confirm=true — this can "
                f"change server state. Re-call with confirm=true once you've reviewed it.")
    try:
        return _dump(await _req(method, path, params=params, body=body), limit=12000)
    except Exception as e:  # noqa: BLE001
        return _err(e)

# ================================================================ SESSIONS

@mcp.tool()
async def oc_sessions(limit: int = 30) -> str:
    """List sessions (most recent first): id, title, agent, updated time, parent."""
    try:
        s = await _req("GET", "/session")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    if not isinstance(s, list):
        return _dump(s)
    def ts(x):
        t = x.get("time", {})
        return t.get("updated", t.get("created", 0)) if isinstance(t, dict) else 0
    s.sort(key=ts, reverse=True)
    rows = []
    for x in s[:limit]:
        rows.append({"id": x.get("id"), "title": (x.get("title") or "")[:60],
                     "parentID": x.get("parentID"),
                     "version": x.get("version"), "updated": ts(x)})
    return f"{len(s)} session(s), showing {min(limit,len(s))}:\n" + _dump(rows)


@mcp.tool()
async def oc_session(session_id: str, messages: bool = False, todos: bool = False) -> str:
    """Get one session's details. messages=true also returns a compact message log;
    todos=true returns the session's todo list."""
    out: dict[str, Any] = {}
    try:
        out["session"] = await _req("GET", f"/session/{session_id}")
        if messages:
            msgs = await _req("GET", f"/session/{session_id}/message")
            out["messages"] = _compact_messages(msgs)
        if todos:
            out["todos"] = await _req("GET", f"/session/{session_id}/todo")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    return _dump(out, limit=12000)


def _compact_messages(msgs: Any) -> list:
    out = []
    if not isinstance(msgs, list):
        return msgs
    for m in msgs:
        info = m.get("info", m) if isinstance(m, dict) else {}
        parts = m.get("parts", []) if isinstance(m, dict) else []
        texts = []
        for p in parts:
            if not isinstance(p, dict):
                continue
            typ = p.get("type")
            if typ == "text":
                texts.append((p.get("text") or "")[:500])
            elif typ == "tool":
                texts.append(f"[tool:{p.get('tool','?')} {p.get('state',{}).get('status','')}]")
            elif typ == "reasoning":
                texts.append("[reasoning]")
            elif typ == "step-start":
                continue
            else:
                texts.append(f"[{typ}]")
        out.append({"role": info.get("role"), "id": info.get("id"),
                    "text": " ".join(t for t in texts if t)[:800]})
    return out


@mcp.tool()
async def oc_session_create(title: str = "", agent: str = "", model: str = "",
                            parent_id: str = "") -> str:
    """Create a new session. model as 'provider/model' (optional). agent name optional.
    parent_id creates a child session. Returns the new session id."""
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if agent:
        body["agent"] = agent
    if parent_id:
        body["parentID"] = parent_id
    if model:
        prov, _, mid = model.partition("/")
        body["model"] = {"providerID": prov, "id": mid or prov}
    try:
        return _dump(await _req("POST", "/session", body=body))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_prompt(text: str, session_id: str = "", agent: str = "", model: str = "",
                    files: Optional[list] = None, title: str = "",
                    wait: bool = True, timeout: int = 300) -> str:
    """Send a prompt to opencode and (by default) wait for the assistant's reply.
    If session_id is empty a new session is created first. model='provider/model',
    agent=agent name (e.g. 'build','plan'). files=list of absolute paths to attach.
    Set wait=false to fire-and-forget (returns immediately). This actually runs the
    model — it costs tokens."""
    try:
        if not session_id:
            cbody: dict[str, Any] = {"title": title or text[:50]}
            if agent:
                cbody["agent"] = agent
            sess = await _req("POST", "/session", body=cbody)
            session_id = sess.get("id") if isinstance(sess, dict) else None
            if not session_id:
                return f"Failed to create session: {_dump(sess)}"
        parts: list = [{"type": "text", "text": text}]
        for f in (files or []):
            fp = Path(f).expanduser()
            mime = "text/plain"
            if fp.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                mime = f"image/{fp.suffix.lower().lstrip('.')}"
            parts.append({"type": "file", "mime": mime, "filename": fp.name,
                          "url": f"file://{fp}"})
        body: dict[str, Any] = {"parts": parts}
        if agent:
            body["agent"] = agent
        if model:
            prov, _, mid = model.partition("/")
            body["model"] = {"providerID": prov, "modelID": mid or prov}
        if not wait:
            r = await _req("POST", f"/session/{session_id}/prompt_async", body=body,
                           timeout=30)
            return f"session={session_id} (async, running in background)\n" + _dump(r)
        r = await _req("POST", f"/session/{session_id}/message", body=body,
                       timeout=timeout)
        # response is the assistant message (info + parts)
        reply = _compact_messages([r]) if isinstance(r, dict) else r
        return f"session={session_id}\n" + _dump(reply, limit=10000)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_messages(session_id: str, limit: int = 20) -> str:
    """Get a compact log of the last messages in a session (role + text/tool summary)."""
    try:
        msgs = await _req("GET", f"/session/{session_id}/message")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    c = _compact_messages(msgs)
    if isinstance(c, list):
        c = c[-limit:]
    return _dump(c, limit=12000)


@mcp.tool()
async def oc_abort(session_id: str) -> str:
    """Abort/interrupt a running session (stops the current model turn)."""
    try:
        return _dump(await _req("POST", f"/session/{session_id}/abort", body={}))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_shell(session_id: str, command: str, agent: str = "") -> str:
    """Run a shell command inside a session's context (recorded in the transcript,
    subject to the session's permissions)."""
    body: dict[str, Any] = {"command": command}
    if agent:
        body["agent"] = agent
    try:
        return _dump(await _req("POST", f"/session/{session_id}/shell", body=body),
                     limit=10000)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_command(session_id: str, command: str, arguments: str = "",
                     agent: str = "", model: str = "") -> str:
    """Run a custom/built-in opencode command (slash-command, e.g. 'init') in a
    session, passing arguments as $ARGUMENTS."""
    body: dict[str, Any] = {"command": command}
    if arguments:
        body["arguments"] = arguments
    if agent:
        body["agent"] = agent
    if model:
        body["model"] = model
    try:
        return _dump(await _req("POST", f"/session/{session_id}/command", body=body),
                     limit=10000)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_session_manage(session_id: str, action: str, confirm: bool = False,
                            title: str = "") -> str:
    """Manage a session lifecycle. action = summarize | fork | share | unshare |
    init | rename | delete. delete/unshare require confirm=true."""
    a = action.lower()
    try:
        if a == "summarize":
            return _dump(await _req("POST", f"/session/{session_id}/summarize", body={}))
        if a == "fork":
            return _dump(await _req("POST", f"/session/{session_id}/fork", body={}))
        if a == "share":
            return _dump(await _req("POST", f"/session/{session_id}/share", body={}))
        if a == "init":
            return _dump(await _req("POST", f"/session/{session_id}/init", body={}))
        if a == "rename":
            return _dump(await _req("PATCH", f"/session/{session_id}", body={"title": title}))
        if a in ("unshare", "delete"):
            if not confirm:
                return f"'{a}' needs confirm=true."
            method = "DELETE"
            path = (f"/session/{session_id}/share" if a == "unshare"
                    else f"/session/{session_id}")
            return _dump(await _req(method, path))
        return f"Unknown action '{action}'. Use summarize|fork|share|unshare|init|rename|delete."
    except Exception as e:  # noqa: BLE001
        return _err(e)

# ================================================================ AGENTS / COMMANDS / SKILLS / MODELS

@mcp.tool()
async def oc_agents() -> str:
    """List all agents opencode knows about (built-in + user/project): name, mode
    (primary/subagent), model, description."""
    try:
        a = await _req("GET", "/agent")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    if isinstance(a, list):
        rows = [{"name": x.get("name"), "mode": x.get("mode"),
                 "model": x.get("model"), "builtin": x.get("builtin"),
                 "description": (x.get("description") or "")[:80]} for x in a]
        return _dump(rows)
    return _dump(a)


@mcp.tool()
async def oc_commands() -> str:
    """List custom/built-in commands (slash commands): name, description, agent, template hint."""
    try:
        c = await _req("GET", "/command")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    if isinstance(c, list):
        rows = [{"name": x.get("name"), "description": (x.get("description") or "")[:70],
                 "agent": x.get("agent"), "source": x.get("source")} for x in c]
        return _dump(rows)
    return _dump(c)


@mcp.tool()
async def oc_skills() -> str:
    """List skills available to opencode agents: name, description, location."""
    try:
        s = await _req("GET", "/skill")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    if isinstance(s, list):
        rows = [{"name": x.get("name"), "location": x.get("location"),
                 "description": (x.get("description") or "")[:100]} for x in s]
        return _dump(rows)
    return _dump(s)


@mcp.tool()
async def oc_models(provider: str = "") -> str:
    """List available models. Optionally filter by provider id (e.g. 'openai')."""
    try:
        m = await _req("GET", "/config/providers")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    providers = m.get("providers", []) if isinstance(m, dict) else m
    out = []
    for p in providers:
        pid = p.get("id")
        if provider and pid != provider:
            continue
        models = list((p.get("models") or {}).keys())
        out.append({"provider": pid, "name": p.get("name"), "models": models})
    return _dump(out, limit=10000)


@mcp.tool()
async def oc_providers() -> str:
    """List configured/available AI providers and how each authenticates (env vars, source)."""
    try:
        p = await _req("GET", "/provider")
    except Exception as e:  # noqa: BLE001
        return _err(e)
    allp = p.get("all", p) if isinstance(p, dict) else p
    if isinstance(allp, list):
        rows = [{"id": x.get("id"), "name": x.get("name"), "source": x.get("source"),
                 "env": x.get("env")} for x in allp]
        return _dump(rows, limit=10000)
    return _dump(p)

# ================================================================ CONFIG (read + patch + file authoring)

@mcp.tool()
async def oc_config_get(scope: str = "merged") -> str:
    """Get opencode configuration. scope='merged' (effective, default) or 'global'."""
    path = "/global/config" if scope == "global" else "/config"
    try:
        return _dump(await _req("GET", path), limit=12000)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_config_update(patch: dict, confirm: bool = False, scope: str = "global") -> str:
    """Patch opencode config (deep-merged). scope='global' writes ~/.config/opencode
    config; 'session-server' patches the running server's in-memory config only.
    Requires confirm=true. Example patch: {"model":"openai/gpt-5.5"}."""
    if not confirm:
        return f"Refusing config update without confirm=true. Patch was:\n{_dump(patch)}"
    path = "/global/config" if scope == "global" else "/config"
    try:
        return _dump(await _req("PATCH", path, body=patch))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_agent_write(name: str, prompt: str, description: str = "",
                         mode: str = "subagent", model: str = "", tools: Optional[dict] = None,
                         temperature: Optional[float] = None, scope: str = "global",
                         project_dir: str = "", confirm: bool = False) -> str:
    """Create/overwrite an agent as a markdown file with YAML frontmatter. mode =
    primary | subagent | all. scope='global' -> <config>/agent/<name>.md;
    scope='project' -> <project_dir>/.opencode/agent/<name>.md. tools is a map like
    {"write": false, "edit": false}. Requires confirm=true."""
    if not confirm:
        return "Refusing to write agent without confirm=true."
    if scope == "project":
        base = Path(project_dir or CFG.get("default_cwd") or Path.home()) / ".opencode" / "agent"
    else:
        base = (await _config_dir()) / "agent"
    base.mkdir(parents=True, exist_ok=True)
    fm: dict[str, Any] = {"description": description or f"{name} agent", "mode": mode}
    if model:
        fm["model"] = model
    if temperature is not None:
        fm["temperature"] = temperature
    if tools:
        fm["tools"] = tools
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  {kk}: {json.dumps(vv)}")
        else:
            lines.append(f"{k}: {json.dumps(v) if not isinstance(v, str) else v}")
    lines.append("---")
    lines.append("")
    lines.append(prompt)
    dest = base / f"{name}.md"
    dest.write_text("\n".join(lines))
    return f"Wrote agent -> {dest}\n\n" + dest.read_text()[:1200]


@mcp.tool()
async def oc_command_write(name: str, template: str, description: str = "",
                           agent: str = "", model: str = "", subtask: bool = False,
                           scope: str = "global", project_dir: str = "",
                           confirm: bool = False) -> str:
    """Create/overwrite a custom command (slash command) as a markdown file. The
    template may use $ARGUMENTS, $1.., !`shell`, and @file refs. scope global ->
    <config>/command/<name>.md; project -> <project_dir>/.opencode/command/<name>.md.
    Requires confirm=true."""
    if not confirm:
        return "Refusing to write command without confirm=true."
    if scope == "project":
        base = Path(project_dir or CFG.get("default_cwd") or Path.home()) / ".opencode" / "command"
    else:
        base = (await _config_dir()) / "command"
    base.mkdir(parents=True, exist_ok=True)
    fm = ["---"]
    if description:
        fm.append(f"description: {json.dumps(description)}")
    if agent:
        fm.append(f"agent: {agent}")
    if model:
        fm.append(f"model: {model}")
    if subtask:
        fm.append("subtask: true")
    fm.append("---")
    dest = base / f"{name}.md"
    dest.write_text("\n".join(fm) + "\n\n" + template + "\n")
    return f"Wrote command -> {dest}\n\n" + dest.read_text()[:1200]


@mcp.tool()
async def oc_skill_write(name: str, description: str, body: str,
                         scope: str = "global", project_dir: str = "",
                         confirm: bool = False) -> str:
    """Create/overwrite an opencode skill as <dir>/skills/<name>/SKILL.md with YAML
    frontmatter (name+description) and markdown body. scope global -> <config>/skills;
    project -> <project_dir>/.opencode/skills. Requires confirm=true."""
    if not confirm:
        return "Refusing to write skill without confirm=true."
    if scope == "project":
        base = Path(project_dir or CFG.get("default_cwd") or Path.home()) / ".opencode" / "skills" / name
    else:
        base = (await _config_dir()) / "skills" / name
    base.mkdir(parents=True, exist_ok=True)
    dest = base / "SKILL.md"
    content = (f"---\nname: {name}\ndescription: {json.dumps(description)}\n---\n\n{body}\n")
    dest.write_text(content)
    return f"Wrote skill -> {dest}\n\n" + content[:1200]

# ================================================================ MCP MANAGEMENT

@mcp.tool()
async def oc_mcp(action: str = "status", name: str = "", config: Optional[dict] = None,
                 confirm: bool = False) -> str:
    """Manage opencode's own MCP servers. action = status | add | connect | disconnect.
    For add: name + config (McpLocalConfig {"type":"local","command":[...]} or
    McpRemoteConfig {"type":"remote","url":...}). add/connect/disconnect need confirm=true."""
    a = action.lower()
    try:
        if a == "status":
            return _dump(await _req("GET", "/mcp"))
        if not confirm:
            return f"'{a}' needs confirm=true."
        if a == "add":
            return _dump(await _req("POST", "/mcp", body={"name": name, "config": config or {}}))
        if a == "connect":
            return _dump(await _req("POST", f"/mcp/{name}/connect", body={}))
        if a == "disconnect":
            return _dump(await _req("POST", f"/mcp/{name}/disconnect", body={}))
        return f"Unknown action '{action}'."
    except Exception as e:  # noqa: BLE001
        return _err(e)

# ================================================================ FILES / SEARCH / VCS

@mcp.tool()
async def oc_find(query: str, kind: str = "text", limit: int = 40) -> str:
    """Search the project. kind = text (ripgrep content) | file (filename fuzzy) |
    symbol (LSP workspace symbols)."""
    k = kind.lower()
    path = {"text": "/find", "file": "/find/file", "symbol": "/find/symbol"}.get(k)
    if not path:
        return "kind must be text|file|symbol"
    param = "pattern" if k == "text" else "query"
    try:
        r = await _req("GET", path, params={param: query})
    except Exception as e:  # noqa: BLE001
        return _err(e)
    if isinstance(r, list):
        return f"{len(r)} result(s):\n" + _dump(r[:limit], limit=8000)
    return _dump(r)


@mcp.tool()
async def oc_file(path: str = "", read: bool = False) -> str:
    """List files (path=dir, default project root) or read a file (read=true, path=file).
    Also reports git status of files when listing."""
    try:
        if read:
            if not path:
                return "Provide a file path to read (read=true requires path)."
            return _dump(await _req("GET", "/file/content", params={"path": path}), limit=12000)
        # listing requires a path; default to the project root
        return _dump(await _req("GET", "/file", params={"path": path or "."}), limit=10000)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
async def oc_vcs(action: str = "status") -> str:
    """Version control info for the project. action = status | diff | info."""
    a = action.lower()
    path = {"status": "/vcs/status", "diff": "/vcs/diff", "info": "/vcs"}.get(a, "/vcs/status")
    try:
        return _dump(await _req("GET", path), limit=12000)
    except Exception as e:  # noqa: BLE001
        return _err(e)

# ================================================================ TUI CONTROL

@mcp.tool()
async def oc_tui(action: str, text: str = "", command: str = "", message: str = "",
                 variant: str = "info") -> str:
    """Drive a RUNNING opencode TUI (must be attached to the same server). action =
    submit-prompt | append-prompt | clear-prompt | execute-command | show-toast |
    open-help | open-models | open-sessions | open-themes. Use text for append/submit,
    command for execute-command, message+variant for show-toast."""
    a = action.lower()
    try:
        if a == "append-prompt":
            return _dump(await _req("POST", "/tui/append-prompt", body={"text": text}))
        if a == "submit-prompt":
            if text:
                await _req("POST", "/tui/append-prompt", body={"text": text})
            return _dump(await _req("POST", "/tui/submit-prompt", body={}))
        if a == "clear-prompt":
            return _dump(await _req("POST", "/tui/clear-prompt", body={}))
        if a == "execute-command":
            return _dump(await _req("POST", "/tui/execute-command", body={"command": command}))
        if a == "show-toast":
            return _dump(await _req("POST", "/tui/show-toast",
                                    body={"message": message, "variant": variant}))
        if a in ("open-help", "open-models", "open-sessions", "open-themes"):
            return _dump(await _req("POST", f"/tui/{a.replace('-', '-')}", body={}))
        return f"Unknown action '{action}'."
    except Exception as e:  # noqa: BLE001
        return _err(e)

# ================================================================ EVENTS (bounded tail)

@mcp.tool()
async def oc_events(seconds: float = 4.0, limit: int = 40) -> str:
    """Tail the server's SSE event bus for a few seconds and return the events seen
    (session updates, message parts, permission requests, etc.). Bounded so it returns."""
    url = CFG["base_url"] + "/event"
    events: list = []
    try:
        async with httpx.AsyncClient(timeout=seconds + 5) as client:
            async with client.stream("GET", url, headers=_headers()) as resp:
                start = time.monotonic()
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            events.append(json.loads(line[5:].strip()))
                        except Exception:  # noqa: BLE001
                            events.append({"raw": line[5:][:200]})
                    if len(events) >= limit or time.monotonic() - start > seconds:
                        break
    except Exception as e:  # noqa: BLE001
        if not events:
            return _err(e)
    summary = [{"type": e.get("type"), "keys": list((e.get("properties") or e).keys())[:6]}
               if isinstance(e, dict) else e for e in events]
    return f"{len(events)} event(s) in {seconds}s:\n" + _dump(summary, limit=8000)


# ================================================================ SERVER LIFECYCLE

def _pidfile() -> Path:
    return Path("~/.local/state/opencode/.control-serve.pid").expanduser()


@mcp.tool()
async def oc_server(action: str = "status") -> str:
    """Manage a headless `opencode serve` for the HTTP tools. action = status | start | stop.
    'start' launches a detached server on the port in base_url if none is reachable
    (the HTTP curated tools need this; the ACP and *_write tools do not). 'stop' kills
    a server this tool started."""
    a = action.lower()
    # is one already reachable?
    reachable = False
    try:
        await _req("GET", "/api/health", timeout=3)
        reachable = True
    except Exception:  # noqa: BLE001
        pass
    if a == "status":
        return _dump({"base_url": CFG["base_url"], "reachable": reachable,
                      "pidfile": str(_pidfile()),
                      "hint": None if reachable else
                      "No server reachable — call oc_server(action='start') or run "
                      "`opencode serve --port <port>` yourself."})
    if a == "start":
        if reachable:
            return f"A server is already reachable at {CFG['base_url']} — nothing to do."
        from urllib.parse import urlparse
        u = urlparse(CFG["base_url"])
        port = str(u.port or 4096)
        host = u.hostname or "127.0.0.1"
        try:
            proc = subprocess.Popen(
                [CFG.get("opencode_bin", "opencode"), "serve", "--port", port, "--hostname", host],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, cwd=CFG.get("default_cwd") or str(Path.home()))
        except FileNotFoundError:
            return f"opencode binary '{CFG.get('opencode_bin')}' not found on PATH."
        _pidfile().parent.mkdir(parents=True, exist_ok=True)
        _pidfile().write_text(str(proc.pid))
        for _ in range(30):
            await asyncio.sleep(0.4)
            try:
                await _req("GET", "/api/health", timeout=2)
                return f"Started opencode serve (pid {proc.pid}) at {CFG['base_url']}."
            except Exception:  # noqa: BLE001
                continue
        return f"Launched pid {proc.pid} but {CFG['base_url']} did not become healthy in ~12s."
    if a == "stop":
        pf = _pidfile()
        if not pf.exists():
            return "No pidfile — this tool didn't start a server. Stop it however you started it."
        try:
            pid = int(pf.read_text().strip())
            os.kill(pid, 15)
            pf.unlink(missing_ok=True)
            return f"Stopped opencode serve (pid {pid})."
        except ProcessLookupError:
            pf.unlink(missing_ok=True)
            return "Server already gone."
        except Exception as e:  # noqa: BLE001
            return _err(e)
    return "action must be status|start|stop"


# ================================================================ ACP CONNECTOR

@mcp.tool()
async def oc_acp_prompt(prompt: str, cwd: str = "", mode: str = "", files: Optional[list] = None,
                        permission: str = "reject", confirm: bool = False,
                        timeout: int = 300) -> str:
    """Call opencode as an ACP agent (spawns `opencode acp`, JSON-RPC over stdio) and
    run ONE prompt, returning the streamed transcript: reply text, tool calls, plan,
    files written, token usage, and stopReason. This is the "drive opencode from
    anywhere" connector — independent of any running server.

      cwd        absolute project dir the agent operates in (defaults to config default_cwd/$HOME)
      mode       optional agent/mode to switch to (e.g. 'plan','build')
      files      absolute paths to attach as resource links
      permission 'reject' (READ-ONLY: agent can read/plan/answer, all edits+bash rejected — DEFAULT),
                 'allow' (approve each action once), 'always' (approve+remember).
                 Any non-reject value RUNS real edits/commands, so it needs confirm=true.
      timeout    seconds to wait for the turn to finish.

    With permission='reject' this is always safe (no mutation). To let opencode make
    changes, pass permission='allow' (or 'always') AND confirm=true."""
    if permission != "reject" and not confirm:
        return (f"permission='{permission}' lets opencode edit files and run commands. "
                f"Re-call with confirm=true to authorize, or use permission='reject' "
                f"(read-only) which needs no confirmation.")
    cwd = cwd or CFG.get("default_cwd") or str(Path.home())
    try:
        out = await ACP.run_prompt(
            prompt, opencode_bin=CFG.get("opencode_bin", "opencode"), cwd=cwd,
            files=files, mode=mode, permission=permission, timeout=timeout)
        return _dump(out, limit=14000)
    except Exception as e:  # noqa: BLE001
        return f"ACP error: {type(e).__name__}: {e}"


@mcp.tool()
async def oc_acp_probe(cwd: str = "") -> str:
    """Prove the ACP channel: spawn `opencode acp`, run the initialize handshake and
    open a session WITHOUT sending a prompt. Returns protocol version, agent info,
    advertised capabilities/auth methods, and the new session id. Safe (no model call)."""
    cwd = cwd or CFG.get("default_cwd") or str(Path.home())
    sess = ACP.ACPSession(opencode_bin=CFG.get("opencode_bin", "opencode"), cwd=cwd)
    try:
        await sess.start()
        init = await sess.initialize()
        sid = await sess.new_session()
        return _dump({"ok": True, "cwd": cwd, "session_id": sid,
                      "protocolVersion": init.get("protocolVersion"),
                      "agentInfo": init.get("agentInfo"),
                      "agentCapabilities": init.get("agentCapabilities"),
                      "authMethods": init.get("authMethods")})
    except Exception as e:  # noqa: BLE001
        return f"ACP probe failed: {type(e).__name__}: {e}"
    finally:
        await sess.close()


if __name__ == "__main__":
    mcp.run()
