#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "python-socketio[client]>=5.11",
# ]
# ///
"""RomM (rommapp) MCP server.

Exposes a RomM ROM-library server to Claude through the Model Context
Protocol. Tested against RomM 5.x. The design is two-layered, mirroring
the Synology/UniFi/GitLab/Emby plugins in this repo:

* A GENERIC passthrough (`romm_call` / `romm_endpoints` / `romm_schema`)
  that can reach *any* of the server's REST operations. The endpoint
  catalog is discovered live from the server's own OpenAPI document
  (`/openapi.json`, 189 operations across 27 tags on 5.x), so it is
  always accurate for the connected version.
* CURATED tools for the common jobs (status, platforms, ROM search &
  metadata editing, collections, users & permissions, saves/states,
  firmware, tasks, config, activity, music, feeds, exports, uploads and
  downloads) so day-to-day tasks are one call with correct params.

Auth model (proven live against 5.x):
* Every REST request carries `Authorization: Bearer rmm_...` (a RomM API
  key created in the web UI under Settings). 403 = missing/invalid key.
* Library SCANS are NOT reachable over REST: `POST /api/tasks/run/
  scan_library` returns 400 "cannot be run" by design. The web UI fires
  scans over Socket.IO (event "scan" on path /ws/socket.io), and the
  socket resolves identity from the `romm_session` COOKIE minted by
  `POST /api/login` (HTTP Basic) — an API key cannot mint that session.
  So `romm_scan` needs the optional `username`/`password` config fields;
  without them every REST feature still works, only scan triggering is
  unavailable.

RomM conventions this file encodes (verified live):
* FastAPI: validation errors are 422 {"detail": [...]}, app errors are
  4xx {"detail": "message"}.
* Most writes are JSON, but ROM/collection edits are multipart/form-data
  and user edits / smart collections are x-www-form-urlencoded.
* Chunked ROM uploads use custom x-upload-* headers.
* ROM objects carry huge raw metadata blobs (raw_igdb_metadata etc.);
  list/detail tools trim them unless verbose=True.

Destructive/disruptive writes are confirm-gated in code (`confirm=True`
required). `romm_rom_delete(delete_from_fs=...)` and platform deletion
remove data permanently — treat with care.

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[romm-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("ROMM_CONFIG"):
        candidates.append(Path(os.environ["ROMM_CONFIG"]))
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root_env:
        candidates.append(Path(root_env) / "config.local.json")
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "config.local.json")
    candidates.append(here / "config.local.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def _load_config() -> dict:
    cfg: dict = {}
    path = _find_config_file()
    if path:
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
            log(f"config loaded from {path}")
        except Exception as e:
            log(f"failed to parse {path}: {e}")
    env_map = {
        "host": "ROMM_HOST",
        "port": "ROMM_PORT",
        "https": "ROMM_HTTPS",
        "api_key": "ROMM_API_KEY",
        "username": "ROMM_USERNAME",
        "password": "ROMM_PASSWORD",
        "verify_ssl": "ROMM_VERIFY_SSL",
        "timeout": "ROMM_TIMEOUT",
    }
    for key, env in env_map.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    cfg.setdefault("host", "127.0.0.1")
    cfg.setdefault("port", 8095)
    cfg.setdefault("https", False)
    cfg.setdefault("verify_ssl", True)
    cfg.setdefault("timeout", 60)
    return cfg


CFG = _load_config()
SCHEME = "https" if _truthy(CFG.get("https")) else "http"
BASE_URL = f"{SCHEME}://{CFG['host']}:{int(CFG['port'])}"
API_KEY = str(CFG.get("api_key", "") or "")
USERNAME = str(CFG.get("username", "") or "")
PASSWORD = str(CFG.get("password", "") or "")
TIMEOUT = float(CFG.get("timeout", 60))
VERIFY_SSL = _truthy(CFG.get("verify_ssl"), True)

if not API_KEY:
    log("WARNING: no api_key configured — every call will fail with 403")

_client_lock = threading.Lock()
_client: Optional[httpx.Client] = None


def client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=TIMEOUT,
                verify=VERIFY_SSL,
                follow_redirects=True,
            )
        return _client


class RommError(Exception):
    pass


def _req(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Any = None,
    form: Optional[dict] = None,
    files: Optional[dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[dict] = None,
    expect_json: bool = True,
) -> Any:
    """Make one authenticated request; return parsed JSON (or text)."""
    if not path.startswith("/"):
        path = "/" + path
    # Drop None-valued params so optional tool args don't become "None" strings
    if params:
        params = {k: v for k, v in params.items() if v is not None}
    try:
        r = client().request(
            method.upper(),
            path,
            params=params or None,
            json=json_body,
            data=form,
            files=files,
            content=content,
            headers=headers,
        )
    except httpx.HTTPError as e:
        raise RommError(f"HTTP error calling {method} {path}: {e}") from e
    if r.status_code >= 400:
        detail: Any = r.text[:2000]
        try:
            detail = r.json().get("detail", detail)
        except Exception:
            pass
        raise RommError(f"{r.status_code} on {method.upper()} {path}: {detail}")
    if r.status_code == 204 or not r.content:
        return {"ok": True, "status": r.status_code}
    if expect_json:
        try:
            return r.json()
        except Exception:
            return r.text
    return r


def _dump(data: Any, limit: int = 60000) -> str:
    out = json.dumps(data, indent=1, ensure_ascii=False, default=str)
    if len(out) > limit:
        out = out[:limit] + f"\n... [truncated at {limit} chars — narrow the query or use limit/offset]"
    return out


# Keys that bloat ROM payloads with per-provider metadata dumps.
_HEAVY_ROM_KEYS = (
    "raw_igdb_metadata", "raw_moby_metadata", "raw_ss_metadata",
    "raw_launchbox_metadata", "raw_hasheous_metadata", "raw_flashpoint_metadata",
    "raw_hltb_metadata", "raw_manual_metadata", "igdb_metadata", "moby_metadata",
    "ss_metadata", "launchbox_metadata", "hasheous_metadata", "flashpoint_metadata",
    "hltb_metadata", "gamelist_metadata", "merged_screenshots",
)


def _slim_rom(rom: dict, keep_files: bool = False) -> dict:
    slim = {k: v for k, v in rom.items() if k not in _HEAVY_ROM_KEYS}
    meta = rom.get("metadatum") or {}
    if isinstance(meta, dict):
        slim["metadatum"] = {
            k: v for k, v in meta.items()
            if k in ("genres", "franchises", "companies", "game_modes",
                     "age_ratings", "first_release_date", "average_rating")
        }
    if not keep_files and isinstance(slim.get("files"), list) and len(slim["files"]) > 5:
        slim["files"] = slim["files"][:5] + [f"... {len(rom['files']) - 5} more (use romm_rom_files)"]
    return slim


def _as_multipart(form: dict) -> dict:
    """Encode plain form fields as multipart/form-data parts for httpx.

    RomM's ROM/collection edit endpoints declare multipart (they accept an
    optional artwork file), so urlencoded bodies are rejected when a file
    part is expected; (None, value) tuples force multipart encoding.
    """
    if not form:
        form = {"_": ""}
    return {k: (None, str(v)) for k, v in form.items()}


def _upload_file_with_header(path: str, file_path: str) -> Any:
    """POST a local file's raw bytes with the x-upload-filename header — the
    convention RomM's manual/soundtrack/rom-screenshot attach endpoints use,
    distinct from the chunked ROM upload and the multipart firmware upload.
    """
    p = Path(file_path)
    if not p.is_file():
        raise RommError(f"file not found: {file_path}")
    with open(p, "rb") as f:
        data = f.read()
    return _req("POST", path, headers={"x-upload-filename": p.name}, content=data)


def _require_confirm(confirm: bool, what: str) -> None:
    if not confirm:
        raise RommError(
            f"CONFIRMATION REQUIRED: this would {what}. "
            "Re-run with confirm=True after the user has explicitly approved it."
        )


mcp = FastMCP("romm")


def _tool_error(fn):
    """Wrap tool functions so RommError surfaces as a clean message."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except RommError as e:
            return f"ERROR: {e}"
    return wrapper


# --------------------------------------------------------------------------- #
# Generic passthrough layer                                                   #
# --------------------------------------------------------------------------- #
_openapi_lock = threading.Lock()
_openapi_cache: Optional[dict] = None


def _openapi() -> dict:
    global _openapi_cache
    with _openapi_lock:
        if _openapi_cache is None:
            r = client().get("/openapi.json")
            r.raise_for_status()
            _openapi_cache = r.json()
        return _openapi_cache


def _op_catalog() -> list[dict]:
    spec = _openapi()
    ops = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "delete", "patch", "head"):
                continue
            ops.append({
                "method": method.upper(),
                "path": path,
                "tags": op.get("tags", []),
                "summary": op.get("summary") or op.get("operationId", ""),
            })
    return ops


@mcp.tool()
@_tool_error
def romm_call(
    method: str,
    path: str,
    query_params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    form_body: Optional[dict] = None,
    file_path: str = "",
    file_field: str = "file",
    extra_headers: Optional[dict] = None,
    multipart: bool = False,
    confirm: bool = False,
) -> str:
    """Generic passthrough: call ANY RomM REST endpoint.

    This reaches all ~189 operations of the connected server — use
    romm_endpoints to find one and romm_schema for its exact parameters.

    Args:
        method: HTTP method (GET/POST/PUT/DELETE/HEAD).
        path: endpoint path, e.g. "/api/roms/42" (leading /api included).
        query_params: query string parameters.
        json_body: JSON request body (Content-Type: application/json).
        form_body: form-encoded body. Sent as multipart/form-data when
            file_path is set or multipart=True, x-www-form-urlencoded
            otherwise.
        file_path: local file to attach as a multipart upload.
        file_field: multipart field name for the file (default "file").
        extra_headers: additional request headers (e.g. x-upload-*).
        multipart: force multipart/form-data encoding for form_body even
            without a file (endpoints like PUT /api/roms/{id} declare
            multipart for text-only edits).
        confirm: required True for any non-GET/HEAD method.
    """
    m = method.upper()
    if m not in ("GET", "HEAD"):
        _require_confirm(confirm, f"execute a write ({m} {path}) against RomM")
    files = None
    form = form_body
    fh = None
    try:
        if file_path:
            p = Path(file_path)
            if not p.is_file():
                raise RommError(f"file not found: {file_path}")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            fh = open(p, "rb")
            files = {file_field: (p.name, fh, ctype)}
        elif multipart and form_body:
            files = _as_multipart(form_body)
            form = None
        result = _req(
            m, path,
            params=query_params,
            json_body=json_body,
            form=form,
            files=files,
            headers=extra_headers,
            expect_json=False,
        )
    finally:
        if fh:
            fh.close()
    if isinstance(result, dict):
        return _dump(result)
    r: httpx.Response = result
    ctype = r.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            return _dump(r.json())
        except Exception:
            pass
    if any(t in ctype for t in ("text/", "xml", "json")):
        body = r.text
        return body[:60000] + ("\n...[truncated]" if len(body) > 60000 else "")
    return f"[binary response: {ctype}, {len(r.content)} bytes — use romm_download_rom or romm_call with a download-capable path]"


@mcp.tool()
@_tool_error
def romm_endpoints(search: str = "", tag: str = "", method: str = "") -> str:
    """Search the live-discovered catalog of all RomM REST operations.

    Args:
        search: case-insensitive substring matched against path + summary.
        tag: filter by API tag (roms, platforms, collections, users, saves,
            states, screenshots, firmware, tasks, config, activity, music,
            feeds, sync, devices, permissions, client-tokens, search, stats,
            system, auth, device-auth, export, logs, netplay, play-sessions,
            upload).
        method: filter by HTTP method.
    """
    ops = _op_catalog()
    s, t, m = search.lower(), tag.lower(), method.upper()
    rows = []
    for op in ops:
        if s and s not in op["path"].lower() and s not in op["summary"].lower():
            continue
        if t and t not in [x.lower() for x in op["tags"]]:
            continue
        if m and op["method"] != m:
            continue
        rows.append(f"{op['method']:6s} {op['path']:55s} [{','.join(op['tags'])}] {op['summary']}")
    if not rows:
        return "no matching operations"
    return f"{len(rows)} operations:\n" + "\n".join(rows)


@mcp.tool()
@_tool_error
def romm_schema(path: str, method: str = "get") -> str:
    """Show full OpenAPI detail (params + request/response schema) for one endpoint.

    Args:
        path: exact path as shown by romm_endpoints, e.g. "/api/roms/{id}".
        method: HTTP method of the operation.
    """
    spec = _openapi()
    node = spec.get("paths", {}).get(path)
    if not node:
        return f"path {path} not in spec — check romm_endpoints for the exact form"
    op = node.get(method.lower())
    if not op:
        return f"{method} not defined for {path}; available: {list(node.keys())}"

    def resolve(s: Any, depth: int = 0) -> Any:
        if depth > 6:
            return s
        if isinstance(s, dict):
            if "$ref" in s:
                target = spec
                for part in s["$ref"].split("/")[1:]:
                    target = target[part]
                return resolve(target, depth + 1)
            return {k: resolve(v, depth + 1) for k, v in s.items()}
        if isinstance(s, list):
            return [resolve(x, depth + 1) for x in s]
        return s

    out = {
        "summary": op.get("summary"),
        "parameters": resolve(op.get("parameters", [])),
        "requestBody": resolve(op.get("requestBody", {})),
    }
    return _dump(out)


# --------------------------------------------------------------------------- #
# System / status / tasks / config                                            #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_status() -> str:
    """Server heartbeat + library stats: version, enabled metadata sources,
    filesystem platforms, scheduled-task config, and ROM/save counts."""
    hb = _req("GET", "/api/heartbeat")
    stats = _req("GET", "/api/stats")
    me = _req("GET", "/api/users/me")
    out = {
        "version": hb.get("SYSTEM", {}).get("VERSION"),
        "base_url": BASE_URL,
        "authenticated_as": {"username": me.get("username"), "role": me.get("role")},
        "stats": stats,
        "metadata_sources": {
            k: v for k, v in hb.get("METADATA_SOURCES", {}).items() if v
        },
        "filesystem_platform_dirs": hb.get("FILESYSTEM", {}).get("FS_PLATFORMS"),
        "scheduled_tasks": hb.get("TASKS"),
        "oidc_enabled": hb.get("OIDC", {}).get("ENABLED"),
        "scan_trigger_available": bool(USERNAME and PASSWORD),
    }
    return _dump(out)


@mcp.tool()
@_tool_error
def romm_stats(include_platform_stats: bool = False) -> str:
    """Library statistics (platform/ROM/save/state/screenshot counts, total size).

    Args:
        include_platform_stats: include per-platform breakdown.
    """
    return _dump(_req("GET", "/api/stats",
                      params={"include_platform_stats": include_platform_stats}))


@mcp.tool()
@_tool_error
def romm_logs(limit: int = 100) -> str:
    """Fetch recent backend log lines (admin only).

    Args:
        limit: number of recent lines to return.
    """
    return _dump(_req("GET", "/api/logs", params={"limit": limit}))


@mcp.tool()
@_tool_error
def romm_tasks() -> str:
    """List all tasks (scheduled/manual/watcher) with enabled state and cron,
    plus any currently-running task status."""
    tasks = _req("GET", "/api/tasks")
    status = _req("GET", "/api/tasks/status")
    return _dump({"tasks": tasks, "running": status})


@mcp.tool()
@_tool_error
def romm_task_run(task_name: str, kwargs_json: str = "", confirm: bool = False) -> str:
    """Run a manual task. Available (5.x): cleanup_orphaned_resources,
    cleanup_missing_roms, sync_folder_scan, recompute_save_content_hashes,
    update_launchbox_metadata, update_switch_titledb, convert_images_to_webp.
    NOTE: scan_library is NOT runnable here — use romm_scan (Socket.IO).

    Args:
        task_name: task identifier from romm_tasks.
        kwargs_json: optional JSON object of task kwargs.
        confirm: must be True — tasks mutate the library/database.
    """
    _require_confirm(confirm, f"run task '{task_name}'")
    body = json.loads(kwargs_json) if kwargs_json else {}
    return _dump(_req("POST", f"/api/tasks/run/{task_name}", json_body=body))


@mcp.tool()
@_tool_error
def romm_config() -> str:
    """Show the server's config.yml view: exclusions, platform bindings/versions,
    and whether the config file is mounted & writable."""
    return _dump(_req("GET", "/api/config"))


@mcp.tool()
@_tool_error
def romm_config_exclude(
    action: str,
    exclusion_type: str,
    exclusion_value: str,
    confirm: bool = False,
) -> str:
    """Add or remove a filesystem-scan exclusion.

    Args:
        action: "add" or "remove".
        exclusion_type: one of EXCLUDED_PLATFORMS, EXCLUDED_SINGLE_EXT,
            EXCLUDED_SINGLE_FILES, EXCLUDED_MULTI_FILES, EXCLUDED_MULTI_PARTS_EXT,
            EXCLUDED_MULTI_PARTS_FILES.
        exclusion_value: the folder/extension/filename value.
        confirm: must be True — edits the server's config.yml.
    """
    _require_confirm(confirm, f"{action} scan exclusion {exclusion_type}={exclusion_value}")
    if action == "add":
        return _dump(_req("POST", "/api/config/exclude",
                          json_body={"exclusion_type": exclusion_type,
                                     "exclusion_value": exclusion_value}))
    if action == "remove":
        return _dump(_req("DELETE", f"/api/config/exclude/{exclusion_type}/{exclusion_value}"))
    raise RommError("action must be 'add' or 'remove'")


@mcp.tool()
@_tool_error
def romm_config_platform_binding(
    action: str,
    fs_slug: str,
    slug: str = "",
    kind: str = "platforms",
    confirm: bool = False,
) -> str:
    """Bind a filesystem folder name to a platform (or version) in config.yml.

    Args:
        action: "add" or "remove".
        fs_slug: the folder name in the library (e.g. "roms/gc").
        slug: the canonical platform slug to bind it to (required for add).
        kind: "platforms" (PLATFORMS_BINDING) or "versions" (PLATFORMS_VERSIONS).
        confirm: must be True — edits the server's config.yml.
    """
    _require_confirm(confirm, f"{action} {kind} binding {fs_slug} -> {slug}")
    if kind not in ("platforms", "versions"):
        raise RommError("kind must be 'platforms' or 'versions'")
    if action == "add":
        if not slug:
            raise RommError("slug required for add")
        return _dump(_req("POST", f"/api/config/system/{kind}",
                          json_body={"fs_slug": fs_slug, "slug": slug}))
    if action == "remove":
        return _dump(_req("DELETE", f"/api/config/system/{kind}/{fs_slug}"))
    raise RommError("action must be 'add' or 'remove'")


# --------------------------------------------------------------------------- #
# Platforms                                                                   #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_platforms() -> str:
    """List all platforms in the library with ROM counts and metadata ids."""
    plats = _req("GET", "/api/platforms")
    slim = [
        {k: p.get(k) for k in ("id", "name", "slug", "fs_slug", "rom_count",
                               "category", "generation", "custom_name")}
        for p in plats
    ]
    return _dump({"count": len(plats), "platforms": slim})


@mcp.tool()
@_tool_error
def romm_platform(platform_id: int) -> str:
    """Full detail for one platform (all metadata-provider ids, firmware, aspect ratios).

    Args:
        platform_id: RomM platform id.
    """
    return _dump(_req("GET", f"/api/platforms/{platform_id}"))


@mcp.tool()
@_tool_error
def romm_platform_create(fs_slug: str, confirm: bool = False) -> str:
    """Create a platform entry from a filesystem slug (folder name).

    Args:
        fs_slug: folder name, e.g. "snes", "gba", "ps2" — see
            romm_supported_platforms for canonical slugs.
        confirm: must be True — creates a library entity.
    """
    _require_confirm(confirm, f"create platform '{fs_slug}'")
    return _dump(_req("POST", "/api/platforms", json_body={"fs_slug": fs_slug}))


@mcp.tool()
@_tool_error
def romm_platform_update(platform_id: int, fields_json: str, confirm: bool = False) -> str:
    """Update platform fields (e.g. custom_name, aspect ratio, metadata ids).

    Args:
        platform_id: RomM platform id.
        fields_json: JSON object of fields to set, e.g.
            '{"custom_name": "Super Nintendo"}'. See romm_schema
            ("/api/platforms/{id}", "put") for accepted fields.
        confirm: must be True — modifies the platform.
    """
    _require_confirm(confirm, f"update platform {platform_id}")
    return _dump(_req("PUT", f"/api/platforms/{platform_id}",
                      json_body=json.loads(fields_json)))


@mcp.tool()
@_tool_error
def romm_platform_delete(platform_id: int, confirm: bool = False) -> str:
    """Delete a platform AND all its ROM database entries (files stay on disk).

    Args:
        platform_id: RomM platform id.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"DELETE platform {platform_id} and all its ROM DB entries")
    return _dump(_req("DELETE", f"/api/platforms/{platform_id}"))


@mcp.tool()
@_tool_error
def romm_supported_platforms(search: str = "") -> str:
    """List the ~459 platforms RomM can identify (canonical slugs + provider ids).

    Args:
        search: case-insensitive filter on name/slug (recommended — full list is big).
    """
    plats = _req("GET", "/api/platforms/supported")
    s = search.lower()
    rows = [
        f"{p['slug']:30s} {p['name']}"
        for p in plats
        if not s or s in p["slug"].lower() or s in p["name"].lower()
    ]
    if not rows:
        return "no matches"
    body = "\n".join(rows[:200])
    if len(rows) > 200:
        body += f"\n... {len(rows) - 200} more — narrow the search"
    return f"{len(rows)} matches:\n{body}"


# --------------------------------------------------------------------------- #
# ROMs                                                                        #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_roms(
    search_term: str = "",
    platform_id: Optional[int] = None,
    collection_id: Optional[int] = None,
    matched: Optional[bool] = None,
    favorite: Optional[bool] = None,
    duplicate: Optional[bool] = None,
    missing: Optional[bool] = None,
    verified: Optional[bool] = None,
    playable: Optional[bool] = None,
    has_saves: Optional[bool] = None,
    has_states: Optional[bool] = None,
    genres: str = "",
    franchises: str = "",
    companies: str = "",
    regions: str = "",
    languages: str = "",
    statuses: str = "",
    tags: str = "",
    order_by: str = "created_at",
    order_dir: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Search/browse the ROM library with filters (the main library query).

    Args:
        search_term: free-text name search.
        platform_id: restrict to one platform.
        collection_id: restrict to a manual collection.
        matched: True = only metadata-matched, False = only unmatched.
        favorite: filter favorites.
        duplicate: filter duplicates.
        missing: filter ROMs whose file is missing from the filesystem.
        verified: filter hash-verified dumps.
        playable: filter browser-playable (EmulatorJS) ROMs.
        has_saves / has_states: filter ROMs with save files / save states.
        genres/franchises/companies/regions/languages/statuses/tags:
            comma-separated value filters.
        order_by: fs_size_bytes | created_at | first_release_date | name ...
            — default created_at. WARNING (verified live on 5.x):
            order_by="name" with no platform_id returns an EMPTY result
            (total:0) — a server-side bug in the global name-sort query.
            It works fine once platform_id is set, or with any other
            order_by. If you need name order across the whole library,
            sort the returned rows client-side instead.
        order_dir: asc | desc.
        limit/offset: pagination (limit max 500 server-side).
    """
    params: dict[str, Any] = {
        "search_term": search_term or None,
        "platform_ids": platform_id,
        "collection_id": collection_id,
        "matched": matched, "favorite": favorite, "duplicate": duplicate,
        "missing": missing, "verified": verified, "playable": playable,
        "has_saves": has_saves, "has_states": has_states,
        "order_by": order_by, "order_dir": order_dir,
        "limit": limit, "offset": offset,
    }
    for name, csv in (("genres", genres), ("franchises", franchises),
                      ("companies", companies), ("regions", regions),
                      ("languages", languages), ("statuses", statuses),
                      ("tags", tags)):
        if csv:
            params[name] = [x.strip() for x in csv.split(",")]
    data = _req("GET", "/api/roms", params=params)
    items = data.get("items", data if isinstance(data, list) else [])
    slim = [
        {k: r.get(k) for k in ("id", "name", "fs_name", "platform_id",
                               "platform_display_name", "fs_size_bytes",
                               "regions", "revision", "tags", "is_identified",
                               "missing_from_fs")}
        for r in items
    ]
    return _dump({"total": data.get("total") if isinstance(data, dict) else len(slim),
                  "offset": offset, "returned": len(slim), "roms": slim})


@mcp.tool()
@_tool_error
def romm_rom(rom_id: int, verbose: bool = False) -> str:
    """Full detail for one ROM: metadata, files, user props, siblings.

    Args:
        rom_id: RomM rom id.
        verbose: include the raw per-provider metadata blobs (large).
    """
    rom = _req("GET", f"/api/roms/{rom_id}")
    return _dump(rom if verbose else _slim_rom(rom))


@mcp.tool()
@_tool_error
def romm_rom_files(rom_id: int) -> str:
    """List all files of a ROM (multi-file/folder ROMs, hashes, sizes).

    Note: NOT /api/roms/{id}/files — that endpoint takes a *file* id (and
    500s on 5.x); the reliable file list is embedded in the ROM detail.

    Args:
        rom_id: RomM rom id.
    """
    rom = _req("GET", f"/api/roms/{rom_id}")
    return _dump({"rom_id": rom_id, "fs_name": rom.get("fs_name"),
                  "files": rom.get("files", [])})


@mcp.tool()
@_tool_error
def romm_rom_by_hash(crc_hash: str = "", md5_hash: str = "", sha1_hash: str = "") -> str:
    """Look up a ROM by file hash (any one of CRC/MD5/SHA1).

    Args:
        crc_hash: CRC32 hex.
        md5_hash: MD5 hex.
        sha1_hash: SHA1 hex.
    """
    params = {"crc_hash": crc_hash or None, "md5_hash": md5_hash or None,
              "sha1_hash": sha1_hash or None}
    return _dump(_slim_rom(_req("GET", "/api/roms/by-hash", params=params)))


@mcp.tool()
@_tool_error
def romm_rom_update(
    rom_id: int,
    name: str = "",
    summary: str = "",
    url_cover: str = "",
    url_manual: str = "",
    fs_name: str = "",
    provider_ids_json: str = "",
    unmatch_metadata: bool = False,
    remove_cover: bool = False,
    confirm: bool = False,
) -> str:
    """Edit a ROM's metadata (name, summary, cover art, provider match).

    Args:
        rom_id: RomM rom id.
        name: new display name.
        summary: new description text.
        url_cover: URL of new cover art to fetch.
        url_manual: URL of a game manual to fetch.
        fs_name: RENAMES the file on disk — use with care.
        provider_ids_json: JSON of provider ids to (re)match, e.g.
            '{"igdb_id": 1074}' — triggers a metadata refresh from that source.
        unmatch_metadata: strip all matched metadata from this ROM.
        remove_cover: remove current cover art.
        confirm: must be True — modifies the ROM (fs_name renames on disk).
    """
    _require_confirm(confirm, f"update ROM {rom_id}"
                     + (" INCLUDING RENAMING ITS FILE ON DISK" if fs_name else ""))
    form: dict[str, Any] = {}
    for key, val in (("name", name), ("summary", summary), ("url_cover", url_cover),
                     ("url_manual", url_manual), ("fs_name", fs_name)):
        if val:
            form[key] = val
    if provider_ids_json:
        form.update(json.loads(provider_ids_json))
    params = {"unmatch_metadata": unmatch_metadata or None,
              "remove_cover": remove_cover or None}
    # multipart/form-data endpoint: send plain fields through `files` tuples
    return _dump(_slim_rom(_req("PUT", f"/api/roms/{rom_id}", params=params,
                                files=_as_multipart(form))))


@mcp.tool()
@_tool_error
def romm_rom_delete(rom_ids: list[int], delete_from_fs: bool = False, confirm: bool = False) -> str:
    """Delete ROMs from the database, optionally including their files on disk.

    Args:
        rom_ids: list of RomM rom ids.
        delete_from_fs: ALSO permanently delete the underlying files.
        confirm: must be True — destructive (irreversible with delete_from_fs).
    """
    _require_confirm(
        confirm,
        f"delete {len(rom_ids)} ROM(s) from the database"
        + (" AND PERMANENTLY DELETE THEIR FILES FROM DISK" if delete_from_fs else ""),
    )
    body = {"roms": rom_ids,
            "delete_from_fs": rom_ids if delete_from_fs else []}
    return _dump(_req("POST", "/api/roms/delete", json_body=body))


@mcp.tool()
@_tool_error
def romm_rom_props(
    rom_id: int,
    status: str = "",
    rating: Optional[int] = None,
    difficulty: Optional[int] = None,
    completion: Optional[int] = None,
    backlogged: Optional[bool] = None,
    now_playing: Optional[bool] = None,
    hidden: Optional[bool] = None,
    update_last_played: bool = False,
) -> str:
    """Set per-user play-tracking properties on a ROM (safe, reversible).

    Args:
        rom_id: RomM rom id.
        status: incomplete | finished | completed_100 | retired | never_playing.
        rating: 0-10 personal rating.
        difficulty: 0-10 difficulty rating.
        completion: 0-100 percent complete.
        backlogged / now_playing / hidden: flags.
        update_last_played: stamp last-played to now.
    """
    body: dict[str, Any] = {}
    if status:
        body["status"] = status
    for key, val in (("rating", rating), ("difficulty", difficulty),
                     ("completion", completion), ("backlogged", backlogged),
                     ("now_playing", now_playing), ("hidden", hidden)):
        if val is not None:
            body[key] = val
    return _dump(_req("PUT", f"/api/roms/{rom_id}/props",
                      params={"update_last_played": update_last_played or None},
                      json_body=body))


@mcp.tool()
@_tool_error
def romm_rom_notes(
    rom_id: int,
    action: str = "list",
    note_id: Optional[int] = None,
    title: str = "",
    content: str = "",
    is_public: bool = False,
    confirm: bool = False,
) -> str:
    """List/add/update/delete notes on a ROM.

    Args:
        rom_id: RomM rom id.
        action: list | add | update | delete.
        note_id: required for update/delete.
        title: note title (add/update).
        content: note markdown content (add/update).
        is_public: make the note visible to other users.
        confirm: required True for delete.
    """
    if action == "list":
        # GET /api/roms/{id}/notes 500s on 5.x; the ROM detail reliably
        # embeds the same data as all_user_notes — fall back to it.
        try:
            return _dump(_req("GET", f"/api/roms/{rom_id}/notes"))
        except RommError:
            rom = _req("GET", f"/api/roms/{rom_id}")
            return _dump({"rom_id": rom_id,
                          "notes": rom.get("all_user_notes", [])})
    if action == "add":
        return _dump(_req("POST", f"/api/roms/{rom_id}/notes",
                          json_body={"title": title, "content": content,
                                     "is_public": is_public}))
    if action == "update":
        if note_id is None:
            raise RommError("note_id required for update")
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if content:
            body["content"] = content
        return _dump(_req("PUT", f"/api/roms/{rom_id}/notes/{note_id}", json_body=body))
    if action == "delete":
        if note_id is None:
            raise RommError("note_id required for delete")
        _require_confirm(confirm, f"delete note {note_id} on ROM {rom_id}")
        return _dump(_req("DELETE", f"/api/roms/{rom_id}/notes/{note_id}"))
    raise RommError("action must be list|add|update|delete")


@mcp.tool()
@_tool_error
def romm_rom_manuals(
    rom_id: int,
    action: str,
    file_path: str = "",
    file_id: Optional[int] = None,
    confirm: bool = False,
) -> str:
    """Manage a ROM's manual PDF(s). There's no separate list endpoint —
    see what's attached via romm_rom(rom_id, verbose=True).

    Args:
        rom_id: RomM rom id.
        action: add (first manual) | add_file (extra page/file alongside an
            existing one) | redownload (re-fetch from the metadata
            provider) | delete_all (remove every manual) | delete_file
            (remove one file_id).
        file_path: local PDF path, required for add/add_file.
        file_id: required for delete_file.
        confirm: required for redownload/delete_all/delete_file (all
            replace or remove files).
    """
    if action == "add":
        if not file_path:
            raise RommError("file_path required for add")
        return _dump(_upload_file_with_header(f"/api/roms/{rom_id}/manuals", file_path))
    if action == "add_file":
        if not file_path:
            raise RommError("file_path required for add_file")
        return _dump(_upload_file_with_header(f"/api/roms/{rom_id}/manuals/files", file_path))
    if action == "redownload":
        _require_confirm(confirm, f"redownload the manual for ROM {rom_id}")
        return _dump(_req("POST", f"/api/roms/{rom_id}/manuals/redownload"))
    if action == "delete_all":
        _require_confirm(confirm, f"delete ALL manuals for ROM {rom_id}")
        return _dump(_req("DELETE", f"/api/roms/{rom_id}/manuals"))
    if action == "delete_file":
        if file_id is None:
            raise RommError("file_id required for delete_file")
        _require_confirm(confirm, f"delete manual file {file_id} on ROM {rom_id}")
        return _dump(_req("DELETE", f"/api/roms/{rom_id}/manuals/files/{file_id}"))
    raise RommError("action must be add|add_file|redownload|delete_all|delete_file")


@mcp.tool()
@_tool_error
def romm_rom_soundtracks(
    rom_id: int,
    action: str = "metadata",
    file_path: str = "",
    file_id: Optional[int] = None,
    confirm: bool = False,
) -> str:
    """Manage a ROM's bundled soundtrack files — distinct from the
    library-wide romm_music browser, which covers standalone music albums.

    Args:
        rom_id: RomM rom id.
        action: metadata (available soundtrack info from providers) | add
            (upload a local audio file) | delete (remove file_id).
        file_path: local audio file path, required for add.
        file_id: required for delete.
        confirm: required True for delete.
    """
    if action == "metadata":
        return _dump(_req("GET", f"/api/roms/{rom_id}/soundtracks/metadata"))
    if action == "add":
        if not file_path:
            raise RommError("file_path required for add")
        return _dump(_upload_file_with_header(f"/api/roms/{rom_id}/soundtracks", file_path))
    if action == "delete":
        if file_id is None:
            raise RommError("file_id required for delete")
        _require_confirm(confirm, f"delete soundtrack file {file_id} on ROM {rom_id}")
        return _dump(_req("DELETE", f"/api/roms/{rom_id}/soundtracks/{file_id}"))
    raise RommError("action must be metadata|add|delete")


@mcp.tool()
@_tool_error
def romm_rom_patch(
    rom_id: int,
    patch_file_id: Optional[int] = None,
    patch_file_path: str = "",
    output_file_name: str = "",
    confirm: bool = False,
) -> str:
    """Apply an IPS/BPS/UPS-style patch to a ROM, producing a new patched
    file in the library alongside the original.

    Args:
        rom_id: RomM rom id (the base game file's ROM id).
        patch_file_id: id of a patch file already in the library (RomFile)
            to apply — use this OR patch_file_path, not both.
        patch_file_path: local patch file to upload and apply without
            storing it in the library.
        output_file_name: custom name for the patched output (default:
            derived from the ROM + patch names).
        confirm: must be True — writes a new file into the library.
    """
    if not patch_file_id and not patch_file_path:
        raise RommError("patch_file_id or patch_file_path required")
    _require_confirm(confirm, f"apply a patch to ROM {rom_id}")
    form: dict[str, Any] = {}
    if patch_file_id:
        form["patch_file_id"] = str(patch_file_id)
    if output_file_name:
        form["output_file_name"] = output_file_name
    if patch_file_path:
        p = Path(patch_file_path)
        if not p.is_file():
            raise RommError(f"file not found: {patch_file_path}")
        with open(p, "rb") as f:
            files = {**_as_multipart(form),
                     "patch_file": (p.name, f, "application/octet-stream")}
            return _dump(_req("POST", f"/api/roms/{rom_id}/patch", files=files))
    return _dump(_req("POST", f"/api/roms/{rom_id}/patch", files=_as_multipart(form)))


@mcp.tool()
@_tool_error
def romm_rom_convert_to_folder(rom_id: int, confirm: bool = False) -> str:
    """Convert a single-file ROM into RomM's multi-file folder structure —
    needed before attaching extra files (patches, DLC) to a ROM that was
    scanned as a single file.

    Args:
        rom_id: RomM rom id.
        confirm: must be True — restructures files on disk.
    """
    _require_confirm(confirm, f"convert ROM {rom_id} to folder structure")
    return _dump(_req("POST", f"/api/roms/{rom_id}/convert-to-folder"))


@mcp.tool()
@_tool_error
def romm_match_search(rom_id: int, search_term: str = "", search_by: str = "name") -> str:
    """Search enabled metadata providers for candidate matches for a ROM.
    Apply a match afterwards with romm_rom_update(provider_ids_json=...).

    Note: 500s with "No metadata providers enabled" when only hash-based
    sources (Hasheous/LibretroDB) are configured — text search needs
    IGDB/ScreenScraper/MobyGames credentials on the server.

    Args:
        rom_id: RomM rom id to find matches for.
        search_term: override the search text (defaults to the ROM's name).
        search_by: "name" or "id".
    """
    params = {"rom_id": rom_id, "search_term": search_term or None,
              "search_by": search_by}
    return _dump(_req("GET", "/api/search/roms", params=params))


@mcp.tool()
@_tool_error
def romm_download_rom(rom_id: int, dest_dir: str, file_name: str = "") -> str:
    """Download a ROM's file(s) to a local directory.

    Args:
        rom_id: RomM rom id.
        dest_dir: local directory to save into (created if missing).
        file_name: specific file to fetch (defaults to the ROM's primary
            fs_name; multi-file ROMs come down as a zip).
    """
    rom = _req("GET", f"/api/roms/{rom_id}")
    fname = file_name or rom.get("fs_name")
    if not fname:
        raise RommError(f"ROM {rom_id} has no fs_name; pass file_name explicitly")
    if ".." in Path(fname).parts or Path(fname).is_absolute():
        raise RommError(f"refusing suspicious file name: {fname!r}")
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / fname
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"/api/roms/{rom_id}/content/{fname}"
    with client().stream("GET", url) as r:
        if r.status_code >= 400:
            raise RommError(f"{r.status_code} downloading {url}")
        with open(out_path, "wb") as f:
            for chunk in r.iter_bytes(1024 * 512):
                f.write(chunk)
    size = out_path.stat().st_size
    return f"downloaded {fname} ({size} bytes) -> {out_path}"


@mcp.tool()
@_tool_error
def romm_upload_rom(platform_id: int, file_path: str, confirm: bool = False) -> str:
    """Upload a local ROM file to a platform via RomM's chunked-upload API.

    Args:
        platform_id: destination platform id (romm_platforms).
        file_path: local path of the ROM file.
        confirm: must be True — writes a file into the library.
    """
    _require_confirm(confirm, f"upload {file_path} into platform {platform_id}")
    p = Path(file_path)
    if not p.is_file():
        raise RommError(f"file not found: {file_path}")
    total = p.stat().st_size
    chunk_size = 8 * 1024 * 1024
    total_chunks = max(1, (total + chunk_size - 1) // chunk_size)
    start = _req("POST", "/api/roms/upload/start", headers={
        "x-upload-platform": str(platform_id),
        "x-upload-filename": p.name,
        "x-upload-total-size": str(total),
        "x-upload-total-chunks": str(total_chunks),
    })
    upload_id = start.get("upload_id") or start.get("id")
    if not upload_id:
        raise RommError(f"no upload_id in start response: {start}")
    try:
        with open(p, "rb") as f:
            for idx in range(total_chunks):
                chunk = f.read(chunk_size)
                _req("PUT", f"/api/roms/upload/{upload_id}",
                     headers={"x-chunk-index": str(idx)}, content=chunk)
        done = _req("POST", f"/api/roms/upload/{upload_id}/complete")
    except Exception:
        try:
            _req("POST", f"/api/roms/upload/{upload_id}/cancel")
        except Exception:
            pass
        raise
    return _dump({"uploaded": p.name, "bytes": total, "chunks": total_chunks,
                  "result": done,
                  "note": "run romm_scan (or wait for the filesystem watcher) to index it"})


@mcp.tool()
@_tool_error
def romm_export(fmt: str, platform_ids: list[int], local_export: bool = False,
                confirm: bool = False) -> str:
    """Export library metadata as gamelist.xml (EmulationStation) or Pegasus.

    IMPORTANT (verified live on 5.x): this ALWAYS writes the export files
    into the platform directories on the server's disk — nothing is
    returned for download. `local_export` only controls whether the XML
    references local file paths (True) or RomM URLs (False).

    Args:
        fmt: "gamelist-xml" or "pegasus".
        platform_ids: platforms to export.
        local_export: reference local paths instead of URLs in the output.
        confirm: must be True — writes files into the server's ROM folders.
    """
    if fmt not in ("gamelist-xml", "pegasus"):
        raise RommError("fmt must be gamelist-xml or pegasus")
    _require_confirm(
        confirm,
        f"write {fmt} export files into the server's platform folder(s) "
        f"for platforms {platform_ids}",
    )
    r = _req("POST", f"/api/export/{fmt}",
             params={"platform_ids": platform_ids, "local_export": local_export})
    return _dump({"result": r,
                  "note": "export files were written next to the ROMs on the "
                          "server (e.g. gamelist.xml in each platform folder)"})


# --------------------------------------------------------------------------- #
# Collections                                                                 #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_collections(kind: str = "all", virtual_type: str = "franchise") -> str:
    """List collections.

    Args:
        kind: manual | smart | virtual | all.
        virtual_type: franchise | genre | company | mode | developer |
            publisher — virtual collections are auto-generated and always
            need this to pick which grouping to list (only used when
            kind is virtual or all).
    """
    out: dict[str, Any] = {}
    if kind in ("manual", "all"):
        out["manual"] = _req("GET", "/api/collections")
    if kind in ("smart", "all"):
        out["smart"] = _req("GET", "/api/collections/smart")
    if kind in ("virtual", "all"):
        out["virtual"] = _req("GET", "/api/collections/virtual",
                              params={"type": virtual_type})
    return _dump(out)


@mcp.tool()
@_tool_error
def romm_collection(collection_id: str, kind: str = "manual") -> str:
    """Detail for one collection.

    Args:
        collection_id: collection id (virtual ids are strings).
        kind: manual | smart | virtual.
    """
    path = {"manual": f"/api/collections/{collection_id}",
            "smart": f"/api/collections/smart/{collection_id}",
            "virtual": f"/api/collections/virtual/{collection_id}"}.get(kind)
    if not path:
        raise RommError("kind must be manual|smart|virtual")
    return _dump(_req("GET", path))


@mcp.tool()
@_tool_error
def romm_collection_create(
    name: str,
    description: str = "",
    is_public: bool = False,
    is_favorite: bool = False,
    url_cover: str = "",
) -> str:
    """Create a manual collection (safe, reversible via delete).

    Args:
        name: collection name.
        description: optional description.
        is_public: visible to all users.
        is_favorite: mark as the user's Favorites collection.
        url_cover: optional cover-art URL.
    """
    form = {"name": name, "description": description}
    if url_cover:
        form["url_cover"] = url_cover
    return _dump(_req("POST", "/api/collections",
                      params={"is_public": is_public, "is_favorite": is_favorite},
                      files=_as_multipart(form)))


@mcp.tool()
@_tool_error
def romm_collection_update(
    collection_id: int,
    name: str = "",
    description: str = "",
    is_public: Optional[bool] = None,
    remove_cover: bool = False,
    confirm: bool = False,
) -> str:
    """Update a manual collection's name/description/visibility/cover.

    Args:
        collection_id: collection id.
        name / description: new values (empty = leave unchanged).
        is_public: change visibility.
        remove_cover: strip the cover image.
        confirm: must be True — modifies the collection.
    """
    _require_confirm(confirm, f"update collection {collection_id}")
    # PUT requires rom_ids (full membership, as a JSON array string) —
    # omitting it 422s, so round-trip the current membership.
    current = _req("GET", f"/api/collections/{collection_id}")
    form = {"rom_ids": json.dumps(current.get("rom_ids", []))}
    if name:
        form["name"] = name
    if description:
        form["description"] = description
    return _dump(_req("PUT", f"/api/collections/{collection_id}",
                      params={"is_public": is_public,
                              "remove_cover": remove_cover or None},
                      files=_as_multipart(form)))


@mcp.tool()
@_tool_error
def romm_collection_delete(collection_id: int, kind: str = "manual", confirm: bool = False) -> str:
    """Delete a manual or smart collection (ROMs are not touched).

    Args:
        collection_id: collection id.
        kind: manual | smart.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"delete {kind} collection {collection_id}")
    path = {"manual": f"/api/collections/{collection_id}",
            "smart": f"/api/collections/smart/{collection_id}"}.get(kind)
    if not path:
        raise RommError("kind must be manual|smart")
    return _dump(_req("DELETE", path))


@mcp.tool()
@_tool_error
def romm_collection_roms(collection_id: int, action: str, rom_ids: list[int]) -> str:
    """Add or remove ROMs in a manual collection (safe, reversible).

    Args:
        collection_id: collection id.
        action: "add" or "remove".
        rom_ids: ROM ids to add/remove.
    """
    if action == "add":
        return _dump(_req("POST", f"/api/collections/{collection_id}/roms",
                          json_body={"rom_ids": rom_ids}))
    if action == "remove":
        return _dump(_req("DELETE", f"/api/collections/{collection_id}/roms",
                          json_body={"rom_ids": rom_ids}))
    raise RommError("action must be add|remove")


@mcp.tool()
@_tool_error
def romm_smart_collection_create(
    name: str,
    filter_criteria_json: str,
    description: str = "",
    is_public: bool = False,
) -> str:
    """Create a smart (rule-based) collection.

    Args:
        name: collection name.
        filter_criteria_json: JSON of the same filters /api/roms accepts,
            e.g. '{"matched": false}' or '{"platform_ids": [3], "genres": ["RPG"]}'.
        description: optional description.
        is_public: visible to all users.
    """
    form = {"name": name, "description": description,
            "filter_criteria": filter_criteria_json}
    return _dump(_req("POST", "/api/collections/smart",
                      params={"is_public": is_public}, form=form))


@mcp.tool()
@_tool_error
def romm_smart_collection_update(
    collection_id: int,
    name: str = "",
    description: str = "",
    filter_criteria_json: str = "",
    is_public: Optional[bool] = None,
    confirm: bool = False,
) -> str:
    """Update a smart collection's name/description/rule.

    Args:
        collection_id: smart collection id.
        name / description: new values (empty = leave unchanged).
        filter_criteria_json: new rule as a JSON string, same shape as
            romm_smart_collection_create — verify it first by running the
            same filters through romm_roms and checking the match count.
        is_public: change visibility.
        confirm: must be True — modifies the collection.
    """
    _require_confirm(confirm, f"update smart collection {collection_id}")
    form: dict[str, str] = {}
    if name:
        form["name"] = name
    if description:
        form["description"] = description
    if filter_criteria_json:
        form["filter_criteria"] = filter_criteria_json
    return _dump(_req("PUT", f"/api/collections/smart/{collection_id}",
                      params={"is_public": is_public}, form=form))


# --------------------------------------------------------------------------- #
# Users / permissions / API keys                                              #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_users() -> str:
    """List all users (admin only): role, enabled, last active."""
    users = _req("GET", "/api/users")
    slim = [{k: u.get(k) for k in ("id", "username", "email", "role", "enabled",
                                   "last_active", "last_login")} for u in users]
    return _dump(slim)


@mcp.tool()
@_tool_error
def romm_user(user_id: int) -> str:
    """Full detail for one user, including their effective permissions.

    Args:
        user_id: user id.
    """
    user = _req("GET", f"/api/users/{user_id}")
    perms = None
    try:
        perms = _req("GET", f"/api/permissions/users/{user_id}")
    except RommError:
        pass
    return _dump({"user": user, "permissions": perms})


@mcp.tool()
@_tool_error
def romm_user_create(username: str, email: str, password: str, role: str = "user",
                     confirm: bool = False) -> str:
    """Create a user (admin only).

    Args:
        username: login name.
        email: email address.
        password: initial password.
        role: "user" or "admin" — RomM 5.x has ONLY these two (the old
            viewer/editor split moved into permission groups; the server
            silently ignores unknown roles). Fine-grained access =
            permission groups via romm_permissions.
        confirm: must be True — creates an account.
    """
    if role not in ("user", "admin"):
        raise RommError("role must be 'user' or 'admin' on RomM 5.x — "
                        "use permission groups for finer access control")
    _require_confirm(confirm, f"create user '{username}' with role {role}")
    return _dump(_req("POST", "/api/users",
                      json_body={"username": username, "email": email,
                                 "password": password, "role": role}))


@mcp.tool()
@_tool_error
def romm_user_update(user_id: int, fields_json: str, confirm: bool = False) -> str:
    """Update a user (role, enabled, email, password, ra_username...).

    Args:
        user_id: user id.
        fields_json: JSON of fields, e.g. '{"role": "admin", "enabled": true}'.
            Valid roles on 5.x: "user" | "admin" only (invalid values are
            SILENTLY ignored by the server — verified live).
        confirm: must be True — modifies an account.
    """
    fields = json.loads(fields_json)
    if "role" in fields and fields["role"] not in ("user", "admin"):
        raise RommError("role must be 'user' or 'admin' on RomM 5.x — the "
                        "server silently ignores anything else")
    _require_confirm(confirm, f"update user {user_id}")
    return _dump(_req("PUT", f"/api/users/{user_id}", form=fields))


@mcp.tool()
@_tool_error
def romm_user_delete(user_id: int, confirm: bool = False) -> str:
    """Delete a user account.

    Args:
        user_id: user id.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"DELETE user {user_id}")
    return _dump(_req("DELETE", f"/api/users/{user_id}"))


@mcp.tool()
@_tool_error
def romm_user_invite(role: str = "user", expiration: Optional[int] = None,
                     confirm: bool = False) -> str:
    """Generate a one-time invite link for a new user.

    Args:
        role: "user" or "admin" (RomM 5.x role vocabulary).
        expiration: link lifetime in minutes (server default if omitted).
        confirm: must be True — mints a usable registration credential.
    """
    if role not in ("user", "admin"):
        raise RommError("role must be 'user' or 'admin' on RomM 5.x")
    _require_confirm(confirm, f"create an invite link with role {role}")
    return _dump(_req("POST", "/api/users/invite-link",
                      params={"role": role, "expiration": expiration}))


@mcp.tool()
@_tool_error
def romm_permissions(scope: str = "me", user_id: Optional[int] = None) -> str:
    """Inspect the permission system.

    Args:
        scope: me (my effective perms) | catalog (all known permissions) |
            groups (permission groups) | user (one user's perms; needs user_id).
        user_id: target user for scope="user".
    """
    if scope == "me":
        return _dump(_req("GET", "/api/permissions/me"))
    if scope == "catalog":
        return _dump(_req("GET", "/api/permissions/catalog"))
    if scope == "groups":
        return _dump(_req("GET", "/api/permissions/groups"))
    if scope == "user":
        if user_id is None:
            raise RommError("user_id required for scope='user'")
        return _dump(_req("GET", f"/api/permissions/users/{user_id}"))
    raise RommError("scope must be me|catalog|groups|user")


@mcp.tool()
@_tool_error
def romm_permission_group(
    action: str,
    group_id: Optional[int] = None,
    name: str = "",
    description: str = "",
    is_default: bool = False,
    color: str = "",
    grants_json: str = "",
    confirm: bool = False,
) -> str:
    """Create/update/delete a permission group (the fine-grained access
    tiers beyond the coarse user/admin role — see romm_permissions
    (scope="groups") to list existing ones, scope="catalog" for the grant
    vocabulary).

    Args:
        action: create | update | delete.
        group_id: required for update/delete.
        name: group name (required for create).
        description: optional description.
        is_default: assign automatically to new users.
        color: optional UI color tag.
        grants_json: JSON array of grant objects matching
            romm_permissions(scope="catalog")'s shape, e.g.
            '[{"action": "rom.view", "scope": {"kind": "all"}}]'.
        confirm: required True for update/delete (create is reversible via
            delete, so not gated).
    """
    if action == "create":
        if not name:
            raise RommError("name required for create")
        body: dict[str, Any] = {"name": name, "description": description,
                                "is_default": is_default}
        if color:
            body["color"] = color
        if grants_json:
            body["grants"] = json.loads(grants_json)
        return _dump(_req("POST", "/api/permissions/groups", json_body=body))
    if group_id is None:
        raise RommError("group_id required for update/delete")
    if action == "update":
        _require_confirm(confirm, f"update permission group {group_id}")
        body = {}
        if name:
            body["name"] = name
        if description:
            body["description"] = description
        if color:
            body["color"] = color
        if grants_json:
            body["grants"] = json.loads(grants_json)
        return _dump(_req("PUT", f"/api/permissions/groups/{group_id}", json_body=body))
    if action == "delete":
        _require_confirm(confirm, f"delete permission group {group_id}")
        return _dump(_req("DELETE", f"/api/permissions/groups/{group_id}"))
    raise RommError("action must be create|update|delete")


@mcp.tool()
@_tool_error
def romm_user_permissions_update(
    user_id: int,
    permission_group_id: Optional[int] = None,
    set_group: bool = False,
    overrides_json: str = "",
    confirm: bool = False,
) -> str:
    """Assign a user's permission group and/or per-entity overrides.

    Args:
        user_id: target user.
        permission_group_id: group to assign (with set_group=True), or the
            group to reference for context (set_group=False).
        set_group: True to actually change the user's group to
            permission_group_id; False to only apply overrides_json.
        overrides_json: JSON array of override objects (grant a specific
            entity beyond the group default), e.g.
            '[{"action": "rom.delete", "scope": {"kind": "all"}}]'.
        confirm: must be True — changes what this user can do.
    """
    _require_confirm(confirm, f"update permissions for user {user_id}")
    body: dict[str, Any] = {"set_group": set_group}
    if permission_group_id is not None:
        body["permission_group_id"] = permission_group_id
    if overrides_json:
        body["overrides"] = json.loads(overrides_json)
    return _dump(_req("PUT", f"/api/permissions/users/{user_id}", json_body=body))


@mcp.tool()
@_tool_error
def romm_permission_hidden(
    action: str,
    entity: str,
    entity_id: int,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    confirm: bool = False,
) -> str:
    """Hide a specific entity (platform, ROM, collection...) from a user or
    group — the mechanism behind "kid-safe" library views.

    Args:
        action: add | remove.
        entity: platforms | roms | collections | firmware | assets |
            devices | users | tasks | logs.
        entity_id: id of the specific entity to hide.
        user_id: hide for this one user (mutually exclusive with group_id).
        group_id: hide for everyone in this permission group.
        confirm: must be True — changes what someone can see.
    """
    if not user_id and not group_id:
        raise RommError("user_id or group_id required")
    _require_confirm(confirm, f"{action} hidden {entity}={entity_id} "
                     f"for {'user ' + str(user_id) if user_id else 'group ' + str(group_id)}")
    body = {"entity": entity, "entity_id": entity_id, "user_id": user_id, "group_id": group_id}
    if action == "add":
        return _dump(_req("POST", "/api/permissions/hidden", json_body=body))
    if action == "remove":
        return _dump(_req("DELETE", "/api/permissions/hidden", json_body=body))
    raise RommError("action must be add|remove")


@mcp.tool()
@_tool_error
def romm_api_keys(
    action: str = "list",
    name: str = "",
    scopes: Optional[list[str]] = None,
    expires_in: Optional[int] = None,
    token_id: Optional[int] = None,
    confirm: bool = False,
) -> str:
    """Manage RomM API keys (client tokens).

    Args:
        action: list (mine) | list_all (admin) | create | revoke | regenerate.
        name: key name (create).
        scopes: scope list for create, e.g. ["roms.read","platforms.read"];
            see romm_permissions(scope="catalog") for the vocabulary.
        expires_in: optional lifetime in seconds (create).
        token_id: target key id (revoke/regenerate).
        confirm: required True for create/revoke/regenerate.
    """
    if action == "list":
        return _dump(_req("GET", "/api/client-tokens"))
    if action == "list_all":
        return _dump(_req("GET", "/api/client-tokens/all"))
    if action == "create":
        _require_confirm(confirm, f"create API key '{name}'")
        if not name or not scopes:
            raise RommError("name and scopes required")
        return _dump(_req("POST", "/api/client-tokens",
                          json_body={"name": name, "scopes": scopes,
                                     "expires_in": expires_in}))
    if action in ("revoke", "regenerate"):
        if token_id is None:
            raise RommError("token_id required")
        _require_confirm(confirm, f"{action} API key {token_id}")
        if action == "revoke":
            return _dump(_req("DELETE", f"/api/client-tokens/{token_id}"))
        return _dump(_req("PUT", f"/api/client-tokens/{token_id}/regenerate"))
    raise RommError("action must be list|list_all|create|revoke|regenerate")


# --------------------------------------------------------------------------- #
# Saves / states / firmware                                                   #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_saves(rom_id: Optional[int] = None, platform_id: Optional[int] = None) -> str:
    """List save files (optionally for one ROM or platform).

    Args:
        rom_id: filter by ROM.
        platform_id: filter by platform.
    """
    return _dump(_req("GET", "/api/saves",
                      params={"rom_id": rom_id, "platform_id": platform_id}))


@mcp.tool()
@_tool_error
def romm_saves_delete(save_ids: list[int], confirm: bool = False) -> str:
    """Delete save files.

    Args:
        save_ids: save ids to delete.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"DELETE {len(save_ids)} save file(s)")
    return _dump(_req("POST", "/api/saves/delete", json_body={"saves": save_ids}))


@mcp.tool()
@_tool_error
def romm_states(rom_id: Optional[int] = None, platform_id: Optional[int] = None) -> str:
    """List save states (optionally for one ROM or platform).

    Args:
        rom_id: filter by ROM.
        platform_id: filter by platform.
    """
    return _dump(_req("GET", "/api/states",
                      params={"rom_id": rom_id, "platform_id": platform_id}))


@mcp.tool()
@_tool_error
def romm_states_delete(state_ids: list[int], confirm: bool = False) -> str:
    """Delete save states.

    Args:
        state_ids: state ids to delete.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"DELETE {len(state_ids)} save state(s)")
    return _dump(_req("POST", "/api/states/delete", json_body={"states": state_ids}))


@mcp.tool()
@_tool_error
def romm_firmware(platform_id: Optional[int] = None) -> str:
    """List firmware/BIOS files (optionally for one platform).

    Args:
        platform_id: filter by platform.
    """
    return _dump(_req("GET", "/api/firmware", params={"platform_id": platform_id}))


@mcp.tool()
@_tool_error
def romm_firmware_upload(platform_id: int, file_path: str, confirm: bool = False) -> str:
    """Upload a firmware/BIOS file for a platform.

    Args:
        platform_id: destination platform id.
        file_path: local path of the firmware file.
        confirm: must be True — writes a file into the library.
    """
    _require_confirm(confirm, f"upload firmware {file_path} to platform {platform_id}")
    p = Path(file_path)
    if not p.is_file():
        raise RommError(f"file not found: {file_path}")
    with open(p, "rb") as f:
        return _dump(_req("POST", "/api/firmware",
                          params={"platform_id": platform_id},
                          files={"files": (p.name, f, "application/octet-stream")}))


@mcp.tool()
@_tool_error
def romm_firmware_delete(firmware_ids: list[int], delete_from_fs: bool = False,
                         confirm: bool = False) -> str:
    """Delete firmware entries, optionally including files on disk.

    Args:
        firmware_ids: firmware ids.
        delete_from_fs: also delete the files from the server's disk.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"DELETE {len(firmware_ids)} firmware file(s)"
                     + (" INCLUDING FILES ON DISK" if delete_from_fs else ""))
    body = {"firmware": firmware_ids,
            "delete_from_fs": firmware_ids if delete_from_fs else []}
    return _dump(_req("POST", "/api/firmware/delete", json_body=body))


# --------------------------------------------------------------------------- #
# Screenshots                                                                 #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_screenshot(
    action: str,
    screenshot_id: Optional[int] = None,
    rom_id: Optional[int] = None,
    file_path: str = "",
    dest_dir: str = "",
    is_public: Optional[bool] = None,
    confirm: bool = False,
) -> str:
    """Manage standalone screenshots. List them via romm_rom(rom_id,
    verbose=True) — there's no top-level screenshot-list endpoint.

    Note: RomM also has a second, header-based attach path at
    POST /api/roms/{id}/screenshots for the same underlying resource — this
    tool uses the plain multipart one below since it has a fully-specified
    schema; both are legitimate, so don't be surprised to see the other in
    server docs.

    Args:
        action: add (needs rom_id + file_path) | update (needs
            screenshot_id + is_public) | delete (needs screenshot_id) |
            download (needs screenshot_id + dest_dir).
        screenshot_id: target screenshot, for update/delete/download.
        rom_id: owning ROM, for add.
        file_path: local image path, for add.
        dest_dir: local directory to save into, for download.
        is_public: new visibility, for update.
        confirm: required True for delete (destructive).
    """
    if action == "add":
        if rom_id is None or not file_path:
            raise RommError("rom_id and file_path required for add")
        p = Path(file_path)
        if not p.is_file():
            raise RommError(f"file not found: {file_path}")
        with open(p, "rb") as f:
            return _dump(_req("POST", "/api/screenshots", params={"rom_id": rom_id},
                              files={"screenshotFile": (p.name, f, "application/octet-stream")}))
    if action == "update":
        if screenshot_id is None or is_public is None:
            raise RommError("screenshot_id and is_public required for update")
        return _dump(_req("PUT", f"/api/screenshots/{screenshot_id}",
                          json_body={"is_public": is_public}))
    if action == "delete":
        if screenshot_id is None:
            raise RommError("screenshot_id required for delete")
        _require_confirm(confirm, f"delete screenshot {screenshot_id}")
        return _dump(_req("DELETE", f"/api/screenshots/{screenshot_id}"))
    if action == "download":
        if screenshot_id is None or not dest_dir:
            raise RommError("screenshot_id and dest_dir required for download")
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"screenshot_{screenshot_id}.png"
        url = f"/api/screenshots/{screenshot_id}/content"
        with client().stream("GET", url) as r:
            if r.status_code >= 400:
                raise RommError(f"{r.status_code} downloading {url}")
            ext = r.headers.get("content-type", "").split("/")[-1]
            if ext and ext.isalnum():
                out_path = out_path.with_suffix(f".{ext}")
            with open(out_path, "wb") as f:
                for chunk in r.iter_bytes(1024 * 256):
                    f.write(chunk)
        return f"downloaded screenshot {screenshot_id} -> {out_path}"
    raise RommError("action must be add|update|delete|download")


# --------------------------------------------------------------------------- #
# Devices / activity / play sessions / music / feeds                          #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_devices() -> str:
    """List registered client devices (sync clients, handhelds, browsers)."""
    return _dump(_req("GET", "/api/devices"))


@mcp.tool()
@_tool_error
def romm_device_delete(device_id: int, confirm: bool = False) -> str:
    """Delete a registered device.

    Args:
        device_id: device id.
        confirm: must be True — destructive.
    """
    _require_confirm(confirm, f"delete device {device_id}")
    return _dump(_req("DELETE", f"/api/devices/{device_id}"))


@mcp.tool()
@_tool_error
def romm_device_update(device_id: str, fields_json: str, confirm: bool = False) -> str:
    """Edit a registered device's name/sync settings.

    Args:
        device_id: device id (string — sync device ids are UUIDs).
        fields_json: JSON object of fields to change, e.g.
            '{"name": "Steam Deck"}' or '{"sync_enabled": false}'. Settable:
            name, platform, client, client_version, ip_address, mac_address,
            hostname, sync_enabled, sync_mode, sync_config.
        confirm: must be True — modifies the device record.
    """
    _require_confirm(confirm, f"update device {device_id}")
    body = json.loads(fields_json)
    return _dump(_req("PUT", f"/api/devices/{device_id}", json_body=body))


# --------------------------------------------------------------------------- #
# Device pairing / sync / netplay                                            #
# --------------------------------------------------------------------------- #
@mcp.tool()
@_tool_error
def romm_device_auth(
    action: str,
    user_code: str = "",
    approved_scopes: Optional[list[str]] = None,
    device_name: str = "",
    expires_in: str = "",
    confirm: bool = False,
) -> str:
    """Admin side of the device-pairing flow (emulator front-ends like
    Pegasus/RetroArch requesting API access): check a pending pairing
    request and approve or deny it. The device's own half (init/token) is
    not exposed here — that's initiated by the pairing device, not an admin.

    Args:
        action: pending (look up a request by user_code) | approve | deny.
        user_code: the short code the pairing device is displaying.
        approved_scopes: scopes to grant, required for approve — see
            romm_permissions(scope="catalog") for the vocabulary.
        device_name: optional friendly name to assign, for approve.
        expires_in: optional token lifetime, for approve.
        confirm: required True for approve/deny.
    """
    if not user_code:
        raise RommError("user_code required")
    if action == "pending":
        return _dump(_req("GET", f"/api/auth/device/pending/{user_code}"))
    if action == "approve":
        if not approved_scopes:
            raise RommError("approved_scopes required for approve")
        _require_confirm(confirm, f"approve device pairing {user_code}")
        body: dict[str, Any] = {"user_code": user_code, "approved_scopes": approved_scopes}
        if device_name:
            body["device_name"] = device_name
        if expires_in:
            body["expires_in"] = expires_in
        return _dump(_req("POST", "/api/auth/device/approve", json_body=body))
    if action == "deny":
        _require_confirm(confirm, f"deny device pairing {user_code}")
        return _dump(_req("POST", "/api/auth/device/deny", json_body={"user_code": user_code}))
    raise RommError("action must be pending|approve|deny")


@mcp.tool()
@_tool_error
def romm_sync(
    action: str = "sessions",
    device_id: str = "",
    session_id: str = "",
    limit: int = 50,
    confirm: bool = False,
) -> str:
    """Inspect and drive device save/state sync sessions.

    Args:
        action: sessions (list, optionally filtered by device_id) | session
            (one session, needs session_id) | trigger (force a push-pull for
            device_id now).
        device_id: filter for sessions, or target for trigger.
        session_id: target for action="session".
        limit: max rows for action="sessions".
        confirm: required True for trigger (kicks off a real sync).
    """
    if action == "sessions":
        return _dump(_req("GET", "/api/sync/sessions",
                          params={"device_id": device_id or None, "limit": limit}))
    if action == "session":
        if not session_id:
            raise RommError("session_id required for action='session'")
        return _dump(_req("GET", f"/api/sync/sessions/{session_id}"))
    if action == "trigger":
        if not device_id:
            raise RommError("device_id required for action='trigger'")
        _require_confirm(confirm, f"trigger a push-pull sync for device {device_id}")
        return _dump(_req("POST", f"/api/sync/devices/{device_id}/push-pull"))
    raise RommError("action must be sessions|session|trigger")


@mcp.tool()
@_tool_error
def romm_netplay_rooms(game_id: str) -> str:
    """List active netplay rooms for a game.

    Args:
        game_id: the game identifier netplay sessions are keyed on (see the
            ROM's netplay-relevant metadata, e.g. RetroAchievements id).
    """
    return _dump(_req("GET", "/api/netplay/list", params={"game_id": game_id}))


@mcp.tool()
@_tool_error
def romm_activity(rom_id: Optional[int] = None) -> str:
    """Show current play activity (who is playing what right now).

    Args:
        rom_id: restrict to activity on one ROM.
    """
    if rom_id is not None:
        return _dump(_req("GET", f"/api/activity/rom/{rom_id}"))
    return _dump(_req("GET", "/api/activity"))


@mcp.tool()
@_tool_error
def romm_play_sessions(
    rom_id: Optional[int] = None,
    device_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List historical play sessions (playtime tracking).

    Args:
        rom_id: filter by ROM.
        device_id: filter by device.
        limit/offset: pagination.
    """
    return _dump(_req("GET", "/api/play-sessions",
                      params={"rom_id": rom_id, "device_id": device_id,
                              "limit": limit, "offset": offset}))


@mcp.tool()
@_tool_error
def romm_music(
    kind: str = "tracks",
    search: str = "",
    artist: str = "",
    album: str = "",
    genre: str = "",
    platform_id: Optional[int] = None,
    year: Optional[int] = None,
    order_by: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Browse the game-music library (RomM 5.x soundtrack support).

    Args:
        kind: tracks | albums | artists | genres | years.
        search / artist / album / genre: text filters.
        platform_id: filter by platform.
        year: filter by release year.
        order_by: sort field.
        limit/offset: pagination.
    """
    if kind not in ("tracks", "albums", "artists", "genres", "years"):
        raise RommError("kind must be tracks|albums|artists|genres|years")
    params = {"search": search or None, "artist": artist or None,
              "album": album or None, "genre": genre or None,
              "platform_ids": platform_id, "year": year,
              "order_by": order_by or None, "limit": limit, "offset": offset}
    return _dump(_req("GET", f"/api/music/{kind}", params=params))


@mcp.tool()
@_tool_error
def romm_feeds(feed: str = "", platform_slug: str = "", content_type: str = "") -> str:
    """Show download-feed endpoints for handheld clients (Tinfoil, webRcade,
    PKGi, Kekatsu, FPKGi) and fetch a feed's content.

    Args:
        feed: empty = list available feeds. Or one of: tinfoil | webrcade |
            kekatsu | fpkgi | pkgi-ps3 | pkgi-psp | pkgi-psvita | pkgj.
        platform_slug: platform slug for kekatsu/fpkgi.
        content_type: content type for pkgi feeds (games/dlc...).
    """
    if not feed:
        return _dump({
            "available": {
                "tinfoil": f"{BASE_URL}/api/feeds/tinfoil (Nintendo Switch)",
                "webrcade": f"{BASE_URL}/api/feeds/webrcade",
                "kekatsu": f"{BASE_URL}/api/feeds/kekatsu/{{platform_slug}} (DS)",
                "fpkgi": f"{BASE_URL}/api/feeds/fpkgi/{{platform_slug}} (PS4)",
                "pkgi-ps3": f"{BASE_URL}/api/feeds/pkgi/ps3/{{content_type}}",
                "pkgi-psp": f"{BASE_URL}/api/feeds/pkgi/psp/{{content_type}}",
                "pkgi-psvita": f"{BASE_URL}/api/feeds/pkgi/psvita/{{content_type}}",
                "pkgj": f"{BASE_URL}/api/feeds/pkgj/... (psp|psvita|psx)",
            },
            "note": "feeds are consumed by the handheld clients; most need auth",
        })
    path_map = {
        "tinfoil": "/api/feeds/tinfoil",
        "webrcade": "/api/feeds/webrcade",
        "kekatsu": f"/api/feeds/kekatsu/{platform_slug}",
        "fpkgi": f"/api/feeds/fpkgi/{platform_slug}",
        "pkgi-ps3": f"/api/feeds/pkgi/ps3/{content_type}",
        "pkgi-psp": f"/api/feeds/pkgi/psp/{content_type}",
        "pkgi-psvita": f"/api/feeds/pkgi/psvita/{content_type}",
    }
    path = path_map.get(feed)
    if not path:
        raise RommError(f"unknown feed '{feed}'")
    return _dump(_req("GET", path))


# --------------------------------------------------------------------------- #
# Library scan (Socket.IO — the one job REST cannot do)                       #
# --------------------------------------------------------------------------- #
# One scan at a time (RomM itself only runs one), tracked here so romm_scan
# can return quickly and romm_scan_status can keep polling the same session
# instead of every call blocking until the whole scan finishes.
_scan_state: dict[str, Any] = {}


def _cleanup_scan_state() -> None:
    sio = _scan_state.get("sio")
    if sio is not None:
        try:
            sio.disconnect()
        except Exception:
            pass
    cookie = _scan_state.get("session_cookie")
    if cookie:
        try:
            httpx.post(f"{BASE_URL}/api/logout", cookies={"romm_session": cookie},
                       timeout=10, verify=VERIFY_SSL)
        except Exception:
            pass
    _scan_state.clear()


@mcp.tool()
@_tool_error
def romm_scan(
    scan_type: str = "quick",
    platform_ids: Optional[list[int]] = None,
    rom_ids: Optional[list[int]] = None,
    metadata_sources: Optional[list[str]] = None,
    wait_seconds: int = 20,
    confirm: bool = False,
) -> str:
    """Start a library scan (the web UI's Scan button) and return early progress.

    Scans run server-side over Socket.IO and can take minutes on a large
    library, so this only blocks up to `wait_seconds` (default 20s — enough
    to see the first few platforms/ROMs go by) and then returns even if the
    scan is still running; it keeps running server-side either way. Follow
    up with repeated `romm_scan_status` calls to keep narrating progress —
    each one reports only what's new since the last poll, so you can report
    stage-by-stage instead of going silent for the whole scan.

    Args:
        scan_type: quick (new files only) | complete (rescan everything) |
            new_platforms (only new platform folders) | update (refresh
            metadata) | unmatched (retry unidentified) | hashes (recompute
            file hashes).
        platform_ids: restrict scan to these platform ids (empty = all).
        rom_ids: restrict to specific ROM ids.
        metadata_sources: providers to use (empty = all enabled), e.g.
            ["igdb","ss","moby","ra","lb","hasheous","tgdb"].
        wait_seconds: how long to wait here before returning control even if
            the scan hasn't finished (use romm_scan_status to keep polling).
        confirm: must be True — scans mutate the library database.
    """
    _require_confirm(confirm, f"run a '{scan_type}' library scan")
    if _scan_state.get("sio") is not None:
        age = time.time() - _scan_state.get("started_at", time.time())
        raise RommError(
            f"a scan is already in progress (started {age:.0f}s ago) — use "
            "romm_scan_status to check on it instead of starting another."
        )
    if not (USERNAME and PASSWORD):
        raise RommError(
            "scan needs username+password in config.local.json (or ROMM_USERNAME/"
            "ROMM_PASSWORD env) — RomM's scan socket authenticates with a session "
            "cookie that an API key cannot create. All other tools work without it."
        )
    valid = {"quick", "complete", "new_platforms", "update", "unmatched", "hashes"}
    if scan_type not in valid:
        raise RommError(f"scan_type must be one of {sorted(valid)}")

    # 1. Mint a session cookie via HTTP Basic login.
    login = httpx.post(f"{BASE_URL}/api/login", auth=(USERNAME, PASSWORD),
                       timeout=TIMEOUT, verify=VERIFY_SSL)
    if login.status_code >= 400:
        raise RommError(f"login failed ({login.status_code}): {login.text[:300]}")
    session_cookie = login.cookies.get("romm_session")
    if not session_cookie:
        raise RommError("login succeeded but no romm_session cookie returned")

    # 2. Connect Socket.IO with that cookie and emit "scan". python-socketio's
    #    sync client runs the read loop on its own background thread once
    #    connected, so events keep arriving into `events`/`done` (shared via
    #    _scan_state below) even after this call returns.
    import socketio  # deferred import; only needed here

    events: list[str] = []
    done = threading.Event()
    result: dict[str, Any] = {}
    sio = socketio.Client(reconnection=False, logger=False, engineio_logger=False)

    @sio.on("scan:scanning_platform")
    def _plat(data):  # noqa: ANN001
        name = data.get("name") if isinstance(data, dict) else data
        events.append(f"scanning platform: {name}")

    @sio.on("scan:scanning_rom")
    def _rom(data):  # noqa: ANN001
        name = data.get("name") if isinstance(data, dict) else data
        events.append(f"scanning rom: {name}")

    @sio.on("scan:done")
    def _done(data):  # noqa: ANN001
        result["stats"] = data
        done.set()

    @sio.on("scan:done_ko")
    def _done_ko(data):  # noqa: ANN001
        result["error"] = data
        done.set()

    try:
        sio.connect(
            BASE_URL,
            socketio_path="/ws/socket.io",
            headers={"Cookie": f"romm_session={session_cookie}"},
            transports=["websocket", "polling"],
            wait_timeout=15,
        )
        sio.emit("scan", {
            "platforms": platform_ids or [],
            "type": scan_type,
            "roms_ids": rom_ids or [],
            "apis": metadata_sources or [],
        })
    except Exception as e:
        # Don't leak the socket or the freshly-minted session on failure.
        try:
            sio.disconnect()
        except Exception:
            pass
        try:
            httpx.post(f"{BASE_URL}/api/logout",
                       cookies={"romm_session": session_cookie},
                       timeout=10, verify=VERIFY_SSL)
        except Exception:
            pass
        raise RommError(f"scan socket connect/emit failed: {e}") from e
    _scan_state.update({
        "sio": sio, "events": events, "done": done, "result": result,
        "session_cookie": session_cookie, "scan_type": scan_type,
        "started_at": time.time(), "reported": 0,
    })

    finished = done.wait(timeout=max(0, wait_seconds))
    out: dict[str, Any] = {"scan_type": scan_type, "finished": finished,
                           "recent_events": events[-20:]}
    if finished:
        if "error" in result:
            _cleanup_scan_state()
            raise RommError(f"scan rejected: {result['error']}")
        out["stats"] = result.get("stats")
        _cleanup_scan_state()
    else:
        out["note"] = ("scan still running — call romm_scan_status(wait_seconds=...) "
                       "to keep checking in; it continues server-side regardless")
        _scan_state["reported"] = len(events)
    return _dump(out)


@mcp.tool()
@_tool_error
def romm_scan_status(wait_seconds: int = 15) -> str:
    """Check on the scan started with romm_scan; reports only new progress.

    Waits up to `wait_seconds` for more events or completion, then returns
    whatever's new since the last call to romm_scan/romm_scan_status — call
    this repeatedly with a short wait to narrate a long scan stage by stage
    instead of blocking once for the whole thing. Cleans up the scan session
    once it finishes, so a `finished: true` reply means it's safe to stop
    polling.

    Args:
        wait_seconds: how long to wait here for new events/completion before
            returning (the scan keeps running server-side regardless of how
            often or how long you poll).
    """
    if _scan_state.get("sio") is None:
        raise RommError("no scan is currently running — start one with romm_scan first")

    done: threading.Event = _scan_state["done"]
    events: list[str] = _scan_state["events"]
    finished = done.wait(timeout=max(0, wait_seconds))

    new_events = events[_scan_state.get("reported", 0):]
    out: dict[str, Any] = {
        "scan_type": _scan_state["scan_type"],
        "finished": finished,
        "elapsed_seconds": round(time.time() - _scan_state["started_at"], 1),
        "new_events": new_events,
    }
    if finished:
        result = _scan_state["result"]
        if "error" in result:
            _cleanup_scan_state()
            raise RommError(f"scan rejected: {result['error']}")
        out["stats"] = result.get("stats")
        _cleanup_scan_state()
    else:
        _scan_state["reported"] = len(events)
    return _dump(out)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    log(f"starting RomM MCP server for {BASE_URL} "
        f"(api_key={'set' if API_KEY else 'MISSING'}, "
        f"scan_login={'set' if USERNAME and PASSWORD else 'not configured'})")
    mcp.run()
