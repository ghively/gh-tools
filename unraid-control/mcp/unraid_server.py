#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "websockets>=12",
#   "paramiko>=3.4",
# ]
# ///
"""Unraid MCP server.

Exposes an Unraid server (tested on Unraid OS 7.3.2, unraid-api 4.35.1) to
Claude through the Model Context Protocol. The design is two-layered:

* A GENERIC passthrough (`unraid_graphql` / `unraid_schema_search` /
  `unraid_schema_type`) that can run ANY query or mutation against Unraid's
  official GraphQL API. This is what makes "control everything" true rather
  than aspirational — the live server has introspection disabled by default,
  so the full schema (pulled from the open-source github.com/unraid/api repo,
  pinned to the exact server version) ships alongside the plugin as the
  offline discovery document.
* CURATED tools for the common jobs (system health, the array & disks, Docker
  containers, VMs, shares, notifications, UPS, network, users/API keys,
  plugins, logs) so day-to-day tasks are a single clean call.

Auth is a single `x-api-key` header — no session/cookie/CSRF dance like
older REST-CGI style NAS APIs. All logging goes to stderr; stdout is
reserved for the MCP protocol.

A SEPARATE, narrowly-scoped SSH layer (`unraid_ssh_test` / `unraid_docker_env_get`
/ `unraid_docker_env_set`) exists only because Unraid's own GraphQL API has NO
mutation for editing a running container's environment variables — that's
template-file territory (`/boot/config/plugins/dockerMan/templates-user/*.xml`)
outside the API entirely. This is intentionally NOT a generic remote-shell
tool: it does exactly one job (read/set container env vars, via a full
docker-inspect-then-recreate, with best-effort template sync so the Unraid
UI's "Edit" screen stays consistent) and nothing else. Requires separate SSH
credentials in config (ssh_host/ssh_port/ssh_user/ssh_password or
ssh_key_path) — leave them unset to disable this layer entirely.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
import websockets
import paramiko
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[unraid-mcp]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _plugin_root() -> Path:
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root_env:
        return Path(root_env)
    return Path(__file__).resolve().parent.parent


def _find_config_file() -> Optional[Path]:
    """Locate config.local.json without hardcoding an absolute path."""
    candidates = []
    if os.environ.get("UNRAID_CONFIG"):
        candidates.append(Path(os.environ["UNRAID_CONFIG"]))
    candidates.append(_plugin_root() / "config.local.json")
    candidates.append(Path(__file__).resolve().parent / "config.local.json")
    candidates.append(Path.cwd() / "config.local.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def load_config() -> dict:
    """Resolve config from config.local.json (defaults) then env vars (overrides)."""
    cfg: dict = {}
    cf = _find_config_file()
    if cf:
        try:
            cfg = json.loads(cf.read_text(encoding="utf-8"))
            log(f"loaded config file: {cf}")
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: could not parse {cf}: {e}")

    env = os.environ
    out = {
        "host": env.get("UNRAID_HOST", cfg.get("host", "")),
        "port": int(env.get("UNRAID_PORT", cfg.get("port", 80)) or 80),
        "https": _truthy(env.get("UNRAID_HTTPS"), cfg.get("https", False)),
        "api_key": env.get("UNRAID_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("UNRAID_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("UNRAID_TIMEOUT", cfg.get("timeout", 30)) or 30),
        # Separate, optional SSH credentials — only used by the
        # unraid_ssh_test / unraid_docker_env_get / unraid_docker_env_set
        # tools. Leave unset to disable that layer entirely. ssh_host
        # defaults to the same host as the GraphQL API.
        "ssh_host": env.get("UNRAID_SSH_HOST", cfg.get("ssh_host", "")) or env.get("UNRAID_HOST", cfg.get("host", "")),
        "ssh_port": int(env.get("UNRAID_SSH_PORT", cfg.get("ssh_port", 22)) or 22),
        "ssh_user": env.get("UNRAID_SSH_USER", cfg.get("ssh_user", "root")),
        "ssh_password": env.get("UNRAID_SSH_PASSWORD", cfg.get("ssh_password", "")),
        "ssh_key_path": env.get("UNRAID_SSH_KEY_PATH", cfg.get("ssh_key_path", "")),
    }
    return out


# --------------------------------------------------------------------------- #
# GraphQL error handling                                                      #
# --------------------------------------------------------------------------- #
# extensions.code values observed on this box / documented by the API.
ERROR_HINTS = {
    "UNAUTHENTICATED": "missing/invalid x-api-key.",
    "FORBIDDEN": "the API key's role(s) don't grant this permission (check roles with unraid_me).",
    "GRAPHQL_VALIDATION_FAILED": "the query/mutation shape is wrong (bad field or arg name) — check unraid_schema_type.",
    "BAD_USER_INPUT": "an argument value was rejected.",
    "INTERNAL_SERVER_ERROR": "the server raised an error handling this request (see message).",
    "INTROSPECTION_DISABLED": "live schema introspection is off on this server; use unraid_schema_search/unraid_schema_type instead.",
    "SANDBOX_DISABLED": "the GraphQL sandbox UI is disabled; the API itself still works over POST.",
}


class UnraidError(RuntimeError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        parts = []
        for e in errors:
            code = ((e.get("extensions") or {}).get("code")) or ""
            msg = e.get("message", "unknown error")
            hint = ERROR_HINTS.get(code)
            path = ".".join(str(p) for p in (e.get("path") or []))
            piece = f"{msg}"
            if path:
                piece += f" [path={path}]"
            if code:
                piece += f" (code={code})"
            if hint:
                piece += f" — {hint}"
            parts.append(piece)
        super().__init__("; ".join(parts) or "unknown GraphQL error")
        self.codes = {((e.get("extensions") or {}).get("code")) for e in errors}

    def has_code(self, code: str) -> bool:
        return code in self.codes

    def message_contains(self, needle: str) -> bool:
        return any(needle.lower() in (e.get("message", "").lower()) for e in self.errors)


# --------------------------------------------------------------------------- #
# Unraid GraphQL client                                                       #
# --------------------------------------------------------------------------- #
class UnraidClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        self.base = f"{scheme}://{cfg['host']}:{cfg['port']}/graphql"
        self._http = httpx.Client(
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
            follow_redirects=True,
            headers={"x-api-key": cfg["api_key"], "Content-Type": "application/json"},
        )
        self._lock = threading.RLock()

    def call(self, query: str, variables: Optional[dict] = None) -> dict:
        if not self.cfg["host"]:
            raise RuntimeError("no host configured — set UNRAID_HOST or config.local.json:host")
        if not self.cfg["api_key"]:
            raise RuntimeError("no api_key configured — set UNRAID_API_KEY or config.local.json:api_key")
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            r = self._http.post(self.base, json=payload)
        except httpx.ConnectError as e:
            raise RuntimeError(
                f"cannot reach Unraid at {self.base}: {e}. Is the server up and the host/port correct?"
            ) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f"request to {self.base} timed out after {self.cfg['timeout']}s: {e}. "
                "Raise UNRAID_TIMEOUT / config timeout if the server is just slow."
            ) from e
        try:
            body = r.json()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"non-JSON response (HTTP {r.status_code}) from {self.base}: {r.text[:300]}"
            ) from e
        if body.get("errors"):
            raise UnraidError(body["errors"])
        if r.status_code >= 400:
            # JSON body but no GraphQL errors array (e.g. a proxy or non-GraphQL
            # error payload) — don't silently return {} as if it succeeded.
            raise RuntimeError(f"HTTP {r.status_code} from {self.base}: {r.text[:300]}")
        return body.get("data") or {}


# --------------------------------------------------------------------------- #
# GraphQL subscriptions (WebSocket, graphql-transport-ws protocol)            #
# --------------------------------------------------------------------------- #
# A handful of schema fields (dockerContainerStats, upsUpdates, live log tail,
# ...) exist ONLY under `Subscription`, with no plain-query equivalent — the
# HTTP client above can't reach them. Confirmed live: this server speaks the
# `graphql-ws` package's "graphql-transport-ws" subprotocol at the same
# /graphql path, auth via the same x-api-key (sent in the connection_init
# payload; the HTTP header also works for the initial handshake).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(s: str) -> str:
    """Some container-stat events observed on this box embed a stray ANSI
    escape sequence inside the id field (an Unraid-API-side quirk from
    parsing raw `docker stats` terminal output) — strip it before comparing."""
    return _ANSI_RE.sub("", s or "")


def _ws_uri(cfg: dict) -> str:
    scheme = "wss" if cfg["https"] else "ws"
    return f"{scheme}://{cfg['host']}:{cfg['port']}/graphql"


async def ws_subscribe(query: str, variables: Optional[dict] = None,
                        timeout: float = 10, max_events: int = 20) -> list[dict]:
    """Open one WebSocket subscription, collect up to max_events `data`
    payloads (or until timeout elapses), then cleanly unsubscribe."""
    cfg = client().cfg
    if not cfg["host"] or not cfg["api_key"]:
        raise RuntimeError("host/api_key not configured")
    events: list[dict] = []
    try:
        async with websockets.connect(
            _ws_uri(cfg),
            subprotocols=["graphql-transport-ws"],
            additional_headers={"x-api-key": cfg["api_key"]},
            open_timeout=cfg["timeout"],
        ) as ws:
            await ws.send(json.dumps({"type": "connection_init", "payload": {"x-api-key": cfg["api_key"]}}))
            await asyncio.wait_for(ws.recv(), timeout=timeout)  # connection_ack
            await ws.send(json.dumps({
                "id": "1", "type": "subscribe",
                "payload": {"query": query, "variables": variables or {}},
            }))
            deadline = asyncio.get_event_loop().time() + timeout
            while len(events) < max_events:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                mtype = msg.get("type")
                if mtype == "next":
                    payload = msg.get("payload") or {}
                    if payload.get("errors"):
                        raise UnraidError(payload["errors"])
                    events.append(payload.get("data") or {})
                elif mtype == "error":
                    raise UnraidError(msg.get("payload") or [{"message": "subscription error"}])
                elif mtype == "complete":
                    break
            try:
                await ws.send(json.dumps({"id": "1", "type": "complete"}))
            except Exception:  # noqa: BLE001
                pass
    except (websockets.exceptions.WebSocketException, OSError) as e:
        raise RuntimeError(f"WebSocket subscription to {_ws_uri(cfg)} failed: {e}") from e
    return events


# --------------------------------------------------------------------------- #
# Offline schema (bundled SDL — live introspection is disabled by default)    #
# --------------------------------------------------------------------------- #
_SCHEMA_TEXT: Optional[str] = None
_SCHEMA_BLOCKS: Optional[list[tuple[str, str, str]]] = None  # (kind, name, block_text)


def _schema_path() -> Path:
    return _plugin_root() / "skills" / "unraid-control" / "references" / "schema.graphql"


def _load_schema() -> str:
    global _SCHEMA_TEXT
    if _SCHEMA_TEXT is None:
        p = _schema_path()
        _SCHEMA_TEXT = p.read_text(encoding="utf-8") if p.is_file() else ""
        if not _SCHEMA_TEXT:
            log(f"WARNING: bundled schema not found at {p}")
    return _SCHEMA_TEXT


_BLOCK_RE = re.compile(r'^(type|input|enum|interface)\s+([A-Za-z0-9_]+)', re.M)


def _schema_blocks() -> list[tuple[str, str, str]]:
    global _SCHEMA_BLOCKS
    if _SCHEMA_BLOCKS is not None:
        return _SCHEMA_BLOCKS
    text = _load_schema()
    blocks: list[tuple[str, str, str]] = []
    lines = text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        m = _BLOCK_RE.match(lines[i])
        if m:
            kind, name = m.group(1), m.group(2)
            start = i
            depth = lines[i].count("{") - lines[i].count("}")
            i += 1
            while i < n and depth > 0:
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
            blocks.append((kind, name, "\n".join(lines[start:i])))
        else:
            i += 1
    _SCHEMA_BLOCKS = blocks
    return blocks


# --------------------------------------------------------------------------- #
# Server wiring                                                               #
# --------------------------------------------------------------------------- #
mcp = FastMCP("unraid")
_client: Optional[UnraidClient] = None
_client_lock = threading.Lock()


def client() -> UnraidClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = UnraidClient(load_config())
        return _client


def ok(data: Any) -> dict:
    return {"success": True, "data": data}


def err(e: Exception) -> dict:
    return {"success": False, "error": str(e)}


def gql(query: str, variables: Optional[dict] = None) -> Any:
    return client().call(query, variables)


def refuse(reason: str) -> dict:
    return {"success": False, "error": f"Refused: {reason}"}


# ============================================================================ #
# GENERIC / DISCOVERY                                                          #
# ============================================================================ #
@mcp.tool()
def unraid_status() -> dict:
    """Connection + identity check. Call this first to confirm the server is
    reachable and the API key is valid. Returns hostname, model, Unraid OS +
    API versions, uptime, array state, and container/notification counts."""
    try:
        data = gql("""
        {
          info { os { hostname uptime } system { manufacturer model }
                 versions { core { unraid api kernel } } }
          array { state }
          docker { containers { id state } }
          notifications { overview { unread { total alert } } }
          me { name roles }
        }
        """)
        info = data.get("info", {})
        containers = (data.get("docker") or {}).get("containers", [])
        return ok({
            "reachable": True,
            "host": f"{client().cfg['host']}:{client().cfg['port']}",
            "authenticated_as": (data.get("me") or {}).get("name"),
            "roles": (data.get("me") or {}).get("roles"),
            "hostname": (info.get("os") or {}).get("hostname"),
            "model": f"{(info.get('system') or {}).get('manufacturer', '')} {(info.get('system') or {}).get('model', '')}".strip(),
            "unraid_version": ((info.get("versions") or {}).get("core") or {}).get("unraid"),
            "unraid_api_version": ((info.get("versions") or {}).get("core") or {}).get("api"),
            "array_state": (data.get("array") or {}).get("state"),
            "containers_total": len(containers),
            "containers_running": sum(1 for c in containers if c.get("state") == "RUNNING"),
            "unread_notifications": ((data.get("notifications") or {}).get("overview") or {}).get("unread", {}),
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_graphql(query: str, variables: Optional[dict] = None) -> dict:
    """THE universal tool — run any GraphQL query OR mutation against Unraid's
    official API. This reaches every field in the schema, including anything
    without a curated wrapper.

    GraphQL lets you request several resources in ONE round-trip — e.g.
    `{ array { state } docker { containers { id state } } }` — prefer that over
    multiple separate calls when you need several reads together.

    Live introspection is disabled on this server, so you can't ask the server
    itself for its schema — use `unraid_schema_search` / `unraid_schema_type`
    (the bundled offline schema, pinned to this server's exact API version)
    to find the right field/argument names first.

    IDs: fields typed `PrefixedID` are opaque strings like
    "<machineId>:<local-id>" — always pass back the exact `id` string a query
    returned; do not construct one by hand.

    Mutations that stop/remove/reboot/delete something act immediately —
    confirm intent with the user before calling them. Prefer the curated
    `unraid_*` tools for anything destructive; they have a confirm=True gate."""
    try:
        return ok(gql(query, variables or {}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_schema_search(filter: str, limit: int = 40) -> dict:
    """Search the bundled offline GraphQL schema (types/enums/inputs and their
    fields) for a case-insensitive substring, e.g. "Docker", "parity",
    "notification". Returns a condensed field list per matching block — use
    this to find the exact field/argument names for `unraid_graphql`.
    `unraid_schema_type` gives the full definition (with descriptions) for one
    exact name."""
    try:
        blocks = _schema_blocks()
        if not blocks:
            return err(RuntimeError(f"bundled schema not found at {_schema_path()}"))
        f = filter.lower()
        matches = []
        for kind, name, block in blocks:
            field_lines = [
                ln.strip() for ln in block.split("\n")[1:-1]
                if ln.strip() and not ln.strip().startswith('"""') and '"""' not in ln
            ]
            if f in name.lower() or any(f in fl.lower() for fl in field_lines):
                matches.append({"kind": kind, "name": name, "fields": field_lines})
        return ok({"count": len(matches), "showing": min(len(matches), limit), "matches": matches[:limit]})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
async def unraid_subscribe_once(query: str, variables: Optional[dict] = None,
                                 timeout: float = 10, max_events: int = 5) -> dict:
    """Subscribe to a GraphQL `Subscription` field over WebSocket and collect
    up to max_events events (or until timeout seconds elapse), then cleanly
    unsubscribe. Use this ONLY for fields that exist solely under
    `Subscription` with no Query equivalent — e.g. dockerContainerStats (live
    per-container CPU/mem — events arrive one container at a time in
    rotation, so filter by id client-side; prefer unraid_docker_stats which
    does this for you), upsUpdates, notificationAdded, or logFile(path:...)
    for a live tail. Most other Subscription fields mirror an existing Query
    field (e.g. systemMetricsCpu ~= `metrics { cpu }` via unraid_graphql) —
    prefer the plain query for those, it's one round-trip instead of a
    held-open socket."""
    try:
        events = await ws_subscribe(query, variables, timeout, max_events)
        return ok({"event_count": len(events), "events": events})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_schema_type(name: str) -> dict:
    """Get the full definition (with doc comments) of one exact type/enum/input
    name from the bundled offline schema, e.g. "DockerContainer",
    "ArrayMutations", "Role". Case-insensitive exact match."""
    try:
        blocks = _schema_blocks()
        for kind, bname, block in blocks:
            if bname.lower() == name.lower():
                return ok({"kind": kind, "name": bname, "definition": block})
        suggestions = sorted({bname for _, bname, _ in blocks if name.lower() in bname.lower()})[:15]
        return err(RuntimeError(f'no exact type "{name}" found. Did you mean: {", ".join(suggestions) or "(no close matches)"}'))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# SYSTEM / IDENTITY                                                            #
# ============================================================================ #
@mcp.tool()
def unraid_info() -> dict:
    """Full hardware/OS info: motherboard, CPU, memory DIMM layout, OS distro/
    kernel, versions (Unraid, API, Docker, PHP...), network interfaces,
    display/case. (GPU/PCI device listing omitted — this server has at least
    one device with a null `type`, a field the schema declares non-null,
    which crashes that sub-query; use unraid_graphql on `info { devices { gpu
    { vendorname } } }` etc. with only the fields you need if you want them.)"""
    try:
        return ok(gql("""
        {
          info {
            time
            baseboard { manufacturer model version serial memMax memSlots }
            cpu { manufacturer brand cores threads speed }
            os { platform distro release codename kernel arch hostname fqdn uptime uefi }
            system { manufacturer model version serial uuid sku virtual }
            versions { core { unraid api kernel } packages { docker php nginx node openssl } }
            memory { layout { size bank type manufacturer } }
            networkInterfaces { name macAddress ipv4Addresses { address } speed operstate }
            primaryNetwork { name ipv4Addresses { address } macAddress }
          }
        }
        """))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vars() -> dict:
    """Low-level system config: server name/timezone, SMB/NFS/AFP share
    toggles, NTP, SSH/Telnet ports, mover schedule, array slot counts,
    registration state, config validity, CSRF token presence."""
    try:
        return ok(gql("{ vars }".replace("vars", "vars { " + _VARS_FIELDS + " }")))
    except Exception as e:  # noqa: BLE001
        return err(e)


_VARS_FIELDS = (
    "name comment timeZone version security workgroup domain "
    "useNtp ntpServer1 ntpServer2 sysModel sysArraySlots sysFlashSlots "
    "useSsl port portssl bindMgt useTelnet porttelnet useSsh portssh startPage startArray "
    "spindownDelay defaultFormat defaultFsType shutdownTimeout "
    "shareSmbEnabled shareNfsEnabled shareAfpEnabled shareMoverSchedule shareMoverActive "
    "safeMode startMode configValid configError joinStatus "
    "regTy regState regTo flashGuid flashProduct flashVendor "
    "mdState mdNumDisks mdNumDisabled mdNumInvalid mdNumMissing mdNumNew "
    "shareCount shareSmbCount shareNfsCount shareAfpCount"
)


@mcp.tool()
def unraid_metrics() -> dict:
    """Live resource utilization: CPU %, memory (total/used/free/%),
    temperature sensors, and per-interface network throughput."""
    try:
        return ok(gql("""
        {
          metrics {
            cpu { percentTotal }
            memory { total used free percentTotal }
            temperature { summary { average warningCount criticalCount }
                          sensors { name type current { value unit status } } }
            network { name operstate rxSec txSec utilizationPercent }
          }
        }
        """))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_registration() -> dict:
    """Unraid license/registration status (Trial, Basic, Plus, Pro, etc.) and
    key file location."""
    try:
        return ok(gql("{ registration { id type keyFile { location } } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_config_status() -> dict:
    """Whether the flash boot config is valid (`config.valid`); if not,
    `config.error` explains why (e.g. GUID mismatch)."""
    try:
        return ok(gql("{ config { valid error } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_system_time() -> dict:
    """Current server time, timezone, NTP state and configured NTP servers."""
    try:
        return ok(gql("{ systemTime { currentTime timeZone useNtp ntpServers } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_system_time_update(time_zone: Optional[str] = None, use_ntp: Optional[bool] = None,
                               ntp_servers: Optional[list[str]] = None,
                               manual_date_time: Optional[str] = None,
                               confirm: bool = False) -> dict:
    """Update timezone / NTP sync / manual date-time ("YYYY-MM-DD HH:mm:ss").
    Affects logs, scheduling and cert validity: requires confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to change system time settings.")
    try:
        inp: dict = {}
        if time_zone is not None:
            inp["timeZone"] = time_zone
        if use_ntp is not None:
            inp["useNtp"] = use_ntp
        if ntp_servers is not None:
            inp["ntpServers"] = ntp_servers
        if manual_date_time is not None:
            inp["manualDateTime"] = manual_date_time
        return ok(gql(
            "mutation($i: UpdateSystemTimeInput!) { updateSystemTime(input: $i) { currentTime timeZone useNtp } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# LOGS                                                                         #
# ============================================================================ #
@mcp.tool()
def unraid_logs_list() -> dict:
    """List available log files (name, path, size, last modified) — syslog,
    docker.log, graphql-api.log, dhcplog, tailscale logs, etc."""
    try:
        return ok(gql("{ logFiles { name path size modifiedAt } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_log_read(path: str, lines: int = 200, start_line: Optional[int] = None) -> dict:
    """Read a log file's content by its exact `path` from unraid_logs_list
    (e.g. "/var/log/syslog"). `lines` caps how many lines are returned."""
    try:
        variables: dict = {"path": path, "lines": lines}
        if start_line is not None:
            variables["startLine"] = start_line
        return ok(gql(
            "query($path: String!, $lines: Int, $startLine: Int) { "
            "logFile(path: $path, lines: $lines, startLine: $startLine) { path content totalLines startLine } }",
            variables,
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# NOTIFICATIONS                                                                #
# ============================================================================ #
@mcp.tool()
def unraid_notifications(type: str = "UNREAD", importance: Optional[str] = None,
                          offset: int = 0, limit: int = 50) -> dict:
    """List notifications. type="UNREAD" or "ARCHIVE". Optional importance
    filter: "INFO"/"WARNING"/"ALERT". Also returns the overview counts."""
    try:
        f: dict = {"type": type, "offset": offset, "limit": limit}
        if importance:
            f["importance"] = importance
        data = gql(
            "query($f: NotificationFilter!) { notifications { "
            "overview { unread { info warning alert total } archive { info warning alert total } } "
            "list(filter: $f) { id title subject description importance type timestamp formattedTimestamp } } }",
            {"f": f},
        )
        return ok(data.get("notifications"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notification_create(title: str, subject: str, description: str,
                                importance: str = "INFO", link: Optional[str] = None) -> dict:
    """Create a custom notification (shows up in the Unraid bell icon / can
    trigger configured agents). importance: "INFO"/"WARNING"/"ALERT".

    Server quirk (confirmed on this API version): `createNotification`'s
    response carries an `id` that does NOT match the real notification file
    (it uses a different suffix than what's actually persisted), so it can't
    be used directly with archive/unread/delete — every one of those would
    404. This tool works around it by re-listing unread notifications right
    after creating and returning the REAL id of the best title/subject/
    description match. Use that corrected id, not `raw_id`."""
    try:
        inp = {"title": title, "subject": subject, "description": description, "importance": importance}
        if link:
            inp["link"] = link
        created = gql(
            "mutation($i: NotificationData!) { createNotification(input: $i) { id title timestamp } }",
            {"i": inp},
        ).get("createNotification", {})
        real_id = None
        listing = gql(
            "{ notifications { list(filter: {type: UNREAD, offset: 0, limit: 20}) { id title subject description timestamp } } }"
        ).get("notifications", {}).get("list", [])
        for n in listing:
            if n.get("title") == title and n.get("subject") == subject and n.get("description") == description:
                real_id = n.get("id")
                break
        return ok({
            "id": real_id or created.get("id"),
            "raw_id": created.get("id"),
            "id_corrected": real_id is not None and real_id != created.get("id"),
            "title": created.get("title"),
            "timestamp": created.get("timestamp"),
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notification_archive(id: str) -> dict:
    """Archive one notification by id (marks it read/filed)."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { archiveNotification(id: $id) { id } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notification_unread(id: str) -> dict:
    """Mark one archived notification as unread again."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { unreadNotification(id: $id) { id } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notification_delete(id: str, confirm: bool = False) -> dict:
    """Permanently delete one notification. Destructive: requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to delete notification '{id}'.")
    try:
        return ok(gql(
            "mutation($id: PrefixedID!, $t: NotificationType!) { deleteNotification(id: $id, type: $t) { unread { total } } }",
            {"id": id, "t": "UNREAD"},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notifications_archive_all(importance: Optional[str] = None) -> dict:
    """Archive ALL unread notifications (optionally filtered by importance).
    Non-destructive (archived notifications are still visible/deletable)."""
    try:
        v = {"importance": importance} if importance else {}
        return ok(gql(
            "mutation($importance: NotificationImportance) { archiveAll(importance: $importance) { unread { total } archive { total } } }",
            v,
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_notifications_delete_archived(confirm: bool = False) -> dict:
    """Permanently delete ALL archived notifications. Destructive: requires
    confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to delete all archived notifications.")
    try:
        return ok(gql("mutation { deleteArchivedNotifications { archive { total } } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# ARRAY & DISKS                                                                #
# ============================================================================ #
_ARRAY_FIELDS = """
  state
  capacity { kilobytes { free used total } disks { free used total } }
  boot { id name device status }
  parities { id name device status size temp }
  disks { id idx name device size status type temp fsSize fsFree fsUsed numErrors isSpinning }
  caches { id name device size status type temp isSpinning }
  parityCheckStatus { status running paused progress speed errors correcting date duration }
"""


@mcp.tool()
def unraid_array() -> dict:
    """Full array status: state (STARTED/STOPPED/...), capacity, parity
    disk(s), data disks, cache disk(s), boot device, and current parity-check
    status. This is the main storage health view."""
    try:
        return ok(gql("{ array { " + _ARRAY_FIELDS + " } }").get("array"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_set_state(desired_state: str, confirm: bool = False) -> dict:
    """Start or stop the array. desired_state="START" or "STOP". HIGHLY
    disruptive: stopping unmounts every disk (all shares/Docker/VMs relying on
    array storage go offline) and starting can trigger a lengthy parity sync
    if disks changed. Requires confirm=True."""
    if desired_state not in ("START", "STOP"):
        return {"success": False, "error": 'desired_state must be "START" or "STOP"'}
    if not confirm:
        return refuse(f"pass confirm=True to {desired_state} the array (disruptive to all array-backed services).")
    try:
        return ok(gql(
            "mutation($i: ArrayStateInput!) { array { setState(input: $i) { state } } }",
            {"i": {"desiredState": desired_state}},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_disks() -> dict:
    """Physical disk inventory (all disks, not just array members): device
    path, model/vendor, size, temperature, SMART status, spin state,
    partitions. Use `assignable=True` disks when picking a new array/cache
    member."""
    try:
        data = gql("""
        { disks { id device type name vendor size temperature smartStatus isSpinning
                  interfaceType partitions { name fsType size } } }
        """)
        return ok(data.get("disks"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_assignable_disks() -> dict:
    """Disks currently eligible to be assigned into the array/cache pool
    (not already in use elsewhere)."""
    try:
        return ok(gql("{ assignableDisks { id device name vendor size smartStatus } }").get("assignableDisks"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_disk(id: str) -> dict:
    """Full detail for one physical disk by its `id` (from unraid_disks /
    unraid_array). Note: this deliberately omits geometry fields
    (bytesPerSector, cylinders/heads/sectors, firmwareRevision, serialNum) —
    they're declared non-null in the schema but the server returns null for
    some devices (observed on a USB flash boot device), which crashes the
    whole query per GraphQL null-propagation. Use unraid_graphql directly if
    you need those fields for a disk where they're populated."""
    try:
        return ok(gql(
            "query($id: PrefixedID!) { disk(id: $id) { id device type name vendor size "
            "interfaceType smartStatus temperature isSpinning partitions { name fsType size } } }",
            {"id": id},
        ).get("disk"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_disk_add(id: str, slot: Optional[int] = None, confirm: bool = False) -> dict:
    """Add a disk to the array configuration (assign it to a data/parity/cache
    slot). Structural change — typically requires the array to be STOPPED
    first. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to add disk '{id}' to the array.")
    try:
        inp: dict = {"id": id}
        if slot is not None:
            inp["slot"] = slot
        return ok(gql(
            "mutation($i: ArrayDiskInput!) { array { addDiskToArray(input: $i) { state disks { id name } } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_disk_remove(id: str, slot: Optional[int] = None, confirm: bool = False) -> dict:
    """Remove a disk from the array configuration. The array MUST be stopped
    first or this errors. Destructive to the array layout: requires
    confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to remove disk '{id}' from the array.")
    try:
        inp: dict = {"id": id}
        if slot is not None:
            inp["slot"] = slot
        return ok(gql(
            "mutation($i: ArrayDiskInput!) { array { removeDiskFromArray(input: $i) { state disks { id name } } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_disk_mount(id: str) -> dict:
    """Mount an array disk by id. Non-disruptive (makes data available)."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { array { mountArrayDisk(id: $id) { id status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_disk_unmount(id: str, confirm: bool = False) -> dict:
    """Unmount an array disk by id. Disrupts access to any shares/data on that
    disk: requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to unmount disk '{id}'.")
    try:
        return ok(gql("mutation($id: PrefixedID!) { array { unmountArrayDisk(id: $id) { id status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_array_disk_clear_stats(id: str) -> dict:
    """Clear the read/write/error counters for one array disk. Benign
    (statistics only)."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { array { clearArrayDiskStatistics(id: $id) } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_parity_history() -> dict:
    """Historical parity-check runs: date, duration, speed, errors, whether it
    was a correcting check. Returns an empty list if no parity check has ever
    run on this array (the server errors on a missing log file in that case —
    this tool treats that as "no history" rather than surfacing an error)."""
    try:
        return ok(gql("{ parityHistory { date duration speed status errors correcting } }").get("parityHistory"))
    except Exception as e:  # noqa: BLE001
        if isinstance(e, UnraidError) and e.message_contains("parity history file not found"):
            return ok([])
        return err(e)


@mcp.tool()
def unraid_parity_check(action: str, correct: bool = True, confirm: bool = False) -> dict:
    """Control the parity check. action = "start" | "pause" | "resume" |
    "cancel". `correct` (start only) controls whether mismatches are
    corrected (True) or just reported (False, a "non-correcting check").
    Parity checks run for many hours and are I/O intensive — "start" and
    "cancel" (which discards progress) require confirm=True. "pause"/"resume"
    don't (you're managing an already-authorized run)."""
    action = action.lower()
    if action == "start":
        if not confirm:
            return refuse("pass confirm=True to start a parity check (multi-hour, I/O intensive).")
        try:
            return ok(gql("mutation($c: Boolean!) { parityCheck { start(correct: $c) } }", {"c": correct}))
        except Exception as e:  # noqa: BLE001
            return err(e)
    if action == "cancel":
        if not confirm:
            return refuse("pass confirm=True to cancel the running parity check (progress is lost).")
        try:
            return ok(gql("mutation { parityCheck { cancel } }"))
        except Exception as e:  # noqa: BLE001
            return err(e)
    if action == "pause":
        try:
            return ok(gql("mutation { parityCheck { pause } }"))
        except Exception as e:  # noqa: BLE001
            return err(e)
    if action == "resume":
        try:
            return ok(gql("mutation { parityCheck { resume } }"))
        except Exception as e:  # noqa: BLE001
            return err(e)
    return {"success": False, "error": 'action must be "start", "pause", "resume", or "cancel"'}


# ============================================================================ #
# DOCKER                                                                       #
# ============================================================================ #
@mcp.tool()
def unraid_docker_containers() -> dict:
    """List Docker containers: name, image, state (RUNNING/PAUSED/EXITED),
    status text, ports, auto-start, and whether an image update is
    available."""
    try:
        data = gql("""
        { docker { containers { id names image state status autoStart
                                 isUpdateAvailable ports { privatePort publicPort type } } } }
        """)
        return ok((data.get("docker") or {}).get("containers"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_container(id: str) -> dict:
    """Full detail for one container by id: command, created time, env/mounts
    (raw), network settings, host config, template/registry URLs, WebUI URL,
    icon."""
    try:
        return ok(gql(
            "query($id: PrefixedID!) { docker { container(id: $id) { "
            "id names image imageId command created ports { privatePort publicPort type } lanIpPorts state status "
            "hostConfig { networkMode } networkSettings mounts labels autoStart autoStartOrder autoStartWait "
            "templatePath projectUrl registryUrl webUiUrl iconUrl isOrphaned isUpdateAvailable isRebuildReady "
            "} } }",
            {"id": id},
        ).get("docker", {}).get("container"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_logs(id: str, tail: int = 200, since: Optional[str] = None) -> dict:
    """Recent log lines for one container. `since` is an ISO timestamp/cursor
    from a previous call to continue streaming forward."""
    try:
        v: dict = {"id": id, "tail": tail}
        if since:
            v["since"] = since
        return ok(gql(
            "query($id: PrefixedID!, $tail: Int, $since: DateTime) { docker { logs(id: $id, tail: $tail, since: $since) "
            "{ containerId cursor lines { timestamp message } } } }",
            v,
        ).get("docker", {}).get("logs"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
async def unraid_docker_stats(id: str, timeout: float = 8) -> dict:
    """Live CPU/memory/network/block IO usage for one running container.
    Stats are subscription-only in this API version (no plain query field) —
    this listens on the shared dockerContainerStats stream, which emits one
    container's stats at a time in rotation across ALL running containers,
    until it sees an event matching `id` (or times out)."""
    try:
        target = strip_ansi(id)
        events = await ws_subscribe(
            "subscription { dockerContainerStats { id cpuPercent memPercent memUsage netIO blockIO } }",
            timeout=timeout, max_events=40,
        )
        for e in events:
            stat = e.get("dockerContainerStats") or {}
            if strip_ansi(stat.get("id", "")) == target:
                return ok(stat)
        return err(RuntimeError(
            f"no stats event seen for container '{id}' within {timeout}s "
            f"({len(events)} other container events observed — try a larger timeout, "
            "or confirm the container is running via unraid_docker_containers)."
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_networks() -> dict:
    """List Docker networks (bridge, host, custom) with driver, scope, and
    IPAM config."""
    try:
        data = gql("{ docker { networks { id name driver scope internal attachable ipam } } }")
        return ok((data.get("docker") or {}).get("networks"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_start(id: str) -> dict:
    """Start a stopped container by id."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { docker { start(id: $id) { id state status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_stop(id: str, confirm: bool = False) -> dict:
    """Stop a running container by id. Disruptive to whatever it serves:
    requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to stop container '{id}'.")
    try:
        return ok(gql("mutation($id: PrefixedID!) { docker { stop(id: $id) { id state status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_restart(id: str, confirm: bool = False) -> dict:
    """Restart a container (stop then start — this API version has no native
    `restart` mutation). Briefly interrupts its service: requires
    confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to restart container '{id}'.")
    try:
        gql("mutation($id: PrefixedID!) { docker { stop(id: $id) { id } } }", {"id": id})
        return ok(gql("mutation($id: PrefixedID!) { docker { start(id: $id) { id state status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_pause(id: str, confirm: bool = False) -> dict:
    """Pause (freeze) a running container's processes. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to pause container '{id}'.")
    try:
        return ok(gql("mutation($id: PrefixedID!) { docker { pause(id: $id) { id state } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_unpause(id: str) -> dict:
    """Resume a paused container."""
    try:
        return ok(gql("mutation($id: PrefixedID!) { docker { unpause(id: $id) { id state } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_remove(id: str, with_image: bool = False, confirm: bool = False) -> dict:
    """Remove/delete a container by id. Destructive: requires confirm=True.
    with_image=True also removes its image (fails if another container uses
    it)."""
    if not confirm:
        return refuse(f"pass confirm=True to remove container '{id}'.")
    try:
        return ok(gql(
            "mutation($id: PrefixedID!, $w: Boolean) { docker { removeContainer(id: $id, withImage: $w) } }",
            {"id": id, "w": with_image},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_update(id: str, confirm: bool = False) -> dict:
    """Update one container to the latest available image (pulls + recreates
    it — briefly interrupts service). Requires confirm=True. Check
    `isUpdateAvailable` via unraid_docker_containers first."""
    if not confirm:
        return refuse(f"pass confirm=True to update container '{id}' to its latest image.")
    try:
        return ok(gql("mutation($id: PrefixedID!) { docker { updateContainer(id: $id) { id state status } } }", {"id": id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_update_all(confirm: bool = False) -> dict:
    """Update every container that has an available image update. Disruptive
    (restarts each one): requires confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to update ALL containers with available updates.")
    try:
        return ok(gql("mutation { docker { updateAllContainers { id state status } } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_autostart_set(entries: list[dict], confirm: bool = False) -> dict:
    """Set the auto-start-on-boot configuration for one or more containers.
    `entries` is a list of {"id": "...", "auto_start": true, "wait": 10}
    (wait = seconds to wait after starting before the next one). Requires
    confirm=True (changes boot behavior)."""
    if not confirm:
        return refuse("pass confirm=True to change container auto-start configuration.")
    try:
        norm = [{"id": e["id"], "autoStart": bool(e.get("auto_start", e.get("autoStart", False))),
                 **({"wait": e["wait"]} if e.get("wait") is not None else {})} for e in entries]
        return ok(gql(
            "mutation($e: [DockerAutostartEntryInput!]!) { docker { updateAutostartConfiguration(entries: $e) } }",
            {"e": norm},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# DOCKER — SSH-backed env-var editing (see module docstring)                  #
# ============================================================================ #
_SECRET_KEY_RE = re.compile(r"(PASS|SECRET|TOKEN|KEY|CRED)", re.IGNORECASE)


def _ssh_configured(cfg: dict) -> bool:
    return bool(cfg.get("ssh_host")) and bool(cfg.get("ssh_password") or cfg.get("ssh_key_path"))


def _ssh_connect(cfg: dict) -> "paramiko.SSHClient":
    if not _ssh_configured(cfg):
        raise RuntimeError(
            "SSH is not configured. Set ssh_host/ssh_user + (ssh_password or "
            "ssh_key_path) in config.local.json or the UNRAID_SSH_* env vars."
        )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict[str, Any] = {
        "hostname": cfg["ssh_host"], "port": cfg["ssh_port"],
        "username": cfg["ssh_user"], "timeout": 15,
        # Without these, paramiko probes the local ssh-agent / default key
        # files first — on Windows this can throw ("lost ssh-agent") before
        # ever trying the credential we were actually given. Go straight to
        # the configured auth method instead.
        "allow_agent": False, "look_for_keys": False,
    }
    if cfg.get("ssh_key_path"):
        kwargs["key_filename"] = cfg["ssh_key_path"]
    else:
        kwargs["password"] = cfg["ssh_password"]
    client.connect(**kwargs)
    return client


def _ssh_exec(cfg: dict, command: str, timeout: float = 30) -> tuple[int, str, str]:
    client = _ssh_connect(cfg)
    try:
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        errtext = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        return code, out, errtext
    finally:
        client.close()


def _ssh_read_file(cfg: dict, path: str) -> str:
    client = _ssh_connect(cfg)
    try:
        sftp = client.open_sftp()
        try:
            with sftp.open(path, "r") as f:
                return f.read().decode("utf-8", "replace")
        finally:
            sftp.close()
    finally:
        client.close()


def _ssh_write_file(cfg: dict, path: str, content: str) -> None:
    client = _ssh_connect(cfg)
    try:
        sftp = client.open_sftp()
        try:
            with sftp.open(path, "w") as f:
                f.write(content.encode("utf-8"))
        finally:
            sftp.close()
    finally:
        client.close()


def _mask_env(env_list: list, reveal: bool) -> dict:
    out = {}
    for item in env_list:
        if "=" not in item:
            continue
        k, _, v = item.partition("=")
        if not reveal and v and _SECRET_KEY_RE.search(k):
            v = "********"
        out[k] = v
    return out


@mcp.tool()
def unraid_ssh_test() -> dict:
    """Verify SSH connectivity/credentials for the container env-var-editing
    tools, without changing anything. Returns hostname + docker version on
    success. If this fails, unraid_docker_env_get/unraid_docker_env_set
    cannot work — check ssh_host/ssh_user/ssh_password/ssh_key_path in
    config.local.json or the UNRAID_SSH_* env vars."""
    cfg = load_config()
    try:
        code, out, errtext = _ssh_exec(
            cfg, "hostname && docker version --format '{{.Server.Version}}'"
        )
        if code != 0:
            return err(RuntimeError(f"exit {code}: {errtext.strip() or out.strip()}"))
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return ok({
            "reachable": True,
            "hostname": lines[0] if lines else "",
            "docker_version": lines[1] if len(lines) > 1 else "",
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_docker_env_get(container_name: str, reveal_secrets: bool = False) -> dict:
    """Read a container's CURRENT environment variables via SSH + `docker
    inspect` — Unraid's GraphQL API does not expose this at all. Values
    whose key looks like a secret (PASS/SECRET/TOKEN/KEY/CRED) are masked
    unless reveal_secrets=True; treat reveal_secrets=True like any other
    credential-exposing read.

    Args:
        container_name: Container name or id (see unraid_docker_containers).
        reveal_secrets: If true, returns secret-looking values unmasked.
    """
    cfg = load_config()
    try:
        code, out, errtext = _ssh_exec(
            cfg, f"docker inspect {shlex.quote(container_name)} "
                 "--format '{{json .Config.Env}}'"
        )
        if code != 0:
            return err(RuntimeError(f"docker inspect failed: {errtext.strip() or out.strip()}"))
        env_list = json.loads(out.strip())
        return ok({"container": container_name, "env": _mask_env(env_list, reveal_secrets)})
    except Exception as e:  # noqa: BLE001
        return err(e)


def _template_path_for(container_name: str) -> str:
    return f"/boot/config/plugins/dockerMan/templates-user/my-{container_name}.xml"


def _sync_template_env(cfg: dict, container_name: str, updates: dict, removes: list) -> dict:
    """Best-effort: keep the Unraid XML template's <Config Target=VAR>
    entries in sync so the 'Edit' screen in the Unraid UI stays accurate.
    Never raises — failures are reported but don't block the container
    recreation itself, which is the operation that actually matters."""
    path = _template_path_for(container_name)
    try:
        text = _ssh_read_file(cfg, path)
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "reason": f"no template at {path} or unreadable: {e}"}
    original = text
    for name in removes:
        text = re.sub(
            rf'\s*<Config\b[^>]*Target="{re.escape(name)}"[^>]*(?:/>|>.*?</Config>)',
            "", text, flags=re.DOTALL,
        )
    for name, value in updates.items():
        esc_value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        pattern = rf'<Config\b[^>]*Target="{re.escape(name)}"[^>]*(?:/>|>.*?</Config>)'
        m = re.search(pattern, text, flags=re.DOTALL)
        if m:
            attrs_match = re.match(r'(<Config\b[^>]*?)\s*(?:/>|>.*)$', m.group(0), flags=re.DOTALL)
            attrs = attrs_match.group(1) if attrs_match else m.group(0)
            text = text[:m.start()] + f"{attrs}>{esc_value}</Config>" + text[m.end():]
        else:
            new_elem = (
                f'  <Config Name="{name}" Target="{name}" Default="" Mode="{{3}}" '
                f'Description="Added by unraid_docker_env_set." Type="Variable" '
                f'Display="advanced" Required="false" Mask="true">{esc_value}</Config>\n'
            )
            text = (text.replace("</Container>", new_elem + "</Container>")
                    if "</Container>" in text else text + "\n" + new_elem)
    if text == original:
        return {"synced": False, "reason": "no changes needed"}
    try:
        _ssh_write_file(cfg, path, text)
        return {"synced": True, "path": path}
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "reason": f"write failed: {e}"}


@mcp.tool()
def unraid_docker_env_set(container_name: str, env: Optional[dict] = None,
                           remove: Optional[list] = None,
                           confirm: bool = False) -> dict:
    """Add/update/remove environment variables on a container by recreating
    it via SSH: `docker inspect` for the full current config (image, mounts,
    ports incl. protocol, log options, labels, network mode, restart policy,
    runtime e.g. nvidia, privileged flag, devices, cap-add/drop, extra hosts,
    user, and command/post-arguments) → `docker stop` + `rm` + `run` with
    that same config plus your changes. NOT carried over (rare in Unraid
    templates — check `docker inspect` first if the container is exotic):
    tmpfs/shm-size, ulimits, sysctls, memory/cpu limits, healthcheck
    overrides, and additional networks beyond the primary NetworkMode.
    WRITES: confirm-gated, DISRUPTIVE — the container restarts (a few
    seconds of downtime). Also
    best-effort syncs the matching Unraid XML template
    (`/boot/config/plugins/dockerMan/templates-user/my-<name>.xml`) so the
    Unraid UI's Edit screen stays accurate; a template-sync failure is
    reported but does not block the actual container recreation.

    This exists because Unraid's GraphQL API has no mutation for editing a
    running container's environment variables — confirmed against the
    schema (DockerMutations only has start/stop/pause/unpause/
    removeContainer/updateContainer/updateContainers/updateAllContainers/
    updateAutostartConfiguration). Requires ssh_host/ssh_user +
    (ssh_password or ssh_key_path) configured — check with unraid_ssh_test
    first.

    Args:
        container_name: Container name (as in unraid_docker_containers'
            `names`, without the leading slash) or id.
        env: Dict of {VAR_NAME: value} to add or update.
        remove: List of VAR_NAME to drop entirely.
        confirm: Must be true — stops and recreates a live container.
    """
    env = env or {}
    remove = remove or []
    if not env and not remove:
        return err(ValueError("provide env and/or remove — nothing to change"))
    cfg = load_config()
    if not confirm:
        return refuse(
            f"recreate container '{container_name}' with env changes "
            f"set={list(env)} remove={remove} (a few seconds of downtime)."
        )
    try:
        code, out, errtext = _ssh_exec(cfg, f"docker inspect {shlex.quote(container_name)}")
        if code != 0:
            return err(RuntimeError(f"docker inspect failed: {errtext.strip() or out.strip()}"))
        inspect = json.loads(out)[0]

        cur_env = {}
        for item in inspect["Config"]["Env"]:
            if "=" in item:
                k, _, v = item.partition("=")
                cur_env[k] = v
        cur_env.update({k: str(v) for k, v in env.items()})
        for name in remove:
            cur_env.pop(name, None)

        config = inspect.get("Config") or {}
        image = config["Image"]
        name = inspect["Name"].lstrip("/")
        host_config = inspect.get("HostConfig") or {}
        binds = host_config.get("Binds") or []
        port_bindings = host_config.get("PortBindings") or {}
        log_cfg = host_config.get("LogConfig") or {}
        network_mode = host_config.get("NetworkMode", "")
        labels = config.get("Labels") or {}
        restart_name = (host_config.get("RestartPolicy") or {}).get("Name", "no")

        args = ["docker", "run", "-d", "--name", name]
        if network_mode:
            args += ["--network", network_mode]
        for b in binds:
            args += ["-v", b]
        seen_ports = set()
        for container_port, hostbindings in port_bindings.items():
            # container_port keeps its protocol suffix ("8080/tcp", "1900/udp")
            # — dropping it would silently turn udp mappings into tcp and
            # collapse tcp+udp bindings on the same port number into one.
            for hb in (hostbindings or [{}]):
                hp = (hb or {}).get("HostPort", "")
                key = (hp, container_port)
                if key in seen_ports:
                    continue
                seen_ports.add(key)
                args += ["-p", f"{hp}:{container_port}" if hp else container_port]
        if log_cfg.get("Type"):
            args += ["--log-driver", log_cfg["Type"]]
        for k, v in (log_cfg.get("Config") or {}).items():
            args += ["--log-opt", f"{k}={v}"]
        for k, v in labels.items():
            if k.startswith("org.opencontainers.image."):
                continue  # baked into the image already; avoid duplicate/conflicting labels
            args += ["--label", f"{k}={v}"]
        if restart_name and restart_name != "no":
            args += ["--restart", restart_name]
        # Settings Unraid containers commonly rely on — dropping any of these
        # on recreate silently degrades the container (e.g. an NVIDIA runtime
        # or /dev/dri passthrough disappearing from a media server).
        runtime = host_config.get("Runtime") or ""
        if runtime and runtime != "runc":
            args += ["--runtime", runtime]
        if host_config.get("Privileged"):
            args += ["--privileged"]
        for dev in host_config.get("Devices") or []:
            spec = (dev or {}).get("PathOnHost", "")
            if not spec:
                continue
            if dev.get("PathInContainer"):
                spec += f":{dev['PathInContainer']}"
                if dev.get("CgroupPermissions"):
                    spec += f":{dev['CgroupPermissions']}"
            args += ["--device", spec]
        for cap in host_config.get("CapAdd") or []:
            args += ["--cap-add", cap]
        for cap in host_config.get("CapDrop") or []:
            args += ["--cap-drop", cap]
        for eh in host_config.get("ExtraHosts") or []:
            args += ["--add-host", eh]
        if config.get("User"):
            args += ["--user", config["User"]]
        for k, v in cur_env.items():
            args += ["-e", f"{k}={v}"]
        args += [image]
        # Preserve the effective command (Unraid templates' "Post Arguments"
        # live here; without this they'd be silently dropped on recreate).
        # Passing it explicitly even when it merely equals the image default
        # reproduces current behavior exactly.
        args += list(config.get("Cmd") or [])

        run_cmd = " ".join(shlex.quote(a) for a in args)
        full_cmd = f"docker stop {shlex.quote(name)} && docker rm {shlex.quote(name)} && {run_cmd}"
        code, out, errtext = _ssh_exec(cfg, full_cmd, timeout=60)
        if code != 0:
            return err(RuntimeError(f"recreate failed: {errtext.strip() or out.strip()}"))

        template_result = _sync_template_env(cfg, name, env, remove)
        return ok({
            "recreated": True,
            "container": name,
            "new_container_id": out.strip().splitlines()[-1] if out.strip() else None,
            "env_set": list(env),
            "env_removed": remove,
            "template_sync": template_result,
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# VIRTUAL MACHINES                                                             #
# ============================================================================ #
def _vm_unavailable_ok() -> dict:
    return ok({"available": False, "reason": "VMs are not available on this server "
               "(libvirt/KVM not enabled, or the VM Manager is disabled in Settings)."})


@mcp.tool()
def unraid_vms() -> dict:
    """List virtual machines (name, state). Returns available=False with a
    reason if the VM Manager isn't enabled on this server."""
    try:
        return ok(gql("{ vms { domains { id name state } } }").get("vms"))
    except Exception as e:  # noqa: BLE001
        if isinstance(e, UnraidError) and e.message_contains("VMs are not available"):
            return _vm_unavailable_ok()
        return err(e)


def _vm_mutation(field: str, id: str) -> dict:
    return ok(gql(f"mutation($id: PrefixedID!) {{ vm {{ {field}(id: $id) }} }}", {"id": id}))


@mcp.tool()
def unraid_vm_start(id: str) -> dict:
    """Start a virtual machine by id."""
    try:
        return _vm_mutation("start", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_stop(id: str, confirm: bool = False) -> dict:
    """Gracefully stop (ACPI shutdown) a VM. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to stop VM '{id}'.")
    try:
        return _vm_mutation("stop", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_force_stop(id: str, confirm: bool = False) -> dict:
    """Force-stop (power off) a VM — like pulling the plug, no graceful
    shutdown. Risk of data loss inside the VM: requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to FORCE stop VM '{id}' (no graceful shutdown).")
    try:
        return _vm_mutation("forceStop", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_pause(id: str, confirm: bool = False) -> dict:
    """Pause (freeze) a VM's execution. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to pause VM '{id}'.")
    try:
        return _vm_mutation("pause", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_resume(id: str) -> dict:
    """Resume a paused VM."""
    try:
        return _vm_mutation("resume", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_reboot(id: str, confirm: bool = False) -> dict:
    """Reboot (graceful ACPI restart) a VM. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to reboot VM '{id}'.")
    try:
        return _vm_mutation("reboot", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_reset(id: str, confirm: bool = False) -> dict:
    """Hard-reset a VM (like the physical reset button — no graceful
    shutdown). Risk of data loss inside the VM: requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to hard-reset VM '{id}'.")
    try:
        return _vm_mutation("reset", id)
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# SHARES                                                                       #
# ============================================================================ #
@mcp.tool()
def unraid_shares() -> dict:
    """List user shares with free/used/total size, cache setting (Yes/No/
    Only/Prefer), and include/exclude disk lists."""
    try:
        return ok(gql("{ shares { id name free used size include exclude cache comment splitLevel floor } }").get("shares"))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# USERS / API KEYS                                                             #
# ============================================================================ #
@mcp.tool()
def unraid_me() -> dict:
    """Identity of the API key this MCP server is using: name, description,
    roles, and effective permissions."""
    try:
        return ok(gql("{ me { id name description roles permissions { resource actions } } }").get("me"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_api_keys() -> dict:
    """List all API keys configured on this server (name, description, roles,
    created date — never returns key secrets other than this key's own)."""
    try:
        return ok(gql("{ apiKeys { id name description roles createdAt } }").get("apiKeys"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_api_key_roles_catalog() -> dict:
    """The full catalog of possible roles (ADMIN/CONNECT/GUEST/VIEWER) and
    possible fine-grained permissions (resource + action) — use this to build
    a `roles`/`permissions` argument for unraid_api_key_create."""
    try:
        return ok(gql("{ apiKeyPossibleRoles apiKeyPossiblePermissions { resource actions } }"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_api_key_create(name: str, description: str = "", roles: Optional[list[str]] = None,
                           overwrite: bool = False, confirm: bool = False) -> dict:
    """Create a new API key. `roles` e.g. ["ADMIN"] or ["VIEWER"] (see
    unraid_api_key_roles_catalog). Security-sensitive (grants server access):
    requires confirm=True. The plaintext key is returned ONCE — save it."""
    if not confirm:
        return refuse(f"pass confirm=True to create a new API key named '{name}'.")
    try:
        inp = {"name": name, "description": description, "roles": roles or [], "overwrite": overwrite}
        return ok(gql(
            "mutation($i: CreateApiKeyInput!) { apiKey { create(input: $i) { id key name roles } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_api_key_delete(ids: list[str], confirm: bool = False) -> dict:
    """Delete one or more API keys by id. Destructive (immediately revokes
    that key's access — check you aren't deleting the key this MCP server
    itself uses): requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to delete API key(s) {ids}.")
    try:
        return ok(gql("mutation($i: DeleteApiKeyInput!) { apiKey { delete(input: $i) } }", {"i": {"ids": ids}}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_api_key_role(api_key_id: str, role: str, action: str = "add", confirm: bool = False) -> dict:
    """Add or remove a role on an existing API key. action="add"|"remove".
    Security-sensitive: requires confirm=True."""
    if action not in ("add", "remove"):
        return {"success": False, "error": 'action must be "add" or "remove"'}
    if not confirm:
        return refuse(f"pass confirm=True to {action} role '{role}' on API key '{api_key_id}'.")
    try:
        field = "addRole" if action == "add" else "removeRole"
        return ok(gql(
            f"mutation($i: {'AddRoleForApiKeyInput' if action == 'add' else 'RemoveRoleFromApiKeyInput'}!) "
            f"{{ apiKey {{ {field}(input: $i) }} }}",
            {"i": {"apiKeyId": api_key_id, "role": role}},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# NETWORK                                                                      #
# ============================================================================ #
@mcp.tool()
def unraid_network_interfaces() -> dict:
    """List network interfaces: name, MAC, IPv4/IPv6 addresses, speed, duplex,
    link state, VLAN id."""
    try:
        return ok(gql("""
        { networkInterfaces { id name macAddress mtu speed duplex operstate type vlanId
                               ipv4Addresses { address netmask } ipv6Addresses { address } } }
        """).get("networkInterfaces"))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# UPS                                                                          #
# ============================================================================ #
@mcp.tool()
def unraid_ups() -> dict:
    """List connected UPS device(s) with status, battery %, runtime left, and
    load. Returns connected=False with a reason if no UPS is detected
    (apcupsd has nothing to report)."""
    try:
        return ok(gql("""
        { upsDevices { id name model status
                       battery { chargeLevel estimatedRuntime health }
                       power { inputVoltage outputVoltage loadPercentage nominalPower currentPower } } }
        """).get("upsDevices"))
    except Exception as e:  # noqa: BLE001
        if isinstance(e, UnraidError) and e.message_contains("No UPS data"):
            return ok({"connected": False, "reason": "No UPS detected by apcupsd — check the UPS is powered on and cabled/connected, and UPS monitoring is enabled."})
        return err(e)


@mcp.tool()
def unraid_ups_config() -> dict:
    """Current UPS monitoring configuration (service enabled, cable/comm type,
    device path, shutdown thresholds)."""
    try:
        return ok(gql("""
        { upsConfiguration { service upsCable upsType device overrideUpsCapacity
                              batteryLevel minutes timeout killUps nisIp netServer upsName modelName } }
        """).get("upsConfiguration"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_ups_set_config(service: Optional[str] = None, ups_cable: Optional[str] = None,
                           ups_type: Optional[str] = None, device: Optional[str] = None,
                           battery_level: Optional[int] = None, minutes: Optional[int] = None,
                           timeout: Optional[int] = None, kill_ups: Optional[str] = None,
                           confirm: bool = False) -> dict:
    """Update UPS monitoring / auto-shutdown configuration. Values mirror the
    webGUI (service="enable"/"disable", ups_cable="usb"/"smart"/"ether"/
    "custom", ups_type="usb"/"net"/"snmp"/..., kill_ups="yes"/"no").
    Misconfiguring shutdown thresholds can cause unwanted (or missed)
    emergency shutdowns: requires confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to change UPS configuration (affects auto-shutdown behavior).")
    try:
        inp: dict = {}
        mapping = {
            "service": service and service.upper(), "upsCable": ups_cable and ups_cable.upper(),
            "upsType": ups_type and ups_type.upper(), "device": device,
            "batteryLevel": battery_level, "minutes": minutes, "timeout": timeout,
            "killUps": kill_ups and kill_ups.upper(),
        }
        for k, v in mapping.items():
            if v is not None:
                inp[k] = v
        return ok(gql("mutation($i: UPSConfigInput!) { configureUps(config: $i) }", {"i": inp}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# SETTINGS                                                                     #
# ============================================================================ #
@mcp.tool()
def unraid_settings() -> dict:
    """The unified settings form: `values` (current settings, JSON) plus
    `dataSchema`/`uiSchema` (JSON Schema describing every field, section by
    section) and the API's own config (version, sandbox/introspection flag,
    installed API plugins). This is the read side of the big dynamic settings
    system — most day-to-day settings don't have a dedicated typed mutation;
    use unraid_settings_update for those."""
    try:
        return ok(gql("""
        { settings { unified { values dataSchema } api { version sandbox extraOrigins plugins ssoSubIds } } }
        """).get("settings"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_settings_update(input: dict, confirm: bool = False) -> dict:
    """Generic settings writer — the escape hatch for any setting that has no
    dedicated typed mutation. `input` is a partial object matching the shape
    from unraid_settings' `values`/`dataSchema` (e.g. changing a share default,
    a display option, a Docker/VM Manager toggle). Broad blast radius, so
    requires confirm=True. Read unraid_settings first to see the exact current
    shape/keys, and check the response's `restartRequired`/`warnings`."""
    if not confirm:
        return refuse("pass confirm=True to write settings (broad system config change).")
    try:
        return ok(gql("mutation($i: JSON!) { updateSettings(input: $i) { restartRequired warnings values } }", {"i": input}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_ssh_settings_update(enabled: bool, port: int = 22, confirm: bool = False) -> dict:
    """Enable/disable SSH and set its port. Can lock out SSH-based access:
    requires confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to change SSH settings (access-affecting).")
    try:
        return ok(gql(
            "mutation($i: UpdateSshInput!) { updateSshSettings(input: $i) { useSsh portssh } }",
            {"i": {"enabled": enabled, "port": port}},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_temperature_config_update(input: dict, confirm: bool = False) -> dict:
    """Update temperature monitoring config: sensors (lm_sensors/smartctl/
    ipmi enable + args), warning/critical thresholds, polling interval,
    history retention. `input` matches TemperatureConfigInput (see
    unraid_schema_type("TemperatureConfigInput")). Can mask real hardware
    problems if thresholds are loosened: requires confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to change temperature monitoring configuration.")
    try:
        return ok(gql("mutation($i: TemperatureConfigInput!) { updateTemperatureConfig(input: $i) }", {"i": input}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_theme_set(theme: str) -> dict:
    """Set the webGUI theme: "azure" | "black" | "gray" | "white". Cosmetic,
    no confirm needed."""
    try:
        return ok(gql("mutation($t: ThemeName!) { customization { setTheme(theme: $t) { name } } }", {"t": theme}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_locale_set(locale: str) -> dict:
    """Set the webGUI display locale, e.g. "en_US". Cosmetic, no confirm
    needed."""
    try:
        return ok(gql("mutation($l: String!) { customization { setLocale(locale: $l) } }", {"l": locale}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# PLUGINS                                                                      #
# ============================================================================ #
@mcp.tool()
def unraid_plugins() -> dict:
    """List installed API plugins (Node-module extensions to the GraphQL API
    itself, e.g. Connect/SSO integrations) — not the same as classic Unraid OS
    .plg plugins (see unraid_installed_unraid_plugins)."""
    try:
        return ok(gql("{ plugins { name version hasApiModule hasCliModule } }").get("plugins"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_installed_unraid_plugins() -> dict:
    """List installed classic Unraid OS plugins by their .plg filename (the
    Community-Applications-style plugin system)."""
    try:
        return ok(gql("{ installedUnraidPlugins }").get("installedUnraidPlugins"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_api_add(names: list[str], bundled: bool = False, restart: bool = True,
                           confirm: bool = False) -> dict:
    """Add API-level plugin(s) by package name. Installs and loads code into
    the running API process (and may restart it): requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to add API plugin(s) {names}.")
    try:
        inp = {"names": names, "bundled": bundled, "restart": restart}
        return ok(gql("mutation($i: PluginManagementInput!) { addPlugin(input: $i) }", {"i": inp}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_api_remove(names: list[str], restart: bool = True, confirm: bool = False) -> dict:
    """Remove API-level plugin(s) by package name. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to remove API plugin(s) {names}.")
    try:
        inp = {"names": names, "bundled": False, "restart": restart}
        return ok(gql("mutation($i: PluginManagementInput!) { removePlugin(input: $i) }", {"i": inp}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_install(url: str, name: Optional[str] = None, forced: bool = True,
                           confirm: bool = False) -> dict:
    """Install a classic Unraid OS plugin from a .plg URL (same mechanism as
    Community Applications). Runs arbitrary installer code from that URL on
    the server: requires confirm=True. Returns an operation id — poll it with
    unraid_plugin_install_operation."""
    if not confirm:
        return refuse(f"pass confirm=True to install the plugin at '{url}' (runs installer code on the server).")
    try:
        inp = {"url": url, "forced": forced}
        if name:
            inp["name"] = name
        return ok(gql(
            "mutation($i: InstallPluginInput!) { unraidPlugins { installPlugin(input: $i) { id status url name } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_install_language(url: str, name: Optional[str] = None, forced: bool = True) -> dict:
    """Install an Unraid language pack from a .plg URL. Lower risk than a
    general plugin (display strings only) — no confirm gate."""
    try:
        inp = {"url": url, "forced": forced}
        if name:
            inp["name"] = name
        return ok(gql(
            "mutation($i: InstallPluginInput!) { unraidPlugins { installLanguage(input: $i) { id status url name } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_install_operation(operation_id: str) -> dict:
    """Check the status/output of a tracked plugin install operation by id."""
    try:
        return ok(gql(
            "query($id: ID!) { pluginInstallOperation(operationId: $id) { id url name status createdAt finishedAt output } }",
            {"id": operation_id},
        ).get("pluginInstallOperation"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_plugin_install_operations() -> dict:
    """List all tracked plugin/language install operations and their status."""
    try:
        return ok(gql("{ pluginInstallOperations { id url name status createdAt finishedAt } }").get("pluginInstallOperations"))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# RCLONE / FLASH BACKUP                                                       #
# ============================================================================ #
@mcp.tool()
def unraid_rclone_settings() -> dict:
    """List configured RClone remotes (name, type, params) — the backend for
    flash/config backups to cloud storage. (The schema also has a `drives`
    field, but this server returns a schema-violating null for it when none
    are configured, which crashes the whole query — omitted here; use
    unraid_graphql if you need it and expect it to be populated.)"""
    try:
        return ok(gql("{ rclone { remotes { name type parameters } } }").get("rclone"))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_rclone_remote_create(name: str, type: str, parameters: dict, confirm: bool = False) -> dict:
    """Create an RClone remote (a cloud storage backend target), e.g.
    type="s3"/"drive"/"backblaze"... with provider-specific `parameters`.
    Stores credentials on the server: requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to create RClone remote '{name}' (stores credentials on the server).")
    try:
        inp = {"name": name, "type": type, "parameters": parameters}
        return ok(gql(
            "mutation($i: CreateRCloneRemoteInput!) { rclone { createRCloneRemote(input: $i) { name type } } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_rclone_remote_delete(name: str, confirm: bool = False) -> dict:
    """Delete an RClone remote by name. Requires confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to delete RClone remote '{name}'.")
    try:
        return ok(gql("mutation($i: DeleteRCloneRemoteInput!) { rclone { deleteRCloneRemote(input: $i) } }", {"i": {"name": name}}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_flash_backup_initiate(remote_name: str, source_path: str, destination_path: str,
                                  options: Optional[dict] = None, confirm: bool = False) -> dict:
    """Start a flash-drive (or arbitrary path) backup to a configured RClone
    remote. source_path is typically the flash boot drive path; options can
    include things like {"dry-run": true, "transfers": 4}. Requires
    confirm=True."""
    if not confirm:
        return refuse("pass confirm=True to initiate a flash backup.")
    try:
        inp = {"remoteName": remote_name, "sourcePath": source_path, "destinationPath": destination_path}
        if options:
            inp["options"] = options
        return ok(gql(
            "mutation($i: InitiateFlashBackupInput!) { initiateFlashBackup(input: $i) { status jobId } }",
            {"i": inp},
        ))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# DEPLOYMENT LAYER (SSH-backed create/deploy)                                  #
#                                                                              #
# Unraid's GraphQL API can operate existing containers/VMs but cannot CREATE   #
# them (no run/define mutation exists). These tools deploy over SSH the way    #
# Unraid itself does — writing a dockerMan template + running with the         #
# `net.unraid.docker.*` managed labels so the result is a first-class citizen  #
# in the Docker/VM tabs — plus Community Applications and compose stacks.      #
# Every value that reaches a shell is shlex.quote()d; every template value is  #
# XML-escaped. All create/deploy/delete tools are confirm-gated.               #
# ============================================================================ #
_TEMPLATES_DIR = "/boot/config/plugins/dockerMan/templates-user"
_COMPOSE_DIR = "/boot/config/plugins/compose.manager/projects"
_DOMAINS_DIR = "/mnt/user/domains"
_ISOS_DIR = "/mnt/user/isos"
_CA_FEED_URL = "https://raw.githubusercontent.com/Squidly271/AppFeed/master/applicationFeed.json"
# VMs that must never be created over / stopped / deleted by these tools. This
# session runs inside GH-Dev on this very box; touching it would be suicidal.
_PROTECTED_VMS = {"gh-dev"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

_ca_feed_cache: dict = {"apps": None}


def _xml_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name or ""))


def _norm_ports(ports) -> list[tuple[str, str, str]]:
    """Normalize ports to (host, container, proto). Accepts "8080:80",
    "8080:80/udp", 8080 (→ same host/container), or {"host","container","proto"}."""
    out = []
    for p in ports or []:
        if isinstance(p, dict):
            host = str(p.get("host") or p.get("container"))
            cont = str(p.get("container") or p.get("host"))
            proto = (p.get("proto") or "tcp").lower()
        else:
            s = str(p)
            proto = "tcp"
            if "/" in s:
                s, proto = s.rsplit("/", 1)
                proto = proto.lower()
            host, _, cont = s.partition(":")
            cont = cont or host
        out.append((host, cont, proto))
    return out


def _norm_volumes(volumes) -> list[tuple[str, str, str]]:
    """Normalize volumes to (host, container, mode). Accepts "/h:/c",
    "/h:/c:ro", or {"host","container","mode"}."""
    out = []
    for v in volumes or []:
        if isinstance(v, dict):
            out.append((str(v["host"]), str(v["container"]), (v.get("mode") or "rw")))
        else:
            parts = str(v).split(":")
            host, cont = parts[0], parts[1] if len(parts) > 1 else parts[0]
            mode = parts[2] if len(parts) > 2 else "rw"
            out.append((host, cont, mode))
    return out


def _build_container_template(spec: dict) -> str:
    """Build an Unraid Container v2 XML template from a normalized spec so the
    deployed container is editable in the Docker tab's Edit screen."""
    name = spec["name"]
    lines = [
        '<?xml version="1.0"?>',
        '<Container version="2">',
        f'  <Name>{_xml_escape(name)}</Name>',
        f'  <Repository>{_xml_escape(spec["image"])}</Repository>',
        f'  <Registry>{_xml_escape(spec.get("registry", ""))}</Registry>',
        f'  <Network>{_xml_escape(spec.get("network", "bridge"))}</Network>',
        '  <MyIP/>',
        f'  <Privileged>{"true" if spec.get("privileged") else "false"}</Privileged>',
        f'  <Support>{_xml_escape(spec.get("support", ""))}</Support>',
        f'  <Overview>{_xml_escape(spec.get("overview", ""))}</Overview>',
        f'  <Category>{_xml_escape(spec.get("category", ""))}</Category>',
        f'  <WebUI>{_xml_escape(spec.get("webui", ""))}</WebUI>',
        f'  <Icon>{_xml_escape(spec.get("icon", ""))}</Icon>',
        f'  <ExtraParams>{_xml_escape(spec.get("extra_params", ""))}</ExtraParams>',
        '  <PostArgs/>',
    ]
    for host, cont, proto in _norm_ports(spec.get("ports")):
        lines.append(
            f'  <Config Name="Port {cont}" Target="{_xml_escape(cont)}" '
            f'Default="{_xml_escape(host)}" Mode="{proto}" Description="" Type="Port" '
            f'Display="always" Required="false" Mask="false">{_xml_escape(host)}</Config>'
        )
    for host, cont, mode in _norm_volumes(spec.get("volumes")):
        lines.append(
            f'  <Config Name="Path {cont}" Target="{_xml_escape(cont)}" '
            f'Default="{_xml_escape(host)}" Mode="{mode}" Description="" Type="Path" '
            f'Display="always" Required="false" Mask="false">{_xml_escape(host)}</Config>'
        )
    for k, v in (spec.get("env") or {}).items():
        lines.append(
            f'  <Config Name="{_xml_escape(k)}" Target="{_xml_escape(k)}" Default="" '
            f'Mode="" Description="" Type="Variable" Display="always" Required="false" '
            f'Mask="false">{_xml_escape(v)}</Config>'
        )
    lines.append('</Container>')
    return "\n".join(lines) + "\n"


def _build_run_command(spec: dict) -> str:
    """Build the `docker run -d` command Unraid would, with managed labels."""
    name = spec["name"]
    parts = ["docker", "run", "-d", "--name", shlex.quote(name),
             "--network", shlex.quote(spec.get("network", "bridge"))]
    # Unraid manages boot-start via its autostart list, so containers run
    # with restart policy "no" (see unraid_docker_autostart_set).
    parts += ["--restart", "no"]
    if spec.get("privileged"):
        parts.append("--privileged")
    for host, cont, proto in _norm_ports(spec.get("ports")):
        parts += ["-p", shlex.quote(f"{host}:{cont}/{proto}")]
    for host, cont, mode in _norm_volumes(spec.get("volumes")):
        parts += ["-v", shlex.quote(f"{host}:{cont}:{mode}")]
    for k, v in (spec.get("env") or {}).items():
        parts += ["-e", shlex.quote(f"{k}={v}")]
    parts += ["-l", shlex.quote("net.unraid.docker.managed=dockerman")]
    if spec.get("icon"):
        parts += ["-l", shlex.quote(f"net.unraid.docker.icon={spec['icon']}")]
    if spec.get("webui"):
        parts += ["-l", shlex.quote(f"net.unraid.docker.webui={spec['webui']}")]
    if spec.get("extra_params"):
        parts.append(spec["extra_params"])  # advanced: passed as-is, like Unraid
    parts.append(shlex.quote(spec["image"]))
    if spec.get("post_args"):
        parts.append(spec["post_args"])
    return " ".join(parts)


def _deploy_container(cfg: dict, spec: dict, pull: bool = True) -> dict:
    """Shared deploy engine: write template, (pull), run, verify."""
    name = spec["name"]
    steps = {}
    template = _build_container_template(spec)
    _ssh_write_file(cfg, f"{_TEMPLATES_DIR}/my-{name}.xml", template)
    steps["template"] = f"{_TEMPLATES_DIR}/my-{name}.xml"
    if pull:
        code, out, e = _ssh_exec(cfg, f"docker pull {shlex.quote(spec['image'])}", timeout=600)
        steps["pull"] = "ok" if code == 0 else (e.strip() or out.strip())
    run_cmd = _build_run_command(spec)
    code, out, e = _ssh_exec(cfg, run_cmd, timeout=120)
    if code != 0:
        return err(RuntimeError(f"docker run failed: {e.strip() or out.strip()}\ncommand: {run_cmd}"))
    steps["container_id"] = out.strip()[:12]
    steps["run_command"] = run_cmd
    return ok({"name": name, **steps})


@mcp.tool()
def unraid_docker_deploy(name: str, image: str, ports: Optional[list] = None,
                          volumes: Optional[list] = None, env: Optional[dict] = None,
                          network: str = "bridge", webui: str = "", icon: str = "",
                          extra_params: str = "", post_args: str = "",
                          privileged: bool = False, autostart: bool = False,
                          pull: bool = True, confirm: bool = False) -> dict:
    """Deploy a NEW Docker container the native Unraid way: writes a dockerMan
    template AND runs the container with Unraid's managed labels, so it appears
    in the Docker tab, is editable in the UI, and works with
    unraid_docker_env_set. Requires SSH (unraid_ssh_test) and confirm=True.

    Args:
        name: Container name (also the template name). Must be unique.
        image: Full image ref, e.g. "lscr.io/linuxserver/syncthing".
        ports: List of "host:container" or "host:container/udp" (or dicts).
        volumes: List of "/host/path:/container/path[:ro]" (or dicts).
        env: {VAR: value} environment variables.
        network: "bridge" (default), "host", "br0", "none", or a custom net.
        webui/icon: optional URLs surfaced in the Docker tab.
        extra_params: advanced raw `docker run` flags (passed as-is).
        post_args: arguments appended after the image (the container command).
        privileged: run privileged.
        autostart: set Unraid autostart on after deploy.
        pull: docker pull the image first (default true).
        confirm: must be True to deploy.
    """
    if not confirm:
        return refuse(f"pass confirm=True to deploy container '{name}'.")
    if not _valid_name(name):
        return refuse(f"invalid container name '{name}' (letters/digits/._- , <=63 chars).")
    cfg = load_config()
    try:
        code, out, _e = _ssh_exec(cfg, f"docker inspect {shlex.quote(name)} >/dev/null 2>&1; echo $?")
        if out.strip().endswith("0"):
            return refuse(f"a container named '{name}' already exists — pick another name "
                          f"or use unraid_docker_remove first.")
        spec = {"name": name, "image": image, "ports": ports, "volumes": volumes,
                "env": env, "network": network, "webui": webui, "icon": icon,
                "extra_params": extra_params, "post_args": post_args, "privileged": privileged}
        result = _deploy_container(cfg, spec, pull=pull)
        if result.get("success") and autostart:
            try:
                gql("mutation($i: DockerAutostartInput!) { docker { updateAutostartConfiguration(input: $i) { id } } }",
                    {"i": {"entries": [{"id": name, "autoStart": True}]}})
                result["data"]["autostart"] = "enabled"
            except Exception as ae:  # noqa: BLE001
                result["data"]["autostart"] = f"deploy ok, autostart failed: {ae}"
        return result
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_template_get(name: str) -> dict:
    """Read back the stored dockerMan template XML for a container (read-only).
    Useful to inspect what unraid_docker_deploy wrote or an existing app's
    template. Requires SSH."""
    cfg = load_config()
    try:
        return ok({"name": name, "xml": _ssh_read_file(cfg, f"{_TEMPLATES_DIR}/my-{name}.xml")})
    except Exception as e:  # noqa: BLE001
        return err(e)


def _load_ca_feed() -> list:
    if _ca_feed_cache["apps"] is None:
        with httpx.Client(timeout=60, follow_redirects=True) as c:
            data = c.get(_CA_FEED_URL).json()
        _ca_feed_cache["apps"] = data.get("applist", [])
    return _ca_feed_cache["apps"]


@mcp.tool()
def unraid_ca_search(query: str, limit: int = 20) -> dict:
    """Search the Community Applications catalog (~4000 apps) by name /
    repository / overview. Returns the app name, image, template URL, category,
    star/download counts, and overview — feed candidates into unraid_ca_deploy.
    Fetched over the internet from the CA app feed (cached in-process)."""
    try:
        q = query.lower().strip()
        apps = _load_ca_feed()
        hits = []
        for a in apps:
            hay = f"{a.get('Name','')} {a.get('Repository','')} {a.get('Overview','')}".lower()
            if q in hay:
                hits.append({
                    "name": a.get("Name"), "repository": a.get("Repository"),
                    "template_url": a.get("TemplateURL"), "category": a.get("Category"),
                    "icon": a.get("Icon"), "webui": a.get("WebUI"),
                    "stars": a.get("stars"), "downloads": a.get("downloads"),
                    "overview": (a.get("Overview") or "")[:200],
                })
        hits.sort(key=lambda h: (h.get("stars") or 0), reverse=True)
        return ok({"query": query, "count": len(hits), "results": hits[:limit]})
    except Exception as e:  # noqa: BLE001
        return err(e)


def _parse_ca_template(xml: str) -> dict:
    """Extract a deployable spec from a CA Container template XML."""
    def tag(t):
        m = re.search(rf"<{t}>(.*?)</{t}>", xml, re.DOTALL)
        return _unescape(m.group(1).strip()) if m else ""
    spec = {
        "name": tag("Name"), "image": tag("Repository"), "registry": tag("Registry"),
        "network": tag("Network") or "bridge", "webui": tag("WebUI"),
        "icon": tag("Icon"), "overview": tag("Overview"), "category": tag("Category"),
        "support": tag("Support"), "extra_params": tag("ExtraParams"),
        "privileged": tag("Privileged").lower() == "true",
        "ports": [], "volumes": [], "env": {},
    }
    # Config entries come in both forms: paired <Config ...>value</Config> and
    # self-closing <Config ... Default="value"/> (linuxserver templates use the
    # latter, with the value in the Default attribute).
    for m in re.finditer(r"<Config\b([^>]*?)(?:/>|>(.*?)</Config>)", xml, re.DOTALL):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        body = (m.group(2) or "").strip()
        value = _unescape(body) if body else attrs.get("Default", "")
        typ, target = attrs.get("Type"), attrs.get("Target", "")
        if typ == "Port" and value and target:
            spec["ports"].append(f"{value}:{target}/{(attrs.get('Mode') or 'tcp')}")
        elif typ == "Path" and value and target:
            spec["volumes"].append(f"{value}:{target}:{(attrs.get('Mode') or 'rw')}")
        elif typ == "Variable" and target:
            spec["env"][target] = value
    return spec


def _unescape(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#xE0;", "à").replace("&amp;", "&"))


@mcp.tool()
def unraid_ca_deploy(template_url: str, name: str = "", overrides: Optional[dict] = None,
                      pull: bool = True, autostart: bool = False, confirm: bool = False) -> dict:
    """Deploy a Community Applications app by its template URL (from
    unraid_ca_search). Fetches the official template, then deploys through the
    same native engine as unraid_docker_deploy. Override any field with
    `overrides` (e.g. {"name": "...", "ports": [...], "volumes": [...],
    "env": {...}, "network": "..."}); paths default to the template's values,
    so review them first. Requires SSH and confirm=True.

    Args:
        template_url: The app's TemplateURL from unraid_ca_search.
        name: Override the container name (defaults to the template's Name).
        overrides: Dict merged over the parsed template spec.
        pull/autostart/confirm: as unraid_docker_deploy.
    """
    if not confirm:
        return refuse("pass confirm=True to deploy this CA app.")
    cfg = load_config()
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as c:
            xml = c.get(template_url).text
        spec = _parse_ca_template(xml)
        if name:
            spec["name"] = name
        if overrides:
            for k, v in overrides.items():
                if k in ("env",) and isinstance(v, dict):
                    spec.setdefault("env", {}).update(v)
                else:
                    spec[k] = v
        if not spec.get("name") or not spec.get("image"):
            return err(RuntimeError("template missing Name/Repository; pass name= and check the URL."))
        if not _valid_name(spec["name"]):
            return refuse(f"invalid container name '{spec['name']}'.")
        code, out, _e = _ssh_exec(cfg, f"docker inspect {shlex.quote(spec['name'])} >/dev/null 2>&1; echo $?")
        if out.strip().endswith("0"):
            return refuse(f"a container named '{spec['name']}' already exists.")
        result = _deploy_container(cfg, spec, pull=pull)
        if result.get("success") and autostart:
            try:
                gql("mutation($i: DockerAutostartInput!) { docker { updateAutostartConfiguration(input: $i) { id } } }",
                    {"i": {"entries": [{"id": spec["name"], "autoStart": True}]}})
                result["data"]["autostart"] = "enabled"
            except Exception as ae:  # noqa: BLE001
                result["data"]["autostart"] = f"deploy ok, autostart failed: {ae}"
        return result
    except Exception as e:  # noqa: BLE001
        return err(e)


_COMPOSE_PLUGIN_URL = "https://raw.githubusercontent.com/dcflachs/compose_plugin/main/compose.manager.plg"


def _compose_bin(cfg: dict) -> str:
    """Return a working compose invocation ('docker compose' or
    'docker-compose'), or '' if neither is present. Unraid ships no compose by
    default — the Compose Manager plugin provides the docker-compose binary."""
    code, out, _e = _ssh_exec(cfg, "docker compose version >/dev/null 2>&1 && echo ok")
    if out.strip() == "ok":
        return "docker compose"
    code, out, _e = _ssh_exec(cfg, "docker-compose version >/dev/null 2>&1 && echo ok")
    if out.strip() == "ok":
        return "docker-compose"
    return ""


def _ensure_compose(cfg: dict) -> tuple[str, str]:
    """Ensure a compose binary exists, installing Compose Manager if needed.
    Returns (invocation, note)."""
    binv = _compose_bin(cfg)
    if binv:
        return binv, "already present"
    code, out, e = _ssh_exec(cfg, f"plugin install {shlex.quote(_COMPOSE_PLUGIN_URL)}", timeout=300)
    binv = _compose_bin(cfg)
    if not binv:
        raise RuntimeError(f"compose unavailable and Compose Manager install failed: "
                           f"{(e or out).strip()[-400:]}")
    return binv, "installed Compose Manager plugin"


def _compose_installed(cfg: dict) -> bool:
    code, out, _e = _ssh_exec(cfg, f"test -d {shlex.quote(_COMPOSE_DIR)} && echo yes")
    return out.strip() == "yes"


@mcp.tool()
def unraid_compose_deploy(name: str, compose_yaml: str, env_file: str = "",
                           confirm: bool = False) -> dict:
    """Deploy a multi-container compose stack. Writes the project under the
    Compose Manager convention (so it shows in the UI) and runs
    `docker compose up -d`. If the Compose Manager plugin dir is absent it
    still deploys via the docker CLI's built-in compose. Requires SSH and
    confirm=True.

    Args:
        name: Stack/project name.
        compose_yaml: Full docker-compose.yml contents.
        env_file: Optional .env file contents for the stack.
        confirm: must be True.
    """
    if not confirm:
        return refuse(f"pass confirm=True to deploy compose stack '{name}'.")
    if not _valid_name(name):
        return refuse(f"invalid stack name '{name}'.")
    cfg = load_config()
    try:
        binv, note = _ensure_compose(cfg)
        proj = f"{_COMPOSE_DIR}/{name}"
        _ssh_exec(cfg, f"mkdir -p {shlex.quote(proj)}")
        _ssh_write_file(cfg, f"{proj}/docker-compose.yml", compose_yaml)
        # Compose Manager marks a project active/visible via a 'name' file.
        _ssh_write_file(cfg, f"{proj}/name", name + "\n")
        if env_file:
            _ssh_write_file(cfg, f"{proj}/.env", env_file)
        code, out, e = _ssh_exec(
            cfg, f"cd {shlex.quote(proj)} && {binv} -p {shlex.quote(name)} up -d",
            timeout=600)
        if code != 0:
            return err(RuntimeError(f"compose up failed: {e.strip() or out.strip()}"))
        return ok({"name": name, "project_dir": proj, "output": (out + e).strip()[-1500:],
                   "compose": binv, "compose_setup": note})
    except Exception as ex:  # noqa: BLE001
        return err(ex)


@mcp.tool()
def unraid_compose_down(name: str, remove_volumes: bool = False,
                         confirm: bool = False) -> dict:
    """Stop and remove a compose stack (`docker compose down`). remove_volumes
    also deletes named volumes (data loss). Requires SSH and confirm=True."""
    if not confirm:
        return refuse(f"pass confirm=True to bring down compose stack '{name}'.")
    cfg = load_config()
    try:
        binv = _compose_bin(cfg) or "docker compose"
        proj = f"{_COMPOSE_DIR}/{name}"
        vol = " -v" if remove_volumes else ""
        code, out, e = _ssh_exec(
            cfg, f"cd {shlex.quote(proj)} && {binv} -p {shlex.quote(name)} down{vol}",
            timeout=300)
        if code != 0:
            return err(RuntimeError(f"compose down failed: {e.strip() or out.strip()}"))
        return ok({"name": name, "output": (out + e).strip()[-1500:]})
    except Exception as ex:  # noqa: BLE001
        return err(ex)


@mcp.tool()
def unraid_compose_list() -> dict:
    """List compose projects and their running state (read-only). Requires SSH."""
    cfg = load_config()
    try:
        binv = _compose_bin(cfg)
        if not binv:
            return ok({"projects": [], "note": "no compose binary installed yet "
                       "(unraid_compose_deploy installs Compose Manager on first use)"})
        code, out, _e = _ssh_exec(cfg, f"{binv} ls --all --format json", timeout=30)
        projects = json.loads(out.strip()) if out.strip().startswith("[") else out.strip()
        return ok({"projects": projects})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_isos() -> dict:
    """List ISO images available for VM creation from /mnt/user/isos
    (read-only). Requires SSH."""
    cfg = load_config()
    try:
        code, out, _e = _ssh_exec(cfg, f"ls -1 {shlex.quote(_ISOS_DIR)} 2>/dev/null")
        return ok({"isos_dir": _ISOS_DIR, "isos": [x for x in out.splitlines() if x.strip()]})
    except Exception as e:  # noqa: BLE001
        return err(e)


def _build_vm_xml(spec: dict) -> str:
    """Generate a libvirt domain XML for an Unraid VM. Modeled on Unraid's own
    VM-manager output for this host: q35 machine + OVMF (UEFI) with an
    auto-copied nvram, virtio disk/net, VNC + qxl. Addresses are left for
    libvirt to assign. `emulator` and OVMF paths are the Unraid defaults."""
    name = spec["name"]
    dom_uuid = spec["uuid"]
    vcpus = int(spec.get("cpu", 2))
    mem_kib = int(float(spec.get("mem_gb", 4)) * 1024 * 1024)
    vdisk = spec["vdisk_path"]
    iso = spec.get("iso_path", "")
    os_type = spec.get("os_type", "linux")
    disk_bus = spec.get("vdisk_bus", "virtio")
    cdrom = ""
    if iso:
        cdrom = f"""
    <disk type='file' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source file='{_xml_escape(iso)}'/>
      <target dev='hda' bus='sata'/>
      <readonly/>
      <boot order='2'/>
    </disk>"""
    return f"""<domain type='kvm'>
  <name>{_xml_escape(name)}</name>
  <uuid>{dom_uuid}</uuid>
  <metadata>
    <vmtemplate xmlns="http://unraid" name="{_xml_escape(name)}" icon="{'windows.png' if os_type=='windows' else 'linux.png'}" os="{_xml_escape(os_type)}" webui="" storage="default"/>
  </metadata>
  <memory unit='KiB'>{mem_kib}</memory>
  <currentMemory unit='KiB'>{mem_kib}</currentMemory>
  <vcpu placement='static'>{vcpus}</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <loader readonly='yes' type='pflash'>/usr/share/qemu/ovmf-x64/OVMF_CODE-pure-efi.fd</loader>
    <nvram template='/usr/share/qemu/ovmf-x64/OVMF_VARS-pure-efi.fd'>/etc/libvirt/qemu/nvram/{dom_uuid}_VARS-pure-efi.fd</nvram>
  </os>
  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough' check='none' migratable='on'/>
  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='pit' tickpolicy='delay'/>
    <timer name='hpet' present='no'/>
  </clock>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>restart</on_crash>
  <devices>
    <emulator>/usr/local/sbin/qemu</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='raw' cache='writeback'/>
      <source file='{_xml_escape(vdisk)}'/>
      <target dev='hdc' bus='{disk_bus}'/>
      <boot order='1'/>
    </disk>{cdrom}
    <controller type='virtio-serial' index='0'/>
    <interface type='bridge'>
      <source bridge='br0'/>
      <model type='virtio-net'/>
    </interface>
    <serial type='pty'/>
    <console type='pty'/>
    <channel type='unix'>
      <target type='virtio' name='org.qemu.guest_agent.0'/>
    </channel>
    <input type='tablet' bus='usb'/>
    <graphics type='vnc' port='-1' autoport='yes' websocket='-1' listen='0.0.0.0'/>
    <video><model type='qxl'/></video>
    <memballoon model='virtio'/>
  </devices>
</domain>
"""


@mcp.tool()
def unraid_vm_create(name: str, cpu: int = 2, mem_gb: float = 4, vdisk_gb: float = 30,
                      iso: str = "", os_type: str = "linux", vdisk_bus: str = "virtio",
                      autostart: bool = False, confirm: bool = False) -> dict:
    """Create a NEW VM the Unraid way: allocate a vdisk, generate libvirt
    domain XML, and `virsh define` it so it appears in the VM Manager. Covers
    Linux and Windows (os_type="windows" adds a USB tablet; attach the
    virtio-win ISO as a second drive later for drivers). Requires SSH and
    confirm=True.

    Args:
        name: VM name (dir /mnt/user/domains/<name> is created).
        cpu: vCPU count. mem_gb: RAM in GiB. vdisk_gb: primary disk size in GiB.
        iso: install ISO filename from unraid_vm_isos (blank = diskless/PXE).
        os_type: "linux" or "windows".
        vdisk_bus: "virtio" (needs drivers for Windows install) or "sata".
        autostart: mark the VM to auto-start on boot.
        confirm: must be True.
    """
    if not confirm:
        return refuse(f"pass confirm=True to create VM '{name}'.")
    if not _valid_name(name):
        return refuse(f"invalid VM name '{name}'.")
    if name.lower() in _PROTECTED_VMS:
        return refuse(f"'{name}' is a protected VM and cannot be created/modified by this tool.")
    cfg = load_config()
    try:
        code, out, _e = _ssh_exec(cfg, f"virsh dominfo {shlex.quote(name)} >/dev/null 2>&1; echo $?")
        if out.strip().endswith("0"):
            return refuse(f"a VM named '{name}' already exists.")
        vm_dir = f"{_DOMAINS_DIR}/{name}"
        vdisk = f"{vm_dir}/vdisk1.img"
        _ssh_exec(cfg, f"mkdir -p {shlex.quote(vm_dir)} /etc/libvirt/qemu/nvram")
        code, out, e = _ssh_exec(
            cfg, f"qemu-img create -f raw {shlex.quote(vdisk)} {int(vdisk_gb)}G", timeout=300)
        if code != 0:
            return err(RuntimeError(f"vdisk create failed: {e.strip() or out.strip()}"))
        spec = {"name": name, "uuid": str(uuid.uuid4()), "cpu": cpu, "mem_gb": mem_gb,
                "vdisk_path": vdisk, "os_type": os_type, "vdisk_bus": vdisk_bus}
        if iso:
            spec["iso_path"] = f"{_ISOS_DIR}/{iso}"
        xml = _build_vm_xml(spec)
        remote_xml = f"{vm_dir}/{name}.xml"
        _ssh_write_file(cfg, remote_xml, xml)
        code, out, e = _ssh_exec(cfg, f"virsh define {shlex.quote(remote_xml)}", timeout=60)
        if code != 0:
            return err(RuntimeError(f"virsh define failed: {e.strip() or out.strip()}"))
        result = {"name": name, "vdisk": vdisk, "vdisk_gb": int(vdisk_gb), "defined": out.strip()}
        if autostart:
            ac, ao, ae = _ssh_exec(cfg, f"virsh autostart {shlex.quote(name)}")
            result["autostart"] = "enabled" if ac == 0 else (ae.strip() or ao.strip())
        return ok(result)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_vm_delete(name: str, delete_vdisk: bool = False, confirm: bool = False,
                      acknowledge: str = "") -> dict:
    """Delete a VM (`virsh destroy` if running, then `virsh undefine`).
    delete_vdisk also removes /mnt/user/domains/<name> (DATA LOSS) and is
    DOUBLE-gated: pass confirm=True AND acknowledge='<name>'. Requires SSH.
    Refuses protected VMs (e.g. GH-Dev)."""
    if not confirm:
        return refuse(f"pass confirm=True to delete VM '{name}'.")
    if name.lower() in _PROTECTED_VMS:
        return refuse(f"'{name}' is a protected VM and cannot be deleted by this tool.")
    if delete_vdisk and acknowledge != name:
        return refuse(f"deleting the vdisk is destructive — also pass acknowledge='{name}'.")
    cfg = load_config()
    try:
        _ssh_exec(cfg, f"virsh destroy {shlex.quote(name)} 2>/dev/null; true")
        code, out, e = _ssh_exec(cfg, f"virsh undefine {shlex.quote(name)} --nvram")
        if code != 0:
            return err(RuntimeError(f"virsh undefine failed: {e.strip() or out.strip()}"))
        result = {"name": name, "undefined": out.strip()}
        if delete_vdisk:
            dc, do, de = _ssh_exec(cfg, f"rm -rf {shlex.quote(_DOMAINS_DIR + '/' + name)}")
            result["vdisk_deleted"] = (dc == 0)
        return ok(result)
    except Exception as e:  # noqa: BLE001
        return err(e)


# ============================================================================ #
# FILES & SHARES (SSH-backed)                                                  #
#                                                                              #
# Unraid's GraphQL API can list shares but has no mutation to create/edit/     #
# delete them, and no file access at all. Shares live as /mnt/user/<name>      #
# dirs + a /boot/config/shares/<name>.cfg settings file; new share config is   #
# applied live via `emcmd`. File ops run over SSH on absolute paths. Every     #
# write/delete is confirm-gated; recursive deletes and data-destroying share   #
# deletes are double-gated, and catastrophic paths are hard-refused.           #
# ============================================================================ #
_SHARES_CFG_DIR = "/boot/config/shares"
_EMCMD = "/usr/local/sbin/emcmd"

# ---------------------------------------------------------------------------- #
# shfs-reload safety guard.
#
# INCIDENT (2026-08-11): creating/deleting a share via `emcmd changeShare`
# makes emhttpd "Restart services", which reloads the /mnt/user FUSE (shfs)
# layer. Any container whose appdata is bind-mounted through a /mnt/user path
# (instead of /mnt/cache/... or a direct disk) has its OPEN FILES severed by
# that reload — which crashed and wiped a running PostgreSQL's data directory.
# Root cause is two-sided: (a) our tool triggered the reload, and (b) those
# containers violate Unraid best practice by mounting appdata via /mnt/user.
#
# Guarantee: any operation in this file that could reload shfs is DEFAULT-OFF
# (writes config only, no service restart), and even the opt-in apply refuses
# while a running container holds appdata open on a /mnt/user path.
# ---------------------------------------------------------------------------- #
# App-state paths on the FUSE overlay that an shfs reload can corrupt. Media
# libraries (e.g. /mnt/user/TV, /mnt/user/Movies, /mnt/user/Roms) are array
# shares that legitimately use /mnt/user and are NOT flagged — the hazard is
# databases/configs (appdata) and VM disks (domains) that hold files open
# continuously and live on the cache pool.
_USER_STATE_PREFIXES = ("/mnt/user/appdata/", "/mnt/user/appdata", "/mnt/user/domains/", "/mnt/user/domains")


def _containers_mounting_user_share(cfg: dict) -> list[str]:
    """Return names of RUNNING containers that bind-mount appdata or VM-domain
    state through the /mnt/user FUSE overlay — the containers an shfs reload
    would corrupt. Media-library mounts under /mnt/user are intentionally NOT
    flagged. Raises on inspect failure so callers can treat it as unsafe."""
    code, out, _e = _ssh_exec(
        cfg,
        "for c in $(docker ps -q); do "
        "  docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}|{{end}}' \"$c\"; "
        "done",
        timeout=30,
    )
    if code != 0:
        raise RuntimeError("docker inspect failed over SSH")
    hits = []
    for line in out.splitlines():
        parts = line.strip().split(" ", 1)
        if len(parts) != 2:
            continue
        cname, sources = parts[0].lstrip("/"), parts[1]
        srcs = [s for s in sources.split("|") if s]
        if any(s == "/mnt/user/appdata" or s == "/mnt/user/domains"
               or s.startswith("/mnt/user/appdata/") or s.startswith("/mnt/user/domains/")
               for s in srcs):
            hits.append(cname)
    return hits


def _assert_shfs_safe(cfg: dict) -> Optional[dict]:
    """Return a refusal dict if reloading shfs right now is unsafe (running
    containers hold appdata open on /mnt/user), else None."""
    try:
        at_risk = _containers_mounting_user_share(cfg)
    except Exception:  # noqa: BLE001 — inspect failed: treat as unsafe
        return refuse("could not verify container mounts over SSH; refusing to "
                      "trigger an Unraid service/shfs reload while that is unknown.")
    if at_risk:
        return refuse(
            "REFUSED to trigger an Unraid service/shfs reload: these RUNNING "
            f"containers mount appdata via the /mnt/user FUSE path and would have "
            f"their open files severed (this previously wiped a live database): "
            f"{', '.join(at_risk)}. Either stop them first, or (better) migrate "
            f"their appdata bind mounts to /mnt/cache/appdata/... which is immune "
            f"to shfs reloads. The share config was NOT applied live.")
    return None


# Exact paths that must never be written to or deleted.
_PROTECTED_PATHS = {
    "/", "/boot", "/boot/config", "/etc", "/usr", "/bin", "/sbin", "/lib",
    "/lib64", "/var", "/root", "/dev", "/proc", "/sys", "/mnt", "/mnt/user",
    "/mnt/user0", "/mnt/cache", "/mnt/disk1", "/mnt/disk2", "/mnt/disks",
}


def _norm_path(path: str) -> str:
    """Normalize an absolute POSIX path (collapse .. and //). Raises on
    relative paths."""
    if not path or not path.startswith("/"):
        raise ValueError("path must be absolute (start with /).")
    parts: list[str] = []
    for seg in path.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


def _guard_path(path: str, recursive: bool = False) -> Optional[str]:
    """Return a refusal reason if the path is unsafe to modify, else None."""
    try:
        norm = _norm_path(path)
    except ValueError as e:
        return str(e)
    if norm in _PROTECTED_PATHS:
        return f"'{norm}' is a protected system path and cannot be modified."
    # A recursive delete must be at least 3 levels deep (e.g. /mnt/user/share/x)
    # so it can't wipe a whole share root or disk/pool by accident — use
    # unraid_share_delete for share roots.
    if recursive and len([p for p in norm.split("/") if p]) < 3:
        return (f"refusing recursive delete of '{norm}' — too shallow (could wipe a "
                f"share/disk root). Use unraid_share_delete for share roots, or target "
                f"a deeper path.")
    return None


@mcp.tool()
def unraid_fs_list(path: str, show_hidden: bool = False) -> dict:
    """List a directory on the server over SSH (name, type, size, mtime, perms).
    Absolute paths only, e.g. "/mnt/user/Movies". Read-only. Requires SSH."""
    cfg = load_config()
    try:
        p = _norm_path(path)
        flag = "-la" if show_hidden else "-l"
        code, out, e = _ssh_exec(cfg, f"ls {flag} --time-style=long-iso {shlex.quote(p)}")
        if code != 0:
            return err(RuntimeError(e.strip() or out.strip() or f"cannot list {p}"))
        entries = []
        for line in out.splitlines():
            cols = line.split(maxsplit=7)
            if len(cols) < 8 or cols[0].startswith("total"):
                continue
            perms, _links, owner, group, size, date, tm, name = cols
            entries.append({"name": name, "type": "dir" if perms[0] == "d" else
                            ("link" if perms[0] == "l" else "file"),
                            "perms": perms, "owner": owner, "group": group,
                            "size": int(size) if size.isdigit() else size,
                            "modified": f"{date} {tm}"})
        return ok({"path": p, "count": len(entries), "entries": entries})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_read(path: str, max_bytes: int = 65536) -> dict:
    """Read a text file on the server over SSH (up to max_bytes, default 64 KiB).
    Absolute path. Read-only. Requires SSH."""
    cfg = load_config()
    try:
        p = _norm_path(path)
        code, out, e = _ssh_exec(cfg, f"head -c {int(max_bytes)} {shlex.quote(p)}")
        if code != 0:
            return err(RuntimeError(e.strip() or f"cannot read {p}"))
        _c, sz, _e = _ssh_exec(cfg, f"stat -c %s {shlex.quote(p)}")
        return ok({"path": p, "size": int(sz.strip()) if sz.strip().isdigit() else None,
                   "truncated": sz.strip().isdigit() and int(sz.strip()) > max_bytes,
                   "content": out})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_write(path: str, content: str, append: bool = False,
                     confirm: bool = False) -> dict:
    """Write (or append to) a text file on the server over SSH. Creates parent
    dirs as needed. Absolute path. WRITES: confirm-gated. Requires SSH."""
    if not confirm:
        return refuse(f"pass confirm=True to write '{path}'.")
    cfg = load_config()
    try:
        p = _norm_path(path)
        guard = _guard_path(p)
        if guard:
            return refuse(guard)
        parent = p.rsplit("/", 1)[0] or "/"
        _ssh_exec(cfg, f"mkdir -p {shlex.quote(parent)}")
        if append:
            existing = _ssh_read_file(cfg, p) if _ssh_exec(cfg, f"test -f {shlex.quote(p)} && echo y")[1].strip() == "y" else ""
            _ssh_write_file(cfg, p, existing + content)
        else:
            _ssh_write_file(cfg, p, content)
        _c, sz, _e = _ssh_exec(cfg, f"stat -c %s {shlex.quote(p)}")
        return ok({"path": p, "bytes": int(sz.strip()) if sz.strip().isdigit() else None,
                   "mode": "append" if append else "overwrite"})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_mkdir(path: str, confirm: bool = False) -> dict:
    """Create a directory (and parents) on the server over SSH. Absolute path.
    WRITES: confirm-gated. Requires SSH."""
    if not confirm:
        return refuse(f"pass confirm=True to create directory '{path}'.")
    cfg = load_config()
    try:
        p = _norm_path(path)
        code, out, e = _ssh_exec(cfg, f"mkdir -p {shlex.quote(p)}")
        if code != 0:
            return err(RuntimeError(e.strip() or out.strip()))
        return ok({"path": p, "created": True})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_move(source: str, dest: str, confirm: bool = False) -> dict:
    """Move/rename a file or directory on the server over SSH. WRITES:
    confirm-gated. Requires SSH."""
    if not confirm:
        return refuse(f"pass confirm=True to move '{source}' -> '{dest}'.")
    cfg = load_config()
    try:
        s, d = _norm_path(source), _norm_path(dest)
        guard = _guard_path(s)
        if guard:
            return refuse(guard)
        code, out, e = _ssh_exec(cfg, f"mv {shlex.quote(s)} {shlex.quote(d)}")
        if code != 0:
            return err(RuntimeError(e.strip() or out.strip()))
        return ok({"source": s, "dest": d, "moved": True})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_copy(source: str, dest: str, confirm: bool = False) -> dict:
    """Copy a file or directory (recursively) on the server over SSH. WRITES:
    confirm-gated. Requires SSH."""
    if not confirm:
        return refuse(f"pass confirm=True to copy '{source}' -> '{dest}'.")
    cfg = load_config()
    try:
        s, d = _norm_path(source), _norm_path(dest)
        code, out, e = _ssh_exec(cfg, f"cp -a {shlex.quote(s)} {shlex.quote(d)}", timeout=1800)
        if code != 0:
            return err(RuntimeError(e.strip() or out.strip()))
        return ok({"source": s, "dest": d, "copied": True})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_fs_delete(path: str, recursive: bool = False, confirm: bool = False,
                      acknowledge: str = "") -> dict:
    """Delete a file or directory on the server over SSH. recursive=True removes
    a directory tree and is DOUBLE-gated: pass confirm=True AND
    acknowledge='<path>'. Catastrophic/system paths are refused. Requires SSH."""
    if not confirm:
        return refuse(f"pass confirm=True to delete '{path}'.")
    cfg = load_config()
    try:
        p = _norm_path(path)
        guard = _guard_path(p, recursive=recursive)
        if guard:
            return refuse(guard)
        if recursive and acknowledge != p:
            return refuse(f"recursive delete is destructive — also pass acknowledge='{p}'.")
        flag = "-rf" if recursive else "-f"
        code, out, e = _ssh_exec(cfg, f"rm {flag} {shlex.quote(p)}")
        if code != 0:
            return err(RuntimeError(e.strip() or out.strip()))
        return ok({"path": p, "deleted": True, "recursive": recursive})
    except Exception as e:  # noqa: BLE001
        return err(e)


def _build_share_cfg(spec: dict) -> str:
    """Build an Unraid /boot/config/shares/<name>.cfg from a spec with defaults
    matching the webGUI's own generated files."""
    g = spec.get
    return (
        "# Generated settings:\n"
        f'shareComment="{g("comment", "")}"\n'
        f'shareInclude="{g("include", "")}"\n'
        f'shareExclude="{g("exclude", "")}"\n'
        f'shareUseCache="{g("use_cache", "no")}"\n'
        f'shareCachePool="{g("cache_pool", "")}"\n'
        f'shareCachePool2=""\n'
        f'shareCOW="{g("cow", "auto")}"\n'
        f'shareAllocator="{g("allocator", "highwater")}"\n'
        f'shareSplitLevel="{g("split_level", "")}"\n'
        f'shareFloor="{g("floor", "0")}"\n'
        f'shareExport="{g("export", "e")}"\n'
        f'shareCaseSensitive="auto"\n'
        f'shareSecurity="{g("security", "public")}"\n'
        f'shareReadList="{g("read_list", "")}"\n'
        f'shareWriteList="{g("write_list", "")}"\n'
        f'shareVolsizelimit=""\n'
        f'shareExportNFS="{g("export_nfs", "-")}"\n'
        f'shareExportNFSFsid="0"\n'
        f'shareSecurityNFS="public"\n'
        f'shareHostListNFS=""\n'
    )


@mcp.tool()
def unraid_share_create(name: str, comment: str = "", use_cache: str = "no",
                         cache_pool: str = "", allocator: str = "highwater",
                         security: str = "public", export: str = "e",
                         apply: bool = False, confirm: bool = False) -> dict:
    """Create a new user share: writes /boot/config/shares/<name>.cfg and creates
    /mnt/user/<name>. Requires SSH and confirm=True.

    SAFETY: writing the config + directory does NOT disturb running containers.
    Making the share LIVE immediately requires emcmd, which restarts Unraid
    services and reloads the /mnt/user (shfs) FUSE layer — that reload can
    CORRUPT any running container whose appdata is bind-mounted via /mnt/user
    (it once wiped a live PostgreSQL). So live-apply is OFF by default:
      - apply=False (default): config-only. The share activates on Unraid's next
        share-settings refresh (e.g. array restart or a share edit in the UI).
      - apply=True: also runs emcmd — but this REFUSES if any running container
        holds appdata open on a /mnt/user path (stop them or move their appdata
        to /mnt/cache first). See unraid_shfs_risk_check.

    Args:
        name: Share name (also the /mnt/user/<name> directory).
        comment: Optional description.
        use_cache: "no" | "yes" | "prefer" | "only" (cache/pool policy).
        cache_pool: pool name when use_cache != "no" (e.g. "cache").
        allocator: "highwater" | "most-free" | "fillup".
        security: "public" | "secure" | "private".
        export: "e" (export SMB) or "-" (do not export).
        apply: also apply live via emcmd (guarded — see SAFETY above).
        confirm: must be True.
    """
    if not confirm:
        return refuse(f"pass confirm=True to create share '{name}'.")
    if not _valid_name(name):
        return refuse(f"invalid share name '{name}'.")
    cfg = load_config()
    try:
        cfg_path = f"{_SHARES_CFG_DIR}/{name}.cfg"
        if _ssh_exec(cfg, f"test -e {shlex.quote(cfg_path)} && echo y")[1].strip() == "y":
            return refuse(f"share '{name}' already exists.")
        applied, apply_note = False, "config-only (apply=False); activates on next Unraid share refresh"
        if apply:
            risk = _assert_shfs_safe(cfg)
            if risk:
                return risk
        spec = {"comment": comment, "use_cache": use_cache, "cache_pool": cache_pool,
                "allocator": allocator, "security": security, "export": export}
        _ssh_exec(cfg, f"mkdir -p {shlex.quote(_SHARES_CFG_DIR)} {shlex.quote('/mnt/user/' + name)}")
        _ssh_write_file(cfg, cfg_path, _build_share_cfg(spec))
        if apply:
            from urllib.parse import quote_plus
            emcmd_args = (f"shareName={quote_plus(name)}&shareComment={quote_plus(comment)}"
                          f"&shareUseCache={use_cache}&shareCachePool={quote_plus(cache_pool)}"
                          f"&shareAllocator={allocator}&shareSecurity={security}"
                          f"&shareExport={export}&changeShare=Apply")
            code, out, e = _ssh_exec(cfg, f"{_EMCMD} {shlex.quote(emcmd_args)}")
            applied, apply_note = code == 0, (out or e).strip()[:200]
        return ok({"name": name, "cfg": cfg_path, "dir": f"/mnt/user/{name}",
                   "applied_live": applied, "apply_note": apply_note})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_share_delete(name: str, delete_data: bool = False, apply: bool = False,
                         confirm: bool = False, acknowledge: str = "") -> dict:
    """Delete a user share by removing /boot/config/shares/<name>.cfg.
    delete_data=True also removes /mnt/user/<name> and ALL its contents —
    DOUBLE-gated: pass confirm=True AND acknowledge='<name>'. Requires SSH.

    SAFETY: apply defaults to False. apply=True runs emcmd to drop the share
    live, which restarts services / reloads shfs and can corrupt running
    containers with /mnt/user appdata — so it REFUSES when any such container
    is running (see unraid_share_create's SAFETY note and unraid_shfs_risk_check).
    """
    if not confirm:
        return refuse(f"pass confirm=True to delete share '{name}'.")
    if not _valid_name(name):
        return refuse(f"invalid share name '{name}'.")
    if delete_data and acknowledge != name:
        return refuse(f"deleting share data is destructive — also pass acknowledge='{name}'.")
    cfg = load_config()
    try:
        applied, apply_note = False, "config-only (apply=False)"
        if apply:
            risk = _assert_shfs_safe(cfg)
            if risk:
                return risk
            from urllib.parse import quote_plus
            code, out, e = _ssh_exec(cfg, f"{_EMCMD} {shlex.quote(f'shareName={quote_plus(name)}&changeShare=Delete')}")
            applied, apply_note = code == 0, (out or e).strip()[:200]
        _ssh_exec(cfg, f"rm -f {shlex.quote(f'{_SHARES_CFG_DIR}/{name}.cfg')}")
        result = {"name": name, "cfg_removed": True, "applied_live": applied, "apply_note": apply_note}
        if delete_data:
            dc, do, de = _ssh_exec(cfg, f"rm -rf {shlex.quote('/mnt/user/' + name)}", timeout=600)
            result["data_deleted"] = (dc == 0)
        return ok(result)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unraid_shfs_risk_check() -> dict:
    """Report which RUNNING containers bind-mount appdata through the /mnt/user
    FUSE path — these are the containers that an Unraid service/shfs reload
    (triggered by applying a share, and some array operations) can corrupt.
    Read-only. If this lists anything, do NOT apply share changes live; migrate
    those containers' appdata to /mnt/cache/appdata/... first. Requires SSH."""
    cfg = load_config()
    try:
        at_risk = _containers_mounting_user_share(cfg)
        return ok({
            "at_risk_containers": at_risk,
            "safe_to_reload_shfs": not at_risk,
            "guidance": ("No running container mounts appdata via /mnt/user — a share "
                         "apply is safe." if not at_risk else
                         "These containers would lose open files on an shfs reload; move "
                         "their appdata bind mounts from /mnt/user/... to /mnt/cache/... "
                         "(or /mnt/<pool>/...) and recreate them before applying shares live."),
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


if __name__ == "__main__":
    cfg = load_config()
    log(f"starting; config target = {cfg.get('host') or '(unset)'}:{cfg.get('port')}")
    mcp.run()
