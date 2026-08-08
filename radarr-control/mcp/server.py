#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Radarr MCP server.

Exposes a Radarr movie manager (v3+ REST API) to Claude through the Model
Context Protocol. Verified against Radarr 6.3.0.10514. Two-layer design,
mirroring the emby/romm/unifi plugins:

* GENERIC passthrough (`radarr_call` / `radarr_list_endpoints`) reaching every
  /api/v3 endpoint. The catalog is hand-enumerated from live probes (Radarr
  does not publish OpenAPI); it is the master index for radarr_call.
* CURATED tools for the common jobs: status, library (movies, collections,
  files), wanted missing/cutoff, calendar, queue, history, blocklist, commands
  (search/refresh/rescan), quality profiles, root folders, tags, custom
  formats, notifications, download clients, indexers, import lists, logs,
  system tasks & backups.

Auth model (proven live): every request carries the API key in the
`X-Api-Key` header. API keys are created under Settings > General > Security
and act with full admin. 401 = bad key.

Radarr conventions this file encodes (all verified live):
* Paths under /api/v3/<resource>.
* POST /movie expects a full movie object (typically a lookup result augmented
  with qualityProfileId, minimumAvailability, rootFolderPath, monitored,
  addOptions). POSTing a partial object silently fails or 400s.
* POST /command with {"name": "<CommandName>", ...} triggers async jobs
  (RefreshMovie, MoviesSearch, DownloadedMoviesScan, RenameMovies, Backup,
  RefreshMonitoredDownloads, ApplicationUpdate). Returns a job object you can
  poll at /command/{id}.
* List endpoints take page (1-based) + pageSize for paging, plus filters.

Destructive writes (DELETE /movie, POST /command that triggers active
downloads/scans, etc.) are confirm-gated in code (`confirm=True`).

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
    print("[radarr-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("RADARR_CONFIG"):
        candidates.append(Path(os.environ["RADARR_CONFIG"]))
    root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root_env:
        candidates.append(Path(root_env) / "config.local.json")
    here = Path(__file__).resolve().parent
    candidates.append(here.parent / "config.local.json")  # plugin root
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
    host = env.get("RADARR_HOST", cfg.get("host", ""))
    https = _truthy(env.get("RADARR_HTTPS"), cfg.get("https", False))
    port = int(env.get("RADARR_PORT", cfg.get("port", 7878)) or 7878)
    url_base = (env.get("RADARR_URL_BASE", cfg.get("url_base", "")) or "").strip().strip("/")
    return {
        "host": host,
        "port": port,
        "https": https,
        "url_base": url_base,
        "api_key": env.get("RADARR_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("RADARR_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("RADARR_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }


CONFIG = load_config()

MAX_RESULT_CHARS = 60_000  # guard against dumping megabytes into the model


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class RadarrError(Exception):
    pass


class RadarrClient:
    """Thin, thread-safe wrapper that speaks Radarr's REST conventions."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        base = f"{scheme}://{cfg['host']}:{cfg['port']}"
        if cfg.get("url_base"):
            base += "/" + cfg["url_base"].lstrip("/")
        self.base = base
        self._client = httpx.Client(
            base_url=self.base,
            headers={"X-Api-Key": cfg["api_key"], "Accept": "application/json"},
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
        )
        self._lock = threading.Lock()
        self._live_routes: Optional[list] = None  # cache of /system/routes entries

    def request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        body: Any = None,
        raw: bool = False,
    ) -> Any:
        """Make a request; return parsed JSON, text, or None (204/empty)."""
        if not path.startswith("/"):
            path = "/" + path
        # Accept /api/v3 and bare resource both ("movie" -> "/api/v3/movie")
        if not path.startswith("/api/v"):
            path = "/api/v3" + ("" if path.startswith("/") else "/") + path
        resp = self._client.request(method.upper(), path, params=params, json=body)
        if resp.status_code == 401:
            raise RadarrError("401 Unauthorized â€” the API key was rejected.")
        if resp.status_code == 403:
            raise RadarrError(f"403 Forbidden on {method} {path} â€” operation not allowed for this key.")
        if resp.status_code >= 400:
            detail = resp.text[:400]
            raise RadarrError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if raw:
            return resp.text
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text

    def command(self, name: str, **extra: Any) -> dict:
        """POST /command with {"name": name, ...extra}."""
        body = {"name": name, **extra}
        return self.request("POST", "/command", body=body)

    def live_routes(self) -> list:
        """Fetch and parse /api/v3/system/routes (Graphviz DOT format) into a
        clean list of {method, path}. Cached for the process lifetime.

        Radarr/Sonarr expose their FULL route table here â€” using it makes the
        endpoint catalog authoritative-by-construction (vs. a hand-typed list
        that drifts). Falls back to the static ENDPOINT_CATALOG on failure.
        """
        with self._lock:
            if self._live_routes is not None:
                return self._live_routes
        import re
        try:
            text = self.request("GET", "/api/v3/system/routes", raw=True)
            seen = set()
            routes = []
            for label in re.findall(r'\[label="([^"]+)"\]', text or ""):
                m = re.match(r'^(/api/v3\S*)\s+HTTP:\s+([A-Z*]+)\s*$', label)
                if not m:
                    continue
                path = m.group(1).rstrip('/')
                method = m.group(2)
                if method == '*':
                    continue
                # Normalize path placeholders to {id}; case-insensitive dedup
                norm = re.sub(r'\{[^}]+\}', '{id}', path).lower()
                key = (method, norm)
                if key in seen:
                    continue
                seen.add(key)
                routes.append({"method": method, "path": path})
            routes.sort(key=lambda r: (r["path"], r["method"]))
            with self._lock:
                self._live_routes = routes
            return routes
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: /system/routes unavailable, falling back to static catalog: {e}")
            with self._lock:
                self._live_routes = []
            return []


CLIENT = RadarrClient(CONFIG)


# --------------------------------------------------------------------------- #
# Formatting helpers                                                          #
# --------------------------------------------------------------------------- #
def _finish(data: Any) -> Any:
    """Final size guard so a huge payload can't flood the context."""
    try:
        text = json.dumps(data, default=str)
    except (TypeError, ValueError):
        return data
    if len(text) <= MAX_RESULT_CHARS:
        return data
    return {
        "_truncated": True,
        "_note": (f"Result was {len(text)} chars; showing the first "
                  f"{MAX_RESULT_CHARS}. Narrow the query (page/pageSize/id) "
                  "or fetch a specific id."),
        "preview": text[:MAX_RESULT_CHARS],
    }


def _err(e: Exception) -> dict:
    return {"error": str(e)}


def _parse_json_arg(name: str, value: str) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise RadarrError(f"{name} is not valid JSON: {e}") from e


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


def compact_movie(m: dict) -> dict:
    """Trim a movie object to the fields that matter for browsing."""
    if not isinstance(m, dict):
        return m
    has_file = bool(m.get("hasFile"))
    out = {
        "id": m.get("id"),
        "title": m.get("title"),
        "tmdbId": m.get("tmdbId"),
        "year": m.get("year"),
        "status": m.get("status"),
        "monitored": m.get("monitored"),
        "minimumAvailability": m.get("minimumAvailability"),
        "hasFile": has_file,
        "isAvailable": m.get("isAvailable"),
        "monitored": m.get("monitored"),
    }
    fa = m.get("file") or {}
    if fa:
        out["file"] = {"path": fa.get("path"), "size": fa.get("size"),
                       "quality": (fa.get("quality") or {}).get("quality", {}).get("name")}
    if m.get("sizeOnDisk"):
        out["sizeOnDisk"] = m["sizeOnDisk"]
    if m.get("path"):
        out["path"] = m["path"]
    if m.get("qualityProfileId"):
        out["qualityProfileId"] = m["qualityProfileId"]
    if m.get("genres"):
        out["genres"] = m["genres"]
    if m.get("ratings"):
        out["ratings"] = {k: v.get("value") for k, v in (m["ratings"] or {}).items() if isinstance(v, dict)}
    if m.get("inCinemas"):
        out["inCinemas"] = m["inCinemas"]
    if m.get("digitalRelease"):
        out["digitalRelease"] = m["digitalRelease"]
    return {k: v for k, v in out.items() if v is not None}


mcp = FastMCP("radarr")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
# Radarr does NOT publish an OpenAPI document. This catalog was hand-enumerated
# by probing the live 6.3 server (HTTP 200 = the resource exists; 400 = exists
# but needs params; 404 = absent). Append entries as new endpoints are verified.
ENDPOINT_CATALOG: list[dict] = [
    # System
    {"method": "GET",    "path": "/api/v3/system/status",            "summary": "Server identity, version, OS, paths"},
    {"method": "GET",    "path": "/api/v3/system/task",              "summary": "Scheduled tasks (next run, interval, last)"},
    {"method": "GET",    "path": "/api/v3/system/backup",            "summary": "Database backups (size, time, download URL)"},
    {"method": "GET",    "path": "/api/v3/system/task/{id}",         "summary": "Single scheduled task"},
    {"method": "GET",    "path": "/api/v3/log",                      "summary": "Application log (paged, level filter)"},
    {"method": "GET",    "path": "/api/v3/health",                   "summary": "Health checks (warnings about config/integrity)"},
    {"method": "GET",    "path": "/api/v3/queue/status",             "summary": "Queue summary (total, errors, unknown)"},
    {"method": "GET",    "path": "/api/v3/diskspace",                "summary": "Disk free space (movies + drone factory)"},
    {"method": "GET",    "path": "/api/v3/qualityDefinition",        "summary": "Quality definitions (size/quality matrix)"},
    # Movies & files
    {"method": "GET",    "path": "/api/v3/movie",                    "summary": "All movies (filterable)"},
    {"method": "GET",    "path": "/api/v3/movie/{id}",               "summary": "Single movie by id"},
    {"method": "GET",    "path": "/api/v3/movie/lookup",             "summary": "Search TMDB for a movie (term=...)"},
    {"method": "GET",    "path": "/api/v3/movie/lookup/tmdb",        "summary": "TMDB lookup by tmdbId=..."},
    {"method": "GET",    "path": "/api/v3/movie/lookup/imdb",        "summary": "IMDB lookup by imdbId=..."},
    {"method": "PUT",    "path": "/api/v3/movie",                    "summary": "Bulk update movies (provide full array)"},
    {"method": "POST",   "path": "/api/v3/movie",                    "summary": "Add a movie (full movie object required)"},
    {"method": "PUT",    "path": "/api/v3/movie/{id}",               "summary": "Update a movie (full object required)"},
    {"method": "DELETE", "path": "/api/v3/movie/{id}",               "summary": "Delete a movie"},
    {"method": "GET",    "path": "/api/v3/movieFile",                "summary": "Movie files (requires movieId or movieFileIds)"},
    {"method": "GET",    "path": "/api/v3/movieFile/{id}",           "summary": "Single movie file by id"},
    {"method": "DELETE", "path": "/api/v3/movieFile/{id}",           "summary": "Delete a movie file"},
    {"method": "GET",    "path": "/api/v3/alternativeRelease",       "summary": "Alternative titles rejected at import"},
    {"method": "GET",    "path": "/api/v3/extraFile",                "summary": "Extra files (subtitles, etc.)"},
    {"method": "GET",    "path": "/api/v3/collection",               "summary": "Movie collections tracked"},
    {"method": "PUT",    "path": "/api/v3/collection/{id}",          "summary": "Update a collection (monitored, etc.)"},
    {"method": "GET",    "path": "/api/v3/importlist",               "summary": "Configured import lists (trakt, lists, etc.)"},
    {"method": "GET",    "path": "/api/v3/customFormat",             "summary": "Custom formats defined"},
    {"method": "GET",    "path": "/api/v3/customFilter",             "summary": "Saved UI custom filters"},
    # Activity / wanted / calendar
    {"method": "GET",    "path": "/api/v3/wanted/missing",           "summary": "Monitored movies with no file"},
    {"method": "GET",    "path": "/api/v3/wanted/cutoff",            "summary": "Movies below their cutoff quality"},
    {"method": "GET",    "path": "/api/v3/calendar",                 "summary": "Movies by release-date range (start/end)"},
    {"method": "GET",    "path": "/api/v3/queue",                    "summary": "Active downloads (import+grabbed)"},
    {"method": "GET",    "path": "/api/v3/queue/details",            "summary": "Queue with full movie + quality info"},
    {"method": "GET",    "path": "/api/v3/history",                  "summary": "Recent activity (grabbed/imported/failed)"},
    {"method": "GET",    "path": "/api/v3/history/movie",            "summary": "History for one movie (movieId=)"},
    {"method": "GET",    "path": "/api/v3/blocklist",                "summary": "Blocked releases"},
    {"method": "GET",    "path": "/api/v3/release",                  "summary": "Recent releases from indexers"},
    {"method": "POST",   "path": "/api/v3/release",                  "summary": "Send a release to the download client"},
    {"method": "GET",    "path": "/api/v3/manualimport",             "summary": "Manual import candidates (folder=)"},
    {"method": "POST",   "path": "/api/v3/command",                  "summary": "Trigger an async job (see command list)"},
    {"method": "GET",    "path": "/api/v3/command",                  "summary": "Recent / running commands"},
    {"method": "GET",    "path": "/api/v3/command/{id}",             "summary": "Status of a single command"},
    {"method": "DELETE", "path": "/api/v3/command/{id}",             "summary": "Cancel a running command"},
    # Config
    {"method": "GET",    "path": "/api/v3/qualityProfile",           "summary": "Quality profiles (movie, anime)"},
    {"method": "GET",    "path": "/api/v3/language",                 "summary": "Languages known to Radarr"},
    {"method": "GET",    "path": "/api/v3/rootfolder",               "summary": "Configured root library folders"},
    {"method": "GET",    "path": "/api/v3/tag",                      "summary": "Tags"},
    {"method": "GET",    "path": "/api/v3/notification",             "summary": "Configured notifications"},
    {"method": "GET",    "path": "/api/v3/notification/schema",      "summary": "Available notification implementations"},
    {"method": "GET",    "path": "/api/v3/downloadclient",           "summary": "Configured download clients"},
    {"method": "GET",    "path": "/api/v3/downloadclient/schema",    "summary": "Available download client implementations"},
    {"method": "GET",    "path": "/api/v3/indexer",                  "summary": "Configured indexers"},
    {"method": "GET",    "path": "/api/v3/indexer/schema",           "summary": "Available indexer implementations"},
    {"method": "GET",    "path": "/api/v3/metadata",                 "summary": "Configured metadata consumers (Kodi/Emby)"},
    {"method": "GET",    "path": "/api/v3/autoTagging",              "summary": "Auto-tagging rules"},
    {"method": "GET",    "path": "/api/v3/config",                   "summary": "Server config (movie/ui/indexers/downloadclient)"},
]


@mcp.tool()
def radarr_call(method: str, path: str, params: str = "", body: str = "") -> Any:
    """Call ANY Radarr REST operation â€” the generic passthrough that reaches
    the server's entire API surface (~50 endpoints). Use radarr_list_endpoints
    to find an endpoint first.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: Endpoint path. Either "/api/v3/movie" or just "movie" (auto-
            prefixed). Path templates like {id} must already be substituted.
        params: Optional query parameters as JSON object string,
            e.g. '{"tmdbId": 12, "page": 1}'.
        body: Optional request body as a JSON string (POST/PUT).

    Returns the parsed JSON response (or text / null for empty responses).
    WRITES: only call POST/DELETE/PUT after the user has approved the action.
    """
    try:
        return _finish(CLIENT.request(
            method, path,
            params=_parse_json_arg("params", params),
            body=_parse_json_arg("body", body),
        ))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_list_endpoints(search: str = "", method: str = "", limit: int = 100,
                          curated_only: bool = False) -> Any:
    """Search the FULL endpoint catalog â€” pulled live from /api/v3/system/routes
    so it's always accurate for the deployed Radarr version (~470 operations on
    6.3). The master index for radarr_call.

    Each operation is annotated with whether a curated tool wraps it (so you
    can see at a glance what's ergonomic vs generic-only). Radarr publishes
    no OpenAPI document; the live route table is the authoritative source.

    Args:
        search: Case-insensitive substring matched against the path,
            e.g. "movie", "queue", "command", "config".
        method: Filter by HTTP method (GET/POST/PUT/DELETE).
        curated_only: If true, only return operations that have a curated tool.
        limit: Max operations to return (default 100).
    """
    import re
    routes = CLIENT.live_routes() or ENDPOINT_CATALOG
    # Build curated-tool lookup keyed on (METHOD, normalized_lower_path)
    curated_keys = set()
    for (m, p), _tool in CURATED_TOOLS.items():
        norm = re.sub(r'\{[^}]+\}', '{id}', p).lower()
        curated_keys.add((m.upper(), norm))
    annotated = []
    for r in routes:
        m = r["method"].upper()
        p = r["path"]
        norm = re.sub(r'\{[^}]+\}', '{id}', p).lower()
        is_curated = (m, norm) in curated_keys
        annotated.append({"method": m, "path": p, "curated": is_curated})
    if method:
        annotated = [o for o in annotated if o["method"] == method.upper()]
    if curated_only:
        annotated = [o for o in annotated if o["curated"]]
    if search:
        s = search.lower()
        annotated = [o for o in annotated if s in o["path"].lower()]
    # Summary
    n_curated = sum(1 for o in annotated if o["curated"])
    return _finish({
        "matched": len(annotated),
        "matched_curated": n_curated,
        "matched_generic_only": len(annotated) - n_curated,
        "total_live_operations": len(routes),
        "operations": annotated[:limit],
    })


# --------------------------------------------------------------------------- #
# System                                                                      #
# --------------------------------------------------------------------------- #
@mcp.tool()
def radarr_status() -> Any:
    """Server health snapshot: identity, version, queue summary, disk usage,
    health checks, and the most recent activity. Call this first."""
    try:
        status = CLIENT.request("GET", "/api/v3/system/status")
        health = CLIENT.request("GET", "/api/v3/health") or []
        queue_status = CLIENT.request("GET", "/api/v3/queue/status") or {}
        disks = CLIENT.request("GET", "/api/v3/diskspace") or []
        movies = CLIENT.request("GET", "/api/v3/movie") or []
        monitored = sum(1 for m in movies if m.get("monitored"))
        with_file = sum(1 for m in movies if m.get("hasFile"))
        missing = sum(1 for m in movies if m.get("monitored") and not m.get("hasFile"))
        return {
            "appName": status.get("appName"),
            "version": status.get("version"),
            "buildTime": status.get("buildTime"),
            "isAdmin": status.get("isAdmin"),
            "isWindows": status.get("isWindows"),
            "startupPath": status.get("startupPath"),
            "appDataPath": status.get("appDataPath"),
            "osName": status.get("isOsx") and "macOS" or (status.get("isLinux") and "Linux" or (status.get("isWindows") and "Windows" or "?")),
            "totalMovies": len(movies),
            "monitored": monitored,
            "withFile": with_file,
            "monitoredMissing": missing,
            "queue": queue_status,
            "healthWarnings": [h for h in health if h.get("type") == "warning"],
            "healthErrors": [h for h in health if h.get("type") == "error"],
            "disks": [{"path": d.get("path"), "label": d.get("label"),
                       "freeSpace": d.get("freeSpace"), "totalSpace": d.get("totalSpace")}
                      for d in disks],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_logs(level: str = "info", page: int = 1, page_size: int = 25) -> Any:
    """Read application logs.

    Args:
        level: Filter by level (info, warn, error, debug, trace). 'all' disables filter.
        page: 1-based page number.
        page_size: Records per page.
    """
    try:
        params = {"page": page, "pageSize": page_size}
        if level and level.lower() != "all":
            params["level"] = level.capitalize()
        data = CLIENT.request("GET", "/api/v3/log", params=params) or {}
        return _finish({
            "page": data.get("page"),
            "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "records": [{"time": r.get("time"), "level": r.get("level"),
                         "source": r.get("source"), "message": r.get("message")}
                        for r in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_system_tasks() -> Any:
    """Scheduled tasks: name, interval, last run, next run, last result."""
    try:
        data = CLIENT.request("GET", "/api/v3/system/task") or []
        return [{"name": t.get("name"), "interval": t.get("interval"),
                 "lastExecution": t.get("lastExecutionTime"),
                 "nextExecution": t.get("nextExecutionTime"),
                 "lastResult": t.get("lastStartTime")}
                for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_system_backups() -> Any:
    """Database backups: name, time, size, type, download URL."""
    try:
        data = CLIENT.request("GET", "/api/v3/system/backup") or []
        return [{"name": b.get("name"), "type": b.get("type"),
                 "time": b.get("time"), "size": b.get("size"),
                 "id": b.get("id")}
                for b in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def radarr_list_movies(monitored: Optional[bool] = None, has_file: Optional[bool] = None,
                       page: int = 1, page_size: int = 50, compact: bool = True) -> Any:
    """List movies (paged, optionally filtered). Returns compact summaries by
    default â€” set compact=false for the full objects.

    Args:
        monitored: Filter to monitored=true or unmonitored=false. None = no filter.
        has_file: Filter to movies with/without a file. None = no filter.
        page: 1-based page.
        page_size: Records per page (server caps at 200 typically).
        compact: Return trimmed fields (recommended).
    """
    try:
        # Radarr's /movie endpoint ignores standard paging in some versions;
        # filter client-side + slice to keep payloads bounded.
        movies = CLIENT.request("GET", "/api/v3/movie") or []
        if monitored is not None:
            movies = [m for m in movies if bool(m.get("monitored")) == monitored]
        if has_file is not None:
            movies = [m for m in movies if bool(m.get("hasFile")) == has_file]
        total = len(movies)
        start = (page - 1) * page_size
        end = start + page_size
        sliced = movies[start:end]
        return {
            "page": page,
            "pageSize": page_size,
            "totalRecords": total,
            "movies": [compact_movie(m) for m in sliced] if compact else sliced,
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_get_movie(movie_id: int) -> Any:
    """Single movie by Radarr id, with its file attached (if any)."""
    try:
        m = CLIENT.request("GET", f"/api/v3/movie/{movie_id}")
        files = CLIENT.request("GET", "/api/v3/movieFile", params={"movieId": movie_id}) or []
        m["movieFiles"] = files
        return m
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_lookup_movies(term: str, limit: int = 10) -> Any:
    """Search TMDB for movies to ADD. Use this before radarr_add_movie to
    get the full lookup object (which the add needs).

    Args:
        term: Search string (title, partial OK).
        limit: Cap results returned (server may return many).
    """
    try:
        if not term or not term.strip():
            raise RadarrError("term is required")
        data = CLIENT.request("GET", "/api/v3/movie/lookup", params={"term": term}) or []
        return _finish([{
            "title": m.get("title"),
            "tmdbId": m.get("tmdbId"),
            "imdbId": m.get("imdbId"),
            "year": m.get("year"),
            "overview": (m.get("overview") or "")[:240],
            "inCinemas": m.get("inCinemas"),
            "runtime": m.get("runtime"),
            "genres": m.get("genres", []),
            "ratings": {k: v.get("value") for k, v in (m.get("ratings") or {}).items() if isinstance(v, dict)},
            "alreadyInLibrary": m.get("id") is not None,
            "id": m.get("id"),
        } for m in data[:limit]])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_add_movie(tmdb_id: int, quality_profile_id: int, root_folder_path: str,
                     monitored: bool = True, minimum_availability: str = "released",
                     search_for_movie: bool = False, tags: Optional[list] = None,
                     confirm: bool = False) -> Any:
    """Add a movie to the library by TMDB id. Performs a lookup then a POST.
    WRITES: confirm-gated.

    Args:
        tmdb_id: TheMovieDB id (from radarr_lookup_movies).
        quality_profile_id: Profile id (see radarr_quality_profiles).
        root_folder_path: Library root path (see radarr_root_folders); must match exactly.
        monitored: Monitor this movie for releases.
        minimum_availability: Announced | InCinemas | Released (default Released).
        search_for_movie: Trigger an initial search after adding (default false).
        tags: Optional list of tag ids.
        confirm: Must be true â€” this adds to the live library.
    """
    try:
        if not confirm:
            return _need_confirm(
                f"add TMDB {tmdb_id} to '{root_folder_path}' "
                f"(profile {quality_profile_id}, monitored={monitored}, search={search_for_movie})"
            )
        # Lookup the full record first â€” POST needs the full object.
        lookup = CLIENT.request("GET", "/api/v3/movie/lookup/tmdb", params={"tmdbId": tmdb_id})
        if not isinstance(lookup, dict):
            raise RadarrError(f"TMDB lookup returned no record for {tmdb_id}")
        # If already in library, server returns the existing record (with id).
        if lookup.get("id"):
            return {"already_in_library": True, "movie": compact_movie(lookup)}
        body = dict(lookup)
        body.update({
            "qualityProfileId": quality_profile_id,
            "rootFolderPath": root_folder_path,
            "monitored": monitored,
            "minimumAvailability": minimum_availability,
            "addOptions": {
                "searchForMovie": search_for_movie,
                "monitor": "movieOnly" if monitored else "none",
            },
        })
        if tags:
            body["tags"] = tags
        created = CLIENT.request("POST", "/api/v3/movie", body=body)
        return {"added": True, "movie": compact_movie(created) if isinstance(created, dict) else created}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_update_movie(movie_id: int, patch: str, confirm: bool = False) -> Any:
    """Update a movie SAFELY: GETs the current object, merges the patch keys
    over it, PUTs the full object back. (Radarr expects the full object on PUT;
    omitted fields reset to defaults.)

    Args:
        movie_id: Radarr movie id.
        patch: JSON object string with just the keys to change,
            e.g. '{"monitored": false}'.
        confirm: Must be true â€” this mutates the live library.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise RadarrError("patch must be a non-empty JSON object")
        current = CLIENT.request("GET", f"/api/v3/movie/{movie_id}")
        if not confirm:
            return _need_confirm(
                f"update movie {movie_id} ({current.get('title')}) "
                f"keys {list(change)} (current values: "
                f"{ {k: current.get(k) for k in change} })"
            )
        merged = {**current, **change}
        updated = CLIENT.request("PUT", f"/api/v3/movie/{movie_id}", body=merged)
        return {"updated": True, "movie": compact_movie(updated) if isinstance(updated, dict) else updated}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_delete_movie(movie_id: int, delete_files: bool = False,
                        add_import_exclusion: bool = False, confirm: bool = False) -> Any:
    """Delete a movie. WRITES: confirm-gated. By default only removes from the
    library; the file stays on disk unless delete_files=true.

    Args:
        movie_id: Radarr movie id.
        delete_files: Also delete the movie file from disk (irreversible).
        add_import_exclusion: Add to import exclusion list so it won't re-add.
        confirm: Must be true â€” irreversible (especially with delete_files).
    """
    try:
        current = CLIENT.request("GET", f"/api/v3/movie/{movie_id}")
        if not confirm:
            return _need_confirm(
                f"delete movie {movie_id} ({current.get('title')}) "
                f"delete_files={delete_files}, "
                f"add_import_exclusion={add_import_exclusion}"
            )
        params = {}
        if delete_files:
            params["deleteFiles"] = "true"
        if add_import_exclusion:
            params["addImportExclusion"] = "true"
        CLIENT.request("DELETE", f"/api/v3/movie/{movie_id}", params=params or None)
        return {"deleted": True, "movie_id": movie_id, "title": current.get("title")}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_movie_files(movie_id: int) -> Any:
    """List the media files attached to a movie (path, size, quality, codecs)."""
    try:
        files = CLIENT.request("GET", "/api/v3/movieFile", params={"movieId": movie_id}) or []
        return [{
            "id": f.get("id"), "path": f.get("path"), "size": f.get("size"),
            "quality": (f.get("quality") or {}).get("quality", {}).get("name"),
            "languages": [l.get("name") for l in (f.get("languages") or [])],
            "edition": f.get("edition"),
            "dateAdded": f.get("dateAdded"),
            "mediaInfo": f.get("mediaInfo"),
        } for f in files]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_collections(monitored_only: bool = False) -> Any:
    """Movie collections tracked by Radarr (e.g. 'Lord of the Rings Collection')."""
    try:
        data = CLIENT.request("GET", "/api/v3/collection") or []
        out = [{"id": c.get("id"), "name": c.get("name"),
                "tmdbId": c.get("tmdbId"),
                "monitored": c.get("monitored"),
                "movieCount": len(c.get("movies") or []),
                "missingMovies": c.get("missingMovies"),
                "hasFileMovies": sum(1 for m in (c.get("movies") or []) if m.get("hasFile"))}
               for c in data]
        if monitored_only:
            out = [c for c in out if c["monitored"]]
        return out
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Activity / wanted / calendar                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
def radarr_calendar(start: str = "", end: str = "", tags: str = "") -> Any:
    """Movies with a release date (theatrical/digital/physical) in a range.

    Args:
        start: ISO date (YYYY-MM-DD). Defaults to today.
        end: ISO date. Defaults to 14 days from today.
        tags: Optional comma-separated tag ids to filter by.
    """
    import datetime as dt
    try:
        today = dt.date.today()
        params = {
            "start": start or today.isoformat(),
            "end": end or (today + dt.timedelta(days=14)).isoformat(),
        }
        if tags:
            params["tags"] = tags
        data = CLIENT.request("GET", "/api/v3/calendar", params=params) or []
        return _finish([compact_movie(m) for m in data])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_queue(include_unknown: bool = True, include_completed: bool = False) -> Any:
    """Current download queue: grabbed, importing, downloading, failed, delayed."""
    try:
        params = {}
        if include_unknown:
            params["includeUnknown"] = "true"
        if include_completed:
            params["includeCompleted"] = "true"
        data = CLIENT.request("GET", "/api/v3/queue", params=params) or {}
        records = data.get("records") or []
        return {
            "totalRecords": data.get("totalRecords", len(records)),
            "queue": [{
                "id": r.get("id"),
                "movieId": r.get("movieId"),
                "movie": (r.get("movie") or {}).get("title"),
                "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
                "status": r.get("status"),
                "trackedDownloadStatus": r.get("trackedDownloadStatus"),
                "trackedDownloadState": r.get("trackedDownloadState"),
                "statusMessages": r.get("statusMessages"),
                "size": r.get("size"),
                "sizeleft": r.get("sizeleft"),
                "timeleft": r.get("timeleft"),
                "protocol": r.get("protocol"),
                "downloadId": r.get("downloadId"),
                "downloadClient": r.get("downloadClient"),
                "outputPath": r.get("outputPath"),
            } for r in records],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_history(movie_id: Optional[int] = None, page: int = 1,
                   page_size: int = 25, event_type: str = "") -> Any:
    """Recent activity (grabbed / import / failed / etc.).

    Args:
        movie_id: Filter to one movie.
        page: 1-based page.
        page_size: Records per page.
        event_type: 'grabbed' | 'downloadFolderImported' | 'downloadFailed' | etc.
    """
    try:
        params = {"page": page, "pageSize": page_size}
        if movie_id:
            params["movieId"] = movie_id
        if event_type:
            params["eventType"] = event_type
        data = CLIENT.request("GET", "/api/v3/history", params=params) or {}
        return _finish({
            "page": data.get("page"),
            "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "records": [{"date": r.get("date"), "eventType": r.get("eventType"),
                         "movie": (r.get("movie") or {}).get("title"),
                         "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
                         "data": r.get("data")}
                        for r in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_wanted_missing(sort_key: str = "movies.sortTitle", page: int = 1,
                          page_size: int = 25, monitored: bool = True) -> Any:
    """Monitored movies without a file yet (sorted by title or by date)."""
    try:
        params = {"sortKey": sort_key, "sortDir": "asc",
                  "page": page, "pageSize": page_size}
        if monitored:
            params["monitored"] = "true"
        data = CLIENT.request("GET", "/api/v3/wanted/missing", params=params) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "movies": [compact_movie(m) for m in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_wanted_cutoff(sort_key: str = "movies.sortTitle", page: int = 1,
                         page_size: int = 25) -> Any:
    """Movies that have a file, but below the quality cutoff (upgradeable)."""
    try:
        params = {"sortKey": sort_key, "sortDir": "asc",
                  "page": page, "pageSize": page_size}
        data = CLIENT.request("GET", "/api/v3/wanted/cutoff", params=params) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "movies": [compact_movie(m) for m in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_blocklist(page: int = 1, page_size: int = 25) -> Any:
    """Releases Radarr auto-rejected (stuck/failed/poor)."""
    try:
        data = CLIENT.request("GET", "/api/v3/blocklist", params={"page": page, "pageSize": page_size}) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "records": [{"date": r.get("date"), "source": r.get("source"),
                         "movie": (r.get("movie") or {}).get("title"),
                         "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
                         "indexer": r.get("indexer"),
                         "message": (r.get("message") or (r.get("data") or {}).get("message"))}
                        for r in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Commands (trigger async jobs)                                               #
# --------------------------------------------------------------------------- #
RADARR_COMMANDS = {
    # See Radarr source: src/NzbDrone.Core/MediaFiles/MediaFileController.cs etc.
    "RefreshMovie": "Refresh metadata + disk scan for movieIds (or all if absent)",
    "MoviesSearch": "Search indexers for monitored missing movies (movieIds optional)",
    "DownloadedMoviesScan": "Scan drone factory / drone folder for completed downloads",
    "RenameFiles": "Rename files for movieIds (uses renaming config)",
    "RenameMovie": "Rename files for movieIds (alias)",
    "Backup": "Trigger an immediate database backup",
    "ApplicationUpdate": "Check for + install an app update (admin only)",
    "RefreshMonitoredDownloads": "Sync state with download clients",
    "MissingMoviesSearch": "Search for all monitored missing movies",
}


@mcp.tool()
def radarr_command(name: str, movie_ids: Optional[list] = None,
                   confirm: bool = False, **extra: Any) -> Any:
    """Trigger a Radarr async command (POST /command). Returns the created job.
    WRITES: confirm-gated (this triggers downloads, scans, renames â€” active work).

    Common names: RefreshMovie, MoviesSearch, DownloadedMoviesScan, RenameMovie,
    Backup, ApplicationUpdate, RefreshMonitoredDownloads, MissingMoviesSearch.

    Args:
        name: Command name (see radarr list of commands in the skill).
        movie_ids: Optional list of movie ids the command applies to.
        confirm: Must be true â€” this triggers active work.
        extra: Pass-through extra params (e.g. sendUpdatesToClient=true).
    """
    try:
        if name not in RADARR_COMMANDS:
            raise RadarrError(
                f"Unknown command '{name}'. Known: {', '.join(sorted(RADARR_COMMANDS))}"
            )
        if not confirm:
            scope = f" for movieIds {movie_ids}" if movie_ids else " (scope: all/library-wide)"
            return _need_confirm(f"run command '{name}'{scope}")
        body: dict = {"name": name}
        if movie_ids is not None:
            # Radarr expects movieIds for RefreshMovie/MoviesSearch/etc.
            body["movieIds"] = list(movie_ids)
        body.update(extra)
        return CLIENT.request("POST", "/api/v3/command", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_command_status(command_id: int) -> Any:
    """Status of one command (poll after radarr_command)."""
    try:
        return CLIENT.request("GET", f"/api/v3/command/{command_id}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_search_movie(movie_id: int, confirm: bool = False) -> Any:
    """Convenience: trigger MoviesSearch for one movie."""
    return radarr_command("MoviesSearch", movie_ids=[movie_id], confirm=confirm)


@mcp.tool()
def radarr_refresh_movie(movie_id: int, confirm: bool = False) -> Any:
    """Convenience: trigger RefreshMovie for one movie (re-scan disk + refresh metadata)."""
    return radarr_command("RefreshMovie", movie_ids=[movie_id], confirm=confirm)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
@mcp.tool()
def radarr_quality_profiles() -> Any:
    """Quality profiles (e.g. HD-1080p, Any). Needed to add movies."""
    try:
        data = CLIENT.request("GET", "/api/v3/qualityProfile") or []
        return [{"id": p.get("id"), "name": p.get("name"),
                 "upgradeAllowed": p.get("upgradeAllowed"),
                 "cutoff": p.get("cutoff"),
                 "items": [(it.get("quality") or {}).get("name") for it in p.get("items", [])
                           if it.get("allowed")]}
                for p in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_root_folders() -> Any:
    """Root library folders (needed for add_movie). Reports free space too."""
    try:
        data = CLIENT.request("GET", "/api/v3/rootfolder") or []
        return [{"id": r.get("id"), "path": r.get("path"),
                 "freeSpace": r.get("freeSpace"), "unmappedFolders": r.get("unmappedFolders")}
                for r in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_tags() -> Any:
    """All tags (id + label)."""
    try:
        data = CLIENT.request("GET", "/api/v3/tag") or []
        return [{"id": t.get("id"), "label": t.get("label")} for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_languages() -> Any:
    """Languages known to Radarr (name + id)."""
    try:
        data = CLIENT.request("GET", "/api/v3/language") or []
        return [{"id": l.get("id"), "name": l.get("name")} for l in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_notifications() -> Any:
    """Configured notifications (Kodi/Emby/Plex/Discord/webhook/etc.)."""
    try:
        data = CLIENT.request("GET", "/api/v3/notification") or []
        return [{"id": n.get("id"), "name": n.get("name"),
                 "implementation": n.get("implementation"),
                 "configContract": n.get("configContract"),
                 "supportsOnGrab": n.get("supportsOnGrab"),
                 "supportsOnDownload": n.get("supportsOnDownload"),
                 "tags": n.get("tags")}
                for n in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_download_clients() -> Any:
    """Configured download clients (SABnzbd, qBittorrent, etc.)."""
    try:
        data = CLIENT.request("GET", "/api/v3/downloadclient") or []
        return [{"id": c.get("id"), "name": c.get("name"),
                 "implementation": c.get("implementation"),
                 "enable": c.get("enable"), "priority": c.get("priority"),
                 "protocol": c.get("protocol")}
                for c in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_indexers() -> Any:
    """Configured indexers / trackers."""
    try:
        data = CLIENT.request("GET", "/api/v3/indexer") or []
        return [{"id": i.get("id"), "name": i.get("name"),
                 "implementation": i.get("implementation"),
                 "enable": i.get("enable"), "protocol": i.get("protocol"),
                 "priority": i.get("priority")}
                for i in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_import_lists() -> Any:
    """Configured import lists (trakt, lists, etc.)."""
    try:
        data = CLIENT.request("GET", "/api/v3/importlist") or []
        return [{"id": l.get("id"), "name": l.get("name"),
                 "implementation": l.get("implementation"),
                 "enable": l.get("enable"),
                 "monitor": l.get("monitor"),
                 "rootFolderPath": l.get("rootFolderPath")}
                for l in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_custom_formats() -> Any:
    """Custom formats defined (for release matching/scoring)."""
    try:
        data = CLIENT.request("GET", "/api/v3/customFormat") or []
        return [{"id": c.get("id"), "name": c.get("name"),
                 "includeCustomFormatWhenRenaming": c.get("includeCustomFormatWhenRenaming")}
                for c in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Round 2: high-value gaps from the live-route audit                           #
# (queue mgmt, parse, log/filesystem, config sections, tag CRUD, blocklist,    #
#  system restart/shutdown, manual import, more reads)                         #
# --------------------------------------------------------------------------- #
@mcp.tool()
def radarr_queue_delete(queue_id: int, blacklist: bool = False,
                        remove_from_client: bool = False,
                        confirm: bool = False) -> Any:
    """Remove a single item from the active queue. WRITES: confirm-gated.

    Args:
        queue_id: The queue record id (from radarr_queue).
        blacklist: Add the release to the blocklist so it won't be re-grabbed.
        remove_from_client: Also delete the download from the download client
            (SABnzbd/qBittorrent/etc.). Irreversible â€” use with care.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(
                f"delete queue item {queue_id} "
                f"(blacklist={blacklist}, remove_from_client={remove_from_client})"
            )
        params = {}
        if blacklist: params["blacklist"] = "true"
        if remove_from_client: params["removeFromClient"] = "true"
        CLIENT.request("DELETE", f"/api/v3/queue/{queue_id}", params=params or None)
        return {"deleted": True, "queue_id": queue_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_queue_grab(queue_id: int, confirm: bool = False) -> Any:
    """Re-grab a release for an aggregated queue item (search indexers for a
    new copy). WRITES: confirm-gated.

    Args:
        queue_id: The queue record id.
        confirm: Must be true â€” triggers a download.
    """
    try:
        if not confirm:
            return _need_confirm(f"re-grab queue item {queue_id}")
        return CLIENT.request("POST", f"/api/v3/queue/grab/{queue_id}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_movies_bulk_edit(movie_ids: list, monitored: Optional[bool] = None,
                             quality_profile_id: Optional[int] = None,
                             minimum_availability: Optional[str] = None,
                             tags: Optional[list] = None,
                             apply_tags: str = "add",
                             move_files: bool = False,
                             confirm: bool = False) -> Any:
    """Bulk-edit multiple movies in one operation. WRITES: confirm-gated.
    Only the supplied fields are changed.

    Args:
        movie_ids: List of Radarr movie ids.
        monitored: Set monitored state (None = leave unchanged).
        quality_profile_id: Set quality profile (None = unchanged).
        minimum_availability: announced|inCinemas|released.
        tags: List of tag ids (with apply_tags).
        apply_tags: add | remove | replace | sync (default add).
        move_files: Move files when path/quality changes.
        confirm: Must be true.
    """
    try:
        if not movie_ids:
            raise RadarrError("movie_ids must be non-empty")
        if not confirm:
            changes = []
            if monitored is not None: changes.append(f"monitored={monitored}")
            if quality_profile_id is not None: changes.append(f"qualityProfileId={quality_profile_id}")
            if minimum_availability: changes.append(f"minimumAvailability={minimum_availability}")
            return _need_confirm(f"bulk-edit movies {movie_ids}: {', '.join(changes) or 'no changes'}")
        body: dict = {"movieIds": list(movie_ids), "moveFiles": bool(move_files)}
        if monitored is not None: body["monitored"] = bool(monitored)
        if quality_profile_id is not None: body["qualityProfileId"] = int(quality_profile_id)
        if minimum_availability: body["minimumAvailability"] = minimum_availability
        if tags is not None:
            body["tags"] = list(tags)
            body["applyTags"] = apply_tags
        return CLIENT.request("PUT", "/api/v3/movie/editor", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_parse(title: str) -> Any:
    """Parse a release title to see what movie + quality Radarr would match it
    to. READ-ONLY â€” the cheapest way to answer "would this release work?"

    Args:
        title: A release string like "Dune.2021.2160p.UHD.BluRay.x265-GROUP".
    """
    try:
        return CLIENT.request("GET", "/api/v3/parse", params={"title": title})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_log_files() -> Any:
    """List the on-disk log files (and update-log files) with sizes."""
    try:
        data = CLIENT.request("GET", "/api/v3/log/file") or []
        return [{"filename": f.get("name"), "lastWriteTime": f.get("lastWriteTime"),
                 "path": f.get("path"), "size": f.get("contentsLength")}
                for f in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_filesystem(path: str = "/", include_files: bool = False,
                      allow_folders_without_trailing_slash: bool = False) -> Any:
    """Browse the server's filesystem (used when configuring root folders)."""
    try:
        params = {"path": path}
        if include_files: params["includeFiles"] = "true"
        if allow_folders_without_trailing_slash: params["allowFoldersWithoutTrailingSlashes"] = "true"
        data = CLIENT.request("GET", "/api/v3/filesystem", params=params) or {}
        return {
            "path": data.get("path"),
            "parent": data.get("parent"),
            "directories": [{"name": d.get("name"), "path": d.get("path")}
                            for d in (data.get("directories") or [])],
            "files": [{"name": f.get("name"), "path": f.get("path"), "size": f.get("size")}
                      for f in (data.get("files") or [])],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_history_since(since: str, event_type: str = "") -> Any:
    """History since an ISO timestamp (lighter than paged history).

    Args:
        since: ISO 8601 timestamp, e.g. "2026-07-19T00:00:00Z".
        event_type: Optional filter (grabbed|downloadFolderImported|...).
    """
    try:
        params = {"since": since}
        if event_type: params["eventType"] = event_type
        return _finish(CLIENT.request("GET", "/api/v3/history/since", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_rename_preview(movie_ids: list) -> Any:
    """Preview what files WOULD be renamed, without doing it. READ-ONLY.

    Note: Radarr's /rename endpoint accepts a SINGLE movieId per request; this
    tool loops over the supplied ids and returns a merged list.
    """
    try:
        if not movie_ids:
            raise RadarrError("movie_ids must be non-empty")
        out = []
        for mid in movie_ids:
            res = CLIENT.request("GET", "/api/v3/rename", params={"movieId": int(mid)}) or []
            for r in res:
                r["_movieId"] = mid
                out.append(r)
        return out
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_quality_definitions() -> Any:
    """Quality definitions (size-by-quality matrix Radarr uses for indexer searches)."""
    try:
        return CLIENT.request("GET", "/api/v3/qualityDefinition")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_delay_profiles() -> Any:
    """Delay profiles (how long Radarr waits before grabbing a release)."""
    try:
        return CLIENT.request("GET", "/api/v3/delayprofile")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_remote_path_mappings() -> Any:
    """Remote path mappings (Docker path translation between download client and Radarr)."""
    try:
        return CLIENT.request("GET", "/api/v3/remotepathmapping")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_release_profiles() -> Any:
    """Release profiles (must-contain / must-not-contain rules for release selection)."""
    try:
        return CLIENT.request("GET", "/api/v3/releaseprofile")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_import_exclusions() -> Any:
    """Import exclusions (movies that will never be auto-added from import lists)."""
    try:
        return CLIENT.request("GET", "/api/v3/exclusions")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_auto_tagging() -> Any:
    """Auto-tagging rules (tags auto-applied when a movie matches a rule)."""
    try:
        return CLIENT.request("GET", "/api/v3/autoTagging")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_tag_details() -> Any:
    """All tags with the counts of movies / delay profiles / etc. that use each."""
    try:
        data = CLIENT.request("GET", "/api/v3/tag/detail") or []
        return [{"id": t.get("id"), "label": t.get("label"),
                 "movieCount": len(t.get("movieIds") or [])}
                for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_config_section(section: str) -> Any:
    """Read a specific config section. READ-ONLY.

    Args:
        section: One of: host, ui, mediamanagement, indexer, downloadclient,
            metadata, importlist, naming.
    """
    try:
        if not section:
            raise RadarrError("section is required (host, ui, mediamanagement, indexer, "
                              "downloadclient, metadata, importlist, naming)")
        return CLIENT.request("GET", f"/api/v3/config/{section}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_update_config_section(section: str, patch: str,
                                  confirm: bool = False) -> Any:
    """Update a config section SAFELY: GET current, merge patch, PUT full.
    WRITES: confirm-gated.

    Args:
        section: host, ui, mediamanagement, indexer, downloadclient, metadata,
            importlist, naming.
        patch: JSON object string with keys to change.
        confirm: Must be true â€” affects live server behavior.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise RadarrError("patch must be a non-empty JSON object")
        if not confirm:
            current = CLIENT.request("GET", f"/api/v3/config/{section}")
            return _need_confirm(
                f"update /config/{section} keys {list(change)} "
                f"(current values: { {k: current.get(k) for k in change} })"
            )
        current = CLIENT.request("GET", f"/api/v3/config/{section}")
        merged = {**current, **change}
        return CLIENT.request("PUT", f"/api/v3/config/{section}", body=merged)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_blocklist_delete(blocklist_id: int, confirm: bool = False) -> Any:
    """Remove one entry from the blocklist. WRITES: confirm-gated."""
    try:
        if not confirm:
            return _need_confirm(f"delete blocklist entry {blocklist_id}")
        CLIENT.request("DELETE", f"/api/v3/blocklist/{blocklist_id}")
        return {"deleted": True, "blocklist_id": blocklist_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_tag_create(label: str, confirm: bool = False) -> Any:
    """Create a new tag. WRITES: confirm-gated."""
    try:
        if not label or not label.strip():
            raise RadarrError("label is required")
        if not confirm:
            return _need_confirm(f"create tag '{label}'")
        return CLIENT.request("POST", "/api/v3/tag", body={"label": label.strip()})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_tag_delete(tag_id: int, confirm: bool = False) -> Any:
    """Delete a tag. WRITES: confirm-gated. Tags in use will be unassigned."""
    try:
        if not confirm:
            return _need_confirm(f"delete tag {tag_id}")
        CLIENT.request("DELETE", f"/api/v3/tag/{tag_id}")
        return {"deleted": True, "tag_id": tag_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_manual_import(folder: str, import_mode: str = "move",
                         confirm: bool = False) -> Any:
    """Perform a manual import for files in a folder. WRITES: confirm-gated.

    Args:
        folder: The server-side path to scan (e.g. /volume2/Downloads/Movies).
        import_mode: 'move' (default) | 'copy'.
        confirm: Must be true â€” moves/copy files into the library.
    """
    try:
        if not folder:
            raise RadarrError("folder is required")
        if not confirm:
            return _need_confirm(f"manual import {folder} (mode={import_mode})")
        # Two-step: list candidates (GET manualimport), then POST them
        candidates = CLIENT.request("GET", "/api/v3/manualimport",
                                    params={"folder": folder, "filterExistingFiles": "true"}) or []
        if not candidates:
            return {"imported": 0, "note": f"no candidates found in {folder}"}
        body = []
        for c in candidates:
            c["importMode"] = import_mode
            body.append(c)
        result = CLIENT.request("POST", "/api/v3/manualimport", body=body)
        return {"imported": len(body), "result": result}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_provider_test(provider_type: str, definition: str) -> Any:
    """Test a notification / downloadclient / indexer / importlist / metadata
    configuration WITHOUT saving. Useful when setting up a new provider.
    WRITE (no save) but no confirm needed â€” it just makes a live test call.

    Args:
        provider_type: One of notification, downloadclient, indexer,
            importlist, metadata.
        definition: Full provider definition object as JSON string.
    """
    try:
        pt = provider_type.lower().strip()
        if pt not in ("notification", "downloadclient", "indexer",
                      "importlist", "metadata"):
            raise RadarrError(f"provider_type must be one of notification, "
                              f"downloadclient, indexer, importlist, metadata")
        body = _parse_json_arg("definition", definition)
        if not isinstance(body, dict):
            raise RadarrError("definition must be a JSON object")
        return CLIENT.request("POST", f"/api/v3/{pt}/test", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_system_routes() -> Any:
    """Return the LIVE route table (~470 operations) â€” Radarr's own introspection
    of its full API surface. Useful for finding endpoints not yet in curated tools.
    """
    try:
        return _finish(CLIENT.live_routes())
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_system_restart(confirm: bool = False, acknowledge: str = "") -> Any:
    """Restart the Radarr service/process.

    DOUBLY GATED â€” requires confirm=true AND acknowledge='restart' (typed).
    Interrupts active downloads/scans. Only invoke after explicit owner
    approval.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'restart'.
    """
    try:
        if not confirm or acknowledge != "restart":
            return {
                "confirmation_required": True,
                "note": ("Restarting Radarr interrupts active downloads and scans. "
                         "Re-run with confirm=true AND acknowledge='restart'."),
            }
        CLIENT.request("POST", "/api/v3/system/restart")
        return {"restart_initiated": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_system_shutdown(confirm: bool = False, acknowledge: str = "") -> Any:
    """Shut down Radarr. The service/container must be restarted externally.

    DOUBLY GATED â€” requires confirm=true AND acknowledge='shutdown' (typed).
    Same hardening as SABnzbd shutdown â€” Radarr honors this literally and
    won't auto-restart depending on DSM.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'shutdown'.
    """
    try:
        if not confirm or acknowledge != "shutdown":
            return {
                "confirmation_required": True,
                "note": ("Shutting down Radarr takes the app offline until "
                         "manually restarted. Re-run with confirm=true AND "
                         "acknowledge='shutdown'."),
            }
        CLIENT.request("POST", "/api/v3/system/shutdown")
        return {"shutdown_initiated": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_crud(resource: str, action: str, id: Optional[int] = None,
                data: str = "", confirm: bool = False) -> Any:
    """Generic CRUD wrapper for Radarr resources that follow the standard
    list/get/create/update/delete/bulk pattern. Use this for the long tail of
    config entities â€” notifications, download clients, indexers, import lists,
    metadata, quality profiles, custom formats, delay/release profiles, root
    folders, remote path mappings, auto-tagging, custom filters, exclusions.

    Most resources support: list, get, create, update, delete. Some support
    bulk_update / bulk_delete (POST/PUT/DELETE on /{resource}/bulk). Providers
    (notification / downloadclient / indexer / importlist / metadata) support
    schema (the implementation templates) and testall (test every configured
    instance).

    Args:
        resource: One of: notification, downloadclient, indexer, importlist,
            metadata, qualityprofile, customformat, delayprofile,
            releaseprofile, rootfolder, remotepathmapping, autoTagging,
            customFilter, exclusions.
        action: One of: list, get, schema, create, update, delete,
            bulk_update, bulk_delete, testall.
        id: Resource id (required for get/update/delete; ignored otherwise).
        data: JSON body string. Required for create/update/bulk_update. For
            bulk_delete pass '{"ids": [1, 2, 3]}'. For create/update of a
            provider (notification/downloadclient/etc.), GET the schema first
            to see required fields, then construct the definition. Example
            for create: data='{"name":"Discord","implementation":"Discord",
            "configContract":"discordSettings","fields":[{"name":"webhookUrl",
            "value":"https://discord.com/api/webhooks/..."}],
            "supportsOnGrab":true}'.
        confirm: Must be true for create/update/delete/bulk_* (mutates live
            config).
    """
    try:
        RESOURCE_ALIASES = {
            "qualityprofile": "qualityProfile",
            "customformat": "customFormat",
            "delayprofile": "delayProfile",
            "releaseprofile": "releaseProfile",
            "rootfolder": "rootFolder",
            "remotepathmapping": "remotePathMapping",
            "autotagging": "autoTagging",
            "customfilter": "customFilter",
            "exclusions": "exclusions",
        }
        res_lc = (resource or "").strip().lower()
        if not res_lc:
            raise RadarrError("resource is required")
        res = RESOURCE_ALIASES.get(res_lc, res_lc)
        valid_actions = ("list", "get", "schema", "create", "update", "delete",
                         "bulk_update", "bulk_delete", "testall")
        act = (action or "").strip().lower()
        if act not in valid_actions:
            raise RadarrError(f"action must be one of {valid_actions}; got {action!r}")
        # Reads â€” no confirm needed
        if act == "list":
            return _finish(CLIENT.request("GET", f"/api/v3/{res}"))
        if act == "schema":
            return CLIENT.request("GET", f"/api/v3/{res}/schema")
        if act == "get":
            if id is None:
                raise RadarrError("id is required for get")
            return CLIENT.request("GET", f"/api/v3/{res}/{int(id)}")
        if act == "testall":
            return CLIENT.request("POST", f"/api/v3/{res}/testall")
        # Writes â€” confirm-gated
        if not confirm:
            return _need_confirm(f"{act} {resource} id={id} data={data[:200]}")
        body = _parse_json_arg("data", data)
        if act == "create":
            if body is None:
                raise RadarrError("data is required for create")
            return CLIENT.request("POST", f"/api/v3/{res}", body=body)
        if act == "update":
            if id is None:
                raise RadarrError("id is required for update")
            if body is None:
                raise RadarrError("data is required for update (full object)")
            return CLIENT.request("PUT", f"/api/v3/{res}/{int(id)}", body=body)
        if act == "delete":
            if id is None:
                raise RadarrError("id is required for delete")
            CLIENT.request("DELETE", f"/api/v3/{res}/{int(id)}")
            return {"deleted": True, "resource": resource, "id": int(id)}
        if act == "bulk_update":
            if not isinstance(body, list):
                raise RadarrError("data must be a JSON array of full objects for bulk_update")
            return CLIENT.request("PUT", f"/api/v3/{res}/bulk", body=body)
        if act == "bulk_delete":
            if not isinstance(body, dict) or "ids" not in body:
                raise RadarrError("data must be {\"ids\": [...]} for bulk_delete")
            return CLIENT.request("DELETE", f"/api/v3/{res}/bulk", body=body)
        raise RadarrError(f"unhandled action {act}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_blocklist_bulk_delete(ids: list, confirm: bool = False) -> Any:
    """Remove multiple entries from the blocklist in one call. WRITES: confirm-gated."""
    try:
        if not ids:
            raise RadarrError("ids must be non-empty")
        if not confirm:
            return _need_confirm(f"bulk-delete blocklist ids {ids}")
        return CLIENT.request("DELETE", "/api/v3/blocklist/bulk", body={"ids": list(ids)})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_movies_bulk_delete(movie_ids: list, delete_files: bool = False,
                               add_import_exclusion: bool = False,
                               confirm: bool = False) -> Any:
    """Delete multiple movies in one call. WRITES: confirm-gated. IRREVERSIBLE
    if delete_files=True.

    Args:
        movie_ids: List of Radarr movie ids.
        delete_files: Also delete the movie files from disk.
        add_import_exclusion: Add to import-exclusion list.
        confirm: Must be true.
    """
    try:
        if not movie_ids:
            raise RadarrError("movie_ids must be non-empty")
        if not confirm:
            return _need_confirm(
                f"bulk-delete movies {movie_ids} "
                f"(delete_files={delete_files}, add_import_exclusion={add_import_exclusion})"
            )
        body: dict = {"movieIds": list(movie_ids),
                      "addImportExclusion": bool(add_import_exclusion),
                      "deleteFiles": bool(delete_files)}
        return CLIENT.request("DELETE", "/api/v3/movie/editor", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_queue_bulk_delete(queue_ids: list, blacklist: bool = False,
                              remove_from_client: bool = False,
                              confirm: bool = False) -> Any:
    """Remove multiple items from the queue in one call. WRITES: confirm-gated.

    Args:
        queue_ids: List of queue record ids.
        blacklist: Add releases to blocklist so they won't be re-grabbed.
        remove_from_client: Also delete downloads from the download client.
        confirm: Must be true.
    """
    try:
        if not queue_ids:
            raise RadarrError("queue_ids must be non-empty")
        if not confirm:
            return _need_confirm(
                f"bulk-delete queue ids {queue_ids} "
                f"(blacklist={blacklist}, remove_from_client={remove_from_client})"
            )
        body: dict = {"ids": list(queue_ids),
                      "blacklist": bool(blacklist),
                      "removeFromClient": bool(remove_from_client)}
        return CLIENT.request("DELETE", "/api/v3/queue/bulk", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_provider_action(provider_type: str, id: int, action_name: str,
                            confirm: bool = False, **extra: Any) -> Any:
    """Invoke a provider-specific action (e.g. importlist "refreshMovies" /
    metadata "getMovies" / notification "test"). WRITE: confirm-gated.

    Args:
        provider_type: notification, downloadclient, indexer, importlist, metadata.
        id: Provider id.
        action_name: The action name (per the provider's contract).
        confirm: Must be true.
        extra: Pass-through extra params.
    """
    try:
        pt = (provider_type or "").lower().strip()
        if pt not in ("notification", "downloadclient", "indexer",
                      "importlist", "metadata"):
            raise RadarrError(f"provider_type must be notification/downloadclient/"
                              f"indexer/importlist/metadata")
        if not action_name:
            raise RadarrError("action_name is required")
        if not confirm:
            return _need_confirm(f"action '{action_name}' on {pt}/{id}")
        body = {"name": action_name, **extra}
        return CLIENT.request("POST", f"/api/v3/{pt}/action/{int(id)}", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def radarr_calendar_ics(start: str = "", end: str = "", tags: str = "",
                        unmonitored: bool = False) -> Any:
    """Fetch the iCalendar feed of upcoming movie releases (the .ics payload).
    Returns the raw iCalendar text â€” useful for importing into a calendar app.

    Args:
        start: YYYY-MM-DD (default 7 days ago).
        end: YYYY-MM-DD (default +90 days).
        tags: Optional comma-separated tag filter.
        unmonitored: Include unmonitored movies.
    """
    import datetime as dt
    try:
        today = dt.date.today()
        params = {
            "start": start or (today - dt.timedelta(days=7)).isoformat(),
            "end": end or (today + dt.timedelta(days=90)).isoformat(),
        }
        if tags: params["tags"] = tags
        if unmonitored: params["unmonitored"] = "true"
        return CLIENT.request("GET", "/feed/v3/calendar/radarr.ics", params=params, raw=True)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Curated-tool registry â€” drives the `curated: True/False` annotation in      #
# radarr_list_endpoints so the user sees at-a-glance what's ergonomic vs       #
# generic-only. Keys are (METHOD, path-pattern); paths use {id} for any path   #
# parameter.                                                                   #
# --------------------------------------------------------------------------- #
CURATED_TOOLS: dict[tuple[str, str], str] = {
    # Generic
    ("GET", "/api/v3/system/status"):                 "radarr_status",
    ("GET", "/api/v3/system/task"):                   "radarr_system_tasks",
    ("GET", "/api/v3/system/backup"):                 "radarr_system_backups",
    ("GET", "/api/v3/system/routes"):                 "radarr_system_routes",
    ("POST", "/api/v3/system/restart"):               "radarr_system_restart",
    ("POST", "/api/v3/system/shutdown"):              "radarr_system_shutdown",
    ("GET", "/api/v3/log"):                           "radarr_logs",
    ("GET", "/api/v3/log/file"):                      "radarr_log_files",
    ("GET", "/api/v3/health"):                        "radarr_status",
    ("GET", "/api/v3/queue/status"):                  "radarr_status",
    ("GET", "/api/v3/diskspace"):                     "radarr_status",
    # Library
    ("GET", "/api/v3/movie"):                         "radarr_list_movies",
    ("GET", "/api/v3/movie/{id}"):                    "radarr_get_movie",
    ("GET", "/api/v3/movie/lookup"):                  "radarr_lookup_movies",
    ("GET", "/api/v3/movie/lookup/tmdb"):             "radarr_lookup_movies",
    ("POST", "/api/v3/movie"):                        "radarr_add_movie",
    ("PUT", "/api/v3/movie/{id}"):                    "radarr_update_movie",
    ("PUT", "/api/v3/movie/editor"):                  "radarr_movies_bulk_edit",
    ("DELETE", "/api/v3/movie/{id}"):                 "radarr_delete_movie",
    ("GET", "/api/v3/moviefile"):                     "radarr_movie_files",
    ("GET", "/api/v3/moviefile/{id}"):                "radarr_movie_files",
    ("GET", "/api/v3/rename"):                        "radarr_rename_preview",
    ("GET", "/api/v3/collection"):                    "radarr_collections",
    ("GET", "/api/v3/credit"):                        "radarr_lookup_movies",  # not curated but reachable
    # Activity
    ("GET", "/api/v3/calendar"):                      "radarr_calendar",
    ("GET", "/api/v3/queue"):                         "radarr_queue",
    ("GET", "/api/v3/queue/{id}"):                    "radarr_queue",
    ("DELETE", "/api/v3/queue/{id}"):                 "radarr_queue_delete",
    ("POST", "/api/v3/queue/grab/{id}"):              "radarr_queue_grab",
    ("GET", "/api/v3/history"):                       "radarr_history",
    ("GET", "/api/v3/history/since"):                 "radarr_history_since",
    ("GET", "/api/v3/wanted/missing"):                "radarr_wanted_missing",
    ("GET", "/api/v3/wanted/cutoff"):                 "radarr_wanted_cutoff",
    ("GET", "/api/v3/blocklist"):                     "radarr_blocklist",
    ("GET", "/api/v3/blocklist/movie"):               "radarr_blocklist",
    ("DELETE", "/api/v3/blocklist/{id}"):             "radarr_blocklist_delete",
    ("POST", "/api/v3/manualimport"):                 "radarr_manual_import",
    ("GET", "/api/v3/manualimport"):                  "radarr_manual_import",
    ("GET", "/api/v3/parse"):                         "radarr_parse",
    ("GET", "/api/v3/filesystem"):                    "radarr_filesystem",
    # Commands
    ("POST", "/api/v3/command"):                      "radarr_command",
    ("GET", "/api/v3/command/{id}"):                  "radarr_command_status",
    # Config
    ("GET", "/api/v3/qualityProfile"):                "radarr_quality_profiles",
    ("GET", "/api/v3/qualityDefinition"):             "radarr_quality_definitions",
    ("GET", "/api/v3/delayprofile"):                  "radarr_delay_profiles",
    ("GET", "/api/v3/releaseprofile"):                "radarr_release_profiles",
    ("GET", "/api/v3/remotepathmapping"):             "radarr_remote_path_mappings",
    ("GET", "/api/v3/autoTagging"):                   "radarr_auto_tagging",
    ("GET", "/api/v3/config/{id}"):                   "radarr_config_section",
    ("PUT", "/api/v3/config/{id}"):                   "radarr_update_config_section",
    ("GET", "/api/v3/config/host"):                   "radarr_config_section",
    ("GET", "/api/v3/config/ui"):                     "radarr_config_section",
    ("GET", "/api/v3/config/mediamanagement"):        "radarr_config_section",
    ("GET", "/api/v3/config/indexer"):                "radarr_config_section",
    ("GET", "/api/v3/config/downloadclient"):         "radarr_config_section",
    ("GET", "/api/v3/config/metadata"):               "radarr_config_section",
    ("GET", "/api/v3/config/importlist"):             "radarr_config_section",
    ("GET", "/api/v3/config/naming"):                 "radarr_config_section",
    ("GET", "/api/v3/language"):                      "radarr_languages",
    ("GET", "/api/v3/rootfolder"):                    "radarr_root_folders",
    ("GET", "/api/v3/tag"):                           "radarr_tags",
    ("GET", "/api/v3/tag/detail"):                    "radarr_tag_details",
    ("POST", "/api/v3/tag"):                          "radarr_tag_create",
    ("DELETE", "/api/v3/tag/{id}"):                   "radarr_tag_delete",
    ("GET", "/api/v3/customFormat"):                  "radarr_custom_formats",
    ("GET", "/api/v3/customFilter"):                  "radarr_list_endpoints",  # reachable, not curated
    ("GET", "/api/v3/notification"):                  "radarr_notifications",
    ("GET", "/api/v3/downloadclient"):                "radarr_download_clients",
    ("GET", "/api/v3/indexer"):                       "radarr_indexers",
    ("GET", "/api/v3/importlist"):                    "radarr_import_lists",
    ("GET", "/api/v3/exclusions"):                    "radarr_import_exclusions",
    ("POST", "/api/v3/notification/test"):            "radarr_provider_test",
    ("POST", "/api/v3/downloadclient/test"):          "radarr_provider_test",
    ("POST", "/api/v3/indexer/test"):                 "radarr_provider_test",
    ("POST", "/api/v3/importlist/test"):              "radarr_provider_test",
    ("POST", "/api/v3/metadata/test"):                "radarr_provider_test",
    # CRUD-wrapped resources (radarr_crud + bulk tools)
    ("GET", "/api/v3/notification/{id}"):             "radarr_crud",
    ("POST", "/api/v3/notification"):                 "radarr_crud",
    ("PUT", "/api/v3/notification/{id}"):             "radarr_crud",
    ("DELETE", "/api/v3/notification/{id}"):          "radarr_crud",
    ("POST", "/api/v3/notification/testall"):         "radarr_crud",
    ("POST", "/api/v3/notification/action/{id}"):     "radarr_provider_action",
    ("GET", "/api/v3/downloadclient/{id}"):           "radarr_crud",
    ("POST", "/api/v3/downloadclient"):               "radarr_crud",
    ("PUT", "/api/v3/downloadclient/{id}"):           "radarr_crud",
    ("DELETE", "/api/v3/downloadclient/{id}"):        "radarr_crud",
    ("POST", "/api/v3/downloadclient/testall"):       "radarr_crud",
    ("GET", "/api/v3/indexer/{id}"):                  "radarr_crud",
    ("POST", "/api/v3/indexer"):                      "radarr_crud",
    ("PUT", "/api/v3/indexer/{id}"):                  "radarr_crud",
    ("DELETE", "/api/v3/indexer/{id}"):               "radarr_crud",
    ("POST", "/api/v3/indexer/testall"):              "radarr_crud",
    ("GET", "/api/v3/importlist/{id}"):               "radarr_crud",
    ("POST", "/api/v3/importlist"):                   "radarr_crud",
    ("PUT", "/api/v3/importlist/{id}"):               "radarr_crud",
    ("DELETE", "/api/v3/importlist/{id}"):            "radarr_crud",
    ("POST", "/api/v3/importlist/testall"):           "radarr_crud",
    ("POST", "/api/v3/importlist/action/{id}"):       "radarr_provider_action",
    ("GET", "/api/v3/metadata/{id}"):                 "radarr_crud",
    ("POST", "/api/v3/metadata"):                     "radarr_crud",
    ("PUT", "/api/v3/metadata/{id}"):                 "radarr_crud",
    ("DELETE", "/api/v3/metadata/{id}"):              "radarr_crud",
    ("POST", "/api/v3/metadata/testall"):             "radarr_crud",
    ("POST", "/api/v3/metadata/action/{id}"):         "radarr_provider_action",
    ("GET", "/api/v3/qualityProfile/{id}"):           "radarr_crud",
    ("POST", "/api/v3/qualityProfile"):               "radarr_crud",
    ("PUT", "/api/v3/qualityProfile/{id}"):           "radarr_crud",
    ("DELETE", "/api/v3/qualityProfile/{id}"):        "radarr_crud",
    ("GET", "/api/v3/qualityprofile/schema"):         "radarr_crud",
    ("GET", "/api/v3/customFormat/{id}"):             "radarr_crud",
    ("POST", "/api/v3/customFormat"):                 "radarr_crud",
    ("PUT", "/api/v3/customFormat/{id}"):             "radarr_crud",
    ("DELETE", "/api/v3/customFormat/{id}"):          "radarr_crud",
    ("GET", "/api/v3/customformat/schema"):           "radarr_crud",
    ("GET", "/api/v3/delayProfile/{id}"):             "radarr_crud",
    ("POST", "/api/v3/delayProfile"):                 "radarr_crud",
    ("PUT", "/api/v3/delayProfile/{id}"):             "radarr_crud",
    ("DELETE", "/api/v3/delayProfile/{id}"):          "radarr_crud",
    ("GET", "/api/v3/releaseProfile/{id}"):           "radarr_crud",
    ("POST", "/api/v3/releaseProfile"):               "radarr_crud",
    ("PUT", "/api/v3/releaseProfile/{id}"):           "radarr_crud",
    ("DELETE", "/api/v3/releaseProfile/{id}"):        "radarr_crud",
    ("GET", "/api/v3/rootFolder/{id}"):               "radarr_crud",
    ("POST", "/api/v3/rootFolder"):                   "radarr_crud",
    ("DELETE", "/api/v3/rootFolder/{id}"):            "radarr_crud",
    ("GET", "/api/v3/remotePathMapping/{id}"):        "radarr_crud",
    ("POST", "/api/v3/remotePathMapping"):            "radarr_crud",
    ("PUT", "/api/v3/remotePathMapping/{id}"):        "radarr_crud",
    ("DELETE", "/api/v3/remotePathMapping/{id}"):     "radarr_crud",
    ("GET", "/api/v3/autoTagging/{id}"):              "radarr_crud",
    ("POST", "/api/v3/autoTagging"):                  "radarr_crud",
    ("PUT", "/api/v3/autoTagging/{id}"):              "radarr_crud",
    ("DELETE", "/api/v3/autoTagging/{id}"):           "radarr_crud",
    ("GET", "/api/v3/autotagging/schema"):            "radarr_crud",
    ("GET", "/api/v3/customFilter/{id}"):             "radarr_crud",
    ("POST", "/api/v3/customFilter"):                 "radarr_crud",
    ("PUT", "/api/v3/customFilter/{id}"):             "radarr_crud",
    ("DELETE", "/api/v3/customFilter/{id}"):          "radarr_crud",
    ("GET", "/api/v3/exclusions/{id}"):               "radarr_crud",
    ("POST", "/api/v3/exclusions"):                   "radarr_crud",
    ("PUT", "/api/v3/exclusions/{id}"):               "radarr_crud",
    ("DELETE", "/api/v3/exclusions/{id}"):            "radarr_crud",
    # Bulk operations
    ("DELETE", "/api/v3/blocklist/bulk"):             "radarr_blocklist_bulk_delete",
    ("DELETE", "/api/v3/movie/editor"):               "radarr_movies_bulk_delete",
    ("DELETE", "/api/v3/queue/bulk"):                 "radarr_queue_bulk_delete",
    ("GET", "/feed/v3/calendar/radarr.ics"):          "radarr_calendar_ics",
}


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("api_key"):
        log("WARNING: no api_key configured â€” every call will 401. "
            "Fill config.local.json or set RADARR_API_KEY.")
    mcp.run()


if __name__ == "__main__":
    main()
