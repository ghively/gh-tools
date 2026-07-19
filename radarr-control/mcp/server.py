#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0",
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
            raise RadarrError("401 Unauthorized — the API key was rejected.")
        if resp.status_code == 403:
            raise RadarrError(f"403 Forbidden on {method} {path} — operation not allowed for this key.")
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
    """Call ANY Radarr REST operation — the generic passthrough that reaches
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
def radarr_list_endpoints(search: str = "", method: str = "", limit: int = 80) -> Any:
    """Search the endpoint catalog (hand-enumerated from live probes — Radarr
    does not publish OpenAPI). The master index for radarr_call.

    Args:
        search: Case-insensitive substring matched against path + summary,
            e.g. "movie", "queue", "command".
        method: Filter by HTTP method (GET/POST/PUT/DELETE).
        limit: Max endpoints to return (default 80).
    """
    ops = ENDPOINT_CATALOG
    if method:
        ops = [o for o in ops if o["method"].upper() == method.upper()]
    if search:
        s = search.lower()
        ops = [o for o in ops if s in o["path"].lower() or s in o["summary"].lower()]
    return _finish({"matched": len(ops), "endpoints": ops[:limit]})


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
    default — set compact=false for the full objects.

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
        confirm: Must be true — this adds to the live library.
    """
    try:
        if not confirm:
            return _need_confirm(
                f"add TMDB {tmdb_id} to '{root_folder_path}' "
                f"(profile {quality_profile_id}, monitored={monitored}, search={search_for_movie})"
            )
        # Lookup the full record first — POST needs the full object.
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
        confirm: Must be true — this mutates the live library.
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
        confirm: Must be true — irreversible (especially with delete_files).
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
    WRITES: confirm-gated (this triggers downloads, scans, renames — active work).

    Common names: RefreshMovie, MoviesSearch, DownloadedMoviesScan, RenameMovie,
    Backup, ApplicationUpdate, RefreshMonitoredDownloads, MissingMoviesSearch.

    Args:
        name: Command name (see radarr list of commands in the skill).
        movie_ids: Optional list of movie ids the command applies to.
        confirm: Must be true — this triggers active work.
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
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("api_key"):
        log("WARNING: no api_key configured — every call will 401. "
            "Fill config.local.json or set RADARR_API_KEY.")
    mcp.run()


if __name__ == "__main__":
    main()
