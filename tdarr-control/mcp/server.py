#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Tdarr MCP server.

Exposes a Tdarr distributed transcoding server (v2 API) to Claude through the
Model Context Protocol.

**STATUS: DOC-VERIFIED â€” NOT YET LIVE-VERIFIED.**

This server was built from the official Tdarr API documentation at
https://tdarr.readme.io/reference (v2.25.01+). Tdarr is not deployed on this
homelab yet, so every call shape, param name, and response structure is taken
from the docs and has NOT been exercised against a live instance. When Tdarr
deploys, run `mcp/_smoketest.py` to verify, and close the gap with reversible
write proofs (add+remove a plugin, etc.).

Two-layer design, mirroring the radarr/sonarr/sabnzbd plugins:

* GENERIC passthrough (`tdarr_call` / `tdarr_list_endpoints`) reaching every
  documented endpoint. The catalog is static (built from the docs) because
  Tdarr has no /system/routes equivalent â€” but it is COMPLETE for the v2 API.
* CURATED tools for the common jobs: status, library (search, scan, delete,
  filescanner), plugins (search/read/install/create/edit/delete/sync), nodes
  (list/restart/disconnect/logs/worker-limits), backups, /cruddb (full DB
  CRUD on 8 collections), codec-exclude and plugin-include management,
  transcode-user-verdict, and flow templates.

Auth model (per docs): NONE. Tdarr does not traditionally require an API key
â€” the API trusts the LAN, like the *arr stack. The optional `api_key` field
in config supports passing a token via a configurable header for users who
front Tdarr with an auth proxy (nginx-basic-auth, Authentik, etc.).

Tdarr conventions this file encodes (from the docs):
* Base path: /api/v2/<endpoint>. Endpoint names are kebab-case (e.g.
  /api/v2/search-db, /api/v2/get-nodes).
* Almost every endpoint is POST with a JSON body of shape {"data": {...}} â€”
  Tdarr wraps every operation's params in a top-level `data` object. The
  client here attaches that wrapper automatically.
* 4 endpoints are GET: /status, /get-nodes, /download-plugins, /get-server-log.
* /cruddb is the generic DB CRUD endpoint â€” mode insert|getById|getAll|update|
  removeOne|removeAll, collection in {FileJSONDB, LibrarySettingsJSONDB,
  StatisticsJSONDB, NodeJSONDB, SettingsGlobalJSONDB, StagedJSONDB,
  F2FOutputJSONDB, FlowsJSONDB}. READS (getById/getAll) are not confirm-gated;
  every other mode IS.

Destructive writes (delete-file, delete-unhealthy-files, remove-library-files,
set-all-status, kill-worker, kill-file-scanner) are confirm-gated. The most
consequential â€” /cruddb writes and node lifecycle ops (kill-worker,
disconnect-node) â€” are doubly gated (confirm + typed acknowledge token) like
the SABnzbd shutdown pattern.

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[tdarr-mcp]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _find_config_file() -> Optional[Path]:
    candidates = []
    if os.environ.get("TDARR_CONFIG"):
        candidates.append(Path(os.environ["TDARR_CONFIG"]))
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
    host = env.get("TDARR_HOST", cfg.get("host", ""))
    https = _truthy(env.get("TDARR_HTTPS"), cfg.get("https", False))
    port = int(env.get("TDARR_PORT", cfg.get("port", 8265)) or 8265)
    url_base = (env.get("TDARR_URL_BASE", cfg.get("url_base", "")) or "").strip().strip("/")
    return {
        "host": host,
        "port": port,
        "https": https,
        "url_base": url_base,
        "api_key": env.get("TDARR_API_KEY", cfg.get("api_key", "")),
        "api_key_header": env.get("TDARR_API_KEY_HEADER",
                                  cfg.get("api_key_header", "X-API-Key")),
        "verify_ssl": _truthy(env.get("TDARR_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("TDARR_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }


CONFIG = load_config()
MAX_RESULT_CHARS = 60_000


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class TdarrError(Exception):
    pass


class TdarrClient:
    """Thin, thread-safe wrapper that speaks Tdarr's v2 API conventions."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        base = f"{scheme}://{cfg['host']}:{cfg['port']}"
        if cfg.get("url_base"):
            base += "/" + cfg["url_base"].lstrip("/")
        self.base = base
        headers = {"Accept": "application/json"}
        if cfg.get("api_key"):
            headers[cfg.get("api_key_header", "X-API-Key")] = cfg["api_key"]
        self._client = httpx.Client(
            base_url=self.base,
            headers=headers,
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
        )
        self._lock = threading.Lock()

    def request(self, method: str, path: str, data: Any = None,
                raw: bool = False, params: Optional[dict] = None) -> Any:
        """Make a request; Tdarr wraps every POST body in {"data": ...}."""
        if not path.startswith("/"):
            path = "/" + path
        if not path.startswith("/api/v"):
            path = "/api/v2" + ("" if path.startswith("/") else "/") + path
        body = None
        if method.upper() != "GET" and data is not None:
            body = {"data": data}
        resp = self._client.request(method.upper(), path, params=params, json=body)
        if resp.status_code == 401:
            raise TdarrError("401 Unauthorized â€” if you've fronted Tdarr with an "
                             "auth proxy, set api_key in config.local.json.")
        if resp.status_code >= 400:
            detail = resp.text[:400]
            raise TdarrError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if raw:
            return resp.text
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text


CLIENT = TdarrClient(CONFIG)


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
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
        "_note": (f"Result was {len(text)} chars; showing the first "
                  f"{MAX_RESULT_CHARS}. Narrow the query."),
        "preview": text[:MAX_RESULT_CHARS],
    }


def _err(e: Exception) -> dict:
    return {"error": str(e)}


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


def _need_acknowledge(what: str, token: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Re-run with confirm=true AND "
                 f"acknowledge='{token}' (typed) â€” this operation is "
                 "disruptive/irreversible."),
    }


mcp = FastMCP("tdarr")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
# Catalog built from the official Tdarr API docs at tdarr.readme.io/reference
# (v2.25.01+, frozen 2026-07-19). Each entry tagged R(ead) / W(rite).
ENDPOINT_CATALOG: list[dict] = [
    # System / status (mostly reads)
    {"method": "GET",  "path": "/api/v2/status",                    "rw": "R", "summary": "Server status (liveness check)"},
    {"method": "POST", "path": "/api/v2/get-time-now",              "rw": "R", "summary": "Current server time"},
    {"method": "POST", "path": "/api/v2/get-res-stats",             "rw": "R", "summary": "Server resource statistics"},
    {"method": "POST", "path": "/api/v2/performance-stats",         "rw": "R", "summary": "Performance statistics"},
    {"method": "POST", "path": "/api/v2/get-db-statuses",           "rw": "R", "summary": "Status of all databases (libraries)"},
    {"method": "GET",  "path": "/api/v2/get-server-log",            "rw": "R", "summary": "Server log file"},
    {"method": "POST", "path": "/api/v2/get-node-log",              "rw": "R", "summary": "Log file for a given node"},
    {"method": "POST", "path": "/api/v2/get-filescanner-status",    "rw": "R", "summary": "File-scanner status for a database"},
    # Backups
    {"method": "POST", "path": "/api/v2/get-backup-status",         "rw": "R", "summary": "Backup status"},
    {"method": "POST", "path": "/api/v2/get-backups",               "rw": "R", "summary": "List backups"},
    {"method": "POST", "path": "/api/v2/create-backup",             "rw": "W", "summary": "Create a backup"},
    {"method": "POST", "path": "/api/v2/delete-backup",             "rw": "W", "summary": "Delete a backup"},
    {"method": "POST", "path": "/api/v2/reset-backup-status",       "rw": "W", "summary": "Reset backup status"},
    # Library / files
    {"method": "POST", "path": "/api/v2/search-db",                 "rw": "R", "summary": "Search files in a library DB"},
    {"method": "POST", "path": "/api/v2/scan-files",                "rw": "W", "summary": "Scan files (full library scan)"},
    {"method": "POST", "path": "/api/v2/scan-individual-file",      "rw": "W", "summary": "Scan one file"},
    {"method": "POST", "path": "/api/v2/delete-file",               "rw": "W", "summary": "Delete a file (irreversible)"},
    {"method": "POST", "path": "/api/v2/delete-unhealthy-files",    "rw": "W", "summary": "Delete unhealthy files from a table"},
    {"method": "POST", "path": "/api/v2/create-sample",             "rw": "W", "summary": "Create a sample file"},
    {"method": "POST", "path": "/api/v2/verify-folder-exists",      "rw": "R", "summary": "Verify a folder exists"},
    {"method": "POST", "path": "/api/v2/get-subdirectories",        "rw": "R", "summary": "List subdirectories of a folder"},
    {"method": "POST", "path": "/api/v2/remove-library-files",      "rw": "W", "summary": "Remove all files from a library"},
    {"method": "POST", "path": "/api/v2/set-all-status",            "rw": "W", "summary": "Set status of all records in a table"},
    {"method": "POST", "path": "/api/v2/kill-file-scanner",         "rw": "W", "summary": "Kill a running file scanner"},
    {"method": "POST", "path": "/api/v2/delete-cache-file",         "rw": "W", "summary": "Delete a cache file"},
    # DB CRUD (the powerful generic endpoint)
    {"method": "POST", "path": "/api/v2/cruddb",                    "rw": "W", "summary": "Direct DB CRUD on 8 collections"},
    # Nodes
    {"method": "GET",  "path": "/api/v2/get-nodes",                 "rw": "R", "summary": "List nodes"},
    {"method": "POST", "path": "/api/v2/update-node",               "rw": "W", "summary": "Update a node"},
    {"method": "POST", "path": "/api/v2/restart-node",              "rw": "W", "summary": "Restart a node"},
    {"method": "POST", "path": "/api/v2/disconnect-node",           "rw": "W", "summary": "Force-disconnect a node"},
    {"method": "POST", "path": "/api/v2/alter-worker-limit",        "rw": "W", "summary": "Change worker type limits on a node"},
    {"method": "POST", "path": "/api/v2/poll-worker-limits",        "rw": "R", "summary": "Poll worker limits + queue lengths for a node"},
    {"method": "POST", "path": "/api/v2/cancel-worker-item",        "rw": "W", "summary": "Cancel a worker item"},
    {"method": "POST", "path": "/api/v2/kill-worker",               "rw": "W", "summary": "Kill a worker (disruptive)"},
    {"method": "POST", "path": "/api/v2/client/{clientType}",       "rw": "R", "summary": "Get client data by type"},
    # Plugins
    {"method": "POST", "path": "/api/v2/search-plugins",            "rw": "R", "summary": "Search plugins"},
    {"method": "POST", "path": "/api/v2/search-flow-plugins",       "rw": "R", "summary": "Search flow plugins"},
    {"method": "POST", "path": "/api/v2/search-flow-templates",     "rw": "R", "summary": "Search flow templates"},
    {"method": "GET",  "path": "/api/v2/download-plugins",          "rw": "R", "summary": "Download plugin zip"},
    {"method": "POST", "path": "/api/v2/sync-plugins",              "rw": "W", "summary": "Sync plugins"},
    {"method": "POST", "path": "/api/v2/update-plugins",            "rw": "W", "summary": "Update all plugins"},
    {"method": "POST", "path": "/api/v2/read-plugin",               "rw": "R", "summary": "Read a plugin file"},
    {"method": "POST", "path": "/api/v2/read-plugin-text",          "rw": "R", "summary": "Read plugin text"},
    {"method": "POST", "path": "/api/v2/save-plugin-text",          "rw": "W", "summary": "Save plugin text"},
    {"method": "POST", "path": "/api/v2/create-plugin",             "rw": "W", "summary": "Create a new plugin"},
    {"method": "POST", "path": "/api/v2/delete-plugin",             "rw": "W", "summary": "Delete a plugin"},
    {"method": "POST", "path": "/api/v2/verify-plugin",             "rw": "R", "summary": "Verify a plugin"},
    {"method": "POST", "path": "/api/v2/copy-community-to-local",   "rw": "W", "summary": "Install a community plugin locally"},
    {"method": "POST", "path": "/api/v2/run-help-command",          "rw": "R", "summary": "Run an FFmpeg/HandBrake help command"},
    # Library settings (per-library config â€” codec excludes, plugin includes, etc.)
    {"method": "POST", "path": "/api/v2/toggle-folder-watch",       "rw": "W", "summary": "Toggle folder watch"},
    {"method": "POST", "path": "/api/v2/toggle-schedule",           "rw": "W", "summary": "Toggle schedule (file/folder/library)"},
    {"method": "POST", "path": "/api/v2/update-schedule-block",     "rw": "W", "summary": "Update a schedule block"},
    {"method": "POST", "path": "/api/v2/add-plugin-include",        "rw": "W", "summary": "Add a plugin include"},
    {"method": "POST", "path": "/api/v2/update-plugin-include",     "rw": "W", "summary": "Update a plugin include"},
    {"method": "POST", "path": "/api/v2/remove-plugin-include",     "rw": "W", "summary": "Remove a plugin include"},
    {"method": "POST", "path": "/api/v2/add-video-codec-exclude",   "rw": "W", "summary": "Add a video codec exclude"},
    {"method": "POST", "path": "/api/v2/update-video-codec-exclude","rw": "W", "summary": "Update a video codec exclude"},
    {"method": "POST", "path": "/api/v2/remove-video-codec-exclude","rw": "W", "summary": "Remove a video codec exclude"},
    {"method": "POST", "path": "/api/v2/add-audio-codec-exclude",   "rw": "W", "summary": "Add an audio codec exclude"},
    {"method": "POST", "path": "/api/v2/update-audio-codec-exclude","rw": "W", "summary": "Update an audio codec exclude"},
    {"method": "POST", "path": "/api/v2/remove-audio-codec-exclude","rw": "W", "summary": "Remove an audio codec exclude"},
    # Reports / jobs
    {"method": "POST", "path": "/api/v2/list-footprintId-reports",  "rw": "R", "summary": "List reports for a footprint ID"},
    {"method": "POST", "path": "/api/v2/read-job-file",             "rw": "R", "summary": "Read a job file"},
    {"method": "POST", "path": "/api/v2/transcode-user-verdict",    "rw": "W", "summary": "Transcode a user verdict"},
    {"method": "POST", "path": "/api/v2/item-proc-end",             "rw": "W", "summary": "Signal item processing complete (internal)"},
]


@mcp.tool()
def tdarr_call(method: str, path: str, data: str = "") -> Any:
    """Call ANY Tdarr REST operation â€” the generic passthrough that reaches
    the server's entire documented v2 API (~67 endpoints). Use
    tdarr_list_endpoints to find an endpoint first.

    Args:
        method: HTTP method (mostly POST; GET for /status, /get-nodes,
            /download-plugins, /get-server-log).
        path: Endpoint path. Either "/api/v2/search-db" or just "search-db"
            (auto-prefixed with /api/v2).
        data: Optional JSON to send as the request body. Tdarr wraps it in
            {"data": <your_data>} automatically â€” pass just the inner object.

    Returns the parsed JSON response.
    WRITES: only call POST after the user has approved the action.
    """
    try:
        body = None
        if data and data.strip():
            try:
                body = json.loads(data)
            except json.JSONDecodeError as e:
                raise TdarrError(f"data is not valid JSON: {e}") from e
        return _finish(CLIENT.request(method, path, data=body))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_list_endpoints(search: str = "", method: str = "", rw: str = "",
                          limit: int = 100) -> Any:
    """Search the static endpoint catalog â€” built from the official Tdarr API
    docs (tdarr.readme.io/reference, v2.25.01+, frozen 2026-07-19). The master
    index for tdarr_call.

    Args:
        search: Case-insensitive substring matched against path + summary.
        method: Filter by HTTP method (GET/POST).
        rw: Filter by 'R' (read) or 'W' (write).
        limit: Max endpoints to return.
    """
    ops = ENDPOINT_CATALOG
    if method:
        ops = [o for o in ops if o["method"].upper() == method.upper()]
    if rw:
        ops = [o for o in ops if o["rw"].upper() == rw.upper()]
    if search:
        s = search.lower()
        ops = [o for o in ops if s in o["path"].lower() or s in o["summary"].lower()]
    return _finish({"matched": len(ops), "endpoints": ops[:limit]})


# --------------------------------------------------------------------------- #
# System / status                                                             #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_status() -> Any:
    """Server liveness check + identity. The cheapest Tdarr call.
    **DOC-VERIFIED** â€” GET /api/v2/status."""
    try:
        return CLIENT.request("GET", "/api/v2/status")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_full_status() -> Any:
    """Composite health snapshot: status + nodes + DB statuses + performance
    stats + resource stats. Best "what's going on" overview.
    **DOC-VERIFIED** â€” composed from GET /status + /get-nodes + /get-db-statuses
    + /performance-stats + /get-res-stats."""
    try:
        status = CLIENT.request("GET", "/api/v2/status")
        nodes = CLIENT.request("GET", "/api/v2/get-nodes")
        db_statuses = CLIENT.request("POST", "/api/v2/get-db-statuses", data={})
        try:
            perf = CLIENT.request("POST", "/api/v2/performance-stats", data={})
        except Exception:
            perf = None
        try:
            res = CLIENT.request("POST", "/api/v2/get-res-stats", data={})
        except Exception:
            res = None
        return {
            "status": status,
            "nodes": nodes,
            "db_statuses": db_statuses,
            "performance_stats": perf,
            "res_stats": res,
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_nodes() -> Any:
    """List all connected nodes (workers). READ-ONLY.
    **DOC-VERIFIED** â€” GET /api/v2/get-nodes."""
    try:
        return CLIENT.request("GET", "/api/v2/get-nodes")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_db_statuses() -> Any:
    """Status of all databases (libraries). READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-db-statuses."""
    try:
        return CLIENT.request("POST", "/api/v2/get-db-statuses", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_performance_stats() -> Any:
    """Throughput / performance statistics. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/performance-stats."""
    try:
        return CLIENT.request("POST", "/api/v2/performance-stats", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_res_stats() -> Any:
    """Server resource statistics (CPU, memory, etc.). READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-res-stats."""
    try:
        return CLIENT.request("POST", "/api/v2/get-res-stats", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_server_log() -> Any:
    """Fetch the server log file (raw text). May be large â€” consider tailing.
    **DOC-VERIFIED** â€” GET /api/v2/get-server-log."""
    try:
        text = CLIENT.request("GET", "/api/v2/get-server-log", raw=True) or ""
        # Return the tail by default to avoid flooding the model
        if len(text) > MAX_RESULT_CHARS:
            return {"_truncated": True, "_note": "Log truncated to last N chars",
                    "tail": text[-MAX_RESULT_CHARS:]}
        return text
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_node_log(node_id: str) -> Any:
    """Fetch the log file for a given node. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-node-log with {"nodeID": "..."}."""
    try:
        if not node_id:
            raise TdarrError("node_id is required")
        text = CLIENT.request("POST", "/api/v2/get-node-log",
                              data={"nodeID": node_id}, raw=True) or ""
        if len(text) > MAX_RESULT_CHARS:
            return {"_truncated": True, "_note": "Log truncated to last N chars",
                    "tail": text[-MAX_RESULT_CHARS:]}
        return text
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library / files                                                             #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_search_db(string: str = "", less_than_gb: int = 100000,
                     greater_than_gb: int = 0, limit: int = 100) -> Any:
    """Search files in the library DB. READ-ONLY.
    **LIVE-VERIFIED** â€” POST /api/v2/search-db (Tdarr 2.84.01).

    Args:
        string: Substring to match against file paths (pass "" for all).
        less_than_gb: Only files smaller than N GB. Tdarr requires this field â€”
            default 100000 effectively means "no upper limit".
        greater_than_gb: Only files larger than N GB. Tdarr requires this field â€”
            default 0 means "no lower limit".
        limit: Cap results returned (client-side).
    """
    try:
        body = {
            "string": string,
            "lessThanGB": int(less_than_gb),
            "greaterThanGB": int(greater_than_gb),
        }
        data = CLIENT.request("POST", "/api/v2/search-db", data=body)
        if isinstance(data, list):
            return _finish(data[:limit])
        return _finish(data)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_scan_files(scan_config: str, confirm: bool = False) -> Any:
    """Trigger a scan. WRITES: confirm-gated. Active work (disk + CPU).
    **DOC-VERIFIED** â€” POST /api/v2/scan-files with {"scanConfig": {...}}.

    Args:
        scan_config: JSON object string â€” the scanConfig (library ID, array of
            paths, etc.). Exact shape TDB on first live use.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"scan files with config {scan_config[:120]}")
        try:
            cfg_obj = json.loads(scan_config) if isinstance(scan_config, str) else scan_config
        except json.JSONDecodeError as e:
            raise TdarrError(f"scan_config is not valid JSON: {e}") from e
        return CLIENT.request("POST", "/api/v2/scan-files", data={"scanConfig": cfg_obj})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_scan_individual_file(file_path: str, db_id: str = "",
                                confirm: bool = False) -> Any:
    """Scan one file. WRITES: confirm-gated (active work).
    **DOC-VERIFIED** â€” POST /api/v2/scan-individual-file."""
    try:
        if not file_path:
            raise TdarrError("file_path is required")
        if not confirm:
            return _need_confirm(f"scan file {file_path}")
        body: dict = {"filePath": file_path}
        if db_id: body["dbID"] = db_id
        return CLIENT.request("POST", "/api/v2/scan-individual-file", data=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_filescanner_status(db_name: str) -> Any:
    """File-scanner status for a given database (library). READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-filescanner-status."""
    try:
        if not db_name:
            raise TdarrError("db_name is required (e.g. 'library_1')")
        return CLIENT.request("POST", "/api/v2/get-filescanner-status", data={"dbName": db_name})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_verify_folder_exists(folder_path: str) -> Any:
    """Verify whether a folder exists on the server. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/verify-folder-exists."""
    try:
        if not folder_path:
            raise TdarrError("folder_path is required")
        return CLIENT.request("POST", "/api/v2/verify-folder-exists", data={"folderPath": folder_path})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_get_subdirectories(folder_path: str) -> Any:
    """List subdirectories of a folder on the server. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-subdirectories."""
    try:
        if not folder_path:
            raise TdarrError("folder_path is required")
        return CLIENT.request("POST", "/api/v2/get-subdirectories", data={"folderPath": folder_path})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_delete_file(file_path: str, db_id: str = "",
                       confirm: bool = False) -> Any:
    """Delete a file from disk. WRITES: confirm-gated. IRREVERSIBLE.
    **DOC-VERIFIED** â€” POST /api/v2/delete-file."""
    try:
        if not file_path:
            raise TdarrError("file_path is required")
        if not confirm:
            return _need_confirm(f"PERMANENTLY DELETE file {file_path}")
        body: dict = {"filePath": file_path}
        if db_id: body["dbID"] = db_id
        return CLIENT.request("POST", "/api/v2/delete-file", data=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_delete_unhealthy_files(table: str, confirm: bool = False) -> Any:
    """Delete unhealthy files from a table. WRITES: confirm-gated. IRREVERSIBLE.
    **DOC-VERIFIED** â€” POST /api/v2/delete-unhealthy-files."""
    try:
        if not table:
            raise TdarrError("table is required")
        if not confirm:
            return _need_confirm(f"delete unhealthy files in table {table}")
        return CLIENT.request("POST", "/api/v2/delete-unhealthy-files", data={"table": table})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_kill_file_scanner(db_name: str, confirm: bool = False,
                             acknowledge: str = "") -> Any:
    """Kill a running file scanner. DOUBLY GATED â€” confirm + acknowledge='kill'.
    **DOC-VERIFIED** â€” POST /api/v2/kill-file-scanner."""
    try:
        if not db_name:
            raise TdarrError("db_name is required")
        if not confirm or acknowledge != "kill":
            return _need_acknowledge(f"kill the file scanner for {db_name}", "kill")
        return CLIENT.request("POST", "/api/v2/kill-file-scanner", data={"dbName": db_name})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Plugins                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_search_plugins(string: str = "", plugin_type: str = "standard") -> Any:
    """Search installed + community plugins. READ-ONLY.
    **LIVE-VERIFIED** â€” POST /api/v2/search-plugins (Tdarr 2.84.01).

    Args:
        string: Substring to match (pass "" for all). Tdarr requires this field.
        plugin_type: 'standard' (default) or 'flow'. Tdarr requires this field.
    """
    try:
        return _finish(CLIENT.request("POST", "/api/v2/search-plugins",
                                       data={"string": string, "pluginType": plugin_type}))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_search_flow_plugins(string: str = "", plugin_type: str = "flow") -> Any:
    """Search flow plugins (Tdarr 2.x flow system). READ-ONLY.
    **LIVE-VERIFIED** â€” POST /api/v2/search-flow-plugins (Tdarr 2.84.01).

    Args:
        string: Substring to match (pass "" for all). Tdarr requires this field.
        plugin_type: 'flow' (default) or 'standard'.
    """
    try:
        return _finish(CLIENT.request("POST", "/api/v2/search-flow-plugins",
                                       data={"string": string, "pluginType": plugin_type}))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_search_flow_templates(string: str = "") -> Any:
    """Search flow templates. READ-ONLY.
    **LIVE-VERIFIED** â€” POST /api/v2/search-flow-templates (Tdarr 2.84.01).

    Args:
        string: Substring to match (pass "" for all). Tdarr requires this field.
    """
    try:
        return _finish(CLIENT.request("POST", "/api/v2/search-flow-templates",
                                       data={"string": string}))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_read_plugin(plugin_id: str) -> Any:
    """Read a plugin file (metadata + source). READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/read-plugin."""
    try:
        if not plugin_id:
            raise TdarrError("plugin_id is required")
        return CLIENT.request("POST", "/api/v2/read-plugin", data={"id": plugin_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_install_plugin(plugin_id: str, confirm: bool = False) -> Any:
    """Install a community plugin locally. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/copy-community-to-local."""
    try:
        if not plugin_id:
            raise TdarrError("plugin_id is required")
        if not confirm:
            return _need_confirm(f"install community plugin {plugin_id}")
        return CLIENT.request("POST", "/api/v2/copy-community-to-local", data={"id": plugin_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_delete_plugin(plugin_id: str, confirm: bool = False) -> Any:
    """Delete an installed plugin. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/delete-plugin."""
    try:
        if not plugin_id:
            raise TdarrError("plugin_id is required")
        if not confirm:
            return _need_confirm(f"delete plugin {plugin_id}")
        return CLIENT.request("POST", "/api/v2/delete-plugin", data={"id": plugin_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_sync_plugins(confirm: bool = False) -> Any:
    """Sync plugins (re-fetch all installed from upstream). WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/sync-plugins."""
    try:
        if not confirm:
            return _need_confirm("sync all plugins from upstream")
        return CLIENT.request("POST", "/api/v2/sync-plugins", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_update_plugins(confirm: bool = False) -> Any:
    """Update all plugins. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/update-plugins."""
    try:
        if not confirm:
            return _need_confirm("update all plugins")
        return CLIENT.request("POST", "/api/v2/update-plugins", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_verify_plugin(plugin_id: str) -> Any:
    """Verify a plugin (lint check). READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/verify-plugin."""
    try:
        if not plugin_id:
            raise TdarrError("plugin_id is required")
        return CLIENT.request("POST", "/api/v2/verify-plugin", data={"id": plugin_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Nodes                                                                       #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_restart_node(node_id: str, confirm: bool = False) -> Any:
    """Restart a node. WRITES: confirm-gated. Interrupts active work.
    **DOC-VERIFIED** â€” POST /api/v2/restart-node."""
    try:
        if not node_id:
            raise TdarrError("node_id is required")
        if not confirm:
            return _need_confirm(f"restart node {node_id} (interrupts active transcodes)")
        return CLIENT.request("POST", "/api/v2/restart-node", data={"nodeID": node_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_disconnect_node(node_id: str, confirm: bool = False,
                           acknowledge: str = "") -> Any:
    """Force-disconnect a node. DOUBLY GATED â€” interrupts active work.
    **DOC-VERIFIED** â€” POST /api/v2/disconnect-node."""
    try:
        if not node_id:
            raise TdarrError("node_id is required")
        if not confirm or acknowledge != "disconnect":
            return _need_acknowledge(f"force-disconnect node {node_id}", "disconnect")
        return CLIENT.request("POST", "/api/v2/disconnect-node", data={"nodeID": node_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_alter_worker_limit(node_id: str, worker_type: str, limit: int,
                              confirm: bool = False) -> Any:
    """Change a worker type limit on a node. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/alter-worker-limit.

    Args:
        node_id: Node id.
        worker_type: One of the 4 worker types (live-confirmed from
            NodeJSONDB.workerLimits on Tdarr 2.84.01):
            'transcodecpu', 'transcodegpu', 'healthcheckcpu', 'healthcheckgpu'.
        limit: New limit (integer).
        confirm: Must be true.
    """
    try:
        if not node_id or not worker_type:
            raise TdarrError("node_id and worker_type are required")
        if not confirm:
            return _need_confirm(f"set node {node_id} {worker_type} worker limit to {limit}")
        body = {"nodeID": node_id, "workerType": worker_type, "limit": int(limit)}
        return CLIENT.request("POST", "/api/v2/alter-worker-limit", data=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_poll_worker_limits(node_id: str) -> Any:
    """Poll worker limits + queue lengths for a node. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/poll-worker-limits."""
    try:
        if not node_id:
            raise TdarrError("node_id is required")
        return CLIENT.request("POST", "/api/v2/poll-worker-limits", data={"nodeID": node_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_cancel_worker_item(node_id: str, worker_type: str,
                              confirm: bool = False) -> Any:
    """Cancel a worker item. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/cancel-worker-item."""
    try:
        if not node_id or not worker_type:
            raise TdarrError("node_id and worker_type are required")
        if not confirm:
            return _need_confirm(f"cancel {worker_type} worker item on {node_id}")
        return CLIENT.request("POST", "/api/v2/cancel-worker-item",
                              data={"nodeID": node_id, "workerType": worker_type})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_kill_worker(node_id: str, worker_type: str,
                       confirm: bool = False, acknowledge: str = "") -> Any:
    """Kill a worker. DOUBLY GATED â€” interrupts active transcode. Confirm + acknowledge='kill'.
    **DOC-VERIFIED** â€” POST /api/v2/kill-worker."""
    try:
        if not node_id or not worker_type:
            raise TdarrError("node_id and worker_type are required")
        if not confirm or acknowledge != "kill":
            return _need_acknowledge(
                f"kill {worker_type} worker on node {node_id} (aborts active transcode)",
                "kill",
            )
        return CLIENT.request("POST", "/api/v2/kill-worker",
                              data={"nodeID": node_id, "workerType": worker_type})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Backups                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_backup_status() -> Any:
    """Get backup status. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-backup-status."""
    try:
        return CLIENT.request("POST", "/api/v2/get-backup-status", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_backups() -> Any:
    """List backups. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/get-backups."""
    try:
        return CLIENT.request("POST", "/api/v2/get-backups", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_create_backup(confirm: bool = False) -> Any:
    """Create a backup now. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/create-backup."""
    try:
        if not confirm:
            return _need_confirm("create a Tdarr backup now")
        return CLIENT.request("POST", "/api/v2/create-backup", data={})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_delete_backup(name: str, confirm: bool = False) -> Any:
    """Delete a backup file. WRITES: confirm-gated.
    **LIVE-VERIFIED** â€” POST /api/v2/delete-backup with {"name": <file>} (Tdarr 2.84.01)."""
    try:
        if not name:
            raise TdarrError("name is required (the backup file name from tdarr_backups)")
        if not confirm:
            return _need_confirm(f"delete backup {name}")
        return CLIENT.request("POST", "/api/v2/delete-backup", data={"name": name})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# /cruddb â€” the powerful generic DB endpoint                                   #
# --------------------------------------------------------------------------- #
TDARR_COLLECTIONS = {
    "FileJSONDB":              "All scanned files (one row per file)",
    "LibrarySettingsJSONDB":   "Per-library settings (codec excludes, plugin includes, etc.)",
    "StatisticsJSONDB":        "Per-node + per-plugin transcode statistics",
    "NodeJSONDB":              "Registered nodes",
    "SettingsGlobalJSONDB":    "Global server settings",
    "StagedJSONDB":            "Staged files awaiting processing",
    "F2FOutputJSONDB":         "F2F (file-to-file) transcode outputs",
    "FlowsJSONDB":             "Flow definitions (Tdarr 2.x flow system)",
}


@mcp.tool()
def tdarr_db(mode: str, collection: str, doc_id: str = "",
              obj: str = "", confirm: bool = False) -> Any:
    """Direct DB CRUD via Tdarr's /cruddb endpoint â€” access any of the 8
    internal collections. READS (getById/getAll) are NOT confirm-gated; every
    other mode IS. **DOC-VERIFIED** â€” POST /api/v2/cruddb.

    This is the escape hatch for everything not covered by a curated tool â€”
    you can read or mutate any internal state. Use with care: a `removeAll`
    on FileJSONDB wipes the file index; `update` with wrong keys can corrupt
    a record. Always getAll first to see the shape.

    Args:
        mode: One of insert, getById, getAll, update, removeOne, removeAll.
        collection: One of: FileJSONDB, LibrarySettingsJSONDB, StatisticsJSONDB,
            NodeJSONDB, SettingsGlobalJSONDB, StagedJSONDB, F2FOutputJSONDB,
            FlowsJSONDB.
        doc_id: Required for insert/getById/update/removeOne â€” the document id
            (often the file path for FileJSONDB).
        obj: JSON object string. Required for insert (full doc) and update
            (keys to change).
        confirm: Required for every mode except getById/getAll.
    """
    try:
        m = (mode or "").strip().lower()
        if m not in ("insert", "getbyid", "getall", "update", "removeone", "removeall"):
            raise TdarrError(f"mode must be one of insert/getById/getAll/update/"
                             f"removeOne/removeAll; got {mode!r}")
        if collection not in TDARR_COLLECTIONS:
            raise TdarrError(f"collection must be one of {list(TDARR_COLLECTIONS)}; "
                             f"got {collection!r}")
        is_read = m in ("getbyid", "getall")
        if not is_read and not confirm:
            return _need_confirm(f"{m} on {collection} (docID={doc_id!r}, obj={obj[:120]})")
        body: dict = {"mode": mode, "collection": collection}
        if doc_id: body["docID"] = doc_id
        if m in ("insert", "update"):
            if not obj:
                raise TdarrError(f"obj is required for {m}")
            try:
                body["obj"] = json.loads(obj) if isinstance(obj, str) else obj
            except json.JSONDecodeError as e:
                raise TdarrError(f"obj is not valid JSON: {e}") from e
        return _finish(CLIENT.request("POST", "/api/v2/cruddb", data=body))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_collections() -> Any:
    """List the 8 internal /cruddb collections with descriptions. READ-ONLY.
    Use this before tdarr_db to know what you're accessing."""
    return TDARR_COLLECTIONS


# --------------------------------------------------------------------------- #
# Library settings â€” codec excludes & plugin includes                         #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_toggle_folder_watch(library_id: str, confirm: bool = False) -> Any:
    """Toggle folder-watch on a library. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/toggle-folder-watch."""
    try:
        if not library_id:
            raise TdarrError("library_id is required")
        if not confirm:
            return _need_confirm(f"toggle folder watch on library {library_id}")
        return CLIENT.request("POST", "/api/v2/toggle-folder-watch",
                              data={"libraryID": library_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_toggle_schedule(library_id: str, schedule_type: str = "",
                           confirm: bool = False) -> Any:
    """Toggle a schedule (file/folder/library). WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/toggle-schedule.

    Args:
        library_id: Library id.
        schedule_type: Optional type filter (exact values TBD on first live use).
        confirm: Must be true.
    """
    try:
        if not library_id:
            raise TdarrError("library_id is required")
        if not confirm:
            return _need_confirm(f"toggle schedule on library {library_id}")
        body: dict = {"libraryID": library_id}
        if schedule_type: body["type"] = schedule_type
        return CLIENT.request("POST", "/api/v2/toggle-schedule", data=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_add_video_codec_exclude(library_id: str, codec: str,
                                   confirm: bool = False) -> Any:
    """Add a video codec exclude for a library. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/add-video-codec-exclude."""
    try:
        if not library_id or not codec:
            raise TdarrError("library_id and codec are required")
        if not confirm:
            return _need_confirm(f"add video codec exclude '{codec}' to library {library_id}")
        return CLIENT.request("POST", "/api/v2/add-video-codec-exclude",
                              data={"libraryID": library_id, "videoCodec": codec})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_add_audio_codec_exclude(library_id: str, codec: str,
                                   confirm: bool = False) -> Any:
    """Add an audio codec exclude for a library. WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/add-audio-codec-exclude."""
    try:
        if not library_id or not codec:
            raise TdarrError("library_id and codec are required")
        if not confirm:
            return _need_confirm(f"add audio codec exclude '{codec}' to library {library_id}")
        return CLIENT.request("POST", "/api/v2/add-audio-codec-exclude",
                              data={"libraryID": library_id, "audioCodec": codec})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_run_help_command(mode: str, text: str = "") -> Any:
    """Run an FFmpeg or HandBrake help command (returns the CLI output).
    READ-ONLY. Useful for "what codecs does this build support?"
    **LIVE-VERIFIED** â€” POST /api/v2/run-help-command with {"mode": ..., "text": ...}
    (Tdarr 2.84.01). Tdarr 2.84 ships ffmpeg 7.1.4-Jellyfin + HandBrake.

    Args:
        mode: 'ffmpeg' or 'handbrake'.
        text: The CLI args/help string to pass, e.g. '-version' or '-decoders'.
    """
    try:
        if not mode:
            raise TdarrError("mode is required ('ffmpeg' or 'handbrake')")
        return CLIENT.request("POST", "/api/v2/run-help-command",
                              data={"mode": mode, "text": text})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Reports                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def tdarr_list_footprint_reports(footprint_id: str) -> Any:
    """List all reports for a given footprint ID. READ-ONLY.
    **DOC-VERIFIED** â€” POST /api/v2/list-footprintId-reports."""
    try:
        if not footprint_id:
            raise TdarrError("footprint_id is required")
        return CLIENT.request("POST", "/api/v2/list-footprintId-reports",
                              data={"footprintId": footprint_id})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def tdarr_transcode_user_verdict(file_path: str, db_id: str = "",
                                  verdict: str = "transcode",
                                  confirm: bool = False) -> Any:
    """Mark a file's user verdict (e.g. 'transcode this now'). WRITES: confirm-gated.
    **DOC-VERIFIED** â€” POST /api/v2/transcode-user-verdict.

    Args:
        file_path: The file path.
        db_id: Optional DB id.
        verdict: Verdict string (exact values TBD on first live use; 'transcode'
            and 'ignore' are typical).
        confirm: Must be true.
    """
    try:
        if not file_path:
            raise TdarrError("file_path is required")
        if not confirm:
            return _need_confirm(f"set verdict '{verdict}' on {file_path}")
        body: dict = {"filePath": file_path, "verdict": verdict}
        if db_id: body["dbID"] = db_id
        return CLIENT.request("POST", "/api/v2/transcode-user-verdict", data=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("host"):
        log("WARNING: no host configured â€” every call will fail. "
            "Fill config.local.json or set TDARR_HOST.")
    mcp.run()


if __name__ == "__main__":
    main()
