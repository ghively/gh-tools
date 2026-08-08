#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""ROMarr MCP server.

Exposes a ROMarr instance (the *arr for games — Cartridge ecosystem by Move
Weight, https://github.com/BlizzHacker/romarr) to Claude through the Model
Context Protocol. Verified live against ROMarr 0.7.0. Two-layer design,
mirroring the sonarr/radarr/romm plugins in this marketplace:

* GENERIC passthrough (`romarr_call` / `romarr_endpoints`) reaching every
  /api/v1 (and legacy /api) endpoint. The catalog is pulled live from the
  server's own `/api/v1/openapi.json` (cached for the process lifetime),
  with a static fallback baked in below in case that fetch ever fails.
* CURATED tools for the common jobs: status/health, library, wanted/missing,
  calendar, queue, history, blocklist, interactive search & release grab,
  collection/DAT set-completion batches, indexers, download clients,
  library backends (RomM/Gaseous/Retrom/folder), connections/notifications,
  metadata lookup, frontend exports, backup/restore, and the ROM Hub plugin
  catalogue.

Auth model (proven live): every request except `/`, `/api/health` and
`/api/v1/login` requires a credential, sent here as the `X-Api-Key` header
(ROMarr also accepts `Authorization: Bearer` or `?apikey=`, but the header
is what this client uses). 401 = missing or wrong key.

ROMarr conventions and quirks discovered live (2026-08-07/08, v0.7.0):
* ROMarr's own `/api/v1/openapi.json` does NOT publish per-operation
  parameter or request-body schemas — only method/path/summary/response
  codes. There is therefore no useful separate "describe one operation"
  tool to build; `romarr_endpoints` (which surfaces the summary text) is
  the full extent of self-description available. Treat summaries as the
  best available hint, verify actual param names live, and fall back to
  `romarr_call` with a hand-built body when guessing wrong.
* Despite the README documenting "the API key is generated on first run
  and shown under Settings > General", the actual shipped 0.7.0 UI's
  General settings page has NO api-key field at all — it only holds the
  Prowlarr/qBittorrent/RomM connection URLs ("Credentials live in the
  environment file, not here — this page never shows or stores a secret").
  The only way to get a stable key for scripts is what the sign-in screen's
  own recovery note says: set `ROMARR_API_KEY` in the container environment
  and restart.
* The Unraid template for this container documents that ROMarr reads most
  of its configuration environment variables ONCE, on first start, then
  saved settings win forever after — EXCEPT `ROMARR_API_KEY` and
  `ROMARR_PASSWORD`, which are explicitly re-read on every start as the
  auth-recovery/pinning mechanism.
* `/api/v1/backup` strips credentials unless called with `?secrets=1` — treat
  that query flag as equivalent to a write for confirmation purposes, since
  it is the one read endpoint capable of exfiltrating every configured
  secret (Prowlarr key, library password, notification tokens, ...).
* POST /api/v1/webhook and /api/v1/webhook/ggrequestz are INBOUND endpoints
  meant to be called BY a front-end (GG Requestz, a request UI) TO ROMarr —
  there is no legitimate reason for this client to call them, so no curated
  tool wraps them; use `romarr_call` if you genuinely need to simulate one.
* POST /api/v1/login and /api/v1/setup are session/first-run only and make
  no sense for an API-key-authenticated client; not wrapped.

Destructive/high-impact writes (release grab, hub plugin install, restore,
connection test [sends real notifications to configured services], import,
request, collection control) are confirm-gated in code (`confirm=True`).
Read-only "test a connection" endpoints (indexer/downloadclient/library
test) are NOT confirm-gated — they verify reachability without persisting
anything.

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[romarr-mcp]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _find_config_file() -> Optional[Path]:
    """Locate config.local.json without hardcoding an absolute path."""
    candidates = []
    if os.environ.get("ROMARR_CONFIG"):
        candidates.append(Path(os.environ["ROMARR_CONFIG"]))
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root_env:
        candidates.append(Path(root_env) / "config.local.json")
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "config.local.json")
    candidates.append(here / "config.local.json")
    candidates.append(Path.cwd() / "config.local.json")
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def load_config() -> dict:
    cfg: dict = {}
    cf = _find_config_file()
    if cf:
        try:
            cfg = json.loads(cf.read_text(encoding="utf-8"))
            log(f"loaded config file: {cf}")
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: could not parse {cf}: {e}")
    env = os.environ
    host = env.get("ROMARR_HOST", cfg.get("host", ""))
    https = _truthy(env.get("ROMARR_HTTPS"), cfg.get("https", False))
    port = int(env.get("ROMARR_PORT", cfg.get("port", 6868)) or 6868)
    return {
        "host": host,
        "port": port,
        "https": https,
        "api_key": env.get("ROMARR_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("ROMARR_VERIFY_SSL"), cfg.get("verify_ssl", True)),
        "timeout": float(env.get("ROMARR_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }


CONFIG = load_config()
MAX_RESULT_CHARS = 60_000


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class RomarrError(Exception):
    pass


class RomarrClient:
    """Thin, thread-safe wrapper that speaks ROMarr's REST conventions."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        self.base = f"{scheme}://{cfg['host']}:{cfg['port']}"
        self._client = httpx.Client(
            base_url=self.base,
            headers={"X-Api-Key": cfg["api_key"], "Accept": "application/json"},
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
        )
        self._lock = threading.Lock()
        self._openapi_cache: Optional[dict] = None

    def request(self, method: str, path: str, params: Optional[dict] = None,
                body: Any = None, raw: bool = False) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        resp = self._client.request(method.upper(), path, params=params, json=body)
        if resp.status_code == 401:
            raise RomarrError("401 Unauthorized — missing or wrong X-Api-Key.")
        if resp.status_code == 403:
            raise RomarrError(f"403 Forbidden on {method} {path}.")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "?")
            raise RomarrError(f"429 Rate limited on {method} {path}. Retry-After: {retry}s")
        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise RomarrError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if raw:
            return resp.text
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text

    def openapi(self) -> dict:
        """Fetch and cache /api/v1/openapi.json for the process lifetime."""
        with self._lock:
            if self._openapi_cache is not None:
                return self._openapi_cache
        try:
            spec = self.request("GET", "/api/v1/openapi.json")
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: live openapi.json unavailable, using static fallback: {e}")
            spec = {}
        with self._lock:
            self._openapi_cache = spec or {}
        return self._openapi_cache

    def live_endpoints(self) -> list:
        spec = self.openapi()
        paths = spec.get("paths") or {}
        if not paths:
            return STATIC_ENDPOINT_CATALOG
        out = []
        for path, ops in paths.items():
            if not isinstance(ops, dict):
                continue
            for method, op in ops.items():
                if method.upper() not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    continue
                out.append({
                    "method": method.upper(),
                    "path": path,
                    "summary": (op or {}).get("summary", ""),
                })
        out.sort(key=lambda r: (r["path"], r["method"]))
        return out


CLIENT = RomarrClient(CONFIG)


# --------------------------------------------------------------------------- #
# Formatting helpers                                                          #
# --------------------------------------------------------------------------- #
def _finish(data: Any) -> Any:
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        return data
    if len(text) <= MAX_RESULT_CHARS:
        return data
    return {
        "_truncated": True,
        "_note": f"Result was {len(text)} chars; showing the first {MAX_RESULT_CHARS}.",
        "preview": text[:MAX_RESULT_CHARS],
    }


def _err(e: Exception) -> dict:
    return {"error": str(e)}


def _parse_json_arg(name: str, value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise RomarrError(f"{name} is not valid JSON: {e}") from e


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


mcp = FastMCP("romarr")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
# Static fallback — the full 53-endpoint surface captured live from
# /api/v1/openapi.json on 2026-08-07 (ROMarr 0.7.0). Used only if the live
# fetch fails; `romarr_endpoints` prefers the live spec.
STATIC_ENDPOINT_CATALOG: list[dict] = [
    {"method": "GET",    "path": "/",                                 "summary": "The web UI."},
    {"method": "GET",    "path": "/api/health",                       "summary": "Liveness. Returns {ok} unauthenticated, the full dependency report with a key."},
    {"method": "POST",   "path": "/api/import",                       "summary": "Import a finished download."},
    {"method": "GET",    "path": "/api/platforms",                    "summary": "Every platform, its media, extensions, size ceiling and how it plays on this install."},
    {"method": "GET",    "path": "/api/queue",                        "summary": "Active downloads (legacy path)."},
    {"method": "POST",   "path": "/api/request",                      "summary": "Request a game."},
    {"method": "GET",    "path": "/api/search",                       "summary": "Search every configured indexer."},
    {"method": "GET",    "path": "/api/v1/backup",                    "summary": "A restorable snapshot. Credentials are stripped unless ?secrets=1."},
    {"method": "GET",    "path": "/api/v1/blocklist",                 "summary": "Releases that will never be taken, with the reason each was blocked."},
    {"method": "GET",    "path": "/api/v1/calendar",                  "summary": "Games released recently or due soon."},
    {"method": "GET",    "path": "/api/v1/collection",                "summary": "Set-acquisition batches in progress, and the DATs available to plan against."},
    {"method": "POST",   "path": "/api/v1/collection/control",        "summary": "pause, resume, retry or cancel a batch."},
    {"method": "GET",    "path": "/api/v1/collection/plan",           "summary": "Compare a DAT against the library: expected, present, missing, and why each dump won its group."},
    {"method": "POST",   "path": "/api/v1/collection/start",          "summary": "Queue every missing title from a plan as a resumable batch."},
    {"method": "POST",   "path": "/api/v1/collection/step",           "summary": "Request the next slice of a batch."},
    {"method": "POST",   "path": "/api/v1/command",                   "summary": "Run a task: search, import or refresh."},
    {"method": "GET",    "path": "/api/v1/config",                    "summary": "Settings, with every credential masked."},
    {"method": "GET",    "path": "/api/v1/connection/schema",         "summary": "The eight notification providers."},
    {"method": "POST",   "path": "/api/v1/connection/test",           "summary": "Send a test notification to every configured connection."},
    {"method": "GET",    "path": "/api/v1/downloadclient",            "summary": "Configured download clients."},
    {"method": "GET",    "path": "/api/v1/downloadclient/schema",     "summary": "The five client types and their fields."},
    {"method": "POST",   "path": "/api/v1/downloadclient/test",       "summary": "Test one client's connection."},
    {"method": "GET",    "path": "/api/v1/export",                    "summary": "Library, wanted or blocklist as JSON or CSV."},
    {"method": "GET",    "path": "/api/v1/frontend/export",           "summary": "LaunchBox XML, ES-DE gamelist.xml or Playnite JSON."},
    {"method": "GET",    "path": "/api/v1/frontend/formats",          "summary": "Available frontend export formats."},
    {"method": "GET",    "path": "/api/v1/game",                      "summary": "The library."},
    {"method": "GET",    "path": "/api/v1/history",                   "summary": "What ROMarr has done."},
    {"method": "GET",    "path": "/api/v1/hub/catalogue",             "summary": "Search the plugin catalogue."},
    {"method": "POST",   "path": "/api/v1/hub/plugin",                "summary": "Install, enable, disable or uninstall a plugin."},
    {"method": "GET",    "path": "/api/v1/hub/plugins",               "summary": "The plugin catalogue, unfiltered."},
    {"method": "POST",   "path": "/api/v1/hub/source/check",          "summary": "Whether a repository URL may be installed from."},
    {"method": "GET",    "path": "/api/v1/hub/status",                "summary": "Whether ROM Hub is installed and reachable."},
    {"method": "POST",   "path": "/api/v1/hub/submit",                "summary": "Validate a catalogue submission and return a link. ROMarr does not post it."},
    {"method": "GET",    "path": "/api/v1/indexer",                   "summary": "Configured indexers, with keys masked."},
    {"method": "GET",    "path": "/api/v1/indexer/schema",            "summary": "The nine indexer types and their fields."},
    {"method": "POST",   "path": "/api/v1/indexer/test",              "summary": "Test one indexer's connection."},
    {"method": "GET",    "path": "/api/v1/library",                   "summary": "Configured library servers."},
    {"method": "GET",    "path": "/api/v1/library/config",            "summary": "One library's stored configuration."},
    {"method": "GET",    "path": "/api/v1/library/schema",            "summary": "Library backend types and their fields."},
    {"method": "POST",   "path": "/api/v1/library/test",              "summary": "Test one library server."},
    {"method": "GET",    "path": "/api/v1/log",                       "summary": "Recent log lines."},
    {"method": "POST",   "path": "/api/v1/login",                     "summary": "Exchange an API key or password for a session cookie."},
    {"method": "GET",    "path": "/api/v1/manualimport",              "summary": "Scan a directory for files ROMarr could adopt."},
    {"method": "GET",    "path": "/api/v1/metadata/lookup",           "summary": "Identify a file. Reports matched_by as 'dat' or 'filename'."},
    {"method": "GET",    "path": "/api/v1/metadata/schema",           "summary": "Metadata providers and their fields."},
    {"method": "GET",    "path": "/api/v1/openapi.json",              "summary": "This document."},
    {"method": "GET",    "path": "/api/v1/queue",                     "summary": "Active downloads."},
    {"method": "GET",    "path": "/api/v1/release",                   "summary": "Interactive search: scored candidates with the reason for each score."},
    {"method": "POST",   "path": "/api/v1/release/grab",              "summary": "Grab a specific release from an interactive search."},
    {"method": "POST",   "path": "/api/v1/restore",                   "summary": "Restore a backup."},
    {"method": "POST",   "path": "/api/v1/setup",                     "summary": "First-run claim: set the admin password on an install that has none."},
    {"method": "GET",    "path": "/api/v1/system/counts",             "summary": "Library and queue sizes."},
    {"method": "GET",    "path": "/api/v1/system/status",             "summary": "Health of every dependency, plus play-route counts."},
    {"method": "GET",    "path": "/api/v1/tag",                       "summary": "Tags, by library item."},
    {"method": "GET",    "path": "/api/v1/wanted/missing",            "summary": "Games wanted but not yet found."},
    {"method": "POST",   "path": "/api/v1/webhook",                   "summary": "Inbound game request from a front-end."},
    {"method": "POST",   "path": "/api/v1/webhook/ggrequestz",        "summary": "Inbound request, GG Requestz shape."},
    {"method": "GET",    "path": "/login",                            "summary": "The sign-in screen."},
    {"method": "GET",    "path": "/metrics",                          "summary": "Prometheus exposition."},
]


@mcp.tool()
def romarr_call(method: str, path: str, params: Optional[dict] = None,
                 body: Optional[dict] = None, confirm: bool = False) -> Any:
    """Call ANY ROMarr REST operation — the generic passthrough that reaches
    the server's entire API surface (~53 endpoints). Use romarr_endpoints to
    find an endpoint first; use a curated romarr_* tool when one exists.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: Endpoint path, e.g. "/api/v1/game" or "/api/health".
        params: Optional query parameters as a JSON object.
        body: Optional request body as a JSON object (POST/PUT).
        confirm: Must be true for any non-GET/HEAD call — this bypasses the
            per-domain confirm-gates the curated tools apply, so treat it as
            the same "only after explicit user approval" contract.

    Returns the parsed JSON response (or text / null for empty responses).
    """
    try:
        if method.upper() not in ("GET", "HEAD") and not confirm:
            return _need_confirm(f"{method.upper()} {path} with body={body}")
        return _finish(CLIENT.request(method, path, params=params, body=body))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_endpoints(search: str = "", method: str = "", curated_only: bool = False,
                      limit: int = 100) -> Any:
    """Search the FULL endpoint catalog — pulled live from
    /api/v1/openapi.json so it's accurate for the deployed ROMarr version.
    The master index for romarr_call. Each operation is annotated with
    whether a curated tool wraps it.

    Note: ROMarr's own OpenAPI document does not publish per-operation
    parameter/body schemas (only method/path/summary/response codes) — the
    summary text here is the fullest description available; verify exact
    param names with a live call before assuming.

    Args:
        search: Case-insensitive substring matched against the path or summary.
        method: Filter by HTTP method (GET/POST/PUT/DELETE).
        curated_only: If true, only return operations that have a curated tool.
        limit: Max operations to return (default 100).
    """
    routes = CLIENT.live_endpoints()
    curated_keys = set(CURATED_TOOLS.keys())
    annotated = []
    for r in routes:
        key = (r["method"].upper(), r["path"])
        annotated.append({**r, "curated": key in curated_keys,
                           "curated_tool": CURATED_TOOLS.get(key)})
    if method:
        annotated = [o for o in annotated if o["method"] == method.upper()]
    if curated_only:
        annotated = [o for o in annotated if o["curated"]]
    if search:
        s = search.lower()
        annotated = [o for o in annotated
                     if s in o["path"].lower() or s in (o.get("summary") or "").lower()]
    n_curated = sum(1 for o in annotated if o["curated"])
    return _finish({
        "matched": len(annotated),
        "matched_curated": n_curated,
        "matched_generic_only": len(annotated) - n_curated,
        "total_live_operations": len(routes),
        "operations": annotated[:limit],
    })


# --------------------------------------------------------------------------- #
# System / health                                                             #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_status() -> Any:
    """Full server health snapshot: dependency health (Prowlarr, RomM/library,
    each library server's readability), platform/queue counts. Call this
    first. Backed by GET /api/v1/system/status."""
    try:
        return CLIENT.request("GET", "/api/v1/system/status")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_health() -> Any:
    """Liveness + full dependency report (same shape as romarr_status but
    served from a different route; GET /api/health)."""
    try:
        return CLIENT.request("GET", "/api/health")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_system_counts() -> Any:
    """Library and queue sizes. GET /api/v1/system/counts."""
    try:
        return CLIENT.request("GET", "/api/v1/system/counts")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_config() -> Any:
    """Full settings, with every credential masked. GET /api/v1/config."""
    try:
        return CLIENT.request("GET", "/api/v1/config")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_logs(limit: int = 200) -> Any:
    """Recent log lines. GET /api/v1/log.

    Args:
        limit: Passed through as a `limit` query param (exact server-side
            support unverified — if ignored, the full default tail returns).
    """
    try:
        return _finish(CLIENT.request("GET", "/api/v1/log", params={"limit": limit}))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_metrics() -> Any:
    """Raw Prometheus exposition text. GET /metrics."""
    try:
        return CLIENT.request("GET", "/metrics", raw=True)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_backup(include_secrets: bool = False, confirm: bool = False) -> Any:
    """A restorable snapshot of ROMarr's configuration. GET /api/v1/backup.

    Args:
        include_secrets: If true, sends ?secrets=1 — this returns EVERY
            configured credential (Prowlarr key, library password,
            notification tokens, ...) in the clear. Treated as a write for
            confirmation purposes: requires confirm=true when combined with
            include_secrets=true. Without it, credentials are stripped.
        confirm: Must be true when include_secrets=true.
    """
    try:
        if include_secrets and not confirm:
            return _need_confirm(
                "fetch a backup WITH every configured credential unmasked "
                "(Prowlarr key, library password, notification tokens, ...)"
            )
        params = {"secrets": 1} if include_secrets else None
        return _finish(CLIENT.request("GET", "/api/v1/backup", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_restore(backup: dict, confirm: bool = False) -> Any:
    """Restore ROMarr's configuration from a backup snapshot. WRITES:
    confirm-gated, destructive — replaces current settings/history.
    POST /api/v1/restore.

    Args:
        backup: The backup object (as returned by romarr_backup).
        confirm: Must be true — overwrites live configuration.
    """
    try:
        if not confirm:
            return _need_confirm("restore ROMarr's configuration from the supplied backup, overwriting current settings")
        return CLIENT.request("POST", "/api/v1/restore", body=backup)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_platforms() -> Any:
    """Every platform: its media, extensions, size ceiling, and how it plays
    on this install (EmulatorJS / Stream / Archive.org / Download-only).
    GET /api/platforms."""
    try:
        return _finish(CLIENT.request("GET", "/api/platforms"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_library(params: Optional[dict] = None) -> Any:
    """The game library. GET /api/v1/game.

    Args:
        params: Optional query filters (exact names unverified — e.g. a
            platform or search filter may exist; pass through as needed).
    """
    try:
        return _finish(CLIENT.request("GET", "/api/v1/game", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_wanted_missing(params: Optional[dict] = None) -> Any:
    """Games requested but not yet found. GET /api/v1/wanted/missing."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/wanted/missing", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_calendar(params: Optional[dict] = None) -> Any:
    """Games released recently or due soon. GET /api/v1/calendar."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/calendar", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_tags() -> Any:
    """Tags, by library item. GET /api/v1/tag."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/tag"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_export(kind: str = "library", fmt: str = "json") -> Any:
    """Library, wanted or blocklist as JSON or CSV. GET /api/v1/export.

    Args:
        kind: What to export — likely one of "library", "wanted", "blocklist"
            (exact accepted values unverified; the tool passes whatever you
            give it straight through as ?type=).
        fmt: "json" or "csv".
    """
    try:
        return CLIENT.request("GET", "/api/v1/export", params={"type": kind, "format": fmt}, raw=(fmt == "csv"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_frontend_formats() -> Any:
    """Available frontend export formats (LaunchBox / ES-DE / Playnite).
    GET /api/v1/frontend/formats."""
    try:
        return CLIENT.request("GET", "/api/v1/frontend/formats")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_frontend_export(fmt: str) -> Any:
    """LaunchBox XML, ES-DE gamelist.xml or Playnite JSON export.
    GET /api/v1/frontend/export.

    Args:
        fmt: One of the values returned by romarr_frontend_formats.
    """
    try:
        return CLIENT.request("GET", "/api/v1/frontend/export", params={"format": fmt}, raw=True)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Acquisition: search, request, interactive search, manual import            #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_search(game: str, platform: str = "") -> Any:
    """Search every configured indexer directly (not the scored interactive
    search — see romarr_release for that). GET /api/search.

    SECURITY NOTE (verified live 2026-08-08): unlike romarr_release, this
    legacy endpoint returns a raw `download_url` for the `best` match and
    every item under `top`/`indexers`, and that URL embeds Prowlarr's API
    key in the clear (`...?apikey=<key>&link=...`) — despite the project's
    own README claiming "download URLs are never returned to a client."
    Prefer romarr_release + romarr_release_grab (which grab by an opaque id
    resolved server-side) for anything beyond a quick look, and never pass
    this tool's raw output to anything untrusted.

    Args:
        game: Search text (query param name confirmed live: `game`, not `q`).
        platform: Optional platform filter.
    """
    try:
        params = {"game": game}
        if platform:
            params["platform"] = platform
        return _finish(CLIENT.request("GET", "/api/search", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_request(title: str, platform: str = "", confirm: bool = False, **extra: Any) -> Any:
    """Request a game: ROMarr searches, scores, grabs the best release and
    imports it. WRITES: confirm-gated (initiates a real download).
    POST /api/request.

    Args:
        title: Game title to request.
        platform: Platform (see romarr_platforms for valid names).
        confirm: Must be true.
        **extra: Any additional fields to merge into the request body.
    """
    try:
        if not confirm:
            return _need_confirm(f"request '{title}'" + (f" for platform {platform}" if platform else ""))
        body = {"title": title, **extra}
        if platform:
            body["platform"] = platform
        return CLIENT.request("POST", "/api/request", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_release(game: str, platform: str = "") -> Any:
    """Interactive search: every scored candidate release with the reasoning
    for its score (seeders, region, size sanity, hack/beta/demo rejection).
    GET /api/v1/release.

    Args:
        game: Game title.
        platform: Platform name.
    """
    try:
        params = {"game": game}
        if platform:
            params["platform"] = platform
        return _finish(CLIENT.request("GET", "/api/v1/release", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_release_grab(release_id: str, confirm: bool = False, **extra: Any) -> Any:
    """Grab a specific release from an interactive search by id (from
    romarr_release). WRITES: confirm-gated (initiates a real download).
    POST /api/v1/release/grab.

    Args:
        release_id: The release's id, as returned by romarr_release.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"grab release {release_id}")
        body = {"id": release_id, **extra}
        return CLIENT.request("POST", "/api/v1/release/grab", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_import(payload: dict, confirm: bool = False) -> Any:
    """Import a finished download. WRITES: confirm-gated (moves/renames
    files into the library). POST /api/import.

    Args:
        payload: Body describing the completed download (exact shape
            unverified — likely a path and/or download-client reference;
            probe with confirm=false first to see the required-field error).
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"import {payload}")
        return CLIENT.request("POST", "/api/import", body=payload)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_manual_import(directory: str = "") -> Any:
    """Scan a directory for files ROMarr could adopt into the library.
    GET /api/v1/manualimport.

    Args:
        directory: Path to scan (exact param name unverified; sent as
            ?directory=).
    """
    try:
        params = {"directory": directory} if directory else None
        return _finish(CLIENT.request("GET", "/api/v1/manualimport", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_command(name: str, confirm: bool = False, **extra: Any) -> Any:
    """Run a background task: search, import or refresh. WRITES:
    confirm-gated. POST /api/v1/command.

    Args:
        name: Task name (exact accepted values unverified — try "Search",
            "Import", "Refresh" per the endpoint summary; check the error
            message if rejected).
        confirm: Must be true.
        **extra: Extra fields merged into the body (e.g. a target id).
    """
    try:
        if not confirm:
            return _need_confirm(f"run command '{name}'" + (f" with {extra}" if extra else ""))
        body = {"name": name, **extra}
        return CLIENT.request("POST", "/api/v1/command", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Queue / history / blocklist                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_queue() -> Any:
    """Active downloads. GET /api/v1/queue."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/queue"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_history(params: Optional[dict] = None) -> Any:
    """What ROMarr has done. GET /api/v1/history."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/history", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_blocklist() -> Any:
    """Releases that will never be taken again, with the reason each was
    blocked. GET /api/v1/blocklist."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/blocklist"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Collections: DAT-based set-completion batches                              #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_collections() -> Any:
    """Set-acquisition batches in progress, and the DATs available to plan
    against. GET /api/v1/collection."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/collection"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_collection_plan(params: dict) -> Any:
    """Compare a No-Intro/Redump DAT against the library: expected, present,
    missing, and why each dump won its group. GET /api/v1/collection/plan.

    Args:
        params: Query identifying the DAT/platform to plan against (exact
            key names unverified — check romarr_collections output first
            for available DAT ids, then try {"dat_id": ...} or
            {"platform": ...}).
    """
    try:
        return _finish(CLIENT.request("GET", "/api/v1/collection/plan", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_collection_start(plan: dict, confirm: bool = False) -> Any:
    """Queue every missing title from a plan as a resumable batch. WRITES:
    confirm-gated (initiates many downloads). POST /api/v1/collection/start.

    Args:
        plan: The plan reference (from romarr_collection_plan) or the
            identifying fields it was built from.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"start a collection batch from plan {plan}")
        return CLIENT.request("POST", "/api/v1/collection/start", body=plan)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_collection_step(batch_id: str, confirm: bool = False) -> Any:
    """Request the next slice of a batch. WRITES: confirm-gated (initiates
    more downloads). POST /api/v1/collection/step.

    Args:
        batch_id: Batch id, from romarr_collections.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"advance collection batch {batch_id} by one step")
        return CLIENT.request("POST", "/api/v1/collection/step", body={"batch_id": batch_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_collection_control(batch_id: str, action: str, confirm: bool = False) -> Any:
    """Pause, resume, retry or cancel a collection batch. WRITES:
    confirm-gated. POST /api/v1/collection/control.

    Args:
        batch_id: Batch id, from romarr_collections.
        action: One of pause, resume, retry, cancel.
        confirm: Must be true.
    """
    try:
        action = action.lower().strip()
        if action not in ("pause", "resume", "retry", "cancel"):
            raise RomarrError("action must be one of pause/resume/retry/cancel")
        if not confirm:
            return _need_confirm(f"{action} collection batch {batch_id}")
        return CLIENT.request("POST", "/api/v1/collection/control",
                               body={"batch_id": batch_id, "action": action})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Indexers                                                                    #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_indexers() -> Any:
    """Configured indexers, with keys masked. GET /api/v1/indexer."""
    try:
        return CLIENT.request("GET", "/api/v1/indexer")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_indexer_schema() -> Any:
    """The nine indexer types and their fields. GET /api/v1/indexer/schema."""
    try:
        return CLIENT.request("GET", "/api/v1/indexer/schema")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_indexer_test(config: dict) -> Any:
    """Test one indexer's connection — safe, does not persist anything.
    POST /api/v1/indexer/test.

    Args:
        config: Indexer config to test (id of a saved indexer, or a full
            config matching romarr_indexer_schema for an unsaved one).
    """
    try:
        return CLIENT.request("POST", "/api/v1/indexer/test", body=config)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Download clients                                                           #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_download_clients() -> Any:
    """Configured download clients. GET /api/v1/downloadclient."""
    try:
        return CLIENT.request("GET", "/api/v1/downloadclient")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_download_client_schema() -> Any:
    """The five download-client types and their fields.
    GET /api/v1/downloadclient/schema."""
    try:
        return CLIENT.request("GET", "/api/v1/downloadclient/schema")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_download_client_test(config: dict) -> Any:
    """Test one download client's connection — safe, does not persist
    anything. POST /api/v1/downloadclient/test.

    Args:
        config: Client config to test (id of a saved client, or a full
            config matching romarr_download_client_schema for an unsaved one).
    """
    try:
        return CLIENT.request("POST", "/api/v1/downloadclient/test", body=config)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library backends (RomM / Gaseous / Retrom / folder)                        #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_libraries() -> Any:
    """Configured library servers (RomM/Gaseous/Retrom/folder), one or more
    with platform-routing rules. GET /api/v1/library."""
    try:
        return CLIENT.request("GET", "/api/v1/library")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_library_config(library_id: str) -> Any:
    """One library's stored configuration. GET /api/v1/library/config.

    Args:
        library_id: Library id, from romarr_libraries.
    """
    try:
        return CLIENT.request("GET", "/api/v1/library/config", params={"id": library_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_library_schema() -> Any:
    """Library backend types (romm/gaseous/retrom/folder) and their fields.
    GET /api/v1/library/schema."""
    try:
        return CLIENT.request("GET", "/api/v1/library/schema")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_library_test(config: dict) -> Any:
    """Test one library server's connection — safe, does not persist
    anything (also flags a path that doesn't exist locally).
    POST /api/v1/library/test.

    Args:
        config: Library config to test (id of a saved library, or a full
            config matching romarr_library_schema for an unsaved one).
    """
    try:
        return CLIENT.request("POST", "/api/v1/library/test", body=config)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Connections (notifications)                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_connection_schema() -> Any:
    """The eight notification provider types and their fields.
    GET /api/v1/connection/schema."""
    try:
        return CLIENT.request("GET", "/api/v1/connection/schema")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_connection_test(confirm: bool = False) -> Any:
    """Send a REAL test notification to every configured connection (pings
    external services — Discord, ntfy, etc). WRITES: confirm-gated.
    POST /api/v1/connection/test.

    Args:
        confirm: Must be true — this has an external side effect.
    """
    try:
        if not confirm:
            return _need_confirm("send a test notification to every configured connection (real external side effect)")
        return CLIENT.request("POST", "/api/v1/connection/test")
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Metadata                                                                    #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_metadata_lookup(params: dict) -> Any:
    """Identify a file (matched_by: 'dat' or 'filename'). GET /api/v1/metadata/lookup.

    Args:
        params: Query identifying the file (exact key names unverified —
            likely {"path": "..."} or {"filename": "..."}).
    """
    try:
        return CLIENT.request("GET", "/api/v1/metadata/lookup", params=params)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_metadata_schema() -> Any:
    """Metadata providers and their fields. GET /api/v1/metadata/schema."""
    try:
        return CLIENT.request("GET", "/api/v1/metadata/schema")
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# ROM Hub (plugin catalogue)                                                 #
# --------------------------------------------------------------------------- #
@mcp.tool()
def romarr_hub_status() -> Any:
    """Whether ROM Hub (the plugin factory, a separate pip install) is
    installed and reachable. GET /api/v1/hub/status."""
    try:
        return CLIENT.request("GET", "/api/v1/hub/status")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_hub_catalogue(search: str = "") -> Any:
    """Search the ROM Hub plugin catalogue. GET /api/v1/hub/catalogue."""
    try:
        params = {"search": search} if search else None
        return _finish(CLIENT.request("GET", "/api/v1/hub/catalogue", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_hub_plugins() -> Any:
    """The full plugin catalogue, unfiltered. GET /api/v1/hub/plugins."""
    try:
        return _finish(CLIENT.request("GET", "/api/v1/hub/plugins"))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_hub_plugin(plugin_id: str, action: str, confirm: bool = False) -> Any:
    """Install, enable, disable or uninstall a ROM Hub plugin. Plugins are
    third-party and sandboxed by the host — only install ones the user
    trusts. WRITES: confirm-gated. POST /api/v1/hub/plugin.

    Args:
        plugin_id: Plugin id, from romarr_hub_catalogue/romarr_hub_plugins.
        action: One of install, enable, disable, uninstall.
        confirm: Must be true.
    """
    try:
        action = action.lower().strip()
        if action not in ("install", "enable", "disable", "uninstall"):
            raise RomarrError("action must be one of install/enable/disable/uninstall")
        if not confirm:
            return _need_confirm(f"{action} ROM Hub plugin '{plugin_id}'")
        return CLIENT.request("POST", "/api/v1/hub/plugin",
                               body={"plugin_id": plugin_id, "action": action})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_hub_source_check(url: str) -> Any:
    """Whether a repository URL may be installed from as a ROM Hub plugin
    source — a check only, nothing is installed. POST /api/v1/hub/source/check.

    Args:
        url: Repository URL to check.
    """
    try:
        return CLIENT.request("POST", "/api/v1/hub/source/check", body={"url": url})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def romarr_hub_submit(payload: dict) -> Any:
    """Validate a ROM Hub catalogue submission and return a link. ROMarr
    itself never posts this anywhere — safe, local validation only.
    POST /api/v1/hub/submit.

    Args:
        payload: Submission fields (exact shape unverified — probe first).
    """
    try:
        return CLIENT.request("POST", "/api/v1/hub/submit", body=payload)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Curated-tool index (for romarr_endpoints annotation)                       #
# --------------------------------------------------------------------------- #
CURATED_TOOLS: dict[tuple[str, str], str] = {
    ("GET", "/api/health"): "romarr_health",
    ("GET", "/api/platforms"): "romarr_platforms",
    ("POST", "/api/import"): "romarr_import",
    ("POST", "/api/request"): "romarr_request",
    ("GET", "/api/search"): "romarr_search",
    ("GET", "/api/v1/backup"): "romarr_backup",
    ("GET", "/api/v1/blocklist"): "romarr_blocklist",
    ("GET", "/api/v1/calendar"): "romarr_calendar",
    ("GET", "/api/v1/collection"): "romarr_collections",
    ("POST", "/api/v1/collection/control"): "romarr_collection_control",
    ("GET", "/api/v1/collection/plan"): "romarr_collection_plan",
    ("POST", "/api/v1/collection/start"): "romarr_collection_start",
    ("POST", "/api/v1/collection/step"): "romarr_collection_step",
    ("POST", "/api/v1/command"): "romarr_command",
    ("GET", "/api/v1/config"): "romarr_config",
    ("GET", "/api/v1/connection/schema"): "romarr_connection_schema",
    ("POST", "/api/v1/connection/test"): "romarr_connection_test",
    ("GET", "/api/v1/downloadclient"): "romarr_download_clients",
    ("GET", "/api/v1/downloadclient/schema"): "romarr_download_client_schema",
    ("POST", "/api/v1/downloadclient/test"): "romarr_download_client_test",
    ("GET", "/api/v1/export"): "romarr_export",
    ("GET", "/api/v1/frontend/export"): "romarr_frontend_export",
    ("GET", "/api/v1/frontend/formats"): "romarr_frontend_formats",
    ("GET", "/api/v1/game"): "romarr_library",
    ("GET", "/api/v1/history"): "romarr_history",
    ("GET", "/api/v1/hub/catalogue"): "romarr_hub_catalogue",
    ("POST", "/api/v1/hub/plugin"): "romarr_hub_plugin",
    ("GET", "/api/v1/hub/plugins"): "romarr_hub_plugins",
    ("POST", "/api/v1/hub/source/check"): "romarr_hub_source_check",
    ("GET", "/api/v1/hub/status"): "romarr_hub_status",
    ("POST", "/api/v1/hub/submit"): "romarr_hub_submit",
    ("GET", "/api/v1/indexer"): "romarr_indexers",
    ("GET", "/api/v1/indexer/schema"): "romarr_indexer_schema",
    ("POST", "/api/v1/indexer/test"): "romarr_indexer_test",
    ("GET", "/api/v1/library"): "romarr_libraries",
    ("GET", "/api/v1/library/config"): "romarr_library_config",
    ("GET", "/api/v1/library/schema"): "romarr_library_schema",
    ("POST", "/api/v1/library/test"): "romarr_library_test",
    ("GET", "/api/v1/log"): "romarr_logs",
    ("GET", "/api/v1/manualimport"): "romarr_manual_import",
    ("GET", "/api/v1/metadata/lookup"): "romarr_metadata_lookup",
    ("GET", "/api/v1/metadata/schema"): "romarr_metadata_schema",
    ("GET", "/api/v1/queue"): "romarr_queue",
    ("GET", "/api/v1/release"): "romarr_release",
    ("POST", "/api/v1/release/grab"): "romarr_release_grab",
    ("POST", "/api/v1/restore"): "romarr_restore",
    ("GET", "/api/v1/system/counts"): "romarr_system_counts",
    ("GET", "/api/v1/system/status"): "romarr_status",
    ("GET", "/api/v1/tag"): "romarr_tags",
    ("GET", "/api/v1/wanted/missing"): "romarr_wanted_missing",
    ("GET", "/metrics"): "romarr_metrics",
}


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("api_key"):
        log("WARNING: no api_key configured — every call will 401. "
            "Fill config.local.json or set ROMARR_API_KEY.")
    mcp.run()


if __name__ == "__main__":
    main()
