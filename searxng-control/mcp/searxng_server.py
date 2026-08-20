#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "ruamel.yaml>=0.18",
# ]
# ///
"""SearXNG MCP server.

Drives a self-hosted SearXNG metasearch instance through the Model Context
Protocol. Verified live against a recent SearXNG release (Granian) running in Docker
on an aarch64 host. Three-layered, mirroring the other gh-tools plugins:

* GENERIC HTTP passthrough (`searx_http` / `searx_endpoints`) — reaches any
  runtime route. SearXNG has no OpenAPI doc, so the route catalog is a
  hand-enumerated, live-verified map of the real surface (see `searx_endpoints`).

* CURATED runtime tools — search (all query params), autocomplete, instance
  `/config`, the full engine inventory, and engine-failure diagnostics parsed
  from `/stats/errors` (the tool that explains SearXNG's #1 failure mode:
  upstream engines CAPTCHA/rate-limit a datacenter IP and get suspended).

* CONFIG-MANAGEMENT layer — SearXNG has NO API to change configuration; the
  control surface is `settings.yml` inside the container. These tools SSH to
  the host, edit `settings.yml` with a round-trip YAML parser (comments and
  formatting preserved), auto-back-up before every write, and apply changes
  with a container restart. Every write is confirm-gated (`confirm=True`).

Auth model (verified live): the HTTP API is UNauthenticated (open on the
trusted tailnet). The config layer authenticates via SSH key to the host and
`docker exec` into the container (which runs as root, so settings.yml is
writable). No secrets are stored in this file.

Config (env overrides the git-ignored config.local.json):
  base_url        HTTP endpoint, e.g. http://arm-host:8888   (required)
  ssh_host        host running the container                (config layer only)
  ssh_user        optional ssh user
  container       docker container name (default: searxng)
  settings_path   settings.yml path in-container (default /etc/searxng/settings.yml)
  verify_ssl      TLS verify (default false)
  timeout         HTTP timeout seconds (default 30)

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import functools
import io
import json
import os
import subprocess
import sys
import time
import urllib.parse
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP
from ruamel.yaml import YAML


# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
def log(*a: Any) -> None:
    print(*a, file=sys.stderr, flush=True)


def _load_config() -> dict:
    cfg: dict = {}
    path = os.environ.get("SEARXNG_CONFIG")
    if path and os.path.exists(path):
        try:
            cfg = json.loads(open(path, encoding="utf-8").read())
        except Exception as e:  # noqa: BLE001
            log(f"WARN: could not read {path}: {e}")
    env_map = {
        "base_url": "SEARXNG_BASE_URL",
        "ssh_host": "SEARXNG_SSH_HOST",
        "ssh_user": "SEARXNG_SSH_USER",
        "container": "SEARXNG_CONTAINER",
        "settings_path": "SEARXNG_SETTINGS_PATH",
        "verify_ssl": "SEARXNG_VERIFY_SSL",
        "timeout": "SEARXNG_TIMEOUT",
    }
    for key, env in env_map.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg.pop("_comment", None)
    return cfg


_CFG = _load_config()
BASE_URL = str(_CFG.get("base_url") or "http://localhost:8888").rstrip("/")
SSH_HOST = str(_CFG.get("ssh_host") or "").strip()
SSH_USER = str(_CFG.get("ssh_user") or "").strip()
CONTAINER = str(_CFG.get("container") or "searxng").strip()
SETTINGS_PATH = str(_CFG.get("settings_path") or "/etc/searxng/settings.yml").strip()
VERIFY_SSL = str(_CFG.get("verify_ssl", "false")).lower() in ("1", "true", "yes")
TIMEOUT = float(_CFG.get("timeout", 30))


class SearxError(Exception):
    pass


def _tool_error(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except SearxError as e:
            return f"ERROR: {e}"
        except httpx.HTTPError as e:
            return f"ERROR: HTTP error: {e}"
        except subprocess.CalledProcessError as e:
            out = (e.stderr or e.stdout or b"")
            if isinstance(out, bytes):
                out = out.decode("utf-8", "replace")
            return f"ERROR: remote command failed (rc={e.returncode}): {out.strip()[:400]}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: {type(e).__name__}: {e}"
    return wrapper


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
_client: Optional[httpx.Client] = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            base_url=BASE_URL,
            verify=VERIFY_SSL,
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "searxng-control/0.1 (gh-tools)"},
        )
    return _client


def _get(path: str, params: Optional[dict] = None) -> httpx.Response:
    r = client().get(path, params=params or {})
    r.raise_for_status()
    return r


def _get_json(path: str, params: Optional[dict] = None) -> Any:
    r = _get(path, params)
    try:
        return r.json()
    except Exception as e:  # noqa: BLE001
        raise SearxError(f"{path} did not return JSON ({e}); body: {r.text[:200]}")


# --------------------------------------------------------------------------- #
# SSH / config-layer helpers                                                  #
# --------------------------------------------------------------------------- #
def _require_ssh() -> None:
    if not SSH_HOST:
        raise SearxError(
            "config-management needs ssh_host + container in config.local.json; "
            "this instance is in search/read-only mode."
        )


def _ssh(remote_cmd: str, input_bytes: Optional[bytes] = None, timeout: int = 60) -> str:
    """Run a command on the SearXNG host over SSH (key auth, BatchMode)."""
    _require_ssh()
    target = f"{SSH_USER}@{SSH_HOST}" if SSH_USER else SSH_HOST
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new", target, remote_cmd,
    ]
    p = subprocess.run(
        cmd, input=input_bytes, capture_output=True, timeout=timeout, check=False,
    )
    if p.returncode != 0:
        err = (p.stderr or p.stdout).decode("utf-8", "replace").strip()
        raise SearxError(f"ssh/docker failed (rc={p.returncode}): {err[:500]}")
    return p.stdout.decode("utf-8", "replace")


def _dexec(sh: str, input_bytes: Optional[bytes] = None, timeout: int = 60) -> str:
    """Run `docker exec <container> sh -c '<sh>'` on the host."""
    flag = "-i " if input_bytes is not None else ""
    # single-quote the inner script safely
    inner = sh.replace("'", "'\"'\"'")
    return _ssh(f"docker exec {flag}{CONTAINER} sh -c '{inner}'", input_bytes, timeout)


def _read_settings() -> str:
    return _dexec(f"cat {SETTINGS_PATH}")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096  # don't wrap long lines
    y.indent(mapping=2, sequence=2, offset=0)
    return y


def _load_settings_obj():
    y = _yaml()
    return y, y.load(_read_settings())


def _dump_settings_obj(y: YAML, obj) -> str:
    buf = io.StringIO()
    y.dump(obj, buf)
    return buf.getvalue()


def _backup_settings() -> str:
    ts = _dexec("date +%Y%m%d-%H%M%S").strip()
    bak = f"{SETTINGS_PATH}.bak.{ts}"
    _dexec(f"cp {SETTINGS_PATH} {bak}")
    return bak


def _write_settings(content: str) -> None:
    # write atomically inside the container
    _dexec(f"cat > {SETTINGS_PATH}.tmp && mv {SETTINGS_PATH}.tmp {SETTINGS_PATH}",
           input_bytes=content.encode("utf-8"))


def _restart() -> str:
    return _ssh(f"docker restart {CONTAINER}", timeout=120).strip()


def _apply_note(apply: bool) -> str:
    if apply:
        out = _restart()
        return f" Applied: container restarted ({out})."
    return " NOT yet applied — run searx_restart (or pass apply=True) to reload."


# --------------------------------------------------------------------------- #
# MCP server                                                                  #
# --------------------------------------------------------------------------- #
mcp = FastMCP("searxng")


# ---- Layer 1: generic passthrough --------------------------------------- #
_ROUTES = [
    {"path": "/search", "methods": "GET,POST",
     "desc": "Run a search. params: q, categories, engines, language, pageno, "
             "time_range(day/week/month/year), safesearch(0/1/2), format(html/json/csv/rss).",
     "formats": ["html", "json", "csv", "rss"]},
    {"path": "/autocompleter", "methods": "GET,POST",
     "desc": "Search-term suggestions. params: q. Returns [term, [suggestions]]."},
    {"path": "/config", "methods": "GET",
     "desc": "Instance config as JSON: version, categories, engines[] (name/enabled/"
             "categories/shortcut), plugins, default settings."},
    {"path": "/stats", "methods": "GET",
     "desc": "Engine reliability + response-time stats (HTML). ?engine=<name> for one."},
    {"path": "/stats/errors", "methods": "GET",
     "desc": "Per-engine error records as JSON (exception class, message, count, %). "
             "The key diagnostic for 'why are results empty'."},
    {"path": "/preferences", "methods": "GET,POST",
     "desc": "User preferences page (HTML). Settings are per-cookie, not global."},
    {"path": "/healthz", "methods": "GET", "desc": "Liveness probe (text 'OK')."},
    {"path": "/opensearch.xml", "methods": "GET", "desc": "OpenSearch descriptor (XML)."},
    {"path": "/info/<locale>/<page>", "methods": "GET",
     "desc": "Built-in docs, e.g. /info/en/search-syntax (HTML)."},
    {"path": "/image_proxy", "methods": "GET", "desc": "Image proxy (needs url+h params)."},
    {"path": "/", "methods": "GET", "desc": "Main search UI (HTML)."},
]


@mcp.tool()
@_tool_error
def searx_endpoints() -> str:
    """List SearXNG's HTTP routes (the generic-passthrough surface map).

    SearXNG has no OpenAPI document; this is the hand-enumerated, live-verified
    route catalog. Use searx_http to call any of them directly."""
    lines = [f"SearXNG @ {BASE_URL} — HTTP route catalog:", ""]
    for r in _ROUTES:
        lines.append(f"  {r['methods']:9} {r['path']}")
        lines.append(f"            {r['desc']}")
    lines.append("")
    lines.append("Config-layer (settings.yml over SSH) is separate — see searx_settings_* tools.")
    return "\n".join(lines)


@mcp.tool()
@_tool_error
def searx_http(path: str, params_json: str = "{}", method: str = "GET") -> str:
    """Generic passthrough: call ANY SearXNG route and return the raw response.

    path: e.g. "/search", "/config", "/stats/errors".
    params_json: JSON object of query params, e.g. '{"q":"linux","format":"json"}'.
    method: GET or POST. JSON responses are pretty-printed; else text is returned
    (truncated to 8000 chars)."""
    params = json.loads(params_json) if params_json.strip() else {}
    if not path.startswith("/"):
        path = "/" + path
    if method.upper() == "POST":
        r = client().post(path, data=params)
    else:
        r = client().get(path, params=params)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if "application/json" in ct or "suggestions" in ct:
        try:
            return json.dumps(r.json(), indent=2)[:12000]
        except Exception:  # noqa: BLE001
            pass
    return r.text[:8000]


# ---- Layer 2: curated runtime tools ------------------------------------- #
@mcp.tool()
@_tool_error
def searx_status() -> str:
    """Instance identity + a live liveness/search probe (start here).

    Reports version, engine counts, enabled formats, and whether a probe
    search actually returns results (the real 'is it working' signal)."""
    cfg = _get_json("/config")
    engines = cfg.get("engines", [])
    enabled = [e for e in engines if e.get("enabled")]
    healthz = _get("/healthz").text.strip()
    # probe search
    probe = _get_json("/search", {"q": "test", "format": "json"})
    n = len(probe.get("results", []))
    unresp = probe.get("unresponsive_engines", []) or []
    out = {
        "base_url": BASE_URL,
        "version": cfg.get("version"),
        "instance_name": cfg.get("instance_name"),
        "healthz": healthz,
        "engines_total": len(engines),
        "engines_enabled_by_default": len(enabled),
        "categories": len(cfg.get("categories", [])),
        "probe_search_results": n,
        "probe_unresponsive_engines": [u[0] if isinstance(u, list) else u for u in unresp],
        "config_layer": "available" if SSH_HOST else "read-only (no ssh_host)",
    }
    verdict = "HEALTHY" if n > 0 else "DEGRADED — search returned 0 results (see searx_engine_errors)"
    return f"{verdict}\n" + json.dumps(out, indent=2)


@mcp.tool()
@_tool_error
def searx_search(q: str, categories: str = "", engines: str = "", language: str = "",
                 time_range: str = "", safesearch: str = "", pageno: int = 1,
                 fmt: str = "json", limit: int = 20) -> str:
    """Run a search. Returns JSON results (url/title/content) by default.

    q: query. categories: comma list (general,news,images,...). engines: comma
    list of specific engines (e.g. "bing,mojeek"). language: e.g. "en" / "en-US".
    time_range: day|week|month|year. safesearch: 0|1|2. pageno: page. fmt:
    json|csv|rss|html (json recommended). limit: max results returned (1-50,
    default 20; use pageno for more). If results are empty, run
    searx_engine_errors to see which engines are suspended."""
    params: dict = {"q": q, "pageno": pageno, "format": fmt}
    if categories:
        params["categories"] = categories
    if engines:
        params["engines"] = engines
    if language:
        params["language"] = language
    if time_range:
        params["time_range"] = time_range
    if safesearch != "":
        params["safesearch"] = safesearch
    if fmt != "json":
        r = _get("/search", params)
        return r.text[:12000]
    d = _get_json("/search", params)
    results = d.get("results", [])
    out = {
        "query": d.get("query"),
        "number_of_results": len(results),
        "answers": d.get("answers", []),
        "suggestions": (d.get("suggestions") or [])[:10],
        "unresponsive_engines": [
            {"engine": u[0], "reason": u[1]} if isinstance(u, list) and len(u) > 1 else u
            for u in (d.get("unresponsive_engines") or [])
        ],
        "results": [
            {"title": r.get("title"), "url": r.get("url"),
             "content": (r.get("content") or "")[:400],
             "engines": r.get("engines", []), "score": r.get("score")}
            for r in results[:max(1, min(int(limit), 50))]
        ],
    }
    if not results:
        out["_hint"] = ("0 results — engines likely suspended (CAPTCHA/rate-limit). "
                        "Run searx_engine_errors, then searx_engines(failing=True). "
                        "On a datacenter IP, prefer engines that don't CAPTCHA "
                        "(bing, mojeek, mwmbl, wikipedia, brave sometimes).")
    return json.dumps(out, indent=2)


@mcp.tool()
@_tool_error
def searx_autocomplete(q: str) -> str:
    """Search-term autocomplete suggestions for `q` (uses the configured backend)."""
    d = _get_json("/autocompleter", {"q": q})
    return json.dumps(d, indent=2)


@mcp.tool()
@_tool_error
def searx_config(section: str = "") -> str:
    """Instance /config as JSON. section: optional top-level key to extract
    (e.g. "categories", "engines", "plugins", "default_locale"). Omit engines
    unless asked — it's large; use searx_engines instead."""
    cfg = _get_json("/config")
    if section:
        if section not in cfg:
            raise SearxError(f"no such config section '{section}'. keys: {list(cfg)}")
        return json.dumps({section: cfg[section]}, indent=2)[:12000]
    slim = {k: v for k, v in cfg.items() if k != "engines"}
    slim["engines_count"] = len(cfg.get("engines", []))
    return json.dumps(slim, indent=2)[:12000]


@mcp.tool()
@_tool_error
def searx_engines(category: str = "", enabled_only: bool = False,
                  failing: bool = False, name_contains: str = "") -> str:
    """The engine inventory (master checklist) from /config, cross-referenced
    with live failures from /stats/errors.

    category: filter to one category (general/news/images/it/...).
    enabled_only: only engines enabled by default. failing: only engines that
    are currently erroring/suspended. name_contains: substring filter."""
    cfg = _get_json("/config")
    engines = cfg.get("engines", [])
    try:
        errors = _get_json("/stats/errors") or {}
    except Exception:  # noqa: BLE001
        errors = {}
    failing_names = set(errors.keys())
    rows = []
    for e in engines:
        nm = e.get("name")
        if category and category not in (e.get("categories") or []):
            continue
        if enabled_only and not e.get("enabled"):
            continue
        if name_contains and name_contains.lower() not in (nm or "").lower():
            continue
        is_failing = nm in failing_names
        if failing and not is_failing:
            continue
        rows.append({
            "name": nm,
            "enabled": e.get("enabled"),
            "categories": e.get("categories"),
            "shortcut": e.get("shortcut"),
            "failing": is_failing,
        })
    summary = {
        "total_shown": len(rows),
        "engines_total": len(engines),
        "enabled_total": sum(1 for e in engines if e.get("enabled")),
        "currently_failing": sorted(failing_names),
        "engines": rows[:120],
    }
    return json.dumps(summary, indent=2)


@mcp.tool()
@_tool_error
def searx_engine_errors() -> str:
    """Diagnose failures: per-engine error records from /stats/errors.

    This is the tool that answers 'why are searches empty'. It groups each
    failing engine's errors by exception class (SearxEngineCaptcha,
    SearxEngineTooManyRequests, SearxEngineAccessDenied, timeouts, ...) so you
    can see what's suspended and why."""
    errors = _get_json("/stats/errors") or {}
    if not errors:
        return "No engine errors reported — all engines are responding."
    out = {}
    for engine, recs in errors.items():
        classes: dict = {}
        for r in recs if isinstance(recs, list) else []:
            cls = r.get("exception_classname") or r.get("log_message") or "error"
            classes[cls] = classes.get(cls, 0) + 1
        out[engine] = classes
    hint = ("SearxEngine*Captcha / TooManyRequests / AccessDenied => the engine "
            "blocked this instance's IP and SearXNG suspended it "
            "(search.suspended_times: captcha=1h, cf_captcha=15d). Common on "
            "datacenter IPs. Fix: disable the CAPTCHA-prone engines and lean on "
            "ones that tolerate datacenter IPs (bing, mojeek, mwmbl, wikipedia).")
    return json.dumps({"failing_engines": out, "_diagnosis": hint}, indent=2)


@mcp.tool()
@_tool_error
def searx_stats(engine: str = "") -> str:
    """Engine reliability & response-time stats (from /stats, HTML → text).
    engine: optional single engine name to focus on."""
    params = {"engine": engine} if engine else None
    r = _get("/stats", params)
    # crude HTML→text: strip tags, collapse whitespace
    import re
    text = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:8000]


@mcp.tool()
@_tool_error
def searx_health() -> str:
    """Full health check: liveness, probe search, and a suspended-engine report
    with a plain-English verdict."""
    parts = []
    healthz = _get("/healthz").text.strip()
    parts.append(f"healthz: {healthz}")
    probe = _get_json("/search", {"q": "wikipedia", "format": "json"})
    n = len(probe.get("results", []))
    parts.append(f"probe search 'wikipedia': {n} results")
    try:
        errors = _get_json("/stats/errors") or {}
    except Exception:  # noqa: BLE001
        errors = {}
    if errors:
        parts.append(f"failing/suspended engines ({len(errors)}): {', '.join(sorted(errors))}")
    verdict = ("HEALTHY" if n > 0 else
               "DEGRADED — 0 results; engines suspended. See searx_engine_errors "
               "and consider searx tuning (disable CAPTCHA-prone engines).")
    return verdict + "\n" + "\n".join("  " + p for p in parts)


# ---- Layer 3: config management (settings.yml over SSH) ------------------ #
@mcp.tool()
@_tool_error
def searx_settings_read(section: str = "", include_engines: bool = False) -> str:
    """Read settings.yml (the real config surface). section: a top-level key
    (search/server/outgoing/ui/general/plugins/valkey/brand/engines). Omit to
    get all sections EXCEPT the huge engines list (set include_engines=True or
    section='engines' for that). Read-only."""
    _, data = _load_settings_obj()
    if section:
        if section not in data:
            raise SearxError(f"no section '{section}'. keys: {list(data.keys())}")
        y = _yaml()
        buf = io.StringIO()
        y.dump({section: data[section]}, buf)
        return buf.getvalue()[:12000]
    y = _yaml()
    buf = io.StringIO()
    slim = {k: v for k, v in data.items() if k != "engines" or include_engines}
    if not include_engines and "engines" in data:
        slim_note = f"(engines: {len(data['engines'])} items — omitted; use section='engines')"
    else:
        slim_note = ""
    y.dump(slim, buf)
    return (buf.getvalue()[:12000] + ("\n" + slim_note if slim_note else ""))


@mcp.tool()
@_tool_error
def searx_engine_show(name: str) -> str:
    """Show one engine's full settings.yml block (all params)."""
    _, data = _load_settings_obj()
    for e in data.get("engines", []):
        if e.get("name") == name:
            y = _yaml()
            buf = io.StringIO()
            y.dump({"engine": e}, buf)
            return buf.getvalue()
    raise SearxError(f"engine '{name}' not found in settings.yml")


@mcp.tool()
@_tool_error
def searx_engine_toggle(name: str, disabled: bool, confirm: bool = False,
                        apply: bool = False) -> str:
    """Enable or disable an engine (write). Sets `disabled: <bool>` on the
    engine's block in settings.yml. confirm=True required. apply=True restarts
    the container to load it (else batch several edits, then searx_restart).
    Auto-backs-up settings.yml first."""
    if not confirm:
        return (f"CONFIRM: this will set disabled={disabled} on engine '{name}' in "
                f"settings.yml on {SSH_HOST}. Re-call with confirm=True.")
    y, data = _load_settings_obj()
    target = None
    for e in data.get("engines", []):
        if e.get("name") == name:
            target = e
            break
    if target is None:
        raise SearxError(f"engine '{name}' not found in settings.yml")
    target["disabled"] = bool(disabled)
    bak = _backup_settings()
    _write_settings(_dump_settings_obj(y, data))
    return (f"OK: engine '{name}' disabled={disabled}. Backup: {bak}." + _apply_note(apply))


@mcp.tool()
@_tool_error
def searx_engine_add(name: str, engine: str, shortcut: str, categories: str = "",
                     extra_yaml_json: str = "{}", confirm: bool = False,
                     apply: bool = False) -> str:
    """Add a custom engine to settings.yml (write). name: display name. engine:
    the SearXNG engine module (e.g. "json_engine", "xpath", "mojeek"). shortcut:
    a bang shortcut (e.g. "mj"). categories: comma list. extra_yaml_json: JSON of
    any extra engine keys (search_url, url_query, timeout, etc.). confirm=True
    required; auto-backs-up. See references/settings-reference.md for engine
    templates."""
    if not confirm:
        return (f"CONFIRM: add engine name='{name}' engine='{engine}' shortcut='{shortcut}' "
                f"to settings.yml on {SSH_HOST}. Re-call with confirm=True.")
    y, data = _load_settings_obj()
    if any(e.get("name") == name for e in data.get("engines", [])):
        raise SearxError(f"engine '{name}' already exists — use searx_engine_toggle / edit instead.")
    block: dict = {"name": name, "engine": engine, "shortcut": shortcut}
    if categories:
        block["categories"] = [c.strip() for c in categories.split(",") if c.strip()]
    extra = json.loads(extra_yaml_json) if extra_yaml_json.strip() else {}
    block.update(extra)
    data.setdefault("engines", []).append(block)
    bak = _backup_settings()
    _write_settings(_dump_settings_obj(y, data))
    return (f"OK: added engine '{name}'. Backup: {bak}." + _apply_note(apply))


def _engines_dir() -> str:
    """Locate searx/engines inside the container. The official searxng image
    installs to /usr/local/searxng/searx; probe that, then fall back to a find.
    (Avoid `import searx` — the bare container python lacks some runtime deps.)"""
    default = "/usr/local/searxng/searx/engines"
    if _dexec(f"test -d {default} && echo yes || echo no").strip() == "yes":
        return default
    found = _dexec("find / -maxdepth 7 -type d -path '*searx/engines' 2>/dev/null | head -1").strip()
    if not found:
        raise SearxError("could not locate searx/engines in the container (set path manually)")
    return found


@mcp.tool()
@_tool_error
def searx_engine_module_deploy(module_name: str, python_code: str, register_name: str,
                               shortcut: str, categories: str = "general",
                               extra_yaml_json: str = "{}", confirm: bool = False,
                               apply: bool = False) -> str:
    """Deploy a CUSTOM PYTHON engine module (write): writes
    searx/engines/<module_name>.py into the container and registers it in
    settings.yml. Use for engines that need real code (custom request/response,
    signing, pagination); for plain JSON/HTML/SQL sources use searx_engine_add.
    python_code must implement the SearXNG engine API (module attrs + request(
    query, params) + response(resp)) — see references/writing-engines.md. The
    module is syntax-checked (py_compile) and removed if it fails. confirm=True
    required; auto-backs-up settings.yml. Note: this runs your code inside the
    search container — review it first."""
    if not confirm:
        return (f"CONFIRM: write searx/engines/{module_name}.py ({len(python_code)} bytes) "
                f"into container '{CONTAINER}' on {SSH_HOST} and register engine "
                f"'{register_name}' (shortcut !{shortcut}). This executes your code "
                f"in the search container. Re-call with confirm=True.")
    if not module_name.replace("_", "").isalnum():
        raise SearxError("module_name must be letters/digits/underscore only")
    eng_dir = _engines_dir()
    target = f"{eng_dir}/{module_name}.py"
    if _dexec(f"test -f {target} && echo yes || echo no").strip() == "yes":
        raise SearxError(f"{target} already exists — pick another module_name or remove it first.")
    _dexec(f"cat > {target}", input_bytes=python_code.encode("utf-8"))
    chk = _dexec(f"python -m py_compile {target} 2>&1 && echo COMPILE_OK || echo COMPILE_FAIL")
    if "COMPILE_OK" not in chk:
        _dexec(f"rm -f {target}")
        raise SearxError(f"module failed to compile (removed, nothing registered): {chk[:400]}")
    y, data = _load_settings_obj()
    if any(e.get("name") == register_name for e in data.get("engines", [])):
        _dexec(f"rm -f {target}")
        raise SearxError(f"engine '{register_name}' already in settings; module removed. Rename.")
    block: dict = {"name": register_name, "engine": module_name, "shortcut": shortcut}
    if categories:
        block["categories"] = [c.strip() for c in categories.split(",") if c.strip()]
    block.update(json.loads(extra_yaml_json) if extra_yaml_json.strip() else {})
    data.setdefault("engines", []).append(block)
    bak = _backup_settings()
    _write_settings(_dump_settings_obj(y, data))
    return (f"OK: deployed {target} and registered engine '{register_name}'. "
            f"Settings backup: {bak}." + _apply_note(apply)
            + " After restart, test with searx_search(engines='%s')." % register_name)


@mcp.tool()
@_tool_error
def searx_engine_module_remove(module_name: str, register_name: str = "",
                               confirm: bool = False, apply: bool = False) -> str:
    """Remove a custom engine module deployed by searx_engine_module_deploy:
    deletes searx/engines/<module_name>.py and (if register_name given) its
    settings.yml entry. confirm=True required; auto-backs-up settings."""
    if not confirm:
        return (f"CONFIRM: delete engine module '{module_name}.py'"
                + (f" and unregister '{register_name}'" if register_name else "")
                + f" on {SSH_HOST}. Re-call with confirm=True.")
    if not module_name.replace("_", "").isalnum():
        raise SearxError("module_name must be letters/digits/underscore only")
    target = f"{_engines_dir()}/{module_name}.py"
    note = ""
    if register_name:
        y, data = _load_settings_obj()
        before = len(data.get("engines", []))
        data["engines"] = [e for e in data.get("engines", []) if e.get("name") != register_name]
        if len(data["engines"]) != before:
            bak = _backup_settings()
            _write_settings(_dump_settings_obj(y, data))
            note = f" Unregistered '{register_name}' (backup {bak})."
    _dexec(f"rm -f {target}")
    return (f"OK: removed {target}.{note}" + _apply_note(apply))


@mcp.tool()
@_tool_error
def searx_setting_set(key_path: str, value: str, confirm: bool = False,
                      apply: bool = False) -> str:
    """Set any scalar/list setting in settings.yml by dotted path (write).

    key_path: e.g. "outgoing.request_timeout", "server.limiter",
    "search.autocomplete", "search.safe_search", "general.instance_name".
    value: interpreted as bool/int/float, JSON (for lists/objects, e.g.
    '["html","json","csv"]'), or string. confirm=True required; auto-backs-up.
    Does NOT create deeply-nested new trees — the parent path must exist."""
    if not confirm:
        return (f"CONFIRM: set {key_path} = {value} in settings.yml on {SSH_HOST}. "
                f"Re-call with confirm=True.")
    parsed: Any = value
    v = value.strip()
    if v.lower() in ("true", "false"):
        parsed = v.lower() == "true"
    elif v.lower() in ("null", "none", "~"):
        parsed = None
    elif (v.startswith("[") or v.startswith("{")):
        parsed = json.loads(v)
    else:
        try:
            parsed = int(v)
        except ValueError:
            try:
                parsed = float(v)
            except ValueError:
                parsed = value
    y, data = _load_settings_obj()
    parts = key_path.split(".")
    node = data
    for p in parts[:-1]:
        if p not in node:
            raise SearxError(f"path '{key_path}' — '{p}' does not exist in settings.yml")
        node = node[p]
    old = node.get(parts[-1], "<unset>")
    node[parts[-1]] = parsed
    bak = _backup_settings()
    _write_settings(_dump_settings_obj(y, data))
    return (f"OK: {key_path}: {old!r} -> {parsed!r}. Backup: {bak}." + _apply_note(apply))


@mcp.tool()
@_tool_error
def searx_settings_backups() -> str:
    """List settings.yml backups made by this tool (newest first)."""
    out = _dexec(f"ls -1t {SETTINGS_PATH}.bak.* 2>/dev/null || true")
    baks = [b for b in out.splitlines() if b.strip()]
    return "No backups yet." if not baks else "Backups:\n" + "\n".join("  " + b for b in baks)


@mcp.tool()
@_tool_error
def searx_settings_restore(backup: str, confirm: bool = False, apply: bool = False) -> str:
    """Restore settings.yml from a backup path (from searx_settings_backups).
    confirm=True required. Backs up the current file before overwriting."""
    if not confirm:
        return f"CONFIRM: restore {backup} over {SETTINGS_PATH}. Re-call with confirm=True."
    if ".bak." not in backup:
        raise SearxError("refusing: backup path must be one of this tool's *.bak.* files")
    cur = _backup_settings()
    _dexec(f"cp {backup} {SETTINGS_PATH}")
    return (f"OK: restored {backup}. Prior file saved as {cur}." + _apply_note(apply))


@mcp.tool()
@_tool_error
def searx_restart(confirm: bool = False) -> str:
    """Restart the SearXNG container to apply settings.yml changes (disruptive:
    brief downtime). confirm=True required."""
    if not confirm:
        return f"CONFIRM: restart container '{CONTAINER}' on {SSH_HOST} (brief downtime). confirm=True."
    out = _restart()
    time.sleep(2)
    try:
        hz = _get("/healthz").text.strip()
    except Exception:  # noqa: BLE001
        hz = "not answering yet (give it a few seconds)"
    return f"OK: restarted {CONTAINER} ({out}). healthz: {hz}"


@mcp.tool()
@_tool_error
def searx_logs(lines: int = 100) -> str:
    """Tail the SearXNG container logs (docker logs)."""
    out = _ssh(f"docker logs --tail {int(lines)} {CONTAINER} 2>&1")
    return out[-8000:]


if __name__ == "__main__":
    log(f"starting SearXNG MCP server for {BASE_URL} "
        f"(config_layer={'ssh:' + SSH_HOST if SSH_HOST else 'read-only'})")
    mcp.run()
