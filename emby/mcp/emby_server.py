#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Emby media server MCP server.

Exposes an Emby server to Claude through the Model Context Protocol.
Tested against Emby Server 4.7.14.0 on Linux. The design is two-layered,
mirroring the Synology/UniFi/GitLab plugins in this repo:

* A GENERIC passthrough (`emby_call` / `emby_list_endpoints`) that can reach
  *any* of the server's REST operations. The endpoint catalog is discovered
  live from the server's own OpenAPI document (`/openapi.json`, ~484
  operations across ~66 service tags on 4.7.14), so it is always accurate for
  the connected version. This is what makes "control everything" true rather
  than aspirational.
* CURATED tools for the common jobs (status, libraries, item search &
  metadata, users & policies, sessions & remote control, scheduled tasks,
  plugins & packages, logs, activity, collections, playlists, configuration)
  so day-to-day tasks are one call with correct params.

Auth model (proven live): every request carries the API key in the
`X-Emby-Token` header (the `api_key` query param also works; we use the
header). API keys are created in the Emby dashboard (Advanced > API Keys)
and act with SERVER ADMIN privilege. 401 = missing/invalid token.

Emby conventions this file encodes (all verified against the live server):
* Paths work with or without the `/emby` prefix; we use the bare form.
* List queries return {"Items": [...], "TotalRecordCount": n}.
* Durations/positions are TICKS: 1 tick = 100 ns; seconds = ticks / 10^7.
* POST /System/Configuration (and /Items/{id}) expect the FULL object —
  posting a partial object silently resets omitted fields. All write tools
  here therefore GET the current object, merge the patch, and POST back.
* User-scoped data (watched state, resume points, favorites) requires a
  UserId; tools default to the configured/first admin user.

Destructive/disruptive writes are confirm-gated in code (`confirm=True`
required). DELETE /Items can remove media FILES from disk — treat with care.

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
    print("[emby-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("EMBY_CONFIG"):
        candidates.append(Path(os.environ["EMBY_CONFIG"]))
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
    return {
        "host": env.get("EMBY_HOST", cfg.get("host", "")),
        "port": int(env.get("EMBY_PORT", cfg.get("port", 8096)) or 8096),
        "https": _truthy(env.get("EMBY_HTTPS"), cfg.get("https", False)),
        "api_key": env.get("EMBY_API_KEY", cfg.get("api_key", "")),
        "verify_ssl": _truthy(env.get("EMBY_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("EMBY_TIMEOUT", cfg.get("timeout", 30)) or 30),
        "default_user": env.get("EMBY_DEFAULT_USER", cfg.get("default_user", "")),
    }


CONFIG = load_config()

TICKS_PER_SECOND = 10_000_000
MAX_RESULT_CHARS = 60_000  # guard against dumping megabytes into the model


# --------------------------------------------------------------------------- #
# HTTP client                                                                 #
# --------------------------------------------------------------------------- #
class EmbyError(Exception):
    pass


class EmbyClient:
    """Thin, thread-safe wrapper that speaks Emby's REST conventions."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        self.base = f"{scheme}://{cfg['host']}:{cfg['port']}"
        self._client = httpx.Client(
            base_url=self.base,
            headers={"X-Emby-Token": cfg["api_key"], "Accept": "application/json"},
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
        )
        self._lock = threading.Lock()
        self._default_user: Optional[dict] = None
        self._openapi_ops: Optional[list] = None

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
        try:
            resp = self._client.request(method.upper(), path, params=params, json=body)
        except httpx.TimeoutException as e:
            # str() of httpx timeout errors is often empty — say what happened.
            raise EmbyError(
                f"Timeout ({type(e).__name__}) after {self.cfg['timeout']}s on "
                f"{method} {path} — server slow or unreachable at {self.base}."
            ) from e
        except httpx.HTTPError as e:
            raise EmbyError(
                f"{type(e).__name__} on {method} {path}: "
                f"{str(e) or 'connection failed'} (target {self.base})"
            ) from e
        if resp.status_code == 401:
            raise EmbyError("401 Unauthorized — the API key was rejected.")
        if resp.status_code == 403:
            raise EmbyError(f"403 Forbidden on {method} {path} — operation not allowed for this key.")
        if resp.status_code >= 400:
            detail = resp.text[:400]
            raise EmbyError(f"HTTP {resp.status_code} on {method} {path}: {detail}")
        if raw:
            return resp.text
        if not resp.content:
            return None
        ctype = resp.headers.get("content-type", "")
        if "json" in ctype:
            return resp.json()
        return resp.text

    # -- helpers ----------------------------------------------------------- #
    def users(self) -> list:
        return self.request("GET", "/Users")

    def default_user(self) -> dict:
        """The user whose view is used for user-scoped queries."""
        with self._lock:
            if self._default_user is not None:
                return self._default_user
            users = self.users()
            wanted = (self.cfg.get("default_user") or "").strip().lower()
            pick = None
            if wanted:
                pick = next((u for u in users if u["Name"].lower() == wanted
                             or u["Id"].lower() == wanted), None)
                if pick is None:
                    log(f"WARNING: default_user '{wanted}' not found; falling back to first admin")
            if pick is None:
                pick = next((u for u in users if u.get("Policy", {}).get("IsAdministrator")), None)
            if pick is None and users:
                pick = users[0]
            if pick is None:
                raise EmbyError("No users found on the server.")
            self._default_user = pick
            return pick

    def resolve_user(self, user: str = "") -> dict:
        """Resolve a username or user id to the full user object."""
        if not user:
            return self.default_user()
        users = self.users()
        u = next((x for x in users if x["Id"].lower() == user.lower()
                  or x["Name"].lower() == user.lower()), None)
        if u is None:
            raise EmbyError(f"No user named or with id '{user}'. Known: "
                            + ", ".join(x["Name"] for x in users))
        return u

    def openapi_ops(self) -> list:
        """Compact operation catalog from the server's live OpenAPI document."""
        with self._lock:
            if self._openapi_ops is not None:
                return self._openapi_ops
        spec = self.request("GET", "/openapi.json")
        ops = []
        for p, methods in spec.get("paths", {}).items():
            for m, op in methods.items():
                if m not in ("get", "post", "put", "delete", "patch", "head", "options"):
                    continue
                params = [
                    {"name": pr.get("name"), "in": pr.get("in"),
                     "required": pr.get("required", False)}
                    for pr in op.get("parameters", [])
                ]
                ops.append({
                    "method": m.upper(),
                    "path": p,
                    "tag": (op.get("tags") or ["untagged"])[0],
                    "summary": op.get("summary", ""),
                    "params": params,
                    "has_body": "requestBody" in op,
                })
        with self._lock:
            self._openapi_ops = ops
        return ops


CLIENT = EmbyClient(CONFIG)


# --------------------------------------------------------------------------- #
# Formatting helpers                                                          #
# --------------------------------------------------------------------------- #
def ticks_to_hms(ticks: Optional[int]) -> Optional[str]:
    if not ticks:
        return None
    s = int(ticks / TICKS_PER_SECOND)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def compact_item(it: dict) -> dict:
    """Trim an Emby item to the fields that matter for browsing."""
    out = {
        "Id": it.get("Id"),
        "Name": it.get("Name"),
        "Type": it.get("Type"),
    }
    for k in ("ProductionYear", "SeriesName", "SeasonName", "IndexNumber",
              "ParentIndexNumber", "CommunityRating", "OfficialRating",
              "Path", "CollectionType", "ChildCount", "RecursiveItemCount",
              "Container", "Status"):
        if it.get(k) is not None:
            out[k] = it[k]
    if it.get("RunTimeTicks"):
        out["RunTime"] = ticks_to_hms(it["RunTimeTicks"])
    ud = it.get("UserData") or {}
    if ud:
        out["Played"] = ud.get("Played")
        if ud.get("PlaybackPositionTicks"):
            out["ResumeAt"] = ticks_to_hms(ud["PlaybackPositionTicks"])
        if ud.get("IsFavorite"):
            out["IsFavorite"] = True
    return out


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
                  f"{MAX_RESULT_CHARS}. Narrow the query (limit/fields) or "
                  "fetch specific ids."),
        "preview": text[:MAX_RESULT_CHARS],
    }


def _err(e: Exception) -> dict:
    # Some exceptions (notably httpx timeouts) stringify to "" — never return
    # an empty error message.
    return {"error": str(e).strip() or type(e).__name__}


def _parse_json_arg(name: str, value: str) -> Any:
    if not value or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise EmbyError(f"{name} is not valid JSON: {e}") from e


def _need_confirm(what: str) -> dict:
    return {
        "confirmation_required": True,
        "note": (f"This would {what}. Nothing was changed. "
                 "Re-run with confirm=true after the user explicitly approves."),
    }


def _csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


mcp = FastMCP("emby")


# --------------------------------------------------------------------------- #
# Generic layer                                                               #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_call(method: str, path: str, params: str = "", body: str = "") -> Any:
    """Call ANY Emby REST operation — the generic passthrough that reaches the
    server's entire API surface (~484 operations). Use emby_list_endpoints to
    find the operation first.

    Args:
        method: HTTP method (GET, POST, DELETE, PUT).
        path: Endpoint path, e.g. "/Items/12345/Refresh". Path template values
            must already be substituted. The "/emby" prefix is optional.
        params: Optional query parameters as a JSON object string,
            e.g. '{"Recursive": true, "Limit": 5}'.
        body: Optional request body as a JSON string.

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
def emby_list_endpoints(search: str = "", tag: str = "", limit: int = 60) -> Any:
    """Search the server's LIVE OpenAPI catalog of every REST operation.
    This is the master index for emby_call.

    Args:
        search: Case-insensitive substring matched against path + summary,
            e.g. "subtitle", "refresh", "policy".
        tag: Filter by service tag, e.g. "LiveTvService", "UserService".
            Pass tag="?" to list all tags with their operation counts.
        limit: Max operations to return (default 60).
    """
    try:
        ops = CLIENT.openapi_ops()
        if tag == "?":
            counts: dict[str, int] = {}
            for o in ops:
                counts[o["tag"]] = counts.get(o["tag"], 0) + 1
            return {"total_operations": len(ops),
                    "tags": dict(sorted(counts.items(), key=lambda x: -x[1]))}
        if tag:
            ops = [o for o in ops if o["tag"].lower() == tag.lower()]
        if search:
            s = search.lower()
            ops = [o for o in ops if s in o["path"].lower() or s in o["summary"].lower()]
        return _finish({"matched": len(ops), "operations": ops[:limit]})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# System                                                                      #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_status() -> Any:
    """Server health snapshot: identity, version, pending restart, library
    item counts, and how many sessions are connected / actively playing.
    Call this first for almost any request."""
    try:
        info = CLIENT.request("GET", "/System/Info")
        counts = CLIENT.request("GET", "/Items/Counts")
        sessions = CLIENT.request("GET", "/Sessions") or []
        playing = [s for s in sessions if s.get("NowPlayingItem")]
        return {
            "ServerName": info.get("ServerName"),
            "Version": info.get("Version"),
            "OperatingSystem": info.get("OperatingSystemDisplayName"),
            "HasPendingRestart": info.get("HasPendingRestart"),
            "HasUpdateAvailable": info.get("HasUpdateAvailable"),
            "InternalUrl": info.get("LocalAddresses"),
            "WanAddress": info.get("WanAddress"),
            "ProgramDataPath": info.get("ProgramDataPath"),
            "TranscodingTempPath": info.get("TranscodingTempPath"),
            "ItemCounts": {k: v for k, v in counts.items() if v},
            "ConnectedSessions": len(sessions),
            "NowPlayingCount": len(playing),
            "NowPlaying": [
                {
                    "User": s.get("UserName"),
                    "Client": s.get("Client"),
                    "Item": (s.get("NowPlayingItem") or {}).get("Name"),
                    "IsTranscoding": bool(s.get("TranscodingInfo")),
                }
                for s in playing
            ],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_get_config(section: str = "") -> Any:
    """Read server configuration.

    Args:
        section: Empty for the main /System/Configuration document, or a named
            store, e.g. "encoding" (transcoding), "notifications", "dlna",
            "livetv", "autoorganize", "chapters", "subtitles" (available
            stores vary by installed features/plugins).
    """
    try:
        path = f"/System/Configuration/{section}" if section else "/System/Configuration"
        return _finish(CLIENT.request("GET", path))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_set_config(patch: str, section: str = "", confirm: bool = False) -> Any:
    """Update server configuration SAFELY: reads the current (full) config
    object, merges your patch keys over it, and POSTs the full object back.
    (Emby resets omitted fields if you POST a partial object — never do that.)

    Args:
        patch: JSON object string with just the keys to change,
            e.g. '{"EnableThrottling": true}'.
        section: Empty for the main config, or a named store like "encoding".
        confirm: Must be true — this changes live server behavior.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise EmbyError("patch must be a non-empty JSON object")
        path = f"/System/Configuration/{section}" if section else "/System/Configuration"
        current = CLIENT.request("GET", path)
        unknown = [k for k in change if k not in current]
        if not confirm:
            return _need_confirm(
                f"update {path} keys {list(change)} "
                f"(current values: { {k: current.get(k) for k in change} })"
            ) | ({"warning_unknown_keys": unknown} if unknown else {})
        merged = {**current, **change}
        CLIENT.request("POST", path, body=merged)
        after = CLIENT.request("GET", path)
        return {"updated": True, "path": path,
                "now": {k: after.get(k) for k in change},
                **({"warning_unknown_keys": unknown} if unknown else {})}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_restart_server(confirm: bool = False) -> Any:
    """Restart the Emby server process (interrupts all active playback).
    Requires confirm=true after explicit user approval."""
    try:
        if not confirm:
            return _need_confirm("RESTART the Emby server, dropping every active stream")
        CLIENT.request("POST", "/System/Restart")
        return {"restarting": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_shutdown_server(confirm: bool = False) -> Any:
    """Shut the Emby server DOWN (it will NOT come back until started by hand
    or by its service manager). Requires confirm=true."""
    try:
        if not confirm:
            return _need_confirm("SHUT DOWN the Emby server process entirely")
        CLIENT.request("POST", "/System/Shutdown")
        return {"shutting_down": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_logs(name: str = "", tail_chars: int = 8000) -> Any:
    """List server log files, or fetch the tail of one.

    Args:
        name: Empty to list available logs (embyserver.txt, ffmpeg transcode
            logs, hardware detection...). Or a file name from that list to
            fetch its content.
        tail_chars: How many characters from the END of the log to return.
    """
    try:
        if not name:
            return CLIENT.request("GET", "/System/Logs")
        text = CLIENT.request("GET", "/System/Logs/Log", params={"Name": name}, raw=True)
        return {"name": name, "total_chars": len(text),
                "tail": text[-max(tail_chars, 200):]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_activity(limit: int = 25, min_date: str = "") -> Any:
    """Recent server activity log (logins, playback starts/stops, config
    changes, task completions, errors).

    Args:
        limit: Number of entries.
        min_date: Optional ISO date lower bound, e.g. "2026-07-14".
    """
    try:
        params: dict[str, Any] = {"Limit": limit, "StartIndex": 0}
        if min_date:
            params["MinDate"] = min_date
        data = CLIENT.request("GET", "/System/ActivityLog/Entries", params=params)
        return {
            "TotalRecordCount": data.get("TotalRecordCount"),
            "Items": [
                {"Date": i.get("Date"), "Type": i.get("Type"),
                 "Name": i.get("Name"), "Severity": i.get("Severity"),
                 **({"Overview": i["ShortOverview"]} if i.get("ShortOverview") else {})}
                for i in data.get("Items", [])
            ],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_scheduled_tasks(include_hidden: bool = False) -> Any:
    """List scheduled tasks (library scan, chapter images, cache cleanup...)
    with state, last run result and triggers."""
    try:
        tasks = CLIENT.request("GET", "/ScheduledTasks",
                               params={"IsHidden": "false"} if not include_hidden else None)
        return [
            {
                "Id": t["Id"], "Name": t["Name"], "State": t["State"],
                "Category": t.get("Category"),
                "CurrentProgress": t.get("CurrentProgressPercentage"),
                "LastRun": {
                    "Status": (t.get("LastExecutionResult") or {}).get("Status"),
                    "Start": (t.get("LastExecutionResult") or {}).get("StartTimeUtc"),
                    "End": (t.get("LastExecutionResult") or {}).get("EndTimeUtc"),
                },
                "Triggers": t.get("Triggers", []),
            }
            for t in tasks
        ]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_run_task(task_id: str, action: str = "start", confirm: bool = False) -> Any:
    """Start or stop a scheduled task by id (from emby_scheduled_tasks).

    Args:
        task_id: The task id.
        action: "start" or "stop".
        confirm: Must be true — tasks can be heavy (full library scans).
    """
    try:
        if action not in ("start", "stop"):
            raise EmbyError('action must be "start" or "stop"')
        if not confirm:
            return _need_confirm(f"{action} scheduled task {task_id}")
        if action == "start":
            CLIENT.request("POST", f"/ScheduledTasks/Running/{task_id}")
        else:
            CLIENT.request("DELETE", f"/ScheduledTasks/Running/{task_id}")
        return {"ok": True, "action": action, "task_id": task_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_devices() -> Any:
    """List devices that have connected to the server (app, last user, last
    activity)."""
    try:
        data = CLIENT.request("GET", "/Devices")
        return [
            {"Id": d.get("Id"), "Name": d.get("Name"), "App": d.get("AppName"),
             "AppVersion": d.get("AppVersion"), "LastUser": d.get("LastUserName"),
             "LastActivity": d.get("DateLastActivity")}
            for d in data.get("Items", [])
        ]
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Users                                                                       #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_users() -> Any:
    """List all users with the policy fields that matter (admin, disabled,
    library access, remote access, deletion rights)."""
    try:
        return [
            {
                "Id": u["Id"], "Name": u["Name"],
                "IsAdministrator": u.get("Policy", {}).get("IsAdministrator"),
                "IsDisabled": u.get("Policy", {}).get("IsDisabled"),
                "IsHidden": u.get("Policy", {}).get("IsHidden"),
                "EnableRemoteAccess": u.get("Policy", {}).get("EnableRemoteAccess"),
                "EnableContentDeletion": u.get("Policy", {}).get("EnableContentDeletion"),
                "EnableAllFolders": u.get("Policy", {}).get("EnableAllFolders"),
                "LastLoginDate": u.get("LastLoginDate"),
                "HasPassword": u.get("HasPassword"),
            }
            for u in CLIENT.users()
        ]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_user(user: str) -> Any:
    """Full detail for one user (identified by name or id), including the
    complete Policy and Configuration objects."""
    try:
        return _finish(CLIENT.resolve_user(user))
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_update_user_policy(user: str, patch: str, confirm: bool = False) -> Any:
    """Change a user's policy (admin flag, folder access, parental controls,
    remote access, deletion rights...). Round-trips the FULL policy object
    with your patch merged in.

    Args:
        user: User name or id.
        patch: JSON object of policy keys to change,
            e.g. '{"EnableContentDeletion": false}'.
        confirm: Must be true.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise EmbyError("patch must be a non-empty JSON object")
        u = CLIENT.resolve_user(user)
        current = u.get("Policy", {})
        if not confirm:
            return _need_confirm(
                f"update policy of user '{u['Name']}' keys {list(change)} "
                f"(current: { {k: current.get(k) for k in change} })")
        CLIENT.request("POST", f"/Users/{u['Id']}/Policy", body={**current, **change})
        after = CLIENT.resolve_user(u["Id"]).get("Policy", {})
        return {"updated": True, "user": u["Name"],
                "now": {k: after.get(k) for k in change}}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_create_user(name: str, confirm: bool = False) -> Any:
    """Create a new user (no password — set one after with
    emby_set_user_password; tune access with emby_update_user_policy)."""
    try:
        if not confirm:
            return _need_confirm(f"create a new user named '{name}'")
        u = CLIENT.request("POST", "/Users/New", body={"Name": name})
        return {"created": True, "Id": u["Id"], "Name": u["Name"]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_delete_user(user: str, confirm: bool = False) -> Any:
    """DELETE a user account permanently (watch history and preferences are
    lost). Requires confirm=true."""
    try:
        u = CLIENT.resolve_user(user)
        if not confirm:
            return _need_confirm(f"permanently delete user '{u['Name']}' ({u['Id']})")
        CLIENT.request("DELETE", f"/Users/{u['Id']}")
        return {"deleted": True, "user": u["Name"]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_set_user_password(user: str, new_password: str, confirm: bool = False) -> Any:
    """Set (or reset) a user's password."""
    try:
        u = CLIENT.resolve_user(user)
        if not confirm:
            return _need_confirm(f"change the password of user '{u['Name']}'")
        CLIENT.request("POST", f"/Users/{u['Id']}/Password",
                       body={"NewPw": new_password, "ResetPassword": False})
        return {"password_set": True, "user": u["Name"]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_libraries() -> Any:
    """List the media libraries (virtual folders): name, type, folder paths,
    refresh status, and the key library options."""
    try:
        vfs = CLIENT.request("GET", "/Library/VirtualFolders")
        out = []
        for v in vfs:
            lo = v.get("LibraryOptions", {})
            out.append({
                "Name": v.get("Name"), "ItemId": v.get("ItemId"),
                "CollectionType": v.get("CollectionType"),
                "Locations": v.get("Locations"),
                "RefreshStatus": v.get("RefreshStatus"),
                "Options": {
                    "EnableRealtimeMonitor": lo.get("EnableRealtimeMonitor"),
                    "EnableChapterImageExtraction": lo.get("EnableChapterImageExtraction"),
                    "ExtractChapterImagesDuringLibraryScan": lo.get("ExtractChapterImagesDuringLibraryScan"),
                    "PreferredMetadataLanguage": lo.get("PreferredMetadataLanguage"),
                },
            })
        return out
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_scan_library(confirm: bool = False) -> Any:
    """Trigger a full library scan (all libraries). For a single item/series
    use emby_refresh_item instead. Requires confirm=true (scans can be heavy)."""
    try:
        if not confirm:
            return _need_confirm("start a full library scan on all libraries")
        CLIENT.request("POST", "/Library/Refresh")
        return {"scan_started": True}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_search(term: str, types: str = "", limit: int = 20, user: str = "") -> Any:
    """Search the whole library by name.

    Args:
        term: Search text.
        types: Optional CSV of item types to restrict to, e.g.
            "Movie,Series,Episode,BoxSet,Person,MusicAlbum,Audio".
        limit: Max results.
        user: Optional user (name/id) whose watch state to include.
    """
    try:
        uid = CLIENT.resolve_user(user)["Id"]
        params: dict[str, Any] = {
            "SearchTerm": term, "Recursive": True, "Limit": limit,
            "UserId": uid, "Fields": "Path,ProductionYear",
        }
        if types:
            params["IncludeItemTypes"] = types
        data = CLIENT.request("GET", "/Items", params=params)
        return {"TotalRecordCount": data.get("TotalRecordCount"),
                "Items": [compact_item(i) for i in data.get("Items", [])]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _items_params(include_types: str, parent_id: str, search_term: str,
                  genres: str, years: str, person: str, studios: str,
                  filters: str, is_missing: str = "") -> dict:
    """Shared /Items query-param assembly (emby_items, emby_bulk_update)."""
    params: dict[str, Any] = {"Recursive": True}
    if include_types:
        params["IncludeItemTypes"] = include_types
    if parent_id:
        params["ParentId"] = parent_id
    if search_term:
        params["SearchTerm"] = search_term
    if genres:
        params["Genres"] = genres
    if years:
        params["Years"] = years
    if person:
        params["Person"] = person
    if studios:
        params["Studios"] = studios
    if filters:
        params["Filters"] = filters
    if is_missing:
        params["IsMissing"] = _truthy(is_missing)
    return params


@mcp.tool()
def emby_items(
    include_types: str = "",
    parent_id: str = "",
    search_term: str = "",
    genres: str = "",
    years: str = "",
    person: str = "",
    studios: str = "",
    filters: str = "",
    sort_by: str = "SortName",
    sort_order: str = "Ascending",
    fields: str = "",
    limit: int = 30,
    start_index: int = 0,
    user: str = "",
    is_missing: str = "",
) -> Any:
    """Flexible library query — the workhorse for browsing/reporting.

    Args:
        include_types: CSV, e.g. "Movie", "Series", "Episode", "BoxSet".
        parent_id: Restrict to a folder/library/series/season id.
        search_term: Name search.
        genres: CSV genre filter, e.g. "Horror,Comedy".
        years: CSV of production years, e.g. "2023,2024".
        person: Filter to items featuring this person (name).
        studios: CSV studio filter.
        filters: CSV of flags: "IsPlayed", "IsUnplayed", "IsFavorite",
            "IsResumable".
        sort_by: e.g. "SortName", "DateCreated", "CommunityRating",
            "ProductionYear", "PlayCount", "Random", "DatePlayed".
        sort_order: "Ascending" or "Descending".
        fields: Extra CSV fields to request, e.g. "Path,Overview,Genres".
        limit / start_index: Paging.
        user: User (name/id) whose watch state applies.
        is_missing: "true" to list MISSING episodes the server tracks (episodes
            that exist in the guide but not on disk), "false" to exclude them.

    Returns compact rows + TotalRecordCount.
    """
    try:
        uid = CLIENT.resolve_user(user)["Id"]
        params = _items_params(include_types, parent_id, search_term, genres,
                               years, person, studios, filters, is_missing)
        params.update({"Limit": limit, "StartIndex": start_index,
                       "SortBy": sort_by, "SortOrder": sort_order, "UserId": uid})
        if fields:
            params["Fields"] = fields
        data = CLIENT.request("GET", "/Items", params=params)
        items = [compact_item(i) for i in data.get("Items", [])]
        extra = _csv(fields)
        if extra:
            for row, raw in zip(items, data.get("Items", [])):
                for f in extra:
                    if f in raw and f not in row:
                        row[f] = raw[f]
        return _finish({"TotalRecordCount": data.get("TotalRecordCount"), "Items": items})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_item(item_id: str, user: str = "") -> Any:
    """Full detail for one item: metadata, media streams (codecs, resolution,
    bitrate), paths, provider ids, user data. Chapters are summarized."""
    try:
        uid = CLIENT.resolve_user(user)["Id"]
        it = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        if isinstance(it, dict):
            if "Chapters" in it and isinstance(it["Chapters"], list):
                it["ChapterCount"] = len(it["Chapters"])
                del it["Chapters"]
            for ms in it.get("MediaSources", []):
                ms.pop("RequiresOpening", None)
        return _finish(it)
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_update_item(item_id: str, patch: str, confirm: bool = False) -> Any:
    """Edit an item's metadata (name, overview, genres, tags, community
    rating, provider ids, dates...). Round-trips the FULL item object with
    your patch merged so nothing else is lost.

    Args:
        item_id: The item to edit.
        patch: JSON object of fields to change, e.g.
            '{"Overview": "...", "Genres": ["Horror"], "Tags": ["kids-safe"]}'.
        confirm: Must be true.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise EmbyError("patch must be a non-empty JSON object")
        uid = CLIENT.default_user()["Id"]
        current = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        if not confirm:
            return _need_confirm(
                f"edit metadata of '{current.get('Name')}' ({item_id}), keys {list(change)}")
        merged = {**current, **change}
        CLIENT.request("POST", f"/Items/{item_id}", body=merged)
        after = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        return {"updated": True, "item": after.get("Name"),
                "now": {k: after.get(k) for k in change}}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_refresh_item(item_id: str, replace_all_metadata: bool = False,
                      replace_all_images: bool = False, confirm: bool = False) -> Any:
    """Refresh one item's metadata from the internet providers (works on a
    movie, series, season, or a whole library folder id).

    Args:
        replace_all_metadata / replace_all_images: True re-downloads and
            OVERWRITES existing metadata/images instead of just filling gaps.
        confirm: Must be true (refreshes write metadata; replace modes
            overwrite local edits).
    """
    try:
        if not confirm:
            mode = ("REPLACING existing data"
                    if (replace_all_metadata or replace_all_images) else "fill-gaps mode")
            return _need_confirm(f"refresh metadata for item {item_id} in {mode}")
        CLIENT.request("POST", f"/Items/{item_id}/Refresh", params={
            "Recursive": True,
            "MetadataRefreshMode": "FullRefresh",
            "ImageRefreshMode": "FullRefresh",
            "ReplaceAllMetadata": replace_all_metadata,
            "ReplaceAllImages": replace_all_images,
        })
        return {"refresh_queued": True, "item_id": item_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_delete_item(item_id: str, confirm: bool = False) -> Any:
    """DELETE an item — this removes the underlying MEDIA FILES from disk,
    not just the database entry. Requires confirm=true after the user has
    explicitly named the item and approved."""
    try:
        uid = CLIENT.default_user()["Id"]
        it = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        if not confirm:
            return _need_confirm(
                f"PERMANENTLY DELETE '{it.get('Name')}' ({it.get('Type')}) and its "
                f"files at {it.get('Path')}")
        CLIENT.request("DELETE", f"/Items/{item_id}")
        return {"deleted": True, "was": it.get("Name"), "path": it.get("Path")}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_set_userdata(item_id: str, user: str = "", played: str = "",
                      favorite: str = "", confirm: bool = False) -> Any:
    """Set per-user item state: watched/unwatched and/or favorite flag.

    Args:
        item_id: The item.
        user: User name/id (default: configured admin).
        played: "true" to mark watched, "false" to mark unwatched, "" to skip.
        favorite: "true"/"false"/"" likewise.
        confirm: Must be true (marking watched also clears any resume point).
    """
    try:
        u = CLIENT.resolve_user(user)
        if not played and not favorite:
            raise EmbyError("Nothing to do — pass played and/or favorite.")
        if not confirm:
            wants = ", ".join(
                f"{k}={v}" for k, v in (("played", played), ("favorite", favorite)) if v)
            return _need_confirm(
                f"set {wants} on item {item_id} for user '{u['Name']}'")
        out: dict[str, Any] = {"user": u["Name"], "item_id": item_id}
        if played:
            if _truthy(played):
                CLIENT.request("POST", f"/Users/{u['Id']}/PlayedItems/{item_id}")
            else:
                CLIENT.request("DELETE", f"/Users/{u['Id']}/PlayedItems/{item_id}")
            out["played"] = _truthy(played)
        if favorite:
            if _truthy(favorite):
                CLIENT.request("POST", f"/Users/{u['Id']}/FavoriteItems/{item_id}")
            else:
                CLIENT.request("DELETE", f"/Users/{u['Id']}/FavoriteItems/{item_id}")
            out["favorite"] = _truthy(favorite)
        return out
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_next_up(limit: int = 15, user: str = "") -> Any:
    """'Continue watching' view: next-up episodes plus in-progress items."""
    try:
        uid = CLIENT.resolve_user(user)["Id"]
        nu = CLIENT.request("GET", "/Shows/NextUp",
                            params={"UserId": uid, "Limit": limit})
        resume = CLIENT.request("GET", f"/Users/{uid}/Items/Resume",
                                params={"Limit": limit, "Recursive": True})
        return {
            "NextUpEpisodes": [compact_item(i) for i in nu.get("Items", [])],
            "InProgress": [compact_item(i) for i in resume.get("Items", [])],
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Sessions & playback                                                         #
# --------------------------------------------------------------------------- #
def _compact_session(s: dict) -> dict:
    out = {
        "SessionId": s.get("Id"),
        "User": s.get("UserName"),
        "Client": s.get("Client"),
        "Device": s.get("DeviceName"),
        "RemoteEndPoint": s.get("RemoteEndPoint"),
        "AppVersion": s.get("ApplicationVersion"),
        "LastActivity": s.get("LastActivityDate"),
        "SupportsRemoteControl": s.get("SupportsRemoteControl"),
    }
    npi = s.get("NowPlayingItem")
    if npi:
        ps = s.get("PlayState", {})
        out["NowPlaying"] = {
            "Item": npi.get("Name"), "ItemId": npi.get("Id"),
            "Type": npi.get("Type"), "SeriesName": npi.get("SeriesName"),
            "RunTime": ticks_to_hms(npi.get("RunTimeTicks")),
            "Position": ticks_to_hms(ps.get("PositionTicks")),
            "IsPaused": ps.get("IsPaused"),
            "PlayMethod": ps.get("PlayMethod"),
        }
        ti = s.get("TranscodingInfo")
        if ti:
            out["Transcoding"] = {
                "VideoCodec": ti.get("VideoCodec"), "AudioCodec": ti.get("AudioCodec"),
                "Bitrate": ti.get("Bitrate"), "CompletionPct": ti.get("CompletionPercentage"),
                "Framerate": ti.get("Framerate"),
                "HardwareAccel": ti.get("VideoDecoderHwAccel") or ti.get("VideoEncoderHwAccel"),
                "Reasons": ti.get("TranscodeReasons"),
            }
    return out


@mcp.tool()
def emby_sessions(active_only: bool = False) -> Any:
    """List connected sessions/clients. Shows who is watching what, playback
    position, direct-play vs transcode (with transcode REASONS and hw-accel).

    Args:
        active_only: True to show only sessions currently playing something.
    """
    try:
        sessions = CLIENT.request("GET", "/Sessions") or []
        if active_only:
            sessions = [s for s in sessions if s.get("NowPlayingItem")]
        return [_compact_session(s) for s in sessions]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_playback_control(session_id: str, command: str,
                          seek_seconds: float = -1, confirm: bool = False) -> Any:
    """Control playback on a client session (from emby_sessions).

    Args:
        session_id: Target session.
        command: "Pause", "Unpause", "PlayPause", "Stop", "Seek",
            "NextTrack", "PreviousTrack".
        seek_seconds: Required for "Seek" — absolute position in seconds.
        confirm: Must be true (this changes what someone is watching).
    """
    try:
        if not confirm:
            return _need_confirm(f"send playback command '{command}' to session {session_id}")
        params = None
        if command == "Seek":
            if seek_seconds < 0:
                raise EmbyError("Seek needs seek_seconds >= 0")
            params = {"SeekPositionTicks": int(seek_seconds * TICKS_PER_SECOND)}
        CLIENT.request("POST", f"/Sessions/{session_id}/Playing/{command}", params=params)
        return {"sent": command, "session": session_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_play(session_id: str, item_ids: str, play_command: str = "PlayNow",
              start_seconds: float = 0, confirm: bool = False) -> Any:
    """Start playing media on a client session (remote control).

    Args:
        session_id: Target session (must SupportRemoteControl).
        item_ids: CSV of item ids to play.
        play_command: "PlayNow", "PlayNext", or "PlayLast" (queue).
        start_seconds: Start position for the first item.
        confirm: Must be true.
    """
    try:
        if not confirm:
            return _need_confirm(f"start playback of {item_ids} on session {session_id}")
        CLIENT.request("POST", f"/Sessions/{session_id}/Playing", params={
            "ItemIds": item_ids,
            "PlayCommand": play_command,
            "StartPositionTicks": int(start_seconds * TICKS_PER_SECOND),
        })
        return {"playing": item_ids, "session": session_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_send_message(session_id: str, text: str, header: str = "Message",
                      timeout_ms: int = 5000, confirm: bool = False) -> Any:
    """Pop a message on a client's screen (e.g. 'server restarting in 5
    minutes'). Requires confirm=true."""
    try:
        if not confirm:
            return _need_confirm(f"display message '{text}' on session {session_id}")
        CLIENT.request("POST", f"/Sessions/{session_id}/Message",
                       body={"Text": text, "Header": header, "TimeoutMs": timeout_ms})
        return {"message_sent": True, "session": session_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_send_command(session_id: str, command: str, arguments: str = "",
                      confirm: bool = False) -> Any:
    """Send a general command to a session: "GoHome", "Back", "Mute",
    "Unmute", "ToggleMute", "SetVolume" (arguments '{"Volume":"40"}'),
    "SetAudioStreamIndex", "SetSubtitleStreamIndex", "DisplayContent",
    "TakeScreenshot"... Requires confirm=true."""
    try:
        if not confirm:
            return _need_confirm(f"send command '{command}' to session {session_id}")
        body = {"Name": command}
        args = _parse_json_arg("arguments", arguments)
        if args:
            body["Arguments"] = args
        CLIENT.request("POST", f"/Sessions/{session_id}/Command", body=body)
        return {"sent": command, "session": session_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_playback_info(item_id: str, max_bitrate: int = 0, user: str = "") -> Any:
    """Analyze how an item would play: media sources, whether direct play /
    direct stream / transcode is required, and why. Useful for 'why does this
    file transcode?' questions.

    Args:
        max_bitrate: Optionally simulate a client bitrate cap (bits/sec).
    """
    try:
        uid = CLIENT.resolve_user(user)["Id"]
        params: dict[str, Any] = {"UserId": uid}
        if max_bitrate:
            params["MaxStreamingBitrate"] = max_bitrate
        data = CLIENT.request("GET", f"/Items/{item_id}/PlaybackInfo", params=params)
        out = []
        for ms in data.get("MediaSources", []):
            streams = [
                {"Type": st.get("Type"), "Codec": st.get("Codec"),
                 "Language": st.get("Language"),
                 "Resolution": f"{st.get('Width')}x{st.get('Height')}" if st.get("Width") else None,
                 "BitRate": st.get("BitRate"), "Profile": st.get("Profile"),
                 "IsExternal": st.get("IsExternal") or None}
                for st in ms.get("MediaStreams", [])
            ]
            out.append({
                "MediaSourceId": ms.get("Id"), "Container": ms.get("Container"),
                "Path": ms.get("Path"), "Bitrate": ms.get("Bitrate"),
                "SupportsDirectPlay": ms.get("SupportsDirectPlay"),
                "SupportsDirectStream": ms.get("SupportsDirectStream"),
                "SupportsTranscoding": ms.get("SupportsTranscoding"),
                "Streams": streams,
            })
        return _finish({"MediaSources": out})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Plugins & packages                                                          #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_plugins() -> Any:
    """List INSTALLED server plugins (name, version, id, config page)."""
    try:
        return [
            {"Id": p.get("Id"), "Name": p.get("Name"), "Version": p.get("Version"),
             "Description": (p.get("Description") or "")[:160]}
            for p in CLIENT.request("GET", "/Plugins")
        ]
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_packages(search: str = "", installed_only: bool = False) -> Any:
    """Browse the official plugin CATALOG (what can be installed).

    Args:
        search: Substring filter on name/description.
        installed_only: True to show only catalog entries already installed.
    """
    try:
        pkgs = CLIENT.request("GET", "/Packages")
        out = []
        for p in pkgs:
            if installed_only and not p.get("isInstalled") and not p.get("installedVersion"):
                continue
            if search:
                s = search.lower()
                hay = f"{p.get('name','')} {p.get('shortDescription','')}".lower()
                if s not in hay:
                    continue
            out.append({
                "name": p.get("name"),
                "shortDescription": p.get("shortDescription"),
                "category": p.get("category"),
                "isPremium": p.get("isPremium"),
                "installedVersion": (p.get("installedVersion") or {}).get("versionStr")
                    if isinstance(p.get("installedVersion"), dict) else p.get("installedVersion"),
            })
        return _finish({"matched": len(out), "packages": out[:80]})
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_install_plugin(name: str, confirm: bool = False) -> Any:
    """Install a plugin from the catalog by its exact package name (from
    emby_packages). Most plugins need a server restart to activate."""
    try:
        if not confirm:
            return _need_confirm(f"install plugin package '{name}'")
        CLIENT.request("POST", f"/Packages/Installed/{name}")
        return {"install_started": True, "package": name,
                "note": "Check emby_scheduled_tasks / emby_activity for completion; "
                        "a server restart is usually required."}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_uninstall_plugin(plugin_id: str, confirm: bool = False) -> Any:
    """Uninstall an installed plugin by id (from emby_plugins). Requires
    confirm=true; takes effect after restart."""
    try:
        if not confirm:
            return _need_confirm(f"uninstall plugin {plugin_id}")
        CLIENT.request("DELETE", f"/Plugins/{plugin_id}")
        return {"uninstalled": True, "plugin_id": plugin_id}
    except Exception as e:  # noqa: BLE001
        return _err(e)


def _plugin_config_target(plugin: str) -> tuple[str, str]:
    """Resolve a plugin id/name/store-key to a working config endpoint.

    Returns (mechanism, path). Emby 4.x plugins rarely implement the legacy
    /Plugins/{id}/Configuration route (it 500s); their settings live in NAMED
    STORES at /System/Configuration/{key}, where the key is derived from the
    plugin's dashboard page names (verified live: opensubtitles, webhooks,
    cinemamode, dlna, fanart, musicbrainz, xmltv...).
    """
    plugins = CLIENT.request("GET", "/Plugins")
    pages = CLIENT.request("GET", "/web/ConfigurationPages") or []
    norm = "".join(c for c in plugin.lower() if c.isalnum())
    match = next((p for p in plugins
                  if p["Id"].lower() == plugin.lower()
                  or "".join(c for c in p["Name"].lower() if c.isalnum()) == norm), None)

    candidates: list[str] = []
    if match:
        # legacy route first — some third-party plugins do implement it
        try:
            CLIENT.request("GET", f"/Plugins/{match['Id']}/Configuration")
            return "legacy", f"/Plugins/{match['Id']}/Configuration"
        except EmbyError:
            pass
        for pg in pages:
            if pg.get("PluginId") == match["Id"]:
                name = pg["Name"]
                for v in (name, name.removesuffix("js"), name.removesuffix("settings"),
                          name.removesuffix("js").removesuffix("settings")):
                    if v and v not in candidates:
                        candidates.append(v)
        n = "".join(c for c in match["Name"].lower() if c.isalnum())
        if n not in candidates:
            candidates.append(n)
    else:
        candidates.append(norm or plugin)

    for key in candidates:
        try:
            CLIENT.request("GET", f"/System/Configuration/{key}")
            return "named_store", f"/System/Configuration/{key}"
        except EmbyError:
            continue
    known = sorted({pg["Name"].removesuffix("js") for pg in pages})
    raise EmbyError(
        f"No configuration object found for '{plugin}' (tried {candidates}). "
        f"Known dashboard config pages: {known}. Some plugins have no settings.")


@mcp.tool()
def emby_plugin_config(plugin: str = "", patch: str = "", confirm: bool = False) -> Any:
    """Read (default) or update a plugin's configuration.

    Args:
        plugin: Plugin name ("Open Subtitles"), plugin id, or named config
            store key ("opensubtitles"). EMPTY: list every dashboard config
            page so you can see what's configurable.
        patch: Empty to READ. Or a JSON object of keys to change — the full
            current config is round-tripped with your patch merged.
        confirm: Must be true when writing.
    """
    try:
        if not plugin:
            pages = CLIENT.request("GET", "/web/ConfigurationPages") or []
            seen: dict[str, dict] = {}
            for pg in pages:
                if pg["Name"].endswith("js"):
                    continue
                seen[pg["Name"]] = {"page": pg["Name"],
                                    "plugin": pg.get("DisplayName"),
                                    "plugin_id": pg.get("PluginId")}
            return {"config_pages": list(seen.values()),
                    "note": "Pass one of these (or the plugin name) as `plugin`."}
        mechanism, path = _plugin_config_target(plugin)
        current = CLIENT.request("GET", path)
        if not patch:
            return _finish({"mechanism": mechanism, "path": path, "config": current})
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict):
            raise EmbyError("patch must be a JSON object")
        if not confirm:
            return _need_confirm(
                f"update plugin config at {path}, keys {list(change)} "
                f"(current: { {k: current.get(k) for k in change} })")
        CLIENT.request("POST", path, body={**current, **change})
        after = CLIENT.request("GET", path)
        return {"updated": True, "path": path,
                "now": {k: after.get(k) for k in change}}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Collections & playlists                                                     #
# --------------------------------------------------------------------------- #
_FRANCHISE_STRIP = (" part", " chapter", " episode", " vol", " volume")


def _franchise_key(name: str) -> str:
    """Normalize a movie name to a franchise base for grouping."""
    import re as _re
    n = name.lower().strip()
    n = _re.sub(r"\s*[:\-–]\s.*$", "", n)                      # drop subtitle
    n = _re.sub(r"\s+(\d+|i{2,3}|iv|v|vi{0,3}|ix|x)$", "", n)  # trailing number/roman
    for suf in _FRANCHISE_STRIP:
        idx = n.find(suf)
        if idx > 0:
            n = n[:idx]
    return n.strip()


@mcp.tool()
def emby_collection(action: str, name: str = "", collection_id: str = "",
                    item_ids: str = "", include_types: str = "Movie",
                    genres: str = "", years: str = "", person: str = "",
                    studios: str = "", filters: str = "", search_term: str = "",
                    confirm: bool = False) -> Any:
    """Full collection (BoxSet) management.

    Args:
        action:
            "list" — all collections (with child counts).
            "items" — contents of collection_id.
            "for_item" — which collections contain item_ids (reverse lookup).
            "create" — new collection `name`, optionally seeded with item_ids
                CSV OR with a query (genres/years/person/studios/filters).
            "add" / "remove" — modify collection_id membership (item_ids CSV).
            "sync_query" — top up collection_id with every item matching the
                query that isn't already a member (smart-collection refresh).
            "find_franchises" — scan the library for movie-name franchises
                (e.g. 'Sonic the Hedgehog 1/2/3') not yet collected; returns
                ready-to-create groups. Name-heuristic based — ALWAYS have the
                user review groups before creating. (TMDb collection names are
                not exposed by Emby 4.7.)
        include_types/genres/years/person/studios/filters/search_term: query
            for create/sync_query (same semantics as emby_items).
        confirm: Required for create/add/remove/sync_query writes.

    Collections are items: set artwork with emby_images(collection_id, ...)
    and overview/sort-name with emby_update_item(collection_id, ...).
    """
    try:
        uid = CLIENT.default_user()["Id"]

        def query_ids() -> list[dict]:
            params = _items_params(include_types, "", search_term, genres,
                                   years, person, studios, filters)
            params.update({"Limit": 500, "UserId": uid, "SortBy": "SortName"})
            return CLIENT.request("GET", "/Items", params=params).get("Items", [])

        def members(cid: str) -> list[dict]:
            return CLIENT.request("GET", "/Items", params={
                "ParentId": cid, "UserId": uid, "Limit": 1000}).get("Items", [])

        if action == "list":
            data = CLIENT.request("GET", "/Items", params={
                "IncludeItemTypes": "BoxSet", "Recursive": True,
                "UserId": uid, "Limit": 300, "SortBy": "SortName",
                "Fields": "ChildCount"})
            return {"TotalRecordCount": data.get("TotalRecordCount"),
                    "Items": [compact_item(i) for i in data.get("Items", [])]}
        if action == "items":
            if not collection_id:
                raise EmbyError("items needs collection_id")
            return {"Items": [compact_item(i) for i in members(collection_id)]}
        if action == "for_item":
            if not item_ids:
                raise EmbyError("for_item needs item_ids (one id)")
            data = CLIENT.request("GET", "/Items", params={
                "IncludeItemTypes": "BoxSet", "Recursive": True,
                "ListItemIds": item_ids, "UserId": uid})
            return {"collections": [{"Id": c["Id"], "Name": c["Name"]}
                                    for c in data.get("Items", [])]}
        if action == "create":
            if not name:
                raise EmbyError("create needs a name")
            seed = _csv(item_ids)
            queried = []
            if not seed and (genres or years or person or studios or filters
                             or search_term):
                queried = query_ids()
                seed = [i["Id"] for i in queried]
            if not confirm:
                return _finish({
                    "confirmation_required": True,
                    "would_create": name,
                    "seed_count": len(seed),
                    **({"from_query": [i.get("Name") for i in queried]}
                       if queried else {"item_ids": seed}),
                    "note": "Nothing created. Re-run with confirm=true after "
                            "the user approves."})
            params = {"Name": name}
            if seed:
                params["Ids"] = ",".join(seed)
            res = CLIENT.request("POST", "/Collections", params=params)
            return {"created": True, "collection": res, "seeded": len(seed)}
        if action in ("add", "remove"):
            if not collection_id or not item_ids:
                raise EmbyError(f"{action} needs collection_id and item_ids")
            if not confirm:
                return _need_confirm(f"{action} items {item_ids} "
                                     f"{'to' if action == 'add' else 'from'} "
                                     f"collection {collection_id}")
            if action == "add":
                CLIENT.request("POST", f"/Collections/{collection_id}/Items",
                               params={"Ids": item_ids})
            else:
                CLIENT.request("DELETE", f"/Collections/{collection_id}/Items",
                               params={"Ids": item_ids})
            return {"ok": True, "action": action,
                    "member_count_now": len(members(collection_id))}
        if action == "sync_query":
            if not collection_id:
                raise EmbyError("sync_query needs collection_id")
            have = {i["Id"] for i in members(collection_id)}
            matching = query_ids()
            adds = [i for i in matching if i["Id"] not in have]
            if not confirm:
                return _finish({
                    "confirmation_required": True,
                    "already_members": len(have),
                    "query_matches": len(matching),
                    "would_add": [{"Id": i["Id"], "Name": i.get("Name")}
                                  for i in adds],
                    "note": "Nothing changed. Re-run with confirm=true to add "
                            "these. (sync only ADDS; removals are manual.)"})
            if adds:
                CLIENT.request("POST", f"/Collections/{collection_id}/Items",
                               params={"Ids": ",".join(i["Id"] for i in adds)})
            return {"added": len(adds),
                    "member_count_now": len(members(collection_id))}
        if action == "find_franchises":
            movies = CLIENT.request("GET", "/Items", params={
                "IncludeItemTypes": "Movie", "Recursive": True, "Limit": 2000,
                "Fields": "ProviderIds", "UserId": uid}).get("Items", [])
            existing = {c["Name"].lower()
                        for c in CLIENT.request("GET", "/Items", params={
                            "IncludeItemTypes": "BoxSet", "Recursive": True,
                            "UserId": uid, "Limit": 300}).get("Items", [])}
            groups: dict[str, dict] = {}
            for m in movies:
                key = _franchise_key(m.get("Name", ""))
                if len(key) < 3:
                    continue
                g = groups.setdefault(key, {"names": set(), "ids": [],
                                            "tmdb": set()})
                tmdb = (m.get("ProviderIds") or {}).get("Tmdb", m["Id"])
                if tmdb in g["tmdb"]:
                    continue  # duplicate copy of same movie
                g["tmdb"].add(tmdb)
                g["names"].add(m.get("Name"))
                g["ids"].append(m["Id"])
            out = []
            for key, g in sorted(groups.items()):
                if len(g["tmdb"]) < 2:
                    continue
                if any(key in e for e in existing):
                    continue  # likely already collected
                out.append({"franchise": key.title(),
                            "movies": sorted(g["names"]),
                            "item_ids": ",".join(g["ids"])})
            return _finish({
                "candidate_groups": out,
                "note": "Name-heuristic groups — REVIEW WITH THE USER, then "
                        "create the approved ones via action=create with "
                        "item_ids. After creating, emby_refresh_item on the "
                        "new collection pulls TMDb collection art/overview."})
        raise EmbyError("action must be list|items|for_item|create|add|remove|"
                        "sync_query|find_franchises")
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_playlist(action: str, name: str = "", playlist_id: str = "",
                  item_ids: str = "", media_type: str = "Video",
                  user: str = "", confirm: bool = False) -> Any:
    """Manage playlists.

    Args:
        action: "list" | "items" | "create" | "add" | "remove".
            remove uses PlaylistItemIds (the EntryId values shown by "items").
        media_type: For create: "Video" or "Audio".
        confirm: Required for create/add/remove.
    """
    try:
        u = CLIENT.resolve_user(user)
        if action == "list":
            data = CLIENT.request("GET", "/Items", params={
                "IncludeItemTypes": "Playlist", "Recursive": True,
                "UserId": u["Id"], "Limit": 200})
            return {"TotalRecordCount": data.get("TotalRecordCount"),
                    "Items": [compact_item(i) for i in data.get("Items", [])]}
        if action == "items":
            if not playlist_id:
                raise EmbyError("items needs playlist_id")
            data = CLIENT.request("GET", f"/Playlists/{playlist_id}/Items",
                                  params={"UserId": u["Id"]})
            rows = []
            for i in data.get("Items", []):
                row = compact_item(i)
                row["EntryId"] = i.get("PlaylistItemId")
                rows.append(row)
            return {"Items": rows}
        if action == "create":
            if not name:
                raise EmbyError("create needs a name")
            if not confirm:
                return _need_confirm(f"create playlist '{name}'")
            params = {"Name": name, "MediaType": media_type, "UserId": u["Id"]}
            if item_ids:
                params["Ids"] = item_ids
            res = CLIENT.request("POST", "/Playlists", params=params)
            return {"created": True, "playlist": res}
        if action == "add":
            if not playlist_id or not item_ids:
                raise EmbyError("add needs playlist_id and item_ids")
            if not confirm:
                return _need_confirm(f"add items {item_ids} to playlist {playlist_id}")
            CLIENT.request("POST", f"/Playlists/{playlist_id}/Items",
                           params={"Ids": item_ids, "UserId": u["Id"]})
            return {"ok": True}
        if action == "remove":
            if not playlist_id or not item_ids:
                raise EmbyError("remove needs playlist_id and item_ids (EntryIds)")
            if not confirm:
                return _need_confirm(f"remove entries {item_ids} from playlist {playlist_id}")
            CLIENT.request("DELETE", f"/Playlists/{playlist_id}/Items",
                           params={"EntryIds": item_ids})
            return {"ok": True}
        raise EmbyError('action must be one of list|items|create|add|remove')
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Deep metadata: identify, artwork, subtitles                                 #
# --------------------------------------------------------------------------- #
_IDENTIFY_TYPES = {"Movie", "Series", "Person", "BoxSet", "MusicAlbum",
                   "MusicArtist", "MusicVideo", "Trailer", "Game", "Book"}


@mcp.tool()
def emby_identify(item_id: str, action: str = "search", name: str = "",
                  year: int = 0, provider_ids: str = "",
                  result_json: str = "", replace_images: bool = True,
                  confirm: bool = False) -> Any:
    """Re-match an item against metadata providers (the dashboard 'Identify'
    feature) — the fix for wrongly-matched movies/series/collections.

    Args:
        item_id: The item to identify.
        action: "providers" (which external ids this item type supports) |
            "search" (query providers; returns candidate matches) |
            "apply" (adopt one candidate — pass its full JSON back).
        name / year: Search criteria (default: the item's current name).
        provider_ids: Optional JSON object for exact lookup,
            e.g. '{"Imdb": "tt1375666"}' or '{"Tmdb": "27205"}'.
        result_json: For apply: ONE result object from a prior search,
            passed back verbatim.
        replace_images: For apply: also replace artwork from the new match.
        confirm: Required for apply (it rewrites the item's metadata).
    """
    try:
        if action == "providers":
            return CLIENT.request("GET", f"/Items/{item_id}/ExternalIdInfos")
        uid = CLIENT.default_user()["Id"]
        item = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        itype = item.get("Type")
        if action == "search":
            if itype not in _IDENTIFY_TYPES:
                raise EmbyError(f"Type '{itype}' does not support identify "
                                f"(supported: {sorted(_IDENTIFY_TYPES)})")
            info: dict[str, Any] = {"Name": name or item.get("Name")}
            if year:
                info["Year"] = year
            pids = _parse_json_arg("provider_ids", provider_ids)
            if pids:
                info["ProviderIds"] = pids
            results = CLIENT.request("POST", f"/Items/RemoteSearch/{itype}",
                                     body={"SearchInfo": info, "ItemId": item_id})
            return _finish({"current": {"Name": item.get("Name"),
                                        "Year": item.get("ProductionYear"),
                                        "ProviderIds": item.get("ProviderIds")},
                            "candidates": results})
        if action == "apply":
            result = _parse_json_arg("result_json", result_json)
            if not isinstance(result, dict) or not result.get("Name"):
                raise EmbyError("apply needs result_json = one candidate object "
                                "from a prior search")
            if not confirm:
                return _need_confirm(
                    f"re-identify '{item.get('Name')}' as '{result.get('Name')}' "
                    f"({result.get('ProductionYear')}, {result.get('ProviderIds')}) — "
                    f"this REWRITES its metadata{' and artwork' if replace_images else ''}")
            CLIENT.request("POST", f"/Items/RemoteSearch/Apply/{item_id}",
                           params={"ReplaceAllImages": replace_images}, body=result)
            return {"applied": True, "item_id": item_id, "matched": result.get("Name"),
                    "note": "Metadata refresh queued; re-read the item shortly."}
        raise EmbyError('action must be providers|search|apply')
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_images(item_id: str, action: str = "list", image_type: str = "Primary",
                index: int = -1, url: str = "", provider: str = "",
                limit: int = 12, confirm: bool = False) -> Any:
    """Manage an item's artwork (works on movies, series, seasons, episodes,
    collections/BoxSets, people, genres...).

    Args:
        item_id: The item.
        action: "list" (current images) | "providers" (available remote image
            sources) | "search" (browse remote artwork candidates) |
            "download" (adopt a remote image by its url) | "delete".
        image_type: "Primary" (poster), "Backdrop", "Logo", "Thumb",
            "Banner", "Art", "Disc".
        index: For delete of multi-image types (Backdrop): which one; -1 = the
            un-indexed single image.
        url: For download: the remote image url (from search results).
        provider: For search: restrict to one provider (e.g. "TheMovieDb").
        limit: For search.
        confirm: Required for download/delete.
    """
    try:
        if action == "list":
            imgs = CLIENT.request("GET", f"/Items/{item_id}/Images")
            return [{"ImageType": i.get("ImageType"), "Index": i.get("ImageIndex"),
                     "Size": f"{i.get('Width')}x{i.get('Height')}"
                             if i.get("Width") else None,
                     "Bytes": i.get("Size")} for i in imgs]
        if action == "providers":
            return CLIENT.request("GET", f"/Items/{item_id}/RemoteImages/Providers")
        if action == "search":
            params: dict[str, Any] = {"Type": image_type, "Limit": limit,
                                      "IncludeAllLanguages": False}
            if provider:
                params["ProviderName"] = provider
            data = CLIENT.request("GET", f"/Items/{item_id}/RemoteImages", params=params)
            return _finish({"TotalRecordCount": data.get("TotalRecordCount"),
                            "Images": [
                                {"Provider": i.get("ProviderName"),
                                 "Url": i.get("Url"),
                                 "Size": f"{i.get('Width')}x{i.get('Height')}"
                                         if i.get("Width") else None,
                                 "Language": i.get("Language"),
                                 "Rating": i.get("CommunityRating"),
                                 "Votes": i.get("VoteCount")}
                                for i in data.get("Images", [])]})
        if action == "download":
            if not url:
                raise EmbyError("download needs url (from a search result)")
            if not confirm:
                return _need_confirm(
                    f"set the {image_type} image of item {item_id} from {url}")
            CLIENT.request("POST", f"/Items/{item_id}/RemoteImages/Download",
                           params={"Type": image_type, "ImageUrl": url})
            return {"downloaded": True, "type": image_type, "item_id": item_id}
        if action == "delete":
            path = f"/Items/{item_id}/Images/{image_type}"
            if index >= 0:
                path += f"/{index}"
            if not confirm:
                return _need_confirm(f"DELETE the {image_type} image"
                                     f"{f' #{index}' if index >= 0 else ''} of item {item_id}")
            CLIENT.request("DELETE", path)
            return {"deleted": True, "type": image_type, "item_id": item_id}
        raise EmbyError('action must be list|providers|search|download|delete')
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_subtitles(item_id: str, action: str = "list", language: str = "eng",
                   subtitle_id: str = "", index: int = -1,
                   confirm: bool = False) -> Any:
    """Manage subtitles for a video (search/download uses the installed
    subtitle providers — Open Subtitles is configured on this server).

    Args:
        item_id: The movie/episode.
        action: "list" (current subtitle streams) | "search" (query providers) |
            "download" (fetch one by subtitle_id) | "delete" (remove an
            external subtitle stream by index).
        language: 3-letter code for search (eng, spa, fre...).
        subtitle_id: For download: the Id from search results.
        index: For delete: the subtitle stream Index (from list; external only).
        confirm: Required for download/delete.
    """
    try:
        uid = CLIENT.default_user()["Id"]
        item = CLIENT.request("GET", f"/Users/{uid}/Items/{item_id}")
        sources = item.get("MediaSources") or []
        if not sources:
            raise EmbyError("Item has no media sources (not a playable video?)")
        ms_id = sources[0]["Id"]
        if action == "list":
            subs = [
                {"Index": s.get("Index"), "Language": s.get("Language"),
                 "Codec": s.get("Codec"), "Title": s.get("DisplayTitle"),
                 "IsExternal": s.get("IsExternal"), "IsForced": s.get("IsForced"),
                 "Path": s.get("Path")}
                for s in sources[0].get("MediaStreams", [])
                if s.get("Type") == "Subtitle"
            ]
            return {"item": item.get("Name"), "MediaSourceId": ms_id,
                    "Subtitles": subs}
        if action == "search":
            res = CLIENT.request(
                "GET", f"/Items/{item_id}/RemoteSearch/Subtitles/{language}",
                params={"MediaSourceId": ms_id})
            return _finish([{"Id": r.get("Id"), "Name": r.get("Name"),
                             "Format": r.get("Format"),
                             "Downloads": r.get("DownloadCount"),
                             "Rating": r.get("CommunityRating")}
                            for r in (res or [])[:20]])
        if action == "download":
            if not subtitle_id:
                raise EmbyError("download needs subtitle_id (from search)")
            if not confirm:
                return _need_confirm(
                    f"download subtitle {subtitle_id} for '{item.get('Name')}'")
            CLIENT.request(
                "POST", f"/Items/{item_id}/RemoteSearch/Subtitles/{subtitle_id}",
                params={"MediaSourceId": ms_id})
            return {"download_queued": True,
                    "note": "Re-run action=list shortly to see the new stream."}
        if action == "delete":
            if index < 0:
                raise EmbyError("delete needs index (an EXTERNAL stream from list)")
            if not confirm:
                return _need_confirm(
                    f"delete subtitle stream #{index} of '{item.get('Name')}'")
            CLIENT.request("DELETE", f"/Videos/{item_id}/Subtitles/{index}",
                           params={"MediaSourceId": ms_id})
            return {"deleted": True, "index": index}
        raise EmbyError('action must be list|search|download|delete')
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Bulk metadata editing                                                       #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_bulk_update(patch: str, include_types: str = "", parent_id: str = "",
                     search_term: str = "", genres: str = "", years: str = "",
                     person: str = "", studios: str = "", filters: str = "",
                     lock_edited: bool = True, limit: int = 100,
                     confirm: bool = False) -> Any:
    """Apply one metadata patch to EVERY item matching a query — the Metadata
    Manager's bulk-edit, scriptable. Example: tag all 80s horror movies
    '{"Tags": ["retro-horror"]}'.

    Args:
        patch: JSON object of fields to set on each item (same fields as
            emby_update_item). NOTE: list fields (Genres, Tags, Studios)
            REPLACE the item's list.
        include_types/parent_id/search_term/genres/years/person/studios/
            filters: The query (same semantics as emby_items).
        lock_edited: Also add the patched fields to each item's LockedFields
            so future metadata refreshes don't undo the edit (recommended).
        limit: Safety cap on affected items (default 100).
        confirm: Must be true. WITHOUT confirm this returns the full list of
            items that WOULD be edited — always show it to the user first.
    """
    try:
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise EmbyError("patch must be a non-empty JSON object")
        uid = CLIENT.default_user()["Id"]
        params = _items_params(include_types, parent_id, search_term, genres,
                               years, person, studios, filters)
        params.update({"Limit": limit, "UserId": uid, "SortBy": "SortName"})
        data = CLIENT.request("GET", "/Items", params=params)
        targets = data.get("Items", [])
        total = data.get("TotalRecordCount", len(targets))
        if not confirm:
            return _finish({
                "confirmation_required": True,
                "would_edit_count": len(targets),
                "total_matching": total,
                "patch": change,
                "lock_edited": lock_edited,
                "items": [{"Id": i["Id"], "Name": i.get("Name"),
                           "Year": i.get("ProductionYear")} for i in targets],
                "note": ("Nothing was changed. Show this list to the user; "
                         "re-run with confirm=true after explicit approval."
                         + (f" WARNING: {total - len(targets)} more items match "
                            f"beyond the {limit}-item cap." if total > len(targets) else "")),
            })
        edited, failed = [], []
        lockable = [k for k in change if k not in ("LockedFields", "IsLocked")]
        for it in targets:
            try:
                full = CLIENT.request("GET", f"/Users/{uid}/Items/{it['Id']}")
                merged = {**full, **change}
                if lock_edited:
                    merged["LockedFields"] = sorted(
                        set(full.get("LockedFields") or []) | set(lockable))
                CLIENT.request("POST", f"/Items/{it['Id']}", body=merged)
                edited.append(it.get("Name"))
            except Exception as ex:  # noqa: BLE001
                failed.append({"item": it.get("Name"), "error": str(ex)[:120]})
        return _finish({"edited_count": len(edited), "edited": edited,
                        **({"failed": failed} if failed else {})})
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Versions: duplicates, merge, split                                          #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_versions(action: str, item_ids: str = "", scan_limit: int = 1000,
                  confirm: bool = False) -> Any:
    """Manage multiple copies of the same movie as quality VERSIONS of one
    library entry (Emby's 'Merge versions' / 'Alternate sources' feature).

    Args:
        action: "find_duplicates" (scan movies sharing a TMDb/IMDb id — merge
            candidates) | "list" (versions of one item) | "merge" (group
            item_ids CSV into one entry) | "split" (un-merge item_ids back
            into separate entries).
        item_ids: For merge: CSV of the duplicate item ids. For list/split:
            the item id(s).
        scan_limit: For find_duplicates: how many movies to scan.
        confirm: Required for merge/split.
    """
    try:
        uid = CLIENT.default_user()["Id"]
        if action == "find_duplicates":
            data = CLIENT.request("GET", "/Items", params={
                "IncludeItemTypes": "Movie", "Recursive": True,
                "Limit": scan_limit, "Fields": "ProviderIds,Path,MediaSources"})
            groups: dict[str, list] = {}
            for it in data.get("Items", []):
                pid = (it.get("ProviderIds") or {}).get("Tmdb") \
                    or (it.get("ProviderIds") or {}).get("Imdb")
                if pid:
                    groups.setdefault(pid, []).append(it)
            dups = []
            for pid, items in groups.items():
                if len(items) > 1:
                    dups.append({
                        "provider_id": pid,
                        "name": items[0].get("Name"),
                        "copies": [{"Id": i["Id"], "Path": i.get("Path"),
                                    "Container": i.get("Container")}
                                   for i in items],
                        "merge_with": ",".join(i["Id"] for i in items),
                    })
            return _finish({"scanned": len(data.get("Items", [])),
                            "duplicate_groups": dups,
                            "note": "Pass a group's merge_with value to "
                                    "action=merge to combine them."})
        if action == "list":
            if not item_ids:
                raise EmbyError("list needs item_ids (one id)")
            it = CLIENT.request("GET", f"/Users/{uid}/Items/{item_ids}")
            return {"item": it.get("Name"),
                    "versions": [{"Id": m.get("Id"), "Name": m.get("Name"),
                                  "Path": m.get("Path"),
                                  "Bitrate": m.get("Bitrate"),
                                  "Container": m.get("Container")}
                                 for m in it.get("MediaSources", [])]}
        if action == "merge":
            ids = _csv(item_ids)
            if len(ids) < 2:
                raise EmbyError("merge needs 2+ item ids (CSV)")
            names = []
            for i in ids:
                it = CLIENT.request("GET", f"/Users/{uid}/Items/{i}")
                names.append(f"{it.get('Name')} ({it.get('Path')})")
            if not confirm:
                return _need_confirm("merge these into ONE library entry with "
                                     f"multiple versions: {names}")
            CLIENT.request("POST", "/Videos/MergeVersions",
                           params={"Ids": ",".join(ids)})
            return {"merged": True, "items": names,
                    "note": "Files are untouched; they now appear as versions "
                            "of one entry. Reversible with action=split."}
        if action == "split":
            if not item_ids:
                raise EmbyError("split needs item_ids (the merged item's id)")
            if not confirm:
                return _need_confirm(f"split item {item_ids} back into separate "
                                     "library entries")
            CLIENT.request("DELETE", f"/Videos/{item_ids}/AlternateSources")
            return {"split": True, "item_id": item_ids}
        raise EmbyError('action must be find_duplicates|list|merge|split')
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Sync & conversion jobs (Premiere)                                           #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_sync_jobs(action: str, target_id: str = "", item_ids: str = "",
                   quality: str = "", container: str = "", bitrate: int = 0,
                   unwatched_only: bool = False, job_id: str = "",
                   confirm: bool = False) -> Any:
    """Sync/downloads & media CONVERSION jobs (Emby Premiere — active here).
    Conversion = a sync job targeting "originalmediafolder" (new file next to
    the original) or "originalmediafolderreplace" (REPLACES the original).

    Args:
        action: "targets" | "jobs" | "create" | "cancel".
        target_id: For create: from action=targets (a device id, or the two
            conversion targets above).
        item_ids: For create: CSV of items to sync/convert.
        quality: For create: e.g. "original", "high", "medium", "low".
        container: For create: e.g. "mkv", "mp4".
        bitrate: For create: explicit bitrate cap (bits/sec), optional.
        unwatched_only: Sync only unwatched items.
        job_id: For cancel.
        confirm: Required for create/cancel. Creating a
            'originalmediafolderreplace' job OVERWRITES source files — warn
            loudly.
    """
    try:
        uid = CLIENT.default_user()["Id"]
        if action == "targets":
            return CLIENT.request("GET", "/Sync/Targets", params={"UserId": uid})
        if action == "jobs":
            data = CLIENT.request("GET", "/Sync/Jobs")
            return [{"Id": j.get("Id"), "Name": j.get("Name"),
                     "Target": j.get("TargetName"), "Status": j.get("Status"),
                     "Progress": j.get("Progress"), "Quality": j.get("Quality"),
                     "Container": j.get("Container"),
                     "ItemCount": j.get("ItemCount")}
                    for j in data.get("Items", [])]
        if action == "create":
            if not target_id or not item_ids:
                raise EmbyError("create needs target_id and item_ids")
            replace = target_id == "originalmediafolderreplace"
            if not confirm:
                return _need_confirm(
                    f"create a sync/conversion job of items {item_ids} to target "
                    f"'{target_id}'"
                    + (" — this target REPLACES THE ORIGINAL FILES with the "
                       "converted output!" if replace else ""))
            body: dict[str, Any] = {"TargetId": target_id,
                                    "ItemIds": _csv(item_ids), "UserId": uid,
                                    "UnwatchedOnly": unwatched_only}
            if quality:
                body["Quality"] = quality
            if container:
                body["Container"] = container
            if bitrate:
                body["Bitrate"] = bitrate
            job = CLIENT.request("POST", "/Sync/Jobs", body=body)
            return {"created": True, "job": {"Id": (job or {}).get("Id"),
                                             "Name": (job or {}).get("Name")}}
        if action == "cancel":
            if not job_id:
                raise EmbyError("cancel needs job_id")
            if not confirm:
                return _need_confirm(f"cancel/delete sync job {job_id}")
            CLIENT.request("DELETE", f"/Sync/Jobs/{job_id}")
            return {"cancelled": True, "job_id": job_id}
        raise EmbyError('action must be targets|jobs|create|cancel')
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Library structure management                                                #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_library_manage(action: str, name: str = "", collection_type: str = "",
                        path: str = "", new_name: str = "",
                        options_patch: str = "", refresh: bool = False,
                        confirm: bool = False) -> Any:
    """Create/delete/rename libraries, manage their folders, and edit
    LibraryOptions — the full library-management surface.

    Args:
        action: "create" | "delete" | "rename" | "add_path" | "remove_path" |
            "get_options" | "update_options".
        name: The library name (all actions).
        collection_type: For create — the COMPLETE list this server's wizard
            offers (extracted from its own UI code, 4.7.14): "movies",
            "tvshows", "music", "musicvideos", "homevideos" (videos+photos),
            "audiobooks", "books" (ebooks AND comics: epub/pdf/cbz/cbr),
            "games" (requires the GameBrowser plugin), or ""/"mixed" for a
            multi-type mixed-content library (sent as null, like the wizard).
        path: For create/add_path/remove_path: the server-side folder path.
        new_name: For rename.
        options_patch: For update_options: JSON object of LibraryOptions keys
            to change (e.g. '{"EnableRealtimeMonitor": true}') — the full
            options object is round-tripped.
        refresh: Trigger a library scan after the change.
        confirm: Required for every action except get_options.
    """
    try:
        def find_vf(n: str) -> dict:
            vfs = CLIENT.request("GET", "/Library/VirtualFolders")
            vf = next((v for v in vfs if v["Name"].lower() == n.lower()), None)
            if vf is None:
                raise EmbyError(f"No library named '{n}'. Existing: "
                                + ", ".join(v["Name"] for v in vfs))
            return vf

        if action == "get_options":
            return _finish(find_vf(name).get("LibraryOptions", {}))
        if not name:
            raise EmbyError("name is required")
        if action == "create":
            if not confirm:
                return _need_confirm(
                    f"create library '{name}' (type: {collection_type or 'mixed'}"
                    f"{', path: ' + path if path else ''})")
            params = {"Name": name, "RefreshLibrary": refresh}
            if collection_type and collection_type != "mixed":
                params["CollectionType"] = collection_type
            body = {"LibraryOptions": {}}
            if path:
                body["LibraryOptions"]["PathInfos"] = [{"Path": path}]
            CLIENT.request("POST", "/Library/VirtualFolders", params=params, body=body)
            return {"created": True, "library": find_vf(name)["Name"]}
        if action == "delete":
            vf = find_vf(name)
            if not confirm:
                return _need_confirm(
                    f"DELETE library '{vf['Name']}' (folders {vf.get('Locations')} "
                    "stay on disk, but the library and its metadata are removed)")
            # 4.7 gotcha (proven live): the route 500s unless the folder's
            # Guid is passed as Id — Name alone is not enough.
            CLIENT.request("DELETE", "/Library/VirtualFolders",
                           params={"Id": vf["Guid"], "Name": vf["Name"],
                                   "RefreshLibrary": refresh})
            return {"deleted": True, "library": vf["Name"]}
        if action == "rename":
            vf = find_vf(name)
            if not new_name:
                raise EmbyError("rename needs new_name")
            if not confirm:
                return _need_confirm(f"rename library '{vf['Name']}' to '{new_name}'")
            CLIENT.request("POST", "/Library/VirtualFolders/Name",
                           params={"Id": vf["Guid"], "Name": vf["Name"],
                                   "NewName": new_name, "RefreshLibrary": refresh})
            return {"renamed": True, "now": new_name}
        if action in ("add_path", "remove_path"):
            vf = find_vf(name)
            if not path:
                raise EmbyError(f"{action} needs path")
            if not confirm:
                return _need_confirm(
                    f"{action.replace('_', ' ')} '{path}' "
                    f"{'to' if action == 'add_path' else 'from'} library '{vf['Name']}'")
            if action == "add_path":
                CLIENT.request("POST", "/Library/VirtualFolders/Paths",
                               params={"Id": vf["Guid"], "Name": vf["Name"],
                                       "Path": path, "RefreshLibrary": refresh})
            else:
                CLIENT.request("DELETE", "/Library/VirtualFolders/Paths",
                               params={"Id": vf["Guid"], "Name": vf["Name"],
                                       "Path": path, "RefreshLibrary": refresh})
            return {"ok": True, "action": action,
                    "locations_now": find_vf(name).get("Locations")}
        if action == "update_options":
            vf = find_vf(name)
            change = _parse_json_arg("options_patch", options_patch)
            if not isinstance(change, dict) or not change:
                raise EmbyError("update_options needs options_patch (JSON object)")
            current = vf.get("LibraryOptions", {})
            if not confirm:
                return _need_confirm(
                    f"update LibraryOptions of '{vf['Name']}', keys {list(change)} "
                    f"(current: { {k: current.get(k) for k in change} })")
            CLIENT.request("POST", "/Library/VirtualFolders/LibraryOptions",
                           body={"Id": vf["ItemId"],
                                 "LibraryOptions": {**current, **change}})
            after = find_vf(name).get("LibraryOptions", {})
            return {"updated": True, "library": vf["Name"],
                    "now": {k: after.get(k) for k in change}}
        raise EmbyError("action must be create|delete|rename|add_path|remove_path|"
                        "get_options|update_options")
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Display preferences & task scheduling                                       #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_display_prefs(user: str = "", client: str = "emby", patch: str = "",
                       confirm: bool = False) -> Any:
    """Read/customize a user's display preferences and HOME SCREEN layout
    (per client app).

    Args:
        user: User name/id (default: configured admin).
        client: "emby" (web/apps), "emby.tv" etc.
        patch: Empty to READ. Or a JSON object merged into CustomPrefs —
            home rows: {"homesection0": "resume", "homesection1": "nextup",
            "homesection2": "latestmedia", ...} with values: "smalllibrarytiles"
            (My Media), "librarybuttons", "resume" (Continue Watching),
            "resumeaudio", "nextup", "latestmedia", "activerecordings",
            "none" (hide), "" (server default). Also: "accentColor",
            "skipForwardLength"/"skipBackLength" (ms), "enableLogoAsTitle".
            Top-level DisplayPreferences fields (e.g. "ShowBackdrop") can be
            patched too — keys are routed automatically.
        confirm: Required when writing.
    """
    try:
        u = CLIENT.resolve_user(user)
        params = {"userId": u["Id"], "client": client}
        current = CLIENT.request("GET", "/DisplayPreferences/usersettings",
                                 params=params)
        if not patch:
            return _finish(current)
        change = _parse_json_arg("patch", patch)
        if not isinstance(change, dict) or not change:
            raise EmbyError("patch must be a non-empty JSON object")
        top = {k: v for k, v in change.items() if k in current and k != "CustomPrefs"}
        custom = {k: v for k, v in change.items() if k not in top}
        if not confirm:
            cp = current.get("CustomPrefs", {})
            return _need_confirm(
                f"update display prefs of '{u['Name']}' (client {client}): "
                f"CustomPrefs {custom} (current: { {k: cp.get(k) for k in custom} })"
                + (f", fields {top}" if top else ""))
        merged = {**current, **top}
        merged["CustomPrefs"] = {**current.get("CustomPrefs", {}),
                                 **{k: str(v) for k, v in custom.items()}}
        CLIENT.request("POST", "/DisplayPreferences/usersettings",
                       params={"UserId": u["Id"], "client": client}, body=merged)
        after = CLIENT.request("GET", "/DisplayPreferences/usersettings",
                               params=params)
        acp = after.get("CustomPrefs", {})
        return {"updated": True, "user": u["Name"],
                "now": {**{k: acp.get(k) for k in custom},
                        **{k: after.get(k) for k in top}}}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_task_triggers(task_id: str, triggers_json: str = "",
                       confirm: bool = False) -> Any:
    """Read or set WHEN a scheduled task runs (maintenance windows).

    Args:
        task_id: From emby_scheduled_tasks.
        triggers_json: Empty to READ current triggers. Or a JSON ARRAY
            replacing them, e.g. nightly 3am:
            '[{"Type": "DailyTrigger", "TimeOfDayTicks": 108000000000}]'
            (ticks: 1 hour = 36000000000). Types: DailyTrigger,
            WeeklyTrigger (+"DayOfWeek"), IntervalTrigger ("IntervalTicks"),
            StartupTrigger, SystemEventTrigger ("SystemEvent":
            "WakeFromSleep"). '[]' disables automatic runs.
        confirm: Required when writing.
    """
    try:
        task = CLIENT.request("GET", f"/ScheduledTasks/{task_id}")
        if not triggers_json:
            return {"task": task.get("Name"), "triggers": task.get("Triggers", [])}
        new = _parse_json_arg("triggers_json", triggers_json)
        if not isinstance(new, list):
            raise EmbyError("triggers_json must be a JSON array (can be empty)")
        if not confirm:
            return _need_confirm(
                f"replace triggers of task '{task.get('Name')}' "
                f"(current: {task.get('Triggers')}) with: {new}")
        CLIENT.request("POST", f"/ScheduledTasks/{task_id}/Triggers", body=new)
        after = CLIENT.request("GET", f"/ScheduledTasks/{task_id}")
        return {"updated": True, "task": task.get("Name"),
                "triggers_now": after.get("Triggers", [])}
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Live TV                                                                     #
# --------------------------------------------------------------------------- #
@mcp.tool()
def emby_livetv_status() -> Any:
    """Live TV overview: enabled state, configured tuners and guide providers,
    channel/timer/recording counts, guide date range, and the tuner/provider
    types this server supports. Start here for any Live TV / IPTV request."""
    try:
        info = CLIENT.request("GET", "/LiveTv/Info")
        tuners = CLIENT.request("GET", "/LiveTv/TunerHosts") or []
        store = CLIENT.request("GET", "/System/Configuration/livetv")
        providers = store.get("ListingProviders", []) or []
        channels = CLIENT.request("GET", "/LiveTv/Channels", params={"Limit": 0})
        recordings = CLIENT.request("GET", "/LiveTv/Recordings", params={"Limit": 0})
        timers = CLIENT.request("GET", "/LiveTv/Timers")
        types = CLIENT.request("GET", "/LiveTv/TunerHosts/Types") or []
        avail = CLIENT.request("GET", "/LiveTv/ListingProviders/Available") or []
        return {
            "IsEnabled": info.get("IsEnabled"),
            "EnabledUsers": info.get("EnabledUsers"),
            "Tuners": [{"Id": t.get("Id"), "Type": t.get("Type"), "Url": t.get("Url"),
                        "FriendlyName": t.get("FriendlyName"),
                        "TunerCount": t.get("TunerCount")} for t in tuners],
            "GuideProviders": [{"Id": p.get("Id"), "Type": p.get("Type"),
                                "Path": p.get("Path"), "ListingsId": p.get("ListingsId")}
                               for p in providers],
            "ChannelCount": channels.get("TotalRecordCount"),
            "RecordingCount": recordings.get("TotalRecordCount"),
            "TimerCount": timers.get("TotalRecordCount"),
            "GuideRange": CLIENT.request("GET", "/LiveTv/GuideInfo"),
            "SupportedTunerTypes": [t.get("Id") for t in types],
            "AvailableGuideProviderTypes": [{"Id": a.get("Id"), "Name": a.get("Name")}
                                            for a in avail],
            "RecordingFolders": (CLIENT.request("GET", "/LiveTv/Recordings/Folders")
                                 or {}).get("Items", []),
        }
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_livetv_tuner(action: str, tuner_type: str = "m3u", url: str = "",
                      friendly_name: str = "", tuner_count: int = 0,
                      tuner_id: str = "", user_agent: str = "",
                      confirm: bool = False) -> Any:
    """Manage Live TV tuner sources (IPTV M3U playlists, HDHomeRun devices).

    Args:
        action: "list" | "add" | "delete".
        tuner_type: For add: "m3u" (IPTV playlist URL/path) or "hdhomerun"
            (device URL). This server supports exactly these two.
        url: For add: the M3U playlist URL/file path, or HDHomeRun base URL.
        friendly_name: Optional display name.
        tuner_count: Max simultaneous streams this source allows (0 = unlimited;
            set this to your IPTV provider's connection limit).
        user_agent: Optional HTTP User-Agent some IPTV providers require.
        tuner_id: For delete: the tuner Id (from list).
        confirm: Required for add/delete.
    """
    try:
        if action == "list":
            return CLIENT.request("GET", "/LiveTv/TunerHosts") or []
        if action == "add":
            if not url:
                raise EmbyError("add needs url (M3U playlist or HDHomeRun address)")
            defaults = CLIENT.request("GET", f"/LiveTv/TunerHosts/Default/{tuner_type}")
            body = {**defaults, "Type": tuner_type, "Url": url}
            if friendly_name:
                body["FriendlyName"] = friendly_name
            if tuner_count:
                body["TunerCount"] = tuner_count
            if user_agent:
                body["UserAgent"] = user_agent
            if not confirm:
                return _need_confirm(f"add a {tuner_type} tuner pointing at {url}")
            created = CLIENT.request("POST", "/LiveTv/TunerHosts", body=body)
            return {"added": True, "tuner": created,
                    "next": "Add a guide provider (emby_livetv_guide_provider), then "
                            "run the 'Refresh Guide' scheduled task."}
        if action == "delete":
            if not tuner_id:
                raise EmbyError("delete needs tuner_id")
            if not confirm:
                return _need_confirm(f"delete tuner {tuner_id}")
            CLIENT.request("DELETE", "/LiveTv/TunerHosts", params={"Id": tuner_id})
            return {"deleted": True, "tuner_id": tuner_id}
        raise EmbyError('action must be list|add|delete')
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_livetv_guide_provider(action: str, provider_type: str = "xmltv",
                               path: str = "", listings_id: str = "",
                               country: str = "US", provider_id: str = "",
                               confirm: bool = False) -> Any:
    """Manage electronic program guide (EPG) sources.

    Args:
        action: "list" | "available" | "add" | "delete".
        provider_type: For add: "xmltv" (XMLTV file/URL — typical for IPTV) or
            "embygn" (Emby Guide Data — Premiere, US/CA broadcast lineups).
        path: For xmltv: the XMLTV guide file path or URL (.xml, may be .gz).
        listings_id: For embygn: the lineup id.
        country: For embygn.
        provider_id: For delete.
        confirm: Required for add/delete.
    """
    try:
        if action == "available":
            return CLIENT.request("GET", "/LiveTv/ListingProviders/Available")
        if action == "list":
            store = CLIENT.request("GET", "/System/Configuration/livetv")
            return store.get("ListingProviders", []) or []
        if action == "add":
            body: dict[str, Any] = {"Type": provider_type, "EnableAllTuners": True}
            if provider_type == "xmltv":
                if not path:
                    raise EmbyError("xmltv needs path (XMLTV file path or URL)")
                body["Path"] = path
            elif provider_type == "embygn":
                if not listings_id:
                    raise EmbyError("embygn needs listings_id")
                body["ListingsId"] = listings_id
                body["Country"] = country
            if not confirm:
                return _need_confirm(f"add a {provider_type} guide provider "
                                     f"({path or listings_id})")
            created = CLIENT.request("POST", "/LiveTv/ListingProviders", body=body)
            return {"added": True, "provider": created,
                    "next": "Run the 'Refresh Guide' scheduled task to pull guide data."}
        if action == "delete":
            if not provider_id:
                raise EmbyError("delete needs provider_id")
            if not confirm:
                return _need_confirm(f"delete guide provider {provider_id}")
            CLIENT.request("DELETE", "/LiveTv/ListingProviders",
                           params={"Id": provider_id})
            return {"deleted": True, "provider_id": provider_id}
        raise EmbyError('action must be list|available|add|delete')
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_livetv_channels(search: str = "", limit: int = 50,
                         start_index: int = 0, user: str = "",
                         include_disabled: bool = False) -> Any:
    """List Live TV channels (number, name, id, current program when guide
    data exists). include_disabled=True uses the management view that also
    shows channels hidden from users."""
    try:
        # When searching, fetch a wide window and filter — otherwise the filter
        # would only see the first `limit` channels of the lineup.
        fetch_limit = 2000 if search else limit
        fetch_start = 0 if search else start_index
        if include_disabled:
            data = CLIENT.request("GET", "/LiveTv/Manage/Channels",
                                  params={"Limit": fetch_limit, "StartIndex": fetch_start})
        else:
            uid = CLIENT.resolve_user(user)["Id"]
            params: dict[str, Any] = {"Limit": fetch_limit, "StartIndex": fetch_start,
                                      "UserId": uid, "AddCurrentProgram": True}
            data = CLIENT.request("GET", "/LiveTv/Channels", params=params)
        items = data.get("Items", [])
        if search:
            s = search.lower()
            items = [c for c in items if s in (c.get("Name") or "").lower()
                     or s == str(c.get("ChannelNumber") or c.get("Number") or "")]
            items = items[start_index:start_index + limit]
        return {"TotalRecordCount": data.get("TotalRecordCount"),
                "Items": [{"Id": c.get("Id"), "Number": c.get("ChannelNumber") or c.get("Number"),
                           "Name": c.get("Name"),
                           "CurrentProgram": (c.get("CurrentProgram") or {}).get("Name"),
                           **({"Disabled": c.get("Disabled")} if include_disabled else {})}
                          for c in items]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_livetv_guide(channel_ids: str = "", hours: int = 12, search: str = "",
                      limit: int = 50, user: str = "") -> Any:
    """Browse the program guide (EPG).

    Args:
        channel_ids: Optional CSV of channel ids to restrict to.
        hours: Look-ahead window from now (default 12).
        search: Optional program title search across the whole guide.
        limit: Max programs returned.
    """
    try:
        import datetime as _dt
        uid = CLIENT.resolve_user(user)["Id"]
        params: dict[str, Any] = {"UserId": uid, "Limit": limit,
                                  "SortBy": "StartDate",
                                  "EnableTotalRecordCount": False}
        if channel_ids:
            params["ChannelIds"] = channel_ids
        if search:
            params["SearchTerm"] = search
        else:
            now = _dt.datetime.now(_dt.timezone.utc)
            params["MinEndDate"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            params["MaxStartDate"] = (now + _dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = CLIENT.request("GET", "/LiveTv/Programs", params=params)
        return {"Items": [
            {"Id": p.get("Id"), "Channel": p.get("ChannelName"),
             "Name": p.get("Name"), "Episode": p.get("EpisodeTitle"),
             "Start": p.get("StartDate"), "End": p.get("EndDate"),
             "IsMovie": p.get("IsMovie") or None, "IsSports": p.get("IsSports") or None,
             "IsNews": p.get("IsNews") or None,
             "TimerId": p.get("TimerId"), "SeriesTimerId": p.get("SeriesTimerId")}
            for p in data.get("Items", [])
        ]}
    except Exception as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def emby_livetv_dvr(action: str, program_id: str = "", timer_id: str = "",
                    series: bool = False, confirm: bool = False) -> Any:
    """DVR: recordings, timers, and scheduling (requires Emby Premiere —
    active on this server).

    Args:
        action: "recordings" | "timers" | "record" | "cancel".
        program_id: For record: the guide program id (from emby_livetv_guide).
        series: record/cancel a whole SERIES instead of one airing.
        timer_id: For cancel: the timer id (or series timer id with series=true).
        confirm: Required for record/cancel.
    """
    try:
        if action == "recordings":
            data = CLIENT.request("GET", "/LiveTv/Recordings", params={"Limit": 100})
            return {"TotalRecordCount": data.get("TotalRecordCount"),
                    "Items": [compact_item(i) for i in data.get("Items", [])]}
        if action == "timers":
            timers = CLIENT.request("GET", "/LiveTv/Timers")
            stimers = CLIENT.request("GET", "/LiveTv/SeriesTimers")

            def slim(t: dict) -> dict:
                return {"Id": t.get("Id"), "Name": t.get("Name"),
                        "Channel": t.get("ChannelName"), "Start": t.get("StartDate"),
                        "Status": t.get("Status")}
            return {"Timers": [slim(t) for t in timers.get("Items", [])],
                    "SeriesTimers": [slim(t) for t in stimers.get("Items", [])]}
        if action == "record":
            if not program_id:
                raise EmbyError("record needs program_id")
            defaults = CLIENT.request("GET", "/LiveTv/Timers/Defaults",
                                      params={"ProgramId": program_id})
            if not confirm:
                return _need_confirm(
                    f"schedule a {'series ' if series else ''}recording of "
                    f"'{defaults.get('Name')}' on {defaults.get('ChannelName')}")
            path = "/LiveTv/SeriesTimers" if series else "/LiveTv/Timers"
            CLIENT.request("POST", path, body=defaults)
            return {"scheduled": True, "program": defaults.get("Name")}
        if action == "cancel":
            if not timer_id:
                raise EmbyError("cancel needs timer_id")
            if not confirm:
                return _need_confirm(f"cancel {'series ' if series else ''}timer {timer_id}")
            path = f"/LiveTv/SeriesTimers/{timer_id}" if series else f"/LiveTv/Timers/{timer_id}"
            CLIENT.request("DELETE", path)
            return {"cancelled": True, "timer_id": timer_id}
        raise EmbyError('action must be recordings|timers|record|cancel')
    except Exception as e:  # noqa: BLE001
        return _err(e)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
def main() -> None:
    if not CONFIG["host"] or not CONFIG["api_key"]:
        log("FATAL: host and api_key must be set (config.local.json or EMBY_HOST/EMBY_API_KEY)")
        sys.exit(1)
    log(f"starting — target {CLIENT.base}")
    mcp.run()


if __name__ == "__main__":
    main()
