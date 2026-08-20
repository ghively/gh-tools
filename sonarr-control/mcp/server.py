#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Sonarr MCP server.

Exposes a Sonarr TV-series manager (v3+ REST API) to Claude through the Model
Context Protocol. Verified against Sonarr 4.x. Two-layer design,
mirroring the emby/radarr plugins:

* GENERIC passthrough (`sonarr_call` / `sonarr_list_endpoints`) reaching every
  /api/v3 endpoint. Catalog is hand-enumerated from live probes (Sonarr does
  not publish OpenAPI).
* CURATED tools for the common jobs: status, library (series, seasons,
  episodes, episode files), wanted missing/cutoff (episodes), calendar,
  queue, history, blocklist, commands (search/refresh/rescan), quality
  profiles, root folders, languages, tags, notifications, download clients,
  indexers, import lists, manual import, logs, system tasks & backups.

Auth model (proven live): every request carries the API key in the
`X-Api-Key` header. API keys are created under Settings > General > Security
and act with full admin. 401 = bad key.

Sonarr conventions this file encodes (all verified live):
* Paths under /api/v3/<resource>.
* POST /series expects a full series object (typically a lookup result
  augmented with qualityProfileId, languageProfileId, rootFolderPath,
  monitored, seasons, addOptions, seriesType). POSTing a partial object
  silently fails or 400s.
* POST /command with {"name": "<CommandName>", ...} triggers async jobs
  (RefreshSeries, SeriesSearch, EpisodesSearch, SeasonSearch,
  DownloadedEpisodesScan, RenameSeries, Backup, RefreshMonitoredDownloads,
  ApplicationUpdate, MissingEpisodesSearch). Returns a job object you can
  poll at /command/{id}.
* /wanted/missing and /wanted/cutoff return EPISODE records (each references
  its series), not series.
* /calendar returns EPISODES (one per airing), each with its series embedded.

Destructive writes (DELETE /series, POST /command that triggers active
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
    print("[sonarr-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("SONARR_CONFIG"):
        candidates.append(Path(os.environ["SONARR_CONFIG"]))
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
    host = env.get("SONARR_HOST", cfg.get("host", ""))
    https = _truthy(env.get("SONARR_HTTPS"), cfg.get("https", False))
    port = int(env.get("SONARR_PORT", cfg.get("port", 8989)) or 8989)
    url_base = (env.get("SONARR_URL_BASE", cfg.get("url_base", "")) or "").strip().strip("/")
    return {
        "host": host,
        "port": port,
        "https": https,
        "url_base": url_base,
        "api_key": env.get("SONARR_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("SONARR_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("SONARR_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }


CONFIG = load_config()
MAX_RESULT_CHARS = 60_000


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class SonarrError(Exception):
    pass


class SonarrClient:
    """Thin, thread-safe wrapper that speaks Sonarr's REST conventions."""

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

    def request(self, method: str, path: str, params: Optional[dict] = None,
                body: Any = None, raw: bool = False) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        # /feed/* (iCal) is a sibling of /api/* — don't force the /api/v3 prefix on it.
        if not path.startswith("/api/v") and not path.startswith("/feed/"):
            path = "/api/v3" + path
        try:
            resp = self._client.request(method.upper(), path, params=params, json=body)
        except httpx.TimeoutException as e:
            raise SonarrError(
                f"Timeout after {self.cfg['timeout']}s on {method} {path} — is Sonarr "
                f"reachable at {self.base}? (SONARR_TIMEOUT raises the limit)") from e
        except httpx.HTTPError as e:
            raise SonarrError(f"Connection error on {method} {path} to {self.base}: {e}") from e
        if resp.status_code == 401:
            raise SonarrError("401 Unauthorized — the API key was rejected.")
        if resp.status_code == 403:
            raise SonarrError(f"403 Forbidden on {method} {path} — operation not allowed for this key.")
        if resp.status_code >= 400:
            detail = resp.text[:400]
            raise SonarrError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if raw:
            return resp.text
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text

    def live_routes(self) -> list:
        """Fetch and parse /api/v3/system/routes (Graphviz DOT format) into a
        clean list of {method, path}. Cached for the process lifetime."""
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


CLIENT = SonarrClient(CONFIG)


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
        "_note": (f"Result was {len(text)} chars; showing the first "
                  f"{MAX_RESULT_CHARS}. Narrow the query (page/pageSize/id/seriesId)."),
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
        raise SonarrError(f"{name} is not valid JSON: {e}") from e


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


def compact_series(s: dict) -> dict:
    """Trim a series object to the fields that matter for browsing."""
    if not isinstance(s, dict):
        return s
    # On v3/v4 the counts live under `statistics`; fall back to top level for
    # older payloads that carried them there.
    stats = s.get("statistics") or {}
    out = {
        "id": s.get("id"),
        "title": s.get("title"),
        "sortTitle": s.get("sortTitle"),
        "tvdbId": s.get("tvdbId"),
        "imdbId": s.get("imdbId"),
        "status": s.get("status"),
        "seriesType": s.get("seriesType"),
        "monitored": s.get("monitored"),
        "seasonCount": len(s.get("seasons") or []),
        "episodeFileCount": stats.get("episodeFileCount", s.get("episodeFileCount")),
        "episodeCount": stats.get("episodeCount", s.get("episodeCount")),
        "sizeOnDisk": stats.get("sizeOnDisk"),
        "percentEpisodes": stats.get("percentOfEpisodes", s.get("percentOfEpisodes")),
        "year": s.get("year"),
        "path": s.get("path"),
        "qualityProfileId": s.get("qualityProfileId"),
        "languageProfileId": s.get("languageProfileId"),
        "seasons": [{
            "seasonNumber": se.get("seasonNumber"),
            "monitored": se.get("monitored"),
            "statistics": se.get("statistics"),
        } for se in (s.get("seasons") or []) if isinstance(se, dict)],
    }
    if s.get("ratings"):
        out["ratings"] = {k: v.get("value") for k, v in (s["ratings"] or {}).items() if isinstance(v, dict)}
    if s.get("genres"):
        out["genres"] = s["genres"]
    return {k: v for k, v in out.items() if v is not None}


def compact_episode(e: dict) -> dict:
    if not isinstance(e, dict):
        return e
    return {
        "id": e.get("id"),
        "seriesId": e.get("seriesId"),
        "seasonNumber": e.get("seasonNumber"),
        "episodeNumber": e.get("episodeNumber"),
        "title": e.get("title"),
        "airDate": e.get("airDate"),
        "airDateUtc": e.get("airDateUtc"),
        "hasFile": e.get("hasFile"),
        "monitored": e.get("monitored"),
        "episodeFileId": e.get("episodeFileId"),
        "series": (e.get("series") or {}).get("title"),
        "quality": (e.get("quality") or {}).get("quality", {}).get("name")
                   if isinstance(e.get("quality"), dict) else None,
    }


mcp = FastMCP("sonarr")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
ENDPOINT_CATALOG: list[dict] = [
    # System
    {"method": "GET",    "path": "/api/v3/system/status",            "summary": "Server identity, version, OS, paths"},
    {"method": "GET",    "path": "/api/v3/system/task",              "summary": "Scheduled tasks (next run, interval, last)"},
    {"method": "GET",    "path": "/api/v3/system/backup",            "summary": "Database backups (size, time, download URL)"},
    {"method": "GET",    "path": "/api/v3/log",                      "summary": "Application log (paged, level filter)"},
    {"method": "GET",    "path": "/api/v3/health",                   "summary": "Health checks"},
    {"method": "GET",    "path": "/api/v3/queue/status",             "summary": "Queue summary (total, errors, unknown)"},
    {"method": "GET",    "path": "/api/v3/diskspace",                "summary": "Disk free space"},
    {"method": "GET",    "path": "/api/v3/qualityDefinition",        "summary": "Quality definitions"},
    # Series, seasons, episodes, files
    {"method": "GET",    "path": "/api/v3/series",                   "summary": "All series (filterable)"},
    {"method": "GET",    "path": "/api/v3/series/{id}",              "summary": "Single series by id"},
    {"method": "GET",    "path": "/api/v3/series/lookup",            "summary": "Search TVDB for a series (term=... OR term=tvdb:<id>)"},
    {"method": "GET",    "path": "/api/v3/series/lookup/tvdb",       "summary": "DEPRECATED — 404s on 4.x; use ?term=tvdb:<id> instead"},
    {"method": "GET",    "path": "/api/v3/series/lookup/imdb",       "summary": "IMDB lookup by imdbId=..."},
    {"method": "PUT",    "path": "/api/v3/series",                   "summary": "Bulk update series (provide full array)"},
    {"method": "POST",   "path": "/api/v3/series",                   "summary": "Add a series (full object required)"},
    {"method": "PUT",    "path": "/api/v3/series/{id}",              "summary": "Update a series (full object required)"},
    {"method": "DELETE", "path": "/api/v3/series/{id}",              "summary": "Delete a series"},
    {"method": "GET",    "path": "/api/v3/episode",                  "summary": "Episodes (requires seriesId or episodeIds)"},
    {"method": "GET",    "path": "/api/v3/episode/{id}",             "summary": "Single episode by id"},
    {"method": "PUT",    "path": "/api/v3/episode/{id}",             "summary": "Update an episode (e.g. monitored)"},
    {"method": "PUT",    "path": "/api/v3/episode/monitor",          "summary": "Bulk-set monitored on episodeIds"},
    {"method": "GET",    "path": "/api/v3/episodeFile",              "summary": "Episode files (requires seriesId)"},
    {"method": "GET",    "path": "/api/v3/episodeFile/{id}",         "summary": "Single episode file by id"},
    {"method": "DELETE", "path": "/api/v3/episodeFile/{id}",         "summary": "Delete an episode file"},
    {"method": "GET",    "path": "/api/v3/seasonPass",               "summary": "Season-pass monitoring map"},
    {"method": "GET",    "path": "/api/v3/alternativeRelease",       "summary": "Alternative titles rejected at import"},
    {"method": "GET",    "path": "/api/v3/extraFile",                "summary": "Extra files (subtitles, etc.)"},
    {"method": "GET",    "path": "/api/v3/importlist",               "summary": "Configured import lists"},
    {"method": "GET",    "path": "/api/v3/customFormat",             "summary": "Custom formats defined"},
    {"method": "GET",    "path": "/api/v3/customFilter",             "summary": "Saved UI custom filters"},
    # Activity / wanted / calendar
    {"method": "GET",    "path": "/api/v3/wanted/missing",           "summary": "Monitored episodes with no file"},
    {"method": "GET",    "path": "/api/v3/wanted/cutoff",            "summary": "Episodes below their cutoff quality"},
    {"method": "GET",    "path": "/api/v3/calendar",                 "summary": "Episodes by air-date range (start/end)"},
    {"method": "GET",    "path": "/api/v3/queue",                    "summary": "Active downloads (import+grabbed)"},
    {"method": "GET",    "path": "/api/v3/queue/details",            "summary": "Queue with full episode + quality info"},
    {"method": "GET",    "path": "/api/v3/history",                  "summary": "Recent activity"},
    {"method": "GET",    "path": "/api/v3/history/series",           "summary": "History for one series (seriesId=)"},
    {"method": "GET",    "path": "/api/v3/blocklist",                "summary": "Blocked releases"},
    {"method": "GET",    "path": "/api/v3/release",                  "summary": "Recent releases from indexers"},
    {"method": "POST",   "path": "/api/v3/release",                  "summary": "Send a release to the download client"},
    {"method": "GET",    "path": "/api/v3/manualimport",             "summary": "Manual import candidates (folder=)"},
    {"method": "POST",   "path": "/api/v3/command",                  "summary": "Trigger an async job"},
    {"method": "GET",    "path": "/api/v3/command",                  "summary": "Recent / running commands"},
    {"method": "GET",    "path": "/api/v3/command/{id}",             "summary": "Status of a single command"},
    {"method": "DELETE", "path": "/api/v3/command/{id}",             "summary": "Cancel a running command"},
    # Config
    {"method": "GET",    "path": "/api/v3/qualityProfile",           "summary": "Quality profiles"},
    {"method": "GET",    "path": "/api/v3/languageProfile",          "summary": "Language profiles (Sonarr-specific)"},
    {"method": "GET",    "path": "/api/v3/language",                 "summary": "Languages known to Sonarr"},
    {"method": "GET",    "path": "/api/v3/rootfolder",               "summary": "Configured root library folders"},
    {"method": "GET",    "path": "/api/v3/tag",                      "summary": "Tags"},
    {"method": "GET",    "path": "/api/v3/notification",             "summary": "Configured notifications"},
    {"method": "GET",    "path": "/api/v3/notification/schema",      "summary": "Available notification implementations"},
    {"method": "GET",    "path": "/api/v3/downloadclient",           "summary": "Configured download clients"},
    {"method": "GET",    "path": "/api/v3/downloadclient/schema",    "summary": "Available download client implementations"},
    {"method": "GET",    "path": "/api/v3/indexer",                  "summary": "Configured indexers"},
    {"method": "GET",    "path": "/api/v3/indexer/schema",           "summary": "Available indexer implementations"},
    {"method": "GET",    "path": "/api/v3/metadata",                 "summary": "Configured metadata consumers"},
    {"method": "GET",    "path": "/api/v3/autoTagging",              "summary": "Auto-tagging rules"},
    {"method": "GET",    "path": "/api/v3/config",                   "summary": "Server config (UI/indexers/downloadclient/mediamanagement)"},
]


@mcp.tool()
def sonarr_call(method: str, path: str, params: str = "", body: str = "") -> Any:
    """Call ANY Sonarr REST operation — the generic passthrough that reaches
    the server's entire API surface (~55 endpoints). Use sonarr_list_endpoints
    to find an endpoint first.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE).
        path: Endpoint path. Either "/api/v3/series" or just "series" (auto-
            prefixed). Path templates like {id} must already be substituted.
        params: Optional query parameters as JSON object string.
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
def sonarr_list_endpoints(search: str = "", method: str = "", limit: int = 100,
                          curated_only: bool = False) -> Any:
    """Search the FULL endpoint catalog — pulled live from /api/v3/system/routes
    so it's always accurate for the deployed Sonarr version (~470 operations on
    4.0). The master index for sonarr_call.

    Each operation is annotated with whether a curated tool wraps it (so you
    can see at a glance what's ergonomic vs generic-only).

    Args:
        search: Case-insensitive substring matched against the path.
        method: Filter by HTTP method (GET/POST/PUT/DELETE).
        curated_only: If true, only return operations that have a curated tool.
        limit: Max operations to return (default 100).
    """
    import re
    routes = CLIENT.live_routes() or ENDPOINT_CATALOG
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
def sonarr_status() -> Any:
    """Server health snapshot: identity, version, queue summary, library
    counts, health checks, disk usage. Call this first."""
    try:
        status = CLIENT.request("GET", "/api/v3/system/status")
        health = CLIENT.request("GET", "/api/v3/health") or []
        queue_status = CLIENT.request("GET", "/api/v3/queue/status") or {}
        disks = CLIENT.request("GET", "/api/v3/diskspace") or []
        series_list = CLIENT.request("GET", "/api/v3/series") or []
        monitored_series = sum(1 for s in series_list if s.get("monitored"))
        return {
            "appName": status.get("appName"),
            "version": status.get("version"),
            "buildTime": status.get("buildTime"),
            "isAdmin": status.get("isAdmin"),
            "osName": status.get("isOsx") and "macOS" or (status.get("isLinux") and "Linux" or (status.get("isWindows") and "Windows" or "?")),
            "startupPath": status.get("startupPath"),
            "appDataPath": status.get("appDataPath"),
            "totalSeries": len(series_list),
            "monitoredSeries": monitored_series,
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
def sonarr_logs(level: str = "info", page: int = 1, page_size: int = 25) -> Any:
    """Read application logs.

    Args:
        level: Filter by level (info, warn, error, debug). 'all' disables filter.
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
def sonarr_system_tasks() -> Any:
    """Scheduled tasks: name, interval, last run, next run."""
    try:
        data = CLIENT.request("GET", "/api/v3/system/task") or []
        return [{"name": t.get("name"), "interval": t.get("interval"),
                 "lastExecution": t.get("lastExecutionTime"),
                 "nextExecution": t.get("nextExecutionTime")}
                for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_system_backups() -> Any:
    """Database backups: name, time, size, type."""
    try:
        data = CLIENT.request("GET", "/api/v3/system/backup") or []
        return [{"name": b.get("name"), "type": b.get("type"),
                 "time": b.get("time"), "size": b.get("size"), "id": b.get("id")}
                for b in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library: series, seasons, episodes                                          #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sonarr_list_series(monitored: Optional[bool] = None, page: int = 1,
                       page_size: int = 50, compact: bool = True) -> Any:
    """List series (paged, optionally filtered).

    Args:
        monitored: Filter to monitored=true or unmonitored=false. None = no filter.
        page: 1-based page.
        page_size: Records per page.
        compact: Return trimmed fields (recommended).
    """
    try:
        series = CLIENT.request("GET", "/api/v3/series") or []
        if monitored is not None:
            series = [s for s in series if bool(s.get("monitored")) == monitored]
        total = len(series)
        start = (page - 1) * page_size
        sliced = series[start:start + page_size]
        return {
            "page": page, "pageSize": page_size, "totalRecords": total,
            "series": [compact_series(s) for s in sliced] if compact else sliced,
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_get_series(series_id: int, include_episodes: bool = True) -> Any:
    """Single series by id, with seasons and (optionally) its episodes."""
    try:
        s = CLIENT.request("GET", f"/api/v3/series/{series_id}")
        if include_episodes:
            eps = CLIENT.request("GET", "/api/v3/episode", params={"seriesId": series_id}) or []
            s["episodes"] = [compact_episode(e) for e in eps]
        return s
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_lookup_series(term: str, limit: int = 10) -> Any:
    """Search TVDB for series to ADD. Use before sonarr_add_series to get the
    full lookup object (which the add needs).

    Args:
        term: Search string.
        limit: Cap results.
    """
    try:
        if not term or not term.strip():
            raise SonarrError("term is required")
        data = CLIENT.request("GET", "/api/v3/series/lookup", params={"term": term}) or []
        return _finish([{
            "title": s.get("title"),
            "tvdbId": s.get("tvdbId"),
            "imdbId": s.get("imdbId"),
            "year": s.get("year"),
            "status": s.get("status"),
            "seriesType": s.get("seriesType"),
            "overview": (s.get("overview") or "")[:240],
            "seasonCount": len(s.get("seasons") or []),
            "genres": s.get("genres", []),
            "ratings": {k: v.get("value") for k, v in (s.get("ratings") or {}).items() if isinstance(v, dict)},
            "alreadyInLibrary": s.get("id") is not None,
            "id": s.get("id"),
        } for s in data[:limit]])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_add_series(tvdb_id: int, quality_profile_id: int, root_folder_path: str,
                      monitored: bool = True, season_count: Optional[int] = None,
                      series_type: str = "standard", search_for_missing: bool = False,
                      language_profile_id: Optional[int] = None,
                      tags: Optional[list] = None, confirm: bool = False) -> Any:
    """Add a series to the library by TVDB id. WRITES: confirm-gated.

    Args:
        tvdb_id: TVDB id (from sonarr_lookup_series).
        quality_profile_id: Profile id (see sonarr_quality_profiles).
        root_folder_path: Library root path (must match exactly; see sonarr_root_folders).
        monitored: Monitor this series for new releases.
        season_count: If set, monitor only the first N seasons (else monitor all
            from the lookup result).
        series_type: standard | anime | daily.
        search_for_missing: Trigger an initial search for missing episodes.
        language_profile_id: Language profile id (Sonarr-specific).
        tags: Optional list of tag ids.
        confirm: Must be true — adds to the live library.
    """
    try:
        if not confirm:
            return _need_confirm(
                f"add TVDB {tvdb_id} to '{root_folder_path}' "
                f"(profile {quality_profile_id}, monitored={monitored}, search={search_for_missing})"
            )
        # Sonarr's /series/lookup/tvdb path 404s on 4.x; the correct form is
        # /series/lookup?term=tvdb:<id> which returns a list of one match.
        # (Verified live 2026-07-19 on Sonarr 4.x.)
        matches = CLIENT.request("GET", "/api/v3/series/lookup",
                                 params={"term": f"tvdb:{tvdb_id}"}) or []
        if not isinstance(matches, list) or not matches:
            raise SonarrError(f"TVDB lookup returned no record for tvdb:{tvdb_id}")
        lookup = matches[0]
        if not isinstance(lookup, dict):
            raise SonarrError(f"TVDB lookup returned non-dict for tvdb:{tvdb_id}")
        if lookup.get("id"):
            return {"already_in_library": True, "series": compact_series(lookup)}
        body = dict(lookup)
        # Per-season monitoring: monitor seasons 1..N by seasonNumber (specials
        # / season 0 stay unmonitored — indexing the list would count them).
        seasons = body.get("seasons") or []
        if season_count is not None:
            for se in seasons:
                sn = se.get("seasonNumber") or 0
                se["monitored"] = 0 < sn <= season_count
        else:
            for se in seasons:
                se["monitored"] = monitored
        body.update({
            "monitored": monitored,
            "seasons": seasons,
            "seriesType": series_type,
            "rootFolderPath": root_folder_path,
            "qualityProfileId": quality_profile_id,
            "addOptions": {
                "monitor": "monitored" if monitored else "none",
                "searchForMissingEpisodes": search_for_missing,
                "searchForCutoffUnmetEpisodes": False,
            },
        })
        if language_profile_id is not None:
            body["languageProfileId"] = language_profile_id
        if tags:
            body["tags"] = tags
        created = CLIENT.request("POST", "/api/v3/series", body=body)
        return {"added": True, "series": compact_series(created) if isinstance(created, dict) else created}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_update_series(series_id: int, patch: str, confirm: bool = False) -> Any:
    """Update a series SAFELY: GET-merge-PUT. Sonarr expects the full object on
    PUT (omitted fields reset to defaults).

    Args:
        series_id: Sonarr series id.
        patch: JSON object string with just the keys to change,
            e.g. '{"monitored": false}' or '{"seasons": [...modified...]}'
        confirm: Must be true — mutates the live library.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise SonarrError("patch must be a non-empty JSON object")
        current = CLIENT.request("GET", f"/api/v3/series/{series_id}")
        if not confirm:
            return _need_confirm(
                f"update series {series_id} ({current.get('title')}) "
                f"keys {list(change)} (current values: "
                f"{ {k: current.get(k) for k in change} })"
            )
        merged = {**current, **change}
        updated = CLIENT.request("PUT", f"/api/v3/series/{series_id}", body=merged)
        return {"updated": True, "series": compact_series(updated) if isinstance(updated, dict) else updated}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_delete_series(series_id: int, delete_files: bool = False,
                         add_import_exclusion: bool = False, confirm: bool = False) -> Any:
    """Delete a series. WRITES: confirm-gated.

    Args:
        series_id: Sonarr series id.
        delete_files: Also delete episode files from disk (irreversible).
        add_import_exclusion: Add to import exclusion list.
        confirm: Must be true — irreversible (especially with delete_files).
    """
    try:
        current = CLIENT.request("GET", f"/api/v3/series/{series_id}")
        if not confirm:
            return _need_confirm(
                f"delete series {series_id} ({current.get('title')}) "
                f"delete_files={delete_files}, "
                f"add_import_exclusion={add_import_exclusion}"
            )
        params = {}
        if delete_files:
            params["deleteFiles"] = "true"
        if add_import_exclusion:
            params["addImportExclusion"] = "true"
        CLIENT.request("DELETE", f"/api/v3/series/{series_id}", params=params or None)
        return {"deleted": True, "series_id": series_id, "title": current.get("title")}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_episodes(series_id: Optional[int] = None, season_number: Optional[int] = None,
                    episode_ids: Optional[list] = None) -> Any:
    """List episodes of a series (optionally one season), or fetch specific
    episodes by id. Requires series_id OR episode_ids."""
    try:
        if series_id is None and not episode_ids:
            raise SonarrError("provide series_id or episode_ids")
        params: dict = {}
        if series_id is not None:
            params["seriesId"] = series_id
        if season_number is not None:
            params["seasonNumber"] = season_number
        if episode_ids:
            # httpx repeats the key for list values (episodeIds=1&episodeIds=2),
            # which is how Sonarr binds List<int> — a comma-joined string 400s.
            params["episodeIds"] = [int(x) for x in episode_ids]
        data = CLIENT.request("GET", "/api/v3/episode", params=params) or []
        return [compact_episode(e) for e in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_episode_files(series_id: int) -> Any:
    """Episode files attached to a series (path, size, quality)."""
    try:
        data = CLIENT.request("GET", "/api/v3/episodeFile", params={"seriesId": series_id}) or []
        return [{
            "id": f.get("id"), "path": f.get("path"), "size": f.get("size"),
            "seasonNumber": f.get("seasonNumber"),
            "episodes": [(e.get("episodeNumber"), e.get("title"))
                         for e in (f.get("episodes") or [])],
            "quality": (f.get("quality") or {}).get("quality", {}).get("name"),
            "languages": [l.get("name") for l in (f.get("languages") or [])],
            "dateAdded": f.get("dateAdded"),
        } for f in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_toggle_season_monitored(series_id: int, season_number: int,
                                    monitored: bool, confirm: bool = False) -> Any:
    """Flip monitoring for an entire season. WRITES: confirm-gated.

    Args:
        series_id: Sonarr series id.
        season_number: 0-based (0 = specials).
        monitored: True = monitor; False = stop monitoring.
        confirm: Must be true.
    """
    try:
        current = CLIENT.request("GET", f"/api/v3/series/{series_id}")
        seasons = current.get("seasons") or []
        target = next((s for s in seasons if s.get("seasonNumber") == season_number), None)
        if target is None:
            raise SonarrError(f"season {season_number} not found on series {series_id}")
        if not confirm:
            return _need_confirm(
                f"set season {season_number} of '{current.get('title')}' "
                f"monitored={monitored} (currently {target.get('monitored')})"
            )
        for s in seasons:
            if s.get("seasonNumber") == season_number:
                s["monitored"] = monitored
        updated = CLIENT.request("PUT", f"/api/v3/series/{series_id}", body=current)
        return {"updated": True,
                "series": compact_series(updated) if isinstance(updated, dict) else updated}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_episode_monitor(episode_ids: list, monitored: bool,
                           confirm: bool = False) -> Any:
    """Bulk-set the monitored flag on specific episodes. WRITES: confirm-gated.

    Args:
        episode_ids: List of episode ids (from sonarr_episodes).
        monitored: True = monitor; False = stop monitoring.
        confirm: Must be true.
    """
    try:
        if not episode_ids:
            raise SonarrError("episode_ids must be non-empty")
        if not confirm:
            return _need_confirm(
                f"set monitored={monitored} on {len(episode_ids)} episode(s) {episode_ids}"
            )
        body = {"episodeIds": [int(x) for x in episode_ids], "monitored": bool(monitored)}
        data = CLIENT.request("PUT", "/api/v3/episode/monitor", body=body) or []
        return {"updated": len(data) if isinstance(data, list) else True,
                "episodes": [compact_episode(e) for e in data] if isinstance(data, list) else data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_episode_file_delete(episode_file_id: int, confirm: bool = False) -> Any:
    """Delete one episode file from disk (the episode stays in the library and
    becomes 'missing'). WRITES: confirm-gated, IRREVERSIBLE.

    Args:
        episode_file_id: Episode file id (from sonarr_episode_files).
        confirm: Must be true — removes the media file from disk.
    """
    try:
        current = CLIENT.request("GET", f"/api/v3/episodeFile/{episode_file_id}")
        if not confirm:
            return _need_confirm(
                f"DELETE episode file {episode_file_id} "
                f"({(current or {}).get('path')}) from disk — irreversible"
            )
        CLIENT.request("DELETE", f"/api/v3/episodeFile/{episode_file_id}")
        return {"deleted": True, "episode_file_id": episode_file_id,
                "path": (current or {}).get("path")}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Activity / wanted / calendar                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sonarr_calendar(start: str = "", end: str = "", tags: str = "",
                    include_unmonitored: bool = False) -> Any:
    """Episodes airing in a date range (default: today → +14 days).

    Args:
        start: ISO date (YYYY-MM-DD). Defaults to today.
        end: ISO date. Defaults to 14 days from today.
        tags: Optional comma-separated tag ids.
        include_unmonitored: Include unmonitored series/episodes.
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
        if include_unmonitored:
            params["includeUnmonitored"] = "true"
        data = CLIENT.request("GET", "/api/v3/calendar", params=params) or []
        return _finish([compact_episode(e) for e in data])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_queue(include_unknown: bool = True, page: int = 1,
                 page_size: int = 50) -> Any:
    """Current download queue: grabbed, importing, downloading, failed, delayed.

    Args:
        include_unknown: Include items Sonarr can't map to an episode.
        page: 1-based page (the endpoint is paged server-side).
        page_size: Records per page (Sonarr's default is only 10).
    """
    try:
        params: dict = {"page": page, "pageSize": page_size}
        if include_unknown:
            params["includeUnknown"] = "true"
        data = CLIENT.request("GET", "/api/v3/queue", params=params) or {}
        records = data.get("records") or []
        return {
            "page": data.get("page", page),
            "pageSize": data.get("pageSize", page_size),
            "totalRecords": data.get("totalRecords", len(records)),
            "queue": [{
                "id": r.get("id"),
                "seriesId": r.get("seriesId"),
                "series": (r.get("series") or {}).get("title"),
                "episode": (r.get("episode") or {}).get("title"),
                "seasonNumber": (r.get("episode") or {}).get("seasonNumber"),
                "episodeNumber": (r.get("episode") or {}).get("episodeNumber"),
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
def sonarr_history(series_id: Optional[int] = None, page: int = 1,
                   page_size: int = 25, event_type: str = "") -> Any:
    """Recent activity (grabbed / import / failed / etc.).

    Args:
        series_id: Filter to one series.
        page: 1-based page.
        page_size: Records per page.
        event_type: 'grabbed' | 'downloadFolderImported' | 'downloadFailed' | etc.
    """
    try:
        params = {"page": page, "pageSize": page_size}
        if series_id:
            params["seriesId"] = series_id
        if event_type:
            params["eventType"] = event_type
        data = CLIENT.request("GET", "/api/v3/history", params=params) or {}
        return _finish({
            "page": data.get("page"),
            "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "records": [{"date": r.get("date"), "eventType": r.get("eventType"),
                         "series": (r.get("series") or {}).get("title"),
                         "episode": (r.get("episode") or {}).get("title"),
                         "seasonNumber": (r.get("episode") or {}).get("seasonNumber"),
                         "episodeNumber": (r.get("episode") or {}).get("episodeNumber"),
                         "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
                         "data": r.get("data")}
                        for r in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_wanted_missing(sort_key: str = "series.sortTitle", page: int = 1,
                          page_size: int = 25, monitored: bool = True) -> Any:
    """Monitored episodes with no file yet. Returns EPISODES (one per missing ep)."""
    try:
        params = {"sortKey": sort_key, "sortDir": "asc",
                  "page": page, "pageSize": page_size}
        if monitored:
            params["monitored"] = "true"
        data = CLIENT.request("GET", "/api/v3/wanted/missing", params=params) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "episodes": [compact_episode(e) for e in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_wanted_cutoff(sort_key: str = "series.sortTitle", page: int = 1,
                         page_size: int = 25) -> Any:
    """Episodes below their quality cutoff (upgradeable)."""
    try:
        params = {"sortKey": sort_key, "sortDir": "asc",
                  "page": page, "pageSize": page_size}
        data = CLIENT.request("GET", "/api/v3/wanted/cutoff", params=params) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "episodes": [compact_episode(e) for e in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_blocklist(page: int = 1, page_size: int = 25) -> Any:
    """Releases Sonarr auto-rejected (stuck/failed/poor)."""
    try:
        data = CLIENT.request("GET", "/api/v3/blocklist", params={"page": page, "pageSize": page_size}) or {}
        return _finish({
            "page": data.get("page"), "pageSize": data.get("pageSize"),
            "totalRecords": data.get("totalRecords"),
            "records": [{"date": r.get("date"), "source": r.get("source"),
                         "series": (r.get("series") or {}).get("title"),
                         "episode": (r.get("episode") or {}).get("title"),
                         "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
                         "indexer": r.get("indexer"),
                         "message": (r.get("message") or (r.get("data") or {}).get("message"))}
                        for r in data.get("records", [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_release_search(episode_id: Optional[int] = None,
                          series_id: Optional[int] = None,
                          season_number: Optional[int] = None,
                          limit: int = 25) -> Any:
    """Interactive search: list candidate releases from the indexers for one
    episode (episode_id) or a whole season (series_id + season_number).
    READ-ONLY — queries the indexers but grabs nothing. Use sonarr_release_grab
    to send one to the download client.

    Args:
        episode_id: Episode id (from sonarr_episodes).
        series_id: Series id — pair with season_number for a season-pack search.
        season_number: Season number (with series_id).
        limit: Cap results.
    """
    try:
        params: dict = {}
        if episode_id is not None:
            params["episodeId"] = int(episode_id)
        elif series_id is not None and season_number is not None:
            params["seriesId"] = int(series_id)
            params["seasonNumber"] = int(season_number)
        else:
            raise SonarrError("provide episode_id OR series_id + season_number")
        data = CLIENT.request("GET", "/api/v3/release", params=params) or []
        return _finish([{
            "guid": r.get("guid"),
            "indexerId": r.get("indexerId"),
            "indexer": r.get("indexer"),
            "title": r.get("title"),
            "size": r.get("size"),
            "age": r.get("age"),
            "seeders": r.get("seeders"),
            "leechers": r.get("leechers"),
            "protocol": r.get("protocol"),
            "quality": (r.get("quality") or {}).get("quality", {}).get("name"),
            "languages": [l.get("name") for l in (r.get("languages") or [])],
            "rejected": r.get("rejected"),
            "rejections": r.get("rejections"),
            "seasonPack": r.get("fullSeason"),
        } for r in data[:limit]])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_release_grab(guid: str, indexer_id: int, confirm: bool = False) -> Any:
    """Send a specific release (from sonarr_release_search) to the download
    client. WRITES: confirm-gated.

    Args:
        guid: Release guid from sonarr_release_search.
        indexer_id: indexerId from the same result row.
        confirm: Must be true — starts a real download.
    """
    try:
        if not guid:
            raise SonarrError("guid is required")
        if not confirm:
            return _need_confirm(f"grab release {guid!r} from indexer {indexer_id}")
        return CLIENT.request("POST", "/api/v3/release",
                              body={"guid": guid, "indexerId": int(indexer_id)})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Commands (trigger async jobs)                                               #
# --------------------------------------------------------------------------- #
SONARR_COMMANDS = {
    "RefreshSeries": "Refresh metadata + disk scan for seriesIds (or all if absent)",
    "RescanSeries": "Disk rescan only (no metadata refresh) for seriesIds (or all)",
    "SeriesSearch": "Search indexers for missing episodes of seriesIds",
    "SeasonSearch": "Search for all episodes in a series+season (seriesId, seasonNumber)",
    "EpisodeSearch": "Search for specific episodeIds",
    "EpisodesSearch": "Search for multiple episodeIds",
    "DownloadedEpisodesScan": "Scan drone factory / completed downloads",
    "RenameSeries": "Rename files for seriesIds (uses renaming config)",
    "Backup": "Trigger an immediate database backup",
    "ApplicationUpdate": "Check for + install an app update (admin only)",
    "RefreshMonitoredDownloads": "Sync state with download clients",
    "MissingEpisodesSearch": "Search for all monitored missing episodes",
    "RssSync": "Force a sync of all RSS indexers",
}


@mcp.tool()
def sonarr_command(name: str, series_ids: Optional[list] = None,
                   episode_ids: Optional[list] = None, season_number: Optional[int] = None,
                   confirm: bool = False, extra: str = "") -> Any:
    """Trigger a Sonarr async command (POST /command). Returns the created job.
    WRITES: confirm-gated.

    Common names: RefreshSeries, SeriesSearch, SeasonSearch, EpisodeSearch,
    EpisodesSearch, DownloadedEpisodesScan, RenameSeries, Backup,
    MissingEpisodesSearch, RssSync, ApplicationUpdate.

    Args:
        name: Command name (see skill for the full list).
        series_ids: Optional list of series ids.
        episode_ids: Optional list of episode ids (EpisodeSearch/EpisodesSearch).
        season_number: Required for SeasonSearch (with series_ids).
        confirm: Must be true — triggers active work.
        extra: Optional JSON object string of pass-through command params.
    """
    try:
        if name not in SONARR_COMMANDS:
            raise SonarrError(
                f"Unknown command '{name}'. Known: {', '.join(sorted(SONARR_COMMANDS))}"
            )
        if not confirm:
            scope_bits = []
            if series_ids: scope_bits.append(f"seriesIds {series_ids}")
            if episode_ids: scope_bits.append(f"episodeIds {episode_ids}")
            if season_number is not None: scope_bits.append(f"season {season_number}")
            scope = (" for " + ", ".join(scope_bits)) if scope_bits else " (scope: all/library-wide)"
            return _need_confirm(f"run command '{name}'{scope}")
        body: dict = {"name": name}
        if series_ids is not None:
            body["seriesIds"] = list(series_ids)
        if episode_ids is not None:
            body["episodeIds"] = list(episode_ids)
        if season_number is not None:
            body["seasonNumber"] = season_number
        extra_params = _parse_json_arg("extra", extra)
        if extra_params is not None:
            if not isinstance(extra_params, dict):
                raise SonarrError("extra must be a JSON object")
            body.update(extra_params)
        return CLIENT.request("POST", "/api/v3/command", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_command_status(command_id: int) -> Any:
    """Status of one command (poll after sonarr_command)."""
    try:
        return CLIENT.request("GET", f"/api/v3/command/{command_id}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_search_episode(episode_id: int, confirm: bool = False) -> Any:
    """Convenience: trigger EpisodeSearch for one episode."""
    return sonarr_command("EpisodeSearch", episode_ids=[episode_id], confirm=confirm)


@mcp.tool()
def sonarr_search_season(series_id: int, season_number: int, confirm: bool = False) -> Any:
    """Convenience: trigger SeasonSearch."""
    return sonarr_command("SeasonSearch", series_ids=[series_id],
                          season_number=season_number, confirm=confirm)


@mcp.tool()
def sonarr_refresh_series(series_id: int, confirm: bool = False) -> Any:
    """Convenience: trigger RefreshSeries for one series."""
    return sonarr_command("RefreshSeries", series_ids=[series_id], confirm=confirm)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sonarr_quality_profiles() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/qualityProfile") or []
        return [{"id": p.get("id"), "name": p.get("name"),
                 "upgradeAllowed": p.get("upgradeAllowed"),
                 "cutoff": p.get("cutoff"),
                 "items": [(it.get("quality") or {}).get("name") for it in p.get("items", []) if it.get("allowed")]}
                for p in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_language_profiles() -> Any:
    """Language profiles (Sonarr-specific — for series add)."""
    try:
        data = CLIENT.request("GET", "/api/v3/languageProfile") or []
        return [{"id": p.get("id"), "name": p.get("name"),
                 "upgradeAllowed": p.get("upgradeAllowed"),
                 "languages": [(l.get("language") or {}).get("name")
                               for l in p.get("languages", []) if l.get("allowed")]}
                for p in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_languages() -> Any:
    """Languages known to Sonarr (id + name)."""
    try:
        data = CLIENT.request("GET", "/api/v3/language") or []
        return [{"id": l.get("id"), "name": l.get("name"),
                 "nameLower": l.get("nameLower")} for l in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_root_folders() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/rootfolder") or []
        return [{"id": r.get("id"), "path": r.get("path"),
                 "freeSpace": r.get("freeSpace"), "unmappedFolders": r.get("unmappedFolders")}
                for r in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_tags() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/tag") or []
        return [{"id": t.get("id"), "label": t.get("label")} for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_notifications() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/notification") or []
        return [{"id": n.get("id"), "name": n.get("name"),
                 "implementation": n.get("implementation"),
                 "supportsOnGrab": n.get("supportsOnGrab"),
                 "supportsOnDownload": n.get("supportsOnDownload")}
                for n in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_download_clients() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/downloadclient") or []
        return [{"id": c.get("id"), "name": c.get("name"),
                 "implementation": c.get("implementation"),
                 "enable": c.get("enable"), "protocol": c.get("protocol")}
                for c in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_indexers() -> Any:
    try:
        data = CLIENT.request("GET", "/api/v3/indexer") or []
        return [{"id": i.get("id"), "name": i.get("name"),
                 "implementation": i.get("implementation"),
                 "enable": i.get("enable"), "protocol": i.get("protocol")}
                for i in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_import_lists() -> Any:
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


# --------------------------------------------------------------------------- #
# Round 2: high-value gaps from the live-route audit                           #
# (queue mgmt, parse, log/filesystem, config sections, tag CRUD, blocklist,    #
#  system restart/shutdown, manual import, more reads)                         #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sonarr_queue_delete(queue_id: int, blacklist: bool = False,
                        remove_from_client: bool = False,
                        confirm: bool = False) -> Any:
    """Remove a single item from the active queue. WRITES: confirm-gated."""
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
def sonarr_queue_grab(queue_id: int, confirm: bool = False) -> Any:
    """Re-grab a release for an aggregated queue item. WRITES: confirm-gated."""
    try:
        if not confirm:
            return _need_confirm(f"re-grab queue item {queue_id}")
        return CLIENT.request("POST", f"/api/v3/queue/grab/{queue_id}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_series_bulk_edit(series_ids: list, monitored: Optional[bool] = None,
                             quality_profile_id: Optional[int] = None,
                             language_profile_id: Optional[int] = None,
                             series_type: Optional[str] = None,
                             tags: Optional[list] = None,
                             apply_tags: str = "add",
                             move_files: bool = False,
                             confirm: bool = False) -> Any:
    """Bulk-edit multiple series in one operation. WRITES: confirm-gated.

    Args:
        series_ids: List of Sonarr series ids.
        monitored: Set monitored state (None = unchanged).
        quality_profile_id: Set quality profile (None = unchanged).
        language_profile_id: Set language profile (None = unchanged).
        series_type: standard | anime | daily.
        tags: List of tag ids (with apply_tags).
        apply_tags: add | remove | replace | sync.
        move_files: Move files when path changes.
        confirm: Must be true.
    """
    try:
        if not series_ids:
            raise SonarrError("series_ids must be non-empty")
        if not confirm:
            changes = []
            if monitored is not None: changes.append(f"monitored={monitored}")
            if quality_profile_id is not None: changes.append(f"qualityProfileId={quality_profile_id}")
            if language_profile_id is not None: changes.append(f"languageProfileId={language_profile_id}")
            return _need_confirm(f"bulk-edit series {series_ids}: {', '.join(changes) or 'no changes'}")
        body: dict = {"seriesIds": list(series_ids), "moveFiles": bool(move_files)}
        if monitored is not None: body["monitored"] = bool(monitored)
        if quality_profile_id is not None: body["qualityProfileId"] = int(quality_profile_id)
        if language_profile_id is not None: body["languageProfileId"] = int(language_profile_id)
        if series_type: body["seriesType"] = series_type
        if tags is not None:
            body["tags"] = list(tags)
            body["applyTags"] = apply_tags
        return CLIENT.request("PUT", "/api/v3/series/editor", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_parse(title: str) -> Any:
    """Parse a release title to see what series + episode + quality Sonarr
    would match it to. READ-ONLY."""
    try:
        return CLIENT.request("GET", "/api/v3/parse", params={"title": title})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_log_files() -> Any:
    """List the on-disk log files (and update-log files) with sizes."""
    try:
        data = CLIENT.request("GET", "/api/v3/log/file") or []
        return [{"filename": f.get("name"), "lastWriteTime": f.get("lastWriteTime"),
                 "path": f.get("path"), "size": f.get("contentsLength")}
                for f in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_filesystem(path: str = "/", include_files: bool = False) -> Any:
    """Browse the server's filesystem (used when configuring root folders)."""
    try:
        params = {"path": path}
        if include_files: params["includeFiles"] = "true"
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
def sonarr_history_since(since: str, event_type: str = "") -> Any:
    """History since an ISO timestamp (lighter than paged history)."""
    try:
        params = {"since": since}
        if event_type: params["eventType"] = event_type
        return _finish(CLIENT.request("GET", "/api/v3/history/since", params=params))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_rename_preview(series_ids: list) -> Any:
    """Preview what files WOULD be renamed, without doing it. READ-ONLY.

    Note: Sonarr's /rename endpoint accepts a SINGLE seriesId per request; this
    tool loops over the supplied ids and returns a merged list.
    """
    try:
        if not series_ids:
            raise SonarrError("series_ids must be non-empty")
        out = []
        for sid in series_ids:
            res = CLIENT.request("GET", "/api/v3/rename", params={"seriesId": int(sid)}) or []
            for r in res:
                r["_seriesId"] = sid
                out.append(r)
        return out
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_quality_definitions() -> Any:
    """Quality definitions (size-by-quality matrix)."""
    try:
        return CLIENT.request("GET", "/api/v3/qualityDefinition")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_delay_profiles() -> Any:
    """Delay profiles (how long Sonarr waits before grabbing a release)."""
    try:
        return CLIENT.request("GET", "/api/v3/delayprofile")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_remote_path_mappings() -> Any:
    """Remote path mappings (Docker path translation between download client and Sonarr)."""
    try:
        return CLIENT.request("GET", "/api/v3/remotepathmapping")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_release_profiles() -> Any:
    """Release profiles (must-contain / must-not-contain rules)."""
    try:
        return CLIENT.request("GET", "/api/v3/releaseprofile")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_import_exclusions() -> Any:
    """Import exclusions (series that will never be auto-added from import lists)."""
    try:
        return CLIENT.request("GET", "/api/v3/importlistexclusion")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_auto_tagging() -> Any:
    """Auto-tagging rules."""
    try:
        return CLIENT.request("GET", "/api/v3/autoTagging")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_tag_details() -> Any:
    """All tags with counts of series / delay profiles / etc. that use each."""
    try:
        data = CLIENT.request("GET", "/api/v3/tag/detail") or []
        return [{"id": t.get("id"), "label": t.get("label"),
                 "seriesCount": len(t.get("seriesIds") or [])}
                for t in data]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_config_section(section: str) -> Any:
    """Read a specific config section. READ-ONLY.

    Args:
        section: One of: host, ui, mediamanagement, indexer, downloadclient,
            metadata, importlist, naming.
    """
    try:
        if not section:
            raise SonarrError("section is required (host, ui, mediamanagement, indexer, "
                              "downloadclient, metadata, importlist, naming)")
        return CLIENT.request("GET", f"/api/v3/config/{section}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_update_config_section(section: str, patch: str,
                                  confirm: bool = False) -> Any:
    """Update a config section SAFELY: GET-merge-PUT. WRITES: confirm-gated."""
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise SonarrError("patch must be a non-empty JSON object")
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
def sonarr_blocklist_delete(blocklist_id: int, confirm: bool = False) -> Any:
    """Remove one entry from the blocklist. WRITES: confirm-gated."""
    try:
        if not confirm:
            return _need_confirm(f"delete blocklist entry {blocklist_id}")
        CLIENT.request("DELETE", f"/api/v3/blocklist/{blocklist_id}")
        return {"deleted": True, "blocklist_id": blocklist_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_tag_create(label: str, confirm: bool = False) -> Any:
    """Create a new tag. WRITES: confirm-gated."""
    try:
        if not label or not label.strip():
            raise SonarrError("label is required")
        if not confirm:
            return _need_confirm(f"create tag '{label}'")
        return CLIENT.request("POST", "/api/v3/tag", body={"label": label.strip()})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_tag_delete(tag_id: int, confirm: bool = False) -> Any:
    """Delete a tag. WRITES: confirm-gated."""
    try:
        if not confirm:
            return _need_confirm(f"delete tag {tag_id}")
        CLIENT.request("DELETE", f"/api/v3/tag/{tag_id}")
        return {"deleted": True, "tag_id": tag_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_manual_import(folder: str, import_mode: str = "move",
                         confirm: bool = False) -> Any:
    """Perform a manual import for files in a folder. WRITES: confirm-gated.

    Args:
        folder: The server-side path to scan.
        import_mode: 'move' (default) | 'copy'.
        confirm: Must be true.
    """
    try:
        if not folder:
            raise SonarrError("folder is required")
        if not confirm:
            return _need_confirm(f"manual import {folder} (mode={import_mode})")
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
def sonarr_provider_test(provider_type: str, definition: str) -> Any:
    """Test a notification / downloadclient / indexer / importlist / metadata
    configuration WITHOUT saving. WRITE (no save) but no confirm needed."""
    try:
        pt = provider_type.lower().strip()
        if pt not in ("notification", "downloadclient", "indexer",
                      "importlist", "metadata"):
            raise SonarrError(f"provider_type must be one of notification, "
                              f"downloadclient, indexer, importlist, metadata")
        body = _parse_json_arg("definition", definition)
        if not isinstance(body, dict):
            raise SonarrError("definition must be a JSON object")
        return CLIENT.request("POST", f"/api/v3/{pt}/test", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_system_routes() -> Any:
    """Return the LIVE route table (~470 operations) — Sonarr's own introspection
    of its full API surface."""
    try:
        return _finish(CLIENT.live_routes())
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_system_restart(confirm: bool = False, acknowledge: str = "") -> Any:
    """Restart the Sonarr service/process. DOUBLY GATED.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'restart'.
    """
    try:
        if not confirm or acknowledge != "restart":
            return {
                "confirmation_required": True,
                "note": ("Restarting Sonarr interrupts active downloads and scans. "
                         "Re-run with confirm=true AND acknowledge='restart'."),
            }
        CLIENT.request("POST", "/api/v3/system/restart")
        return {"restart_initiated": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_system_shutdown(confirm: bool = False, acknowledge: str = "") -> Any:
    """Shut down Sonarr. DOUBLY GATED.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'shutdown'.
    """
    try:
        if not confirm or acknowledge != "shutdown":
            return {
                "confirmation_required": True,
                "note": ("Shutting down Sonarr takes the app offline until "
                         "manually restarted. Re-run with confirm=true AND "
                         "acknowledge='shutdown'."),
            }
        CLIENT.request("POST", "/api/v3/system/shutdown")
        return {"shutdown_initiated": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_crud(resource: str, action: str, id: Optional[int] = None,
                data: str = "", confirm: bool = False) -> Any:
    """Generic CRUD wrapper for Sonarr resources that follow the standard
    list/get/create/update/delete/bulk pattern. Use this for the long tail of
    config entities — notifications, download clients, indexers, import lists,
    metadata, quality profiles, language profiles, custom formats, delay/release
    profiles, root folders, remote path mappings, auto-tagging, custom filters,
    importlistexclusions.

    Args:
        resource: One of: notification, downloadclient, indexer, importlist,
            metadata, qualityprofile, languageprofile, customformat,
            delayprofile, releaseprofile, rootfolder, remotepathmapping,
            autoTagging, customFilter, importlistexclusion.
        action: One of: list, get, schema, create, update, delete,
            bulk_update, bulk_delete, testall.
        id: Resource id (required for get/update/delete).
        data: JSON body string. Required for create/update/bulk_update. For
            bulk_delete pass '{"ids": [1,2,3]}'.
        confirm: Required for any write.
    """
    try:
        RESOURCE_ALIASES = {
            "qualityprofile": "qualityProfile",
            "languageprofile": "languageProfile",
            "customformat": "customFormat",
            "delayprofile": "delayProfile",
            "releaseprofile": "releaseProfile",
            "rootfolder": "rootFolder",
            "remotepathmapping": "remotePathMapping",
            "autotagging": "autoTagging",
            "customfilter": "customFilter",
            "importlistexclusion": "importlistexclusion",
        }
        res_lc = (resource or "").strip().lower()
        if not res_lc:
            raise SonarrError("resource is required")
        res = RESOURCE_ALIASES.get(res_lc, res_lc)
        valid_actions = ("list", "get", "schema", "create", "update", "delete",
                         "bulk_update", "bulk_delete", "testall")
        act = (action or "").strip().lower()
        if act not in valid_actions:
            raise SonarrError(f"action must be one of {valid_actions}; got {action!r}")
        if act == "list":
            return _finish(CLIENT.request("GET", f"/api/v3/{res}"))
        if act == "schema":
            return CLIENT.request("GET", f"/api/v3/{res}/schema")
        if act == "get":
            if id is None:
                raise SonarrError("id is required for get")
            return CLIENT.request("GET", f"/api/v3/{res}/{int(id)}")
        if act == "testall":
            return CLIENT.request("POST", f"/api/v3/{res}/testall")
        if not confirm:
            return _need_confirm(f"{act} {resource} id={id} data={data[:200]}")
        body = _parse_json_arg("data", data)
        if act == "create":
            if body is None:
                raise SonarrError("data is required for create")
            return CLIENT.request("POST", f"/api/v3/{res}", body=body)
        if act == "update":
            if id is None:
                raise SonarrError("id is required for update")
            if body is None:
                raise SonarrError("data is required for update (full object)")
            return CLIENT.request("PUT", f"/api/v3/{res}/{int(id)}", body=body)
        if act == "delete":
            if id is None:
                raise SonarrError("id is required for delete")
            CLIENT.request("DELETE", f"/api/v3/{res}/{int(id)}")
            return {"deleted": True, "resource": resource, "id": int(id)}
        if act == "bulk_update":
            if not isinstance(body, list):
                raise SonarrError("data must be a JSON array of full objects for bulk_update")
            return CLIENT.request("PUT", f"/api/v3/{res}/bulk", body=body)
        if act == "bulk_delete":
            if not isinstance(body, dict) or "ids" not in body:
                raise SonarrError("data must be {\"ids\": [...]} for bulk_delete")
            return CLIENT.request("DELETE", f"/api/v3/{res}/bulk", body=body)
        raise SonarrError(f"unhandled action {act}")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_blocklist_bulk_delete(ids: list, confirm: bool = False) -> Any:
    """Bulk-remove blocklist entries. WRITES: confirm-gated."""
    try:
        if not ids:
            raise SonarrError("ids must be non-empty")
        if not confirm:
            return _need_confirm(f"bulk-delete blocklist ids {ids}")
        return CLIENT.request("DELETE", "/api/v3/blocklist/bulk", body={"ids": list(ids)})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_series_bulk_delete(series_ids: list, delete_files: bool = False,
                               add_import_exclusion: bool = False,
                               confirm: bool = False) -> Any:
    """Delete multiple series in one call. WRITES: confirm-gated.
    IRREVERSIBLE if delete_files=True."""
    try:
        if not series_ids:
            raise SonarrError("series_ids must be non-empty")
        if not confirm:
            return _need_confirm(
                f"bulk-delete series {series_ids} "
                f"(delete_files={delete_files}, add_import_exclusion={add_import_exclusion})"
            )
        body: dict = {"seriesIds": list(series_ids),
                      "addImportExclusion": bool(add_import_exclusion),
                      "deleteFiles": bool(delete_files)}
        return CLIENT.request("DELETE", "/api/v3/series/editor", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_queue_bulk_delete(queue_ids: list, blacklist: bool = False,
                              remove_from_client: bool = False,
                              confirm: bool = False) -> Any:
    """Remove multiple items from the queue in one call. WRITES: confirm-gated."""
    try:
        if not queue_ids:
            raise SonarrError("queue_ids must be non-empty")
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
def sonarr_provider_action(provider_type: str, id: int, action_name: str,
                            confirm: bool = False, extra: str = "") -> Any:
    """Invoke a provider-specific action. WRITE: confirm-gated.

    Args:
        extra: Optional JSON object string of extra action params.
    """
    try:
        pt = (provider_type or "").lower().strip()
        if pt not in ("notification", "downloadclient", "indexer",
                      "importlist", "metadata"):
            raise SonarrError(f"provider_type must be notification/downloadclient/"
                              f"indexer/importlist/metadata")
        if not action_name:
            raise SonarrError("action_name is required")
        if not confirm:
            return _need_confirm(f"action '{action_name}' on {pt}/{id}")
        body = {"name": action_name}
        extra_params = _parse_json_arg("extra", extra)
        if extra_params is not None:
            if not isinstance(extra_params, dict):
                raise SonarrError("extra must be a JSON object")
            body.update(extra_params)
        return CLIENT.request("POST", f"/api/v3/{pt}/action/{int(id)}", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_season_pass(series_ids: list, monitored: bool,
                        confirm: bool = False) -> Any:
    """Update the season-pass monitoring map — bulk-toggle season monitoring
    across multiple series at once. WRITES: confirm-gated.

    Args:
        series_ids: List of series ids to update.
        monitored: True to monitor, False to unmonitor.
        confirm: Must be true.
    """
    try:
        if not series_ids:
            raise SonarrError("series_ids must be non-empty")
        if not confirm:
            return _need_confirm(
                f"season-pass: set monitored={monitored} for series {series_ids}"
            )
        body = {
            "seriesIds": list(series_ids),
            "monitored": bool(monitored),
            "seasons": [],  # empty = apply to all seasons of each series
        }
        return CLIENT.request("POST", "/api/v3/seasonPass", body=body)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sonarr_calendar_ics(start: str = "", end: str = "", tags: str = "",
                         unmonitored: bool = False) -> Any:
    """Fetch the iCalendar feed of upcoming episode airings (the .ics payload)."""
    import datetime as dt
    try:
        today = dt.date.today()
        params = {
            "start": start or (today - dt.timedelta(days=7)).isoformat(),
            "end": end or (today + dt.timedelta(days=90)).isoformat(),
        }
        if tags: params["tags"] = tags
        if unmonitored: params["unmonitored"] = "true"
        return CLIENT.request("GET", "/feed/v3/calendar/sonarr.ics", params=params, raw=True)
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Curated-tool registry — drives the `curated: True/False` annotation in      #
# sonarr_list_endpoints so the user sees at-a-glance what's ergonomic vs       #
# generic-only.                                                                #
# --------------------------------------------------------------------------- #
CURATED_TOOLS: dict[tuple[str, str], str] = {
    # Generic / system
    ("GET", "/api/v3/system/status"):                 "sonarr_status",
    ("GET", "/api/v3/system/task"):                   "sonarr_system_tasks",
    ("GET", "/api/v3/system/backup"):                 "sonarr_system_backups",
    ("GET", "/api/v3/system/routes"):                 "sonarr_system_routes",
    ("POST", "/api/v3/system/restart"):               "sonarr_system_restart",
    ("POST", "/api/v3/system/shutdown"):              "sonarr_system_shutdown",
    ("GET", "/api/v3/log"):                           "sonarr_logs",
    ("GET", "/api/v3/log/file"):                      "sonarr_log_files",
    ("GET", "/api/v3/health"):                        "sonarr_status",
    ("GET", "/api/v3/queue/status"):                  "sonarr_status",
    ("GET", "/api/v3/diskspace"):                     "sonarr_status",
    # Library
    ("GET", "/api/v3/series"):                        "sonarr_list_series",
    ("GET", "/api/v3/series/{id}"):                   "sonarr_get_series",
    ("GET", "/api/v3/series/lookup"):                 "sonarr_lookup_series",
    ("POST", "/api/v3/series"):                       "sonarr_add_series",
    ("PUT", "/api/v3/series/{id}"):                   "sonarr_update_series",
    ("PUT", "/api/v3/series/editor"):                 "sonarr_series_bulk_edit",
    ("DELETE", "/api/v3/series/{id}"):                "sonarr_delete_series",
    ("GET", "/api/v3/episode"):                       "sonarr_episodes",
    ("GET", "/api/v3/episode/{id}"):                  "sonarr_episodes",
    ("PUT", "/api/v3/episode/monitor"):               "sonarr_episode_monitor",
    ("GET", "/api/v3/episodeFile"):                   "sonarr_episode_files",
    ("GET", "/api/v3/episodeFile/{id}"):              "sonarr_episode_files",
    ("DELETE", "/api/v3/episodeFile/{id}"):           "sonarr_episode_file_delete",
    ("GET", "/api/v3/rename"):                        "sonarr_rename_preview",
    # Activity
    ("GET", "/api/v3/calendar"):                      "sonarr_calendar",
    ("GET", "/api/v3/queue"):                         "sonarr_queue",
    ("DELETE", "/api/v3/queue/{id}"):                 "sonarr_queue_delete",
    ("POST", "/api/v3/queue/grab/{id}"):              "sonarr_queue_grab",
    ("GET", "/api/v3/history"):                       "sonarr_history",
    ("GET", "/api/v3/history/since"):                 "sonarr_history_since",
    ("GET", "/api/v3/wanted/missing"):                "sonarr_wanted_missing",
    ("GET", "/api/v3/wanted/cutoff"):                 "sonarr_wanted_cutoff",
    ("GET", "/api/v3/blocklist"):                     "sonarr_blocklist",
    ("DELETE", "/api/v3/blocklist/{id}"):             "sonarr_blocklist_delete",
    ("GET", "/api/v3/release"):                       "sonarr_release_search",
    ("POST", "/api/v3/release"):                      "sonarr_release_grab",
    ("POST", "/api/v3/manualimport"):                 "sonarr_manual_import",
    ("GET", "/api/v3/manualimport"):                  "sonarr_manual_import",
    ("GET", "/api/v3/parse"):                         "sonarr_parse",
    ("GET", "/api/v3/filesystem"):                    "sonarr_filesystem",
    # Commands
    ("POST", "/api/v3/command"):                      "sonarr_command",
    ("GET", "/api/v3/command/{id}"):                  "sonarr_command_status",
    # Config
    ("GET", "/api/v3/qualityProfile"):                "sonarr_quality_profiles",
    ("GET", "/api/v3/qualityDefinition"):             "sonarr_quality_definitions",
    ("GET", "/api/v3/languageProfile"):               "sonarr_language_profiles",
    ("GET", "/api/v3/delayprofile"):                  "sonarr_delay_profiles",
    ("GET", "/api/v3/releaseprofile"):                "sonarr_release_profiles",
    ("GET", "/api/v3/remotepathmapping"):             "sonarr_remote_path_mappings",
    ("GET", "/api/v3/autoTagging"):                   "sonarr_auto_tagging",
    ("GET", "/api/v3/importlistexclusion"):           "sonarr_import_exclusions",
    ("GET", "/api/v3/config/host"):                   "sonarr_config_section",
    ("GET", "/api/v3/config/ui"):                     "sonarr_config_section",
    ("GET", "/api/v3/config/mediamanagement"):        "sonarr_config_section",
    ("GET", "/api/v3/config/indexer"):                "sonarr_config_section",
    ("GET", "/api/v3/config/downloadclient"):         "sonarr_config_section",
    ("GET", "/api/v3/config/metadata"):               "sonarr_config_section",
    ("GET", "/api/v3/config/importlist"):             "sonarr_config_section",
    ("GET", "/api/v3/config/naming"):                 "sonarr_config_section",
    ("GET", "/api/v3/language"):                      "sonarr_languages",
    ("GET", "/api/v3/rootfolder"):                    "sonarr_root_folders",
    ("GET", "/api/v3/tag"):                           "sonarr_tags",
    ("GET", "/api/v3/tag/detail"):                    "sonarr_tag_details",
    ("POST", "/api/v3/tag"):                          "sonarr_tag_create",
    ("DELETE", "/api/v3/tag/{id}"):                   "sonarr_tag_delete",
    ("GET", "/api/v3/notification"):                  "sonarr_notifications",
    ("GET", "/api/v3/downloadclient"):                "sonarr_download_clients",
    ("GET", "/api/v3/indexer"):                       "sonarr_indexers",
    ("GET", "/api/v3/importlist"):                    "sonarr_import_lists",
    ("POST", "/api/v3/notification/test"):            "sonarr_provider_test",
    ("POST", "/api/v3/downloadclient/test"):          "sonarr_provider_test",
    ("POST", "/api/v3/indexer/test"):                 "sonarr_provider_test",
    ("POST", "/api/v3/importlist/test"):              "sonarr_provider_test",
    ("POST", "/api/v3/metadata/test"):                "sonarr_provider_test",
    # CRUD-wrapped resources (sonarr_crud + bulk tools)
    ("GET", "/api/v3/notification/{id}"):             "sonarr_crud",
    ("POST", "/api/v3/notification"):                 "sonarr_crud",
    ("PUT", "/api/v3/notification/{id}"):             "sonarr_crud",
    ("DELETE", "/api/v3/notification/{id}"):          "sonarr_crud",
    ("POST", "/api/v3/notification/testall"):         "sonarr_crud",
    ("POST", "/api/v3/notification/action/{id}"):     "sonarr_provider_action",
    ("GET", "/api/v3/downloadclient/{id}"):           "sonarr_crud",
    ("POST", "/api/v3/downloadclient"):               "sonarr_crud",
    ("PUT", "/api/v3/downloadclient/{id}"):           "sonarr_crud",
    ("DELETE", "/api/v3/downloadclient/{id}"):        "sonarr_crud",
    ("POST", "/api/v3/downloadclient/testall"):       "sonarr_crud",
    ("GET", "/api/v3/indexer/{id}"):                  "sonarr_crud",
    ("POST", "/api/v3/indexer"):                      "sonarr_crud",
    ("PUT", "/api/v3/indexer/{id}"):                  "sonarr_crud",
    ("DELETE", "/api/v3/indexer/{id}"):               "sonarr_crud",
    ("POST", "/api/v3/indexer/testall"):              "sonarr_crud",
    ("GET", "/api/v3/importlist/{id}"):               "sonarr_crud",
    ("POST", "/api/v3/importlist"):                   "sonarr_crud",
    ("PUT", "/api/v3/importlist/{id}"):               "sonarr_crud",
    ("DELETE", "/api/v3/importlist/{id}"):            "sonarr_crud",
    ("POST", "/api/v3/importlist/testall"):           "sonarr_crud",
    ("POST", "/api/v3/importlist/action/{id}"):       "sonarr_provider_action",
    ("GET", "/api/v3/metadata/{id}"):                 "sonarr_crud",
    ("POST", "/api/v3/metadata"):                     "sonarr_crud",
    ("PUT", "/api/v3/metadata/{id}"):                 "sonarr_crud",
    ("DELETE", "/api/v3/metadata/{id}"):              "sonarr_crud",
    ("POST", "/api/v3/metadata/testall"):             "sonarr_crud",
    ("POST", "/api/v3/metadata/action/{id}"):         "sonarr_provider_action",
    ("GET", "/api/v3/qualityProfile/{id}"):           "sonarr_crud",
    ("POST", "/api/v3/qualityProfile"):               "sonarr_crud",
    ("PUT", "/api/v3/qualityProfile/{id}"):           "sonarr_crud",
    ("DELETE", "/api/v3/qualityProfile/{id}"):        "sonarr_crud",
    ("GET", "/api/v3/qualityprofile/schema"):         "sonarr_crud",
    ("GET", "/api/v3/languageProfile/{id}"):          "sonarr_crud",
    ("POST", "/api/v3/languageProfile"):              "sonarr_crud",
    ("PUT", "/api/v3/languageProfile/{id}"):          "sonarr_crud",
    ("DELETE", "/api/v3/languageProfile/{id}"):       "sonarr_crud",
    ("GET", "/api/v3/customFormat/{id}"):             "sonarr_crud",
    ("POST", "/api/v3/customFormat"):                 "sonarr_crud",
    ("PUT", "/api/v3/customFormat/{id}"):             "sonarr_crud",
    ("DELETE", "/api/v3/customFormat/{id}"):          "sonarr_crud",
    ("GET", "/api/v3/customformat/schema"):           "sonarr_crud",
    ("GET", "/api/v3/delayProfile/{id}"):             "sonarr_crud",
    ("POST", "/api/v3/delayProfile"):                 "sonarr_crud",
    ("PUT", "/api/v3/delayProfile/{id}"):             "sonarr_crud",
    ("DELETE", "/api/v3/delayProfile/{id}"):          "sonarr_crud",
    ("GET", "/api/v3/releaseProfile/{id}"):           "sonarr_crud",
    ("POST", "/api/v3/releaseProfile"):               "sonarr_crud",
    ("PUT", "/api/v3/releaseProfile/{id}"):           "sonarr_crud",
    ("DELETE", "/api/v3/releaseProfile/{id}"):        "sonarr_crud",
    ("GET", "/api/v3/rootFolder/{id}"):               "sonarr_crud",
    ("POST", "/api/v3/rootFolder"):                   "sonarr_crud",
    ("DELETE", "/api/v3/rootFolder/{id}"):            "sonarr_crud",
    ("GET", "/api/v3/remotePathMapping/{id}"):        "sonarr_crud",
    ("POST", "/api/v3/remotePathMapping"):            "sonarr_crud",
    ("PUT", "/api/v3/remotePathMapping/{id}"):        "sonarr_crud",
    ("DELETE", "/api/v3/remotePathMapping/{id}"):     "sonarr_crud",
    ("GET", "/api/v3/autoTagging/{id}"):              "sonarr_crud",
    ("POST", "/api/v3/autoTagging"):                  "sonarr_crud",
    ("PUT", "/api/v3/autoTagging/{id}"):              "sonarr_crud",
    ("DELETE", "/api/v3/autoTagging/{id}"):           "sonarr_crud",
    ("GET", "/api/v3/autotagging/schema"):            "sonarr_crud",
    ("GET", "/api/v3/customFilter/{id}"):             "sonarr_crud",
    ("POST", "/api/v3/customFilter"):                 "sonarr_crud",
    ("PUT", "/api/v3/customFilter/{id}"):             "sonarr_crud",
    ("DELETE", "/api/v3/customFilter/{id}"):          "sonarr_crud",
    ("GET", "/api/v3/importlistexclusion/{id}"):      "sonarr_crud",
    ("POST", "/api/v3/importlistexclusion"):          "sonarr_crud",
    ("PUT", "/api/v3/importlistexclusion/{id}"):      "sonarr_crud",
    ("DELETE", "/api/v3/importlistexclusion/{id}"):   "sonarr_crud",
    # Bulk operations
    ("DELETE", "/api/v3/blocklist/bulk"):             "sonarr_blocklist_bulk_delete",
    ("DELETE", "/api/v3/series/editor"):              "sonarr_series_bulk_delete",
    ("DELETE", "/api/v3/queue/bulk"):                 "sonarr_queue_bulk_delete",
    ("POST", "/api/v3/seasonPass"):                   "sonarr_season_pass",
    ("GET", "/feed/v3/calendar/sonarr.ics"):          "sonarr_calendar_ics",
}


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("api_key"):
        log("WARNING: no api_key configured — every call will 401. "
            "Fill config.local.json or set SONARR_API_KEY.")
    mcp.run()


if __name__ == "__main__":
    main()
