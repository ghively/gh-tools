#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0",
#   "httpx>=0.27",
# ]
# ///
"""SABnzbd MCP server.

Exposes a SABnzbd usenet downloader (v4+/5+ HTTP API) to Claude through the
Model Context Protocol. Verified against SABnzbd 5.0.4. Two-layer design,
mirroring the other gh-tools plugins:

* GENERIC passthrough (`sabnzbd_call` / `sabnzbd_list_modes`) reaching every
  documented /api mode. SABnzbd has no OpenAPI; the catalog is hand-built
  from the official SABnzbd API wiki + live probes.
* CURATED tools for the common jobs: status/version, queue, history, server
  stats, warnings, pause/resume, add-by-URL, delete/retry jobs, speed limit,
  get/set config. Destructive modes (shutdown/restart) require BOTH
  `confirm=true` AND an explicit `acknowledge="shutdown"`/`"restart"` token.

Auth model (proven live): every request carries the API key as the `apikey`
query parameter. API keys are created under Config > General and grant full
control. 401/`error: Missing api key` = bad key.

SABnzbd conventions this file encodes (all verified live):
* All actions are GET-or-POST /api?mode=<name>&output=json&apikey=<key>.
* Modes that change state accept their inputs as query params (e.g.
  pause?minutes=60, addurl?name=<url>, delete?value=<nzo_id>&del_files=1).
* `queue`, `history`, `fullstatus` return rich nested dicts.
* Server returns `{"error": "..."}` on most failures (HTTP 200, error in body)
  or `{"status": true/false}` for simple acknowledgements.
* `version` returns `{"version": "x.y.z"}`.
* Add NZB by URL: `addurl` with `name=<url>` (URL-encoded).

WRITES are confirm-gated in code. SHUTDOWN/RESTART additionally require an
explicit acknowledgement token — never call these without explicit owner
approval. (During initial development of this integration, a probe of
`mode=shutdown` actually shut the server down. We learned.)

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[sabnzbd-mcp]", *a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #
def _truthy(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _find_config_file() -> Optional[Path]:
    candidates = []
    if os.environ.get("SABNZBD_CONFIG"):
        candidates.append(Path(os.environ["SABNZBD_CONFIG"]))
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
    host = env.get("SABNZBD_HOST", cfg.get("host", ""))
    https = _truthy(env.get("SABNZBD_HTTPS"), cfg.get("https", False))
    port = int(env.get("SABNZBD_PORT", cfg.get("port", 8080)) or 8080)
    url_base = (env.get("SABNZBD_URL_BASE", cfg.get("url_base", "")) or "").strip().strip("/")
    return {
        "host": host, "port": port, "https": https, "url_base": url_base,
        "api_key": env.get("SABNZBD_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("SABNZBD_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("SABNZBD_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }


CONFIG = load_config()
MAX_RESULT_CHARS = 60_000


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class SabnzbdError(Exception):
    pass


class SabnzbdClient:
    """Thin wrapper around SABnzbd's /api mode-based HTTP API."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        base = f"{scheme}://{cfg['host']}:{cfg['port']}"
        if cfg.get("url_base"):
            base += "/" + cfg["url_base"].lstrip("/")
        self.base = base
        self._client = httpx.Client(
            base_url=self.base,
            headers={"Accept": "application/json"},
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
        )
        self._lock = threading.Lock()

    def call(self, mode: str, params: Optional[dict] = None,
             raw: bool = False) -> Any:
        """Invoke a SABnzbd /api mode with output=json + apikey attached.

        Args:
            mode: The mode name (e.g. "queue", "addurl", "version").
            params: Optional extra query params.
            raw: Return raw text (don't parse JSON).
        """
        if not mode:
            raise SabnzbdError("mode is required")
        q = {"mode": mode, "output": "json", "apikey": self.cfg["api_key"]}
        if params:
            for k, v in params.items():
                if v is None or v == "":
                    continue
                q[k] = v
        resp = self._client.get("/api", params=q)
        if resp.status_code == 401:
            raise SabnzbdError("401 Unauthorized — the API key was rejected.")
        if resp.status_code >= 400:
            raise SabnzbdError(f"HTTP {resp.status_code} on mode={mode}: {resp.text[:300]}")
        if not resp.content:
            return None
        if raw:
            return resp.text
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype or resp.text.lstrip().startswith(("{", "[")):
            try:
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                # Some modes return non-JSON; surface as text with a hint.
                raise SabnzbdError(f"mode={mode} returned non-JSON: {resp.text[:200]}") from e
            # SABnzbd often returns {"error": "..."} even with HTTP 200
            if isinstance(data, dict) and "error" in data and len(data) == 1:
                raise SabnzbdError(f"mode={mode} error: {data['error']}")
            return data
        return resp.text


CLIENT = SabnzbdClient(CONFIG)


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
                  f"{MAX_RESULT_CHARS}. Narrow the query (limit/start/search)."),
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
        raise SabnzbdError(f"{name} is not valid JSON: {e}") from e


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


def _bytes_to_human(n: Optional[int]) -> Optional[str]:
    if n is None:
        return None
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} EB"


mcp = FastMCP("sabnzbd")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
# SABnzbd API modes (from the official wiki + live probes on 5.0.4). Each is
# tagged [R]ead / [W]rite so callers can tell at a glance.
MODE_CATALOG: list[dict] = [
    # Status
    {"mode": "version",       "rw": "R", "summary": "SABnzbd version string"},
    {"mode": "fullstatus",    "rw": "R", "summary": "Full status dict (paused, speed, sessions)"},
    {"mode": "queue",         "rw": "R", "summary": "Active download queue (limit/start/search optional)"},
    {"mode": "history",       "rw": "R", "summary": "Completed/failed history (limit/search optional)"},
    {"mode": "server_stats",  "rw": "R", "summary": "Per-server byte totals (total/month/week/day)"},
    {"mode": "warnings",      "rw": "R", "summary": "Recent warnings"},
    {"mode": "get_config",    "rw": "R", "summary": "Full config dict (servers, categories, misc, etc.)"},
    # Queue control (WRITE)
    {"mode": "pause",         "rw": "W", "summary": "Pause queue (optional minutes=N for timed)"},
    {"mode": "resume",        "rw": "W", "summary": "Resume queue"},
    {"mode": "speedlimit",    "rw": "W", "summary": "Set speed limit (value=Kbps or percentage)"},
    {"mode": "pauseall",      "rw": "W", "summary": "Pause ALL actions (queue + post-proc + scanner)"},
    {"mode": "resumeall",     "rw": "W", "summary": "Resume ALL actions"},
    # Job management (WRITE)
    {"mode": "addurl",        "rw": "W", "summary": "Add NZB by URL (name=<url>)"},
    {"mode": "addlocalfile",  "rw": "W", "summary": "Add NZB from local path (name=<path>)"},
    {"mode": "delete",        "rw": "W", "summary": "Delete job(s): value=<nzo_ids> del_files=1"},
    {"mode": "retry",         "rw": "W", "summary": "Retry a failed history job: value=<nzo_id>"},
    {"mode": "change_opts",   "rw": "W", "summary": "Change post-proc options for a job"},
    {"mode": "queue",         "rw": "W", "summary": "Also writable: queue delete/rename/priority via name=..."},
    # Config (WRITE)
    {"mode": "set_config",    "rw": "W", "summary": "Update config: section, keyword, value"},
    {"mode": "set_apikey",    "rw": "W", "summary": "Generate a new API key (DANGEROUS)"},
    # Lifecycle (DANGEROUS)
    {"mode": "restart",       "rw": "W", "summary": "Restart SABnzbd — HEAVILY confirm-gated in tools"},
    {"mode": "shutdown",      "rw": "W", "summary": "Shut down SABnzbd — HEAVILY confirm-gated in tools"},
    # Misc
    {"mode": "history",       "rw": "W", "summary": "History also accepts delete/clear via value=..."},
]


@mcp.tool()
def sabnzbd_call(mode: str, params: str = "") -> Any:
    """Call ANY SABnzbd /api mode — the generic passthrough. Use
    sabnzbd_list_modes to find a mode first.

    Args:
        mode: Mode name (e.g. "queue", "history", "addurl").
        params: Optional query parameters as JSON object string, e.g.
            '{"name": "https://example.com/file.nzb"}'.

    Returns the parsed JSON response. WRITES (mode=pause/resume/addurl/delete/
    set_config/restart/shutdown/etc.) only call after the user has approved.
    """
    try:
        return _finish(CLIENT.call(mode, _parse_json_arg("params", params)))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_list_modes(search: str = "", rw: str = "", limit: int = 40) -> Any:
    """Search the SABnzbd mode catalog (hand-enumerated). The master index
    for sabnzbd_call.

    Args:
        search: Case-insensitive substring matched against mode + summary.
        rw: Filter by "R" (read) or "W" (write).
        limit: Max modes to return.
    """
    modes = MODE_CATALOG
    if rw:
        modes = [m for m in modes if m["rw"].upper() == rw.upper()]
    if search:
        s = search.lower()
        modes = [m for m in modes if s in m["mode"].lower() or s in m["summary"].lower()]
    return _finish({"matched": len(modes), "modes": modes[:limit]})


# --------------------------------------------------------------------------- #
# Status                                                                      #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sabnzbd_status() -> Any:
    """Server health snapshot: version, paused state, current speed, queue
    summary, recent warnings. Call this first."""
    try:
        version = CLIENT.call("version") or {}
        full = (CLIENT.call("fullstatus") or {}).get("status", {})
        q = (CLIENT.call("queue", {"limit": "1"}) or {}).get("queue", {})
        warnings = (CLIENT.call("warnings") or {}).get("warnings", [])
        return {
            "version": version.get("version"),
            "paused": q.get("paused") or full.get("paused"),
            "pause_int": q.get("pause_int") or full.get("pause_int"),
            "speed": q.get("speed"),
            "speedlimit_abs": q.get("speedlimit_abs") or full.get("speedlimit_abs"),
            "speedlimit": q.get("speedlimit") or full.get("speedlimit"),
            "diskspace1": q.get("diskspace1"),
            "diskspace2": q.get("diskspace2"),
            "diskspacetotal1": q.get("diskspacetotal1"),
            "have_warnings": q.get("have_warnings") or full.get("have_warnings"),
            "loadavg": full.get("loadavg"),
            "noofslots": q.get("noofslots"),
            "status": q.get("status"),
            "time_left": q.get("timeleft"),
            "sizeleft": q.get("sizeleft"),
            "recent_warnings": warnings[-5:] if warnings else [],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_version() -> Any:
    """Return the SABnzbd version string only (cheapest liveness check)."""
    try:
        data = CLIENT.call("version") or {}
        return {"version": data.get("version")}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_queue(limit: int = 50, start: int = 0, search: str = "") -> Any:
    """Current download queue with per-slot detail.

    Args:
        limit: Max slots to return (default 50).
        start: Pagination offset.
        search: Filter slots by substring.
    """
    try:
        params: dict = {"limit": str(limit), "start": str(start)}
        if search:
            params["search"] = search
        data = CLIENT.call("queue", params) or {}
        q = data.get("queue") or {}
        return _finish({
            "version": q.get("version"),
            "paused": q.get("paused"),
            "pause_int": q.get("pause_int"),
            "speed": q.get("speed"),
            "speedlimit": q.get("speedlimit"),
            "timeleft": q.get("timeleft"),
            "mb": q.get("mb"),
            "mb_remaining": q.get("mbleft"),
            "noofslots_total": q.get("noofslots"),
            "noofslots": len(q.get("slots") or []),
            "diskspace1": q.get("diskspace1"),
            "diskspace2": q.get("diskspace2"),
            "slots": [{
                "nzo_id": s.get("nzo_id"),
                "filename": s.get("filename"),
                "category": s.get("cat"),
                "priority": s.get("priority"),
                "status": s.get("status"),
                "mb": s.get("mb"),
                "mb_remaining": s.get("mbleft"),
                "percentage": s.get("percentage"),
                "timeleft": s.get("timeleft"),
                "size": s.get("size"),
                "age": s.get("avg_age"),
            } for s in (q.get("slots") or [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_history(limit: int = 25, search: str = "") -> Any:
    """Completed/failed download history.

    Args:
        limit: Max records to return.
        search: Filter by substring.
    """
    try:
        params: dict = {"limit": str(limit)}
        if search:
            params["search"] = search
        data = CLIENT.call("history", params) or {}
        h = data.get("history") or {}
        return _finish({
            "total_size": h.get("total_size"),
            "month_size": h.get("month_size"),
            "week_size": h.get("week_size"),
            "day_size": h.get("day_size"),
            "noofslots": h.get("noofslots"),
            "slots": [{
                "nzo_id": s.get("nzo_id"),
                "name": s.get("name"),
                "status": s.get("status"),
                "stage": s.get("stage"),
                "fail_message": s.get("fail_message"),
                "completed": s.get("completed"),
                "size": s.get("size"),
                "category": s.get("category"),
                "download_time": s.get("download_time"),
                "storage": s.get("storage"),
                "action_line": s.get("action_line"),
            } for s in (h.get("slots") or [])],
        })
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_server_stats() -> Any:
    """Per-server byte totals (total/month/week/day) and per-server daily sums."""
    try:
        data = CLIENT.call("server_stats") or {}
        return data
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_warnings() -> Any:
    """Recent SABnzbd warnings (server, repair, disk space, etc.)."""
    try:
        data = CLIENT.call("warnings") or {}
        return data.get("warnings", [])
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_get_config(section: str = "", keyword: str = "") -> Any:
    """Read SABnzbd configuration.

    Args:
        section: Filter to one section (servers, categories, misc, sorting,
            schedlines, rss, warnings, converters, etc.). Empty = all.
        keyword: Further filter to a specific keyword within the section.
    """
    try:
        params: dict = {}
        if section:
            params["section"] = section
        if keyword:
            params["keyword"] = keyword
        data = CLIENT.call("get_config", params) or {}
        return _finish(data.get("config", data))
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Queue control (WRITE — confirm-gated)                                       #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sabnzbd_pause(minutes: Optional[int] = None, confirm: bool = False) -> Any:
    """Pause the queue. WRITES: confirm-gated.

    Args:
        minutes: If given, pause for N minutes (timed). If absent, indefinite.
        confirm: Must be true.
    """
    try:
        if not confirm:
            duration = f" for {minutes}m" if minutes else " indefinitely"
            return _need_confirm(f"pause the SABnzbd queue{duration}")
        params: dict = {}
        if minutes is not None:
            params["value"] = str(minutes)
        data = CLIENT.call("pause", params)
        return {"paused": True, "minutes": minutes, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_resume(confirm: bool = False) -> Any:
    """Resume the queue. WRITES: confirm-gated.

    Args:
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm("resume the SABnzbd queue")
        data = CLIENT.call("resume")
        return {"resumed": True, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_speed_limit(value: int, confirm: bool = False) -> Any:
    """Set a download speed limit (Kbps or percentage). WRITES: confirm-gated.

    Args:
        value: Speed in KB/s, OR a percentage of line speed (e.g. 50 = 50%).
        confirm: Must be true.
    """
    try:
        if not confirm:
            current = (CLIENT.call("fullstatus") or {}).get("status", {})
            return _need_confirm(
                f"set SABnzbd speed limit to {value} "
                f"(currently {current.get('speedlimit')} / {current.get('speedlimit_abs')})"
            )
        data = CLIENT.call("speedlimit", {"value": str(value)})
        return {"speedlimit_set": value, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Job management (WRITE — confirm-gated)                                      #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sabnzbd_add_url(url: str, pp: str = "", category: str = "", priority: str = "",
                    confirm: bool = False) -> Any:
    """Add an NZB by URL. WRITES: confirm-gated.

    Args:
        url: HTTP(S) URL to the .nzb file.
        pp: Post-processing options (e.g. "3" for repair+unpack+delete).
        category: Category name (must match one configured in SABnzbd).
        priority: Priority (-100 .. 2, where 2 = force).
        confirm: Must be true — adds a real download.
    """
    try:
        if not url or not url.startswith(("http://", "https://")):
            raise SabnzbdError("url must be a http(s) URL")
        if not confirm:
            extras = []
            if pp: extras.append(f"pp={pp}")
            if category: extras.append(f"cat={category}")
            if priority: extras.append(f"priority={priority}")
            tail = (" with " + ", ".join(extras)) if extras else ""
            return _need_confirm(f"add NZB from {url}{tail}")
        params = {"name": url}
        if pp: params["pp"] = pp
        if category: params["cat"] = category
        if priority: params["priority"] = str(priority)
        data = CLIENT.call("addurl", params)
        # addurl returns {"status": true, "nzo_ids": [...]} on success
        return {"added": True, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_delete_jobs(nzo_ids: list, delete_files: bool = False,
                         confirm: bool = False) -> Any:
    """Delete one or more jobs from the queue or history. WRITES: confirm-gated.

    Args:
        nzo_ids: List of nzo_id strings to delete.
        delete_files: Also delete downloaded files from disk (irreversible).
        confirm: Must be true.
    """
    try:
        if not nzo_ids:
            raise SabnzbdError("nzo_ids must be a non-empty list")
        if not confirm:
            return _need_confirm(
                f"delete SABnzbd job(s) {nzo_ids} "
                f"(delete_files={delete_files})"
            )
        params = {"name": "delete", "value": ",".join(nzo_ids)}
        if delete_files:
            params["del_files"] = "1"
        # delete is invoked via the queue OR history endpoint; both accept it.
        data = CLIENT.call("queue", params)
        return {"deleted": True, "nzo_ids": nzo_ids, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_retry_job(nzo_id: str, confirm: bool = False) -> Any:
    """Retry a failed job from history (puts it back in the queue).
    WRITES: confirm-gated.

    Args:
        nzo_id: The nzo_id from history.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"retry SABnzbd job {nzo_id}")
        data = CLIENT.call("retry", {"value": nzo_id})
        return {"retried": True, "nzo_id": nzo_id, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_set_config(section: str, keyword: str, value: str,
                       confirm: bool = False) -> Any:
    """Update a SABnzbd configuration value. WRITES: confirm-gated.

    Args:
        section: Config section (servers, categories, misc, sorting, etc.).
        keyword: The keyword within the section.
        value: The new value (string form).
        confirm: Must be true.
    """
    try:
        if not all([section, keyword]):
            raise SabnzbdError("section and keyword are required")
        if not confirm:
            # Read current so the user sees what they're changing
            current = (CLIENT.call("get_config", {"section": section, "keyword": keyword})
                       or {}).get("config", {})
            cur_val = (current.get(section) or {})
            cur_val = cur_val.get(keyword) if isinstance(cur_val, dict) else cur_val
            return _need_confirm(
                f"set SABnzbd config [{section}].{keyword} "
                f"from {cur_val!r} to {value!r}"
            )
        data = CLIENT.call("set_config", {
            "section": section, "keyword": keyword, "value": value,
        })
        return {"updated": True, "section": section, "keyword": keyword,
                "value": value, "raw": data}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# DANGEROUS — double-gated (confirm + acknowledge token)                      #
# --------------------------------------------------------------------------- #
@mcp.tool()
def sabnzbd_restart(confirm: bool = False, acknowledge: str = "") -> Any:
    """Restart the SABnzbd service/process.

    DOUBLY GATED — requires confirm=true AND acknowledge='restart' (typed).
    This is intentional: SABnzbd honors mode=restart, which kills active
    downloads mid-flight. Only invoke after explicit owner approval.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'restart' (typed confirmation).
    """
    try:
        if not confirm or acknowledge != "restart":
            return {
                "confirmation_required": True,
                "note": ("Restarting SABnzbd kills active downloads and "
                         "interrupts post-proc. To proceed, re-run with "
                         "confirm=true AND acknowledge='restart'."),
            }
        data = CLIENT.call("restart")
        return {"restart_initiated": True, "raw": data,
                "warning": "Server may be unresponsive for a few seconds."}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def sabnzbd_shutdown(confirm: bool = False, acknowledge: str = "") -> Any:
    """Shut down SABnzbd. The container/process must be restarted externally
    (DSM, systemd, Docker) to bring it back.

    DOUBLY GATED — requires confirm=true AND acknowledge='shutdown' (typed).
    SABnzbd honors mode=shutdown and will NOT auto-restart. Only invoke after
    explicit owner approval.

    Args:
        confirm: Must be true.
        acknowledge: Must be the literal string 'shutdown' (typed confirmation).
    """
    try:
        if not confirm or acknowledge != "shutdown":
            return {
                "confirmation_required": True,
                "note": ("Shutting down SABnzbd takes the downloader offline "
                         "until manually restarted. To proceed, re-run with "
                         "confirm=true AND acknowledge='shutdown'."),
            }
        data = CLIENT.call("shutdown")
        return {"shutdown_initiated": True, "raw": data,
                "warning": "Server is going offline; manual restart required."}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Entrypoint                                                                  #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG.get("api_key"):
        log("WARNING: no api_key configured — every call will error. "
            "Fill config.local.json or set SABNZBD_API_KEY.")
    mcp.run()


if __name__ == "__main__":
    main()
