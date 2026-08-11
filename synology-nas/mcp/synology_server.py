#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Synology DSM MCP server.

Exposes a Synology DiskStation (tested on a DS1817+ running DSM 7.3) to Claude
through the Model Context Protocol. The design is two-layered:

* A GENERIC passthrough (`synology_call` / `synology_batch` / `synology_list_apis`
  / `synology_describe_api`) that can reach *any* of the ~870 SYNO.* Web APIs the
  box exposes. This is what makes "control everything" true rather than aspirational.
* CURATED tools for the common jobs (system health, storage, files, downloads,
  packages, users, shares, services) so day-to-day tasks are a single clean call.

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import atexit
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[synology-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("SYNOLOGY_CONFIG"):
        candidates.append(Path(os.environ["SYNOLOGY_CONFIG"]))
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
    out = {
        "host": env.get("SYNOLOGY_HOST", cfg.get("host", "")),
        "port": int(env.get("SYNOLOGY_PORT", cfg.get("port", 5001)) or 5001),
        "https": _truthy(env.get("SYNOLOGY_HTTPS"), cfg.get("https", True)),
        "username": env.get("SYNOLOGY_USERNAME", cfg.get("username", "")),
        "password": env.get("SYNOLOGY_PASSWORD", cfg.get("password", "")),
        "otp_code": env.get("SYNOLOGY_OTP_CODE", cfg.get("otp_code", "")),
        "verify_ssl": _truthy(env.get("SYNOLOGY_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("SYNOLOGY_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }
    return out


# --------------------------------------------------------------------------- #
# DSM error codes -> human-readable messages                                  #
# --------------------------------------------------------------------------- #
COMMON_ERRORS = {
    100: "Unknown error.",
    101: "No parameter of API, method or version, or invalid parameter.",
    102: "The requested API does not exist (not registered for this session/DSM).",
    103: "The requested method does not exist.",
    104: "The requested version does not support this functionality.",
    105: "The logged-in session does not have permission.",
    106: "Session timeout.",
    107: "Session interrupted by duplicate login.",
    117: "Access denied / need manager rights.",
    119: "SID not found or missing CSRF (SynoToken).",
    120: "Invalid parameter.",
}
AUTH_ERRORS = {
    400: "No such account or incorrect password.",
    401: "Disabled account.",
    402: "Permission denied.",
    403: "2-factor authentication code required (set otp_code).",
    404: "Failed to authenticate 2-factor code.",
    406: "Enforce to authenticate with 2-factor code.",
    407: "Blocked IP source.",
    408: "Expired password cannot change.",
    409: "Expired password.",
    410: "Password must be changed.",
}


class DSMError(RuntimeError):
    def __init__(self, code: int, api: str = "", method: str = "", auth: bool = False):
        table = AUTH_ERRORS if auth else COMMON_ERRORS
        msg = table.get(code) or COMMON_ERRORS.get(code) or f"Error code {code}."
        ctx = f" [{api}.{method}]" if api else ""
        super().__init__(f"DSM error {code}: {msg}{ctx}")
        self.code = code


# --------------------------------------------------------------------------- #
# DSM client                                                                  #
# --------------------------------------------------------------------------- #
def _encode_param(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return json.dumps(v, separators=(",", ":"))
    return str(v)


class DSMClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        self.base = f"{scheme}://{cfg['host']}:{cfg['port']}/webapi"
        self._http = httpx.Client(
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
            follow_redirects=True,
        )
        self.sid: Optional[str] = None
        self.synotoken: Optional[str] = None
        self.confirm_token: Optional[str] = None
        self.api_info: dict[str, dict] = {}
        self._all_discovered = False
        self._lock = threading.RLock()

    # -- discovery -------------------------------------------------------- #
    def discover(self, names: Optional[list[str]] = None, refresh: bool = False) -> dict:
        query = ",".join(names) if names else "all"
        params = {"api": "SYNO.API.Info", "version": 1, "method": "query", "query": query}
        r = self._http.get(f"{self.base}/query.cgi", params=params)
        data = self._parse(r, "SYNO.API.Info", "query")
        if not names:
            self.api_info = data
            self._all_discovered = True
        else:
            self.api_info.update(data)
        return data

    def _resolve(self, api: str, version: Optional[int]) -> tuple[str, int]:
        info = self.api_info.get(api)
        if info is None and not self._all_discovered:
            try:
                self.discover()
                info = self.api_info.get(api)
            except Exception:  # noqa: BLE001
                info = None
        if info is None:
            # Might be a hidden/package API; probe it directly.
            try:
                found = self.discover(names=[api])
                info = found.get(api)
            except Exception:  # noqa: BLE001
                info = None
        path = (info or {}).get("path", "entry.cgi")
        if version is None:
            version = (info or {}).get("maxVersion", 1)
        return path, int(version)

    # -- auth ------------------------------------------------------------- #
    def login(self) -> dict:
        cfg = self.cfg
        if not cfg["host"]:
            raise DSMError(101, "SYNO.API.Auth", "login")
        params = {
            "api": "SYNO.API.Auth",
            "version": 7,
            "method": "login",
            "account": cfg["username"],
            "passwd": cfg["password"],
            "format": "sid",
            "enable_syno_token": "yes",
        }
        if cfg.get("otp_code"):
            params["otp_code"] = cfg["otp_code"]
        r = self._http.post(f"{self.base}/entry.cgi", data=params)
        data = self._parse(r, "SYNO.API.Auth", "login", auth=True)
        self.sid = data.get("sid")
        self.synotoken = data.get("synotoken")
        log(f"logged in as {cfg['username']} (sid ok, csrf {'ok' if self.synotoken else 'none'})")
        return {"account": data.get("account"), "device_id": data.get("device_id")}

    def ensure_session(self) -> None:
        with self._lock:
            if not self.sid:
                self.login()

    def confirm_password(self, force: bool = False) -> str:
        """DSM gates sensitive settings (share/permission/network writes) behind a
        password re-confirmation. This returns a short-lived SynoConfirmPWToken to
        attach to those calls (via call(..., elevate=True))."""
        if self.confirm_token and not force:
            return self.confirm_token
        self.ensure_session()
        data = self.call("SYNO.Core.User.PasswordConfirm", "auth", 2,
                         {"password": self.cfg["password"]})
        self.confirm_token = data.get("SynoConfirmPWToken")
        if not self.confirm_token:
            raise RuntimeError("password confirmation did not return a token")
        return self.confirm_token

    def logout(self) -> None:
        if not self.sid:
            return
        try:
            self._http.post(
                f"{self.base}/entry.cgi",
                data={"api": "SYNO.API.Auth", "version": 7, "method": "logout"},
            )
        except Exception:  # noqa: BLE001
            pass
        self.sid = None
        self.synotoken = None

    # -- core call -------------------------------------------------------- #
    def _parse(self, r: httpx.Response, api: str, method: str, auth: bool = False) -> Any:
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            raise RuntimeError(
                f"Non-JSON response from {api}.{method} (HTTP {r.status_code}): "
                f"{r.text[:300]}"
            )
        if not body.get("success"):
            err = body.get("error", {}) or {}
            code = int(err.get("code", 100))
            e = DSMError(code, api, method, auth=auth)
            # attach extra error payload if present (some APIs return details)
            if err.get("errors"):
                e.args = (f"{e.args[0]} details={json.dumps(err['errors'])[:400]}",)
            raise e
        return body.get("data", {})

    def call(
        self,
        api: str,
        method: str,
        version: Optional[int] = None,
        params: Optional[dict] = None,
        http_method: str = "POST",
        elevate: bool = False,
        _retried: bool = False,
    ) -> Any:
        self.ensure_session()
        path, ver = self._resolve(api, version)
        payload = {"api": api, "version": ver, "method": method, "_sid": self.sid}
        for k, v in (params or {}).items():
            if v is None:
                continue
            payload[k] = _encode_param(v)
        if elevate:
            payload["SynoConfirmPWToken"] = self.confirm_password()
        headers = {}
        if self.synotoken:
            headers["X-SYNO-TOKEN"] = self.synotoken
        url = f"{self.base}/{path}"
        try:
            if http_method.upper() == "GET":
                r = self._http.get(url, params=payload, headers=headers)
            else:
                r = self._http.post(url, data=payload, headers=headers)
            return self._parse(r, api, method)
        except DSMError as e:
            if e.code in (105, 106, 107, 119) and not _retried:
                log(f"session error {e.code}; re-authenticating and retrying")
                self.sid = None
                self.synotoken = None
                self.confirm_token = None
                self.login()
                return self.call(api, method, version, params, http_method, elevate, _retried=True)
            if elevate and e.code in (402, 403) and not _retried:
                log("elevated call denied; refreshing confirm-password token and retrying")
                self.confirm_token = None
                self.confirm_password(force=True)
                return self.call(api, method, version, params, http_method, elevate, _retried=True)
            raise

    def batch(self, requests: list[dict], mode: str = "sequential") -> Any:
        """Compound request via SYNO.Entry.Request (many calls, one round-trip)."""
        self.ensure_session()
        compound = []
        for req in requests:
            item = {
                "api": req["api"],
                "method": req["method"],
                "version": req.get("version") or self._resolve(req["api"], None)[1],
            }
            for k, v in (req.get("params") or {}).items():
                item[k] = v
            compound.append(item)
        payload = {
            "api": "SYNO.Entry.Request",
            "version": 1,
            "method": "request",
            "mode": mode,
            "compound": json.dumps(compound, separators=(",", ":")),
            "_sid": self.sid,
        }
        headers = {"X-SYNO-TOKEN": self.synotoken} if self.synotoken else {}
        r = self._http.post(f"{self.base}/entry.cgi", data=payload, headers=headers)
        return self._parse(r, "SYNO.Entry.Request", "request")

    # -- files (binary) --------------------------------------------------- #
    def download(self, remote_path: str, dest: Optional[str] = None,
                 _retried: bool = False) -> dict:
        self.ensure_session()
        path, ver = self._resolve("SYNO.FileStation.Download", None)
        params = {
            "api": "SYNO.FileStation.Download",
            "version": ver,
            "method": "download",
            "path": json.dumps([remote_path]),
            "mode": "download",
            "_sid": self.sid,
        }
        headers = {"X-SYNO-TOKEN": self.synotoken} if self.synotoken else {}
        try:
            with self._http.stream("GET", f"{self.base}/{path}", params=params, headers=headers) as r:
                ctype = r.headers.get("content-type", "")
                if "application/json" in ctype:
                    # A JSON body here means DSM answered with an error envelope
                    # (or, rarely, a bare success envelope) instead of file bytes.
                    body = json.loads(b"".join(r.iter_bytes()))
                    self._parse_ok(body, "SYNO.FileStation.Download", "download")
                    return {"result": body.get("data", {})}
                if dest:
                    size = 0
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_bytes():
                            fh.write(chunk)
                            size += len(chunk)
                    return {"saved_to": dest, "bytes": size}
                content = b"".join(r.iter_bytes())
        except DSMError as e:
            if e.code in (105, 106, 107, 119) and not _retried:
                log(f"session error {e.code} on download; re-authenticating and retrying")
                self.sid = None
                self.synotoken = None
                self.confirm_token = None
                self.login()
                return self.download(remote_path, dest, _retried=True)
            raise
        try:
            text = content.decode("utf-8")
            preview = text if len(text) <= 4000 else text[:4000] + f"\n...[truncated, {len(text)} chars total]"
            return {"bytes": len(content), "text": preview}
        except UnicodeDecodeError:
            return {"bytes": len(content), "note": "binary content; pass save_to to write it to disk"}

    @staticmethod
    def _parse_ok(body: dict, api: str, method: str) -> None:
        if not body.get("success"):
            code = int((body.get("error") or {}).get("code", 100))
            raise DSMError(code, api, method)

    def upload(self, local_path: str, remote_folder: str, overwrite: bool = True,
               _retried: bool = False) -> dict:
        self.ensure_session()
        path, ver = self._resolve("SYNO.FileStation.Upload", None)
        lp = Path(local_path)
        if not lp.is_file():
            raise FileNotFoundError(local_path)
        headers = {"X-SYNO-TOKEN": self.synotoken} if self.synotoken else {}
        # The upload CGI ignores identity fields placed inside the multipart body,
        # and format=sid logins set no cookie — api/version/method/_sid must ride
        # the query string or DSM answers 119 (verified on DSM 7.3.1-86003).
        query = {
            "api": "SYNO.FileStation.Upload",
            "version": str(ver),
            "method": "upload",
            "_sid": self.sid,
        }
        fields = {
            "path": remote_folder,
            "create_parents": "true",
            "overwrite": "true" if overwrite else "false",
        }
        try:
            with open(lp, "rb") as fh:
                files = {"file": (lp.name, fh, "application/octet-stream")}
                r = self._http.post(f"{self.base}/{path}", params=query, data=fields,
                                    files=files, headers=headers)
            data = self._parse(r, "SYNO.FileStation.Upload", "upload")
        except DSMError as e:
            if e.code in (105, 106, 107, 119) and not _retried:
                log(f"session error {e.code} on upload; re-authenticating and retrying")
                self.sid = None
                self.synotoken = None
                self.confirm_token = None
                self.login()
                return self.upload(local_path, remote_folder, overwrite, _retried=True)
            raise
        return {"uploaded": lp.name, "to": remote_folder, "result": data}


# --------------------------------------------------------------------------- #
# Server wiring                                                               #
# --------------------------------------------------------------------------- #
mcp = FastMCP("synology")
_client: Optional[DSMClient] = None
_client_lock = threading.Lock()


def client() -> DSMClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = DSMClient(load_config())
        return _client


@atexit.register
def _cleanup() -> None:
    """End the DSM session on shutdown so it doesn't linger until timeout."""
    with _client_lock:
        if _client is not None:
            _client.logout()


def ok(data: Any) -> dict:
    return {"success": True, "data": data}


def err(e: Exception) -> dict:
    return {"success": False, "error": str(e)}


# ---- Generic / discovery -------------------------------------------------- #
@mcp.tool()
def synology_status() -> dict:
    """Connection + DSM identity check. Call this first to confirm the NAS is
    reachable and you're authenticated. Returns model, DSM version, uptime, RAM,
    and the total number of controllable APIs discovered on this box."""
    try:
        c = client()
        c.ensure_session()
        c.discover()
        info = c.call("SYNO.Core.System", "info", 1)
        return ok({
            "reachable": True,
            "host": f"{c.cfg['host']}:{c.cfg['port']}",
            "logged_in_as": c.cfg["username"],
            "model": info.get("model"),
            "serial": info.get("serial"),
            "dsm_version": info.get("firmware_ver"),
            "ram_mb": info.get("ram_size"),
            "uptime_seconds": info.get("up_time"),
            "temperature_c": info.get("sys_temp"),
            "controllable_apis": len(c.api_info),
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_list_apis(filter: str = "", limit: int = 80) -> dict:
    """Search the APIs this NAS exposes (the master list of what can be controlled).
    `filter` is a case-insensitive substring, e.g. "Storage", "Firewall",
    "DownloadStation", "User", "Network.VPN". Returns each API's name, version
    range, and cgi path. Use this to discover the exact api name to pass to
    synology_call. There are ~870 APIs, so always filter."""
    try:
        c = client()
        if not c.api_info:
            c.discover()
        f = filter.lower()
        rows = [
            {"api": k, "minVersion": v.get("minVersion"), "maxVersion": v.get("maxVersion"), "path": v.get("path")}
            for k, v in sorted(c.api_info.items())
            if f in k.lower()
        ]
        total = len(rows)
        return ok({"count": total, "showing": min(total, limit), "apis": rows[:limit]})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_describe_api(names: str) -> dict:
    """Live-probe specific API names (comma-separated) and return their metadata.
    Use for package APIs that don't appear in the global list (e.g. some
    Container Manager / package-specific APIs are only registered on direct query)."""
    try:
        c = client()
        data = c.discover(names=[n.strip() for n in names.split(",") if n.strip()])
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_call(api: str, method: str, version: Optional[int] = None, params: Optional[dict] = None,
                  http_method: str = "POST", elevate: bool = False) -> dict:
    """THE universal tool — call any SYNO.* Web API method on the NAS. This reaches
    every controllable feature, including ones without a curated wrapper.

    - api: e.g. "SYNO.Core.System", "SYNO.Core.Security.Firewall.Rules"
    - method: e.g. "list", "get", "info", "set", "create", "delete", "start", "stop"
    - version: optional; omit to auto-use the API's max version
    - params: dict of extra parameters. Arrays/objects are JSON-encoded automatically,
      e.g. params={"additional": ["email","description"], "type": "local"}

    On error the DSM code is mapped to a message (e.g. 105 = no permission,
    103 = no such method, 102 = api not registered). If unsure of the api name,
    use synology_list_apis first. Destructive methods (delete/format/reboot) act
    immediately — confirm intent with the user before calling them.

    Set elevate=True for sensitive settings that return error 403 (creating/deleting/
    modifying shared folders, share permissions, network config) — this attaches a
    password-confirmation token automatically."""
    try:
        c = client()
        return ok(c.call(api, method, version, params or {}, http_method, elevate=elevate))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_batch(requests: list[dict], mode: str = "sequential") -> dict:
    """Run several API calls in ONE round-trip (compound request). Efficient for
    dashboards/health checks. `requests` is a list of
    {"api","method","version"(opt),"params"(opt)} objects. `mode` is "sequential"
    or "parallel". Returns a list of per-call results in order."""
    try:
        c = client()
        return ok(c.batch(requests, mode))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- System / health ------------------------------------------------------ #
@mcp.tool()
def synology_system_info() -> dict:
    """Full hardware/system info: model, serial, DSM firmware, CPU, RAM, uptime,
    temperature, fan/hardware status."""
    try:
        return ok(client().call("SYNO.Core.System", "info", 1))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_utilization() -> dict:
    """Live resource utilization: CPU load, memory, per-disk and network throughput."""
    try:
        return ok(client().call("SYNO.Core.System.Utilization", "get", 1))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_logs(limit: int = 50) -> dict:
    """Recent system log entries (Log Center) with info/warning/error counts.
    Useful for health checks and diagnosing what went wrong recently."""
    try:
        data = client().call("SYNO.Core.SyslogClient.Log", "list", None,
                             {"offset": 0, "limit": limit})
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_storage() -> dict:
    """Storage overview: volumes (size/used/fs/status), storage pools, and physical
    disks (model, health/SMART status, temperature)."""
    try:
        data = client().call("SYNO.Storage.CGI.Storage", "load_info", 1)
        vols = [
            {
                "id": v.get("id"),
                "fs_type": v.get("fs_type"),
                "status": v.get("status"),
                "total": v.get("size", {}).get("total"),
                "used": v.get("size", {}).get("used"),
            }
            for v in data.get("volumes", [])
        ]
        disks = [
            {
                "id": d.get("id"),
                "model": d.get("model"),
                "status": d.get("status"),
                "temp_c": d.get("temp"),
                "size_bytes": d.get("size_total"),
            }
            for d in data.get("disks", [])
        ]
        return ok({"volumes": vols, "disks": disks, "pools": data.get("storagePools", [])})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_reboot(confirm: bool = False) -> dict:
    """Reboot the NAS. Destructive/disruptive: requires confirm=True. All sessions,
    services and running containers/VMs will be interrupted."""
    if not confirm:
        return {"success": False, "error": "Refused: pass confirm=True to reboot the NAS."}
    try:
        return ok(client().call("SYNO.Core.System", "reboot", 2))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_shutdown(confirm: bool = False) -> dict:
    """Power off the NAS. Destructive: requires confirm=True. You will lose remote
    access until it is physically powered back on."""
    if not confirm:
        return {"success": False, "error": "Refused: pass confirm=True to shut down the NAS."}
    try:
        return ok(client().call("SYNO.Core.System", "shutdown", 2))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Packages / services -------------------------------------------------- #
@mcp.tool()
def synology_packages_list() -> dict:
    """List installed packages (Container Manager, ActiveBackup, DownloadStation,
    VMM, etc.) with their running status and versions."""
    try:
        data = client().call("SYNO.Core.Package", "list", 2, {"additional": ["status"]})
        pkgs = [
            {"id": p.get("id"), "name": p.get("name") or p.get("dname") or p.get("id"),
             "version": p.get("version"), "status": (p.get("additional") or {}).get("status")}
            for p in data.get("packages", [])
        ]
        return ok({"count": len(pkgs), "packages": pkgs})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_services_list() -> dict:
    """List system services and their enabled/running state (SMB, AFP, NFS, FTP,
    SSH, WebDAV, etc.)."""
    try:
        data = client().call("SYNO.Core.Service", "get", 3)
        raw = data.get("service") or data.get("services") or []
        svcs = [
            {"service_id": s.get("service_id"),
             "section": s.get("display_name_section_key"),
             "enabled": s.get("enable_status")}
            for s in raw
        ] if isinstance(raw, list) else raw
        return ok({"count": len(svcs) if isinstance(svcs, list) else None, "services": svcs})
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- FileStation ---------------------------------------------------------- #
@mcp.tool()
def synology_fs_shares() -> dict:
    """List shared folders available through File Station (the top-level roots you
    can browse, e.g. /home, /photo, /music)."""
    try:
        return ok(client().call("SYNO.FileStation.List", "list_share", 2,
                                {"additional": ["real_path", "size", "owner", "perm"]}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_list(folder_path: str, limit: int = 200, sort_by: str = "name") -> dict:
    """List files/folders inside a File Station path, e.g. "/home", "/photo/2024".
    Returns names, whether each is a directory, size and modified time."""
    try:
        data = client().call("SYNO.FileStation.List", "list", 2, {
            "folder_path": folder_path, "limit": limit, "sort_by": sort_by,
            "additional": ["size", "time", "type", "perm"],
        })
        files = [
            {"name": f.get("name"), "path": f.get("path"), "is_dir": f.get("isdir"),
             "size": (f.get("additional") or {}).get("size"),
             "mtime": ((f.get("additional") or {}).get("time") or {}).get("mtime")}
            for f in data.get("files", [])
        ]
        return ok({"path": folder_path, "total": data.get("total"), "files": files})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_search(folder_path: str, pattern: str, limit: int = 100) -> dict:
    """Search for files by name/glob under a folder (recursive). Returns matches."""
    try:
        c = client()
        start = c.call("SYNO.FileStation.Search", "start", 2,
                       {"folder_path": folder_path, "pattern": pattern})
        taskid = start.get("taskid")
        results = {}
        for _ in range(20):
            time.sleep(0.4)
            results = c.call("SYNO.FileStation.Search", "list", 2,
                             {"taskid": taskid, "limit": limit,
                              "additional": ["size", "type"]})
            if results.get("finished"):
                break
        # Best-effort cleanup; a failure here must not discard the results.
        for m in ("stop", "clean"):
            try:
                c.call("SYNO.FileStation.Search", m, 2, {"taskid": taskid})
            except Exception as ce:  # noqa: BLE001
                log(f"search {m} cleanup failed for task {taskid}: {ce}")
        files = [{"name": f.get("name"), "path": f.get("path"), "is_dir": f.get("isdir")}
                 for f in results.get("files", [])]
        return ok({"total": results.get("total"), "files": files})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_download(remote_path: str, save_to: str = "") -> dict:
    """Download a file from the NAS. If save_to is given, streams it to that local
    path; otherwise returns text content (truncated for large files)."""
    try:
        return ok(client().download(remote_path, save_to or None))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_upload(local_path: str, remote_folder: str, overwrite: bool = True) -> dict:
    """Upload a local file to a File Station folder (e.g. remote_folder="/home/uploads").
    Parent folders are created if needed."""
    try:
        return ok(client().upload(local_path, remote_folder, overwrite))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_create_folder(parent_path: str, name: str) -> dict:
    """Create a folder `name` inside `parent_path` (e.g. parent_path="/home", name="backups")."""
    try:
        return ok(client().call("SYNO.FileStation.CreateFolder", "create", 2,
                                {"folder_path": parent_path, "name": name, "force_parent": True}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_delete(paths: list[str], confirm: bool = False) -> dict:
    """Permanently delete file(s)/folder(s) by absolute path. Destructive:
    requires confirm=True. Pass a list, e.g. ["/home/tmp/old.log"]."""
    if not confirm:
        return {"success": False, "error": "Refused: pass confirm=True to delete these paths."}
    try:
        return ok(client().call("SYNO.FileStation.Delete", "delete", 2, {"path": paths}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_rename(path: str, new_name: str) -> dict:
    """Rename a file/folder in place (new_name is just the new basename)."""
    try:
        return ok(client().call("SYNO.FileStation.Rename", "rename", 2,
                                {"path": path, "name": new_name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_fs_copy_move(source_paths: list[str], dest_folder: str, mode: str = "copy",
                          overwrite: bool = False) -> dict:
    """Copy or move files/folders. mode="copy" or "move". Returns a background
    task id; the operation runs server-side."""
    try:
        return ok(client().call("SYNO.FileStation.CopyMove", "start", 3, {
            "path": source_paths, "dest_folder_path": dest_folder,
            "overwrite": overwrite, "remove_src": mode == "move",
        }))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Users / groups / shares ---------------------------------------------- #
@mcp.tool()
def synology_users_list() -> dict:
    """List local user accounts with email, description and expiry status."""
    try:
        data = client().call("SYNO.Core.User", "list", 1,
                             {"type": "local", "additional": ["email", "description", "expired"]})
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_groups_list() -> dict:
    """List local groups and their descriptions."""
    try:
        return ok(client().call("SYNO.Core.Group", "list", 1, {"additional": ["description"]}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_shares_list() -> dict:
    """List shared folders with their volume location, encryption and permission info."""
    try:
        return ok(client().call("SYNO.Core.Share", "list", 1,
                                {"additional": ["volume_status", "hidden", "encryption", "share_quota_status"]}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_snapshots_list(share_name: str) -> dict:
    """List Btrfs snapshots of a shared folder (e.g. share_name="photo").
    Read-only; snapshot create/delete needs the Snapshot Replication package."""
    try:
        return ok(client().call("SYNO.Core.Share.Snapshot", "list", None,
                                {"name": share_name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- DownloadStation ------------------------------------------------------ #
@mcp.tool()
def synology_downloads_list() -> dict:
    """List Download Station tasks (name, status, size, progress, up/down speed)."""
    try:
        data = client().call("SYNO.DownloadStation2.Task", "list", 2,
                             {"additional": ["transfer", "detail"]})
        tasks = []
        for t in data.get("task", []):
            tr = (t.get("additional") or {}).get("transfer") or {}
            tasks.append({
                "id": t.get("id"), "title": t.get("title"), "status": t.get("status"),
                "size": t.get("size"),
                "downloaded": tr.get("size_downloaded"), "uploaded": tr.get("size_uploaded"),
                "down_speed": tr.get("speed_download"), "up_speed": tr.get("speed_upload"),
            })
        return ok({"total": data.get("total"), "tasks": tasks})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_download_add(uri: str, destination: str = "") -> dict:
    """Add a download task from a URL, magnet link, or ftp/thunder link.
    `destination` is an optional share-relative path (e.g. "Downloads")."""
    try:
        params = {"type": "url", "url": [uri], "create_list": False}
        if destination:
            params["destination"] = destination
        return ok(client().call("SYNO.DownloadStation2.Task", "create", 2, params))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_download_control(task_ids: list[str], action: str, confirm: bool = False) -> dict:
    """Control download task(s): action = "pause", "resume", or "delete".
    task_ids is a list of task id strings from synology_downloads_list.
    Deleting removes the tasks from Download Station: requires confirm=True."""
    try:
        c = client()
        if action == "delete":
            if not confirm:
                return {"success": False,
                        "error": "Refused: pass confirm=True to delete these download tasks."}
            return ok(c.call("SYNO.DownloadStation2.Task", "delete", 2,
                             {"id": task_ids, "force_complete": False}))
        if action in ("pause", "resume"):
            return ok(c.call("SYNO.DownloadStation2.Task", action, 2, {"id": task_ids}))
        return {"success": False, "error": "action must be pause, resume, or delete"}
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Container Manager (Docker) ------------------------------------------- #
# Note: these require the ContainerManager package to be RUNNING; otherwise the
# SYNO.Docker.* APIs are unregistered (error 102). Check with synology_packages_list
# and start it via synology_package_control(package_id="ContainerManager", action="start").
@mcp.tool()
def synology_containers_list() -> dict:
    """List Docker containers (Container Manager): name, image, and status
    (running/stopped). Requires Container Manager running."""
    try:
        data = client().call("SYNO.Docker.Container", "list", 1, {"limit": 500, "offset": 0})
        conts = [
            {"name": x.get("name"), "image": x.get("image"), "status": x.get("status"),
             "id": x.get("id")}
            for x in data.get("containers", [])
        ]
        return ok({"total": data.get("total", len(conts)), "containers": conts})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_inspect(name: str) -> dict:
    """Full configuration/profile of one container (image, env, ports, volumes,
    restart policy, etc.). Useful as a template before creating a similar one."""
    try:
        return ok(client().call("SYNO.Docker.Container", "get", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_logs(name: str) -> dict:
    """Fetch a container's recent logs."""
    try:
        return ok(client().call("SYNO.Docker.Container", "get_log", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_stats(name: str) -> dict:
    """Live resource usage (CPU/memory/network) for a running container."""
    try:
        return ok(client().call("SYNO.Docker.Container.Resource", "get", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_start(name: str) -> dict:
    """Start a stopped container by name."""
    try:
        return ok(client().call("SYNO.Docker.Container", "start", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_stop(name: str, confirm: bool = False) -> dict:
    """Stop a running container by name. Disruptive to whatever it serves:
    requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to stop container '{name}'."}
    try:
        return ok(client().call("SYNO.Docker.Container", "stop", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_restart(name: str, confirm: bool = False) -> dict:
    """Restart a container by name. Briefly interrupts its service: requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to restart container '{name}'."}
    try:
        return ok(client().call("SYNO.Docker.Container", "restart", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_delete(name: str, confirm: bool = False) -> dict:
    """Delete/remove a container by name. Destructive: requires confirm=True.
    (Does not remove the underlying image or named volumes.)"""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to delete container '{name}'."}
    try:
        return ok(client().call("SYNO.Docker.Container", "delete", 1, {"name": name}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_container_create(name: str, image: str, settings: Optional[dict] = None) -> dict:
    """Create/deploy a new container from an image. `settings` is merged into the
    create request for advanced options (ports, volumes, env, network, restart
    policy). For anything non-trivial, prefer a Compose project
    (synology_project_create) or copy a profile from synology_container_inspect.
    The image must already be present — pull it first with synology_image_pull."""
    try:
        params = {"name": name, "image": image}
        params.update(settings or {})
        return ok(client().call("SYNO.Docker.Container", "create", 1, params))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_images_list() -> dict:
    """List Docker images present on the NAS (repository, tags, size)."""
    try:
        data = client().call("SYNO.Docker.Image", "list", 1, {"limit": 500, "offset": 0})
        imgs = [
            {"repository": i.get("repository"), "tags": i.get("tags"), "size": i.get("size"),
             "id": i.get("id")}
            for i in data.get("images", [])
        ]
        return ok({"total": data.get("total", len(imgs)), "images": imgs})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_image_pull(repository: str, tag: str = "latest") -> dict:
    """Pull (download) a Docker image, e.g. repository="nginx", tag="latest", or
    repository="ghcr.io/owner/app", tag="v1". Runs asynchronously on the NAS;
    check progress with synology_images_list once it finishes."""
    try:
        return ok(client().call("SYNO.Docker.Image", "pull_start", 1,
                                {"repository": repository, "tag": tag}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_image_remove(reference: str, confirm: bool = False) -> dict:
    """Delete a Docker image by reference (e.g. "nginx:latest"). Destructive:
    requires confirm=True. Fails if a container still uses it."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to remove image '{reference}'."}
    try:
        return ok(client().call("SYNO.Docker.Image", "delete", 1, {"reference": reference}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_projects_list() -> dict:
    """List Container Manager Compose projects (multi-container stacks) with their
    status and member containers."""
    try:
        data = client().call("SYNO.Docker.Project", "list", 1, {})
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_project_inspect(project_id: str) -> dict:
    """Show a Compose project's definition and current state."""
    try:
        return ok(client().call("SYNO.Docker.Project", "get", 1, {"id": project_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_project_start(project_id: str) -> dict:
    """Start (compose up) all services in a Compose project."""
    try:
        return ok(client().call("SYNO.Docker.Project", "start", 1, {"id": project_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_project_stop(project_id: str, confirm: bool = False) -> dict:
    """Stop (compose down) all services in a Compose project. Disruptive:
    requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to stop project '{project_id}'."}
    try:
        return ok(client().call("SYNO.Docker.Project", "stop", 1, {"id": project_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_project_create(name: str, compose_yaml: str, share_path: str = "") -> dict:
    """Deploy a new Compose project (multi-container stack) from a docker-compose
    YAML string. `share_path` is where the project files live (e.g. "/docker/myapp").
    This is the recommended way to deploy anything beyond a single container."""
    try:
        params = {"name": name, "content": compose_yaml}
        if share_path:
            params["share_path"] = share_path
        return ok(client().call("SYNO.Docker.Project", "create", 1, params))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_project_delete(project_id: str, confirm: bool = False) -> dict:
    """Delete a Compose project. Destructive: requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to delete project '{project_id}'."}
    try:
        return ok(client().call("SYNO.Docker.Project", "delete", 1, {"id": project_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Package lifecycle & app deployment ----------------------------------- #
@mcp.tool()
def synology_package_control(package_id: str, action: str, confirm: bool = False) -> dict:
    """Start or stop an installed package/app (e.g. "ContainerManager",
    "DownloadStation", "WebStation"). action="start" or "stop". Stopping a package
    disrupts its service, so action="stop" requires confirm=True."""
    if action not in ("start", "stop"):
        return {"success": False, "error": 'action must be "start" or "stop"'}
    if action == "stop" and not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to stop package '{package_id}'."}
    try:
        return ok(client().call("SYNO.Core.Package.Control", action, 1, {"id": package_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_package_uninstall(package_id: str, confirm: bool = False) -> dict:
    """Uninstall a package. Destructive (removes the app; may remove its data):
    requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to uninstall '{package_id}'."}
    try:
        return ok(client().call("SYNO.Core.Package.Uninstallation", "uninstall", 1, {"id": package_id}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_package_available() -> dict:
    """List packages available to install from Synology's package server (the online
    Package Center catalog) — names, versions, and descriptions."""
    try:
        return ok(client().call("SYNO.Core.Package.Server", "list", 2,
                                {"blforcereload": False, "blloadothers": True}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- DSM updates ---------------------------------------------------------- #
@mcp.tool()
def synology_dsm_update_check() -> dict:
    """Check whether a DSM (operating system) update is available, and report the
    current update status."""
    try:
        c = client()
        avail = c.call("SYNO.Core.Upgrade.Server", "check", 1)
        status = c.call("SYNO.Core.Upgrade", "status", 1)
        return ok({"available_update": avail.get("update"), "status": status})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_dsm_update_apply(confirm: bool = False) -> dict:
    """Install a pending DSM update and REBOOT the NAS. Highly disruptive and only
    partially reversible: requires confirm=True. Ensure an update was found by
    synology_dsm_update_check first, and that no critical jobs are running. You will
    lose access to the NAS for several minutes while it reboots."""
    if not confirm:
        return {"success": False,
                "error": "Refused: pass confirm=True to install a DSM update and reboot the NAS. "
                         "Run synology_dsm_update_check first and confirm with the user."}
    try:
        return ok(client().call("SYNO.Core.Upgrade", "start", 1, {}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Shared folders (write; needs elevation) ------------------------------ #
@mcp.tool()
def synology_share_create(name: str, volume_path: str = "/volume1", description: str = "",
                          hidden: bool = False, enable_recycle_bin: bool = True,
                          confirm: bool = False) -> dict:
    """Create a new shared folder. volume_path like "/volume1" or "/volume2".
    Requires confirm=True (creates real storage config). Uses password-confirm
    elevation automatically."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to create share '{name}'."}
    try:
        shareinfo = {
            "name": name, "vol_path": volume_path, "desc": description,
            "enable_share_compress": False, "enable_recycle_bin": enable_recycle_bin,
            "enable_share_cow": False, "hidden": hidden,
        }
        return ok(client().call("SYNO.Core.Share", "create", 1,
                                {"name": name, "shareinfo": shareinfo}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_share_delete(name: str, confirm: bool = False) -> dict:
    """Delete a shared folder AND its contents. Destructive: requires confirm=True.
    Uses password-confirm elevation."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to DELETE share '{name}' and its data."}
    try:
        return ok(client().call("SYNO.Core.Share", "delete", 1, {"name": name}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_share_set_permissions(share_name: str, permissions: list[dict],
                                   confirm: bool = False) -> dict:
    """Set per-user permissions on a shared folder. `permissions` is a list of
    objects like {"name":"poomonkey405","is_writable":true} /
    {"name":"guest","is_readonly":true} / {"name":"someone","is_deny":true}.
    Requires confirm=True. Uses password-confirm elevation."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to change permissions on '{share_name}'."}
    try:
        norm = []
        for p in permissions:
            norm.append({
                "name": p["name"],
                "is_readonly": bool(p.get("is_readonly", False)),
                "is_writable": bool(p.get("is_writable", False)),
                "is_deny": bool(p.get("is_deny", False)),
                "is_custom": bool(p.get("is_custom", False)),
            })
        return ok(client().call("SYNO.Core.Share.Permission", "set", 1,
                                {"name": share_name, "user_group_type": "local_user",
                                 "permissions": norm}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_network_set_dns(dns_primary: str, dns_secondary: str = "",
                             confirm: bool = False) -> dict:
    """Set the NAS's DNS server(s). Requires confirm=True (can affect connectivity).
    Uses password-confirm elevation."""
    if not confirm:
        return {"success": False, "error": "Refused: pass confirm=True to change DNS settings."}
    try:
        params = {"dns_primary": dns_primary, "dns_manual": True}
        if dns_secondary:
            params["dns_secondary"] = dns_secondary
        return ok(client().call("SYNO.Core.Network", "set", 1, params, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Users & groups (write) ----------------------------------------------- #
@mcp.tool()
def synology_user_create(name: str, password: str, description: str = "", email: str = "",
                         confirm: bool = False) -> dict:
    """Create a local user account. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to create user '{name}'."}
    try:
        params = {"name": name, "password": password, "description": description,
                  "email": email, "cannot_chg_passwd": False, "passwd_never_expire": True,
                  "notify_by_email": False, "send_password": False}
        return ok(client().call("SYNO.Core.User", "create", 1, params, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_user_modify(name: str, changes: dict, confirm: bool = False) -> dict:
    """Modify a user. `changes` may include description, email, expired ("normal"/
    "now"), cannot_chg_passwd, passwd_never_expire. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to modify user '{name}'."}
    try:
        params = {"name": name}
        params.update(changes or {})
        return ok(client().call("SYNO.Core.User", "set", 1, params, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_user_set_password(name: str, new_password: str, confirm: bool = False) -> dict:
    """Set/reset a user's password. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to reset the password for '{name}'."}
    try:
        return ok(client().call("SYNO.Core.User", "set", 1,
                                {"name": name, "password": new_password}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_user_delete(name: str, confirm: bool = False) -> dict:
    """Delete a local user account. Destructive: requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to delete user '{name}'."}
    try:
        return ok(client().call("SYNO.Core.User", "delete", 1, {"name": [name]}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_group_create(name: str, description: str = "", confirm: bool = False) -> dict:
    """Create a local group. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to create group '{name}'."}
    try:
        return ok(client().call("SYNO.Core.Group", "create", 1,
                                {"name": name, "description": description}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_group_delete(name: str, confirm: bool = False) -> dict:
    """Delete a local group. Destructive: requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to delete group '{name}'."}
    try:
        return ok(client().call("SYNO.Core.Group", "delete", 1, {"name": [name]}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_group_add_members(group: str, users: list[str], confirm: bool = False) -> dict:
    """Add local user(s) to a group. Requires confirm=True."""
    if not confirm:
        return {"success": False, "error": f"Refused: pass confirm=True to modify group '{group}'."}
    try:
        return ok(client().call("SYNO.Core.Group.Member", "add", 1,
                                {"name": group, "add_members": users}, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Task Scheduler & firewall -------------------------------------------- #
@mcp.tool()
def synology_scheduler_list() -> dict:
    """List scheduled tasks (Control Panel > Task Scheduler): scripts, scheduled
    backups, etc., with their trigger and enabled state. Note: use version 3 of the
    API — the max version does not support list."""
    try:
        data = client().call("SYNO.Core.TaskScheduler", "list", 3, {"offset": 0, "limit": 200})
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_firewall_status() -> dict:
    """Show whether the firewall is enabled and which profile is active, plus the
    available profiles."""
    try:
        c = client()
        fw = c.call("SYNO.Core.Security.Firewall", "get", 1)
        prof = c.call("SYNO.Core.Security.Firewall.Profile", "list", 1)
        return ok({"enabled": fw.get("enable_firewall"), "active_profile": fw.get("profile_name"),
                   "profiles": prof.get("profile_names")})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_firewall_set_enabled(enable: bool, confirm: bool = False) -> dict:
    """Enable or disable the firewall (keeps the current active profile). Can lock
    you out of the NAS if the active profile blocks your access — requires
    confirm=True and uses password-confirm elevation. Check synology_firewall_status
    first."""
    if not confirm:
        return {"success": False, "error": "Refused: pass confirm=True to change the firewall state (lock-out risk)."}
    try:
        c = client()
        cur = c.call("SYNO.Core.Security.Firewall", "get", 1)
        params = {"enable_firewall": enable, "profile_name": cur.get("profile_name", "default")}
        return ok(c.call("SYNO.Core.Security.Firewall", "set", 1, params, elevate=True))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_firewall_rules() -> dict:
    """List firewall rules for every firewall profile (read-only). For each profile it
    returns the global default policy and the ordered rule list (per-rule action, ports,
    protocol, source IP). Editing rules is high-risk (a wrong rule can lock you out of
    the NAS) and is intentionally NOT a curated tool — after reading this, make edits
    deliberately via synology_call on SYNO.Core.Security.Firewall / .Profile with the
    user's explicit go-ahead. Rules are read via SYNO.Core.Security.Firewall.Profile.get
    (v1), which embeds the rule list under `global.rules`."""
    try:
        c = client()
        prof = c.call("SYNO.Core.Security.Firewall.Profile", "list", 1)
        names = [p.get("name") if isinstance(p, dict) else p
                 for p in prof.get("profile_names", [])]
        profiles = []
        for nm in names:
            if not nm:
                continue
            d = c.call("SYNO.Core.Security.Firewall.Profile", "get", 1, {"name": nm})
            g = d.get("global") or {}
            profiles.append({
                "name": d.get("name") or nm,
                "default_policy": g.get("policy"),
                "rules": g.get("rules", []),
            })
        return ok({"count": len(profiles), "profiles": profiles})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_autoblock_list(list_type: str = "deny", limit: int = 200) -> dict:
    """Auto-block (Control Panel > Security > Protection) state: the config (enabled,
    failed-login `attempts` threshold, `within_mins` window, `expire_day` block
    duration) plus the IP list. list_type="deny" returns the blocked IPs (default);
    "allow" returns the allow-list. Read-only. Reads
    SYNO.Core.Security.AutoBlock.get (config) and
    SYNO.Core.Security.AutoBlock.Rules.list with type=deny|allow (v1)."""
    if list_type not in ("deny", "allow"):
        return {"success": False, "error": 'list_type must be "deny" or "allow"'}
    try:
        c = client()
        cfg = c.call("SYNO.Core.Security.AutoBlock", "get", 1)
        rules = c.call("SYNO.Core.Security.AutoBlock.Rules", "list", 1,
                       {"offset": 0, "limit": limit, "type": list_type})
        return ok({"config": cfg, "list_type": list_type,
                   "total": rules.get("total"), "ip_info": rules.get("ip_info", [])})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_autoblock_manage(action: str, ips: list[str], list_type: str = "deny",
                              confirm: bool = False) -> dict:
    """Add or remove IP addresses in the auto-block block/allow list. action="add" or
    "remove"; list_type="deny" (block list) or "allow" (allow list); ips is a list of
    IP strings (e.g. ["203.0.113.5"]). Security-affecting write — a stray allow entry
    weakens protection and a wrong block entry can cut off a host: requires confirm=True.
    Verify the current list first with synology_autoblock_list. (The read side of
    SYNO.Core.Security.Firewall/AutoBlock is verified live; the add/remove methods on
    SYNO.Core.Security.AutoBlock.Rules follow DSM's own UI convention and are gated —
    read back with synology_autoblock_list after applying to confirm the change.)"""
    if action not in ("add", "remove"):
        return {"success": False, "error": 'action must be "add" or "remove"'}
    if list_type not in ("deny", "allow"):
        return {"success": False, "error": 'list_type must be "deny" or "allow"'}
    if not confirm:
        return {"success": False,
                "error": f"Refused: pass confirm=True to {action} {ips} in the auto-block "
                         f"{list_type} list."}
    try:
        return ok(client().call("SYNO.Core.Security.AutoBlock.Rules", action, 1,
                                {"type": list_type, "ip_list": ips}))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Certificates & power hardware (read) --------------------------------- #
@mcp.tool()
def synology_certificates_list() -> dict:
    """List DSM certificates (Control Panel > Security > Certificate): each cert's id,
    description, subject/issuer common name, validity window (valid_from/valid_till),
    signature algorithm, and whether it's the default, broken, renewable, or
    user-deletable, plus which services use it. Read-only
    (SYNO.Core.Certificate.CRT.list, v1)."""
    try:
        data = client().call("SYNO.Core.Certificate.CRT", "list", 1)
        certs = [
            {
                "id": x.get("id"),
                "desc": x.get("desc"),
                "is_default": x.get("is_default"),
                "is_broken": x.get("is_broken"),
                "renewable": x.get("renewable"),
                "user_deletable": x.get("user_deletable"),
                "signature_algorithm": x.get("signature_algorithm"),
                "subject_cn": (x.get("subject") or {}).get("common_name"),
                "issuer_cn": (x.get("issuer") or {}).get("common_name"),
                "valid_from": x.get("valid_from"),
                "valid_till": x.get("valid_till"),
                "services": [s.get("display_name") for s in (x.get("services") or [])],
            }
            for x in data.get("certificates", [])
        ]
        return ok({"count": len(certs), "certificates": certs})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_ups_status() -> dict:
    """UPS (uninterruptible power supply) status & settings: whether UPS support is
    enabled, mode (master/slave/network), battery charge %, estimated runtime, the
    low-battery safe-shutdown behavior, and any network-UPS server IP. Read-only
    (SYNO.Core.ExternalDevice.UPS.get, v1). `enable=false` means no UPS is attached
    or configured on this NAS."""
    try:
        return ok(client().call("SYNO.Core.ExternalDevice.UPS", "get", 1))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ---- Backups (Hyper Backup + Active Backup for Business) ------------------- #
# API method/param shapes reverse-engineered from the DSM web UI's own traffic.
# Note the version: these list methods live at v1, not the API's max version.
@mcp.tool()
def synology_backup_hyper_tasks() -> dict:
    """List Hyper Backup tasks (backup jobs to local/external/cloud/C2 targets) with
    each task's last backup time and result. Returns an empty list if no Hyper
    Backup tasks are configured."""
    try:
        data = client().call("SYNO.Backup.Task", "list", 1, {
            "node": "module_root", "sort_by": "name",
            "additional": ["last_bkp_time", "last_bkp_result", "get_source", "is_modified"],
        })
        tasks = data.get("task_list", [])
        return ok({"total": data.get("total", len(tasks)),
                   "is_restoring": data.get("is_restoring"),
                   "is_downloading": data.get("is_downloading"),
                   "tasks": tasks})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_backup_active_devices(backup_type: Optional[int] = None) -> dict:
    """List Active Backup for Business protected devices/tasks (Synology NAS, PC/Mac,
    physical & file servers, VMs) with their last backup result. Optional
    backup_type filters by category (e.g. 2 = PC/Mac); omit for all devices."""
    try:
        params = {"load_result": True}
        if backup_type is not None:
            params["filter"] = {"load_available": True, "backup_type": backup_type}
        data = client().call("SYNO.ActiveBackup.Device", "list", 1, params)
        devs = data.get("devices", [])
        return ok({"total": data.get("total", len(devs)),
                   "total_of_type": data.get("total_devices_of_backup_type"),
                   "devices": devs})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def synology_backup_active_logs(limit: int = 50) -> dict:
    """Recent Active Backup for Business activity/log entries (backup runs, errors,
    completions)."""
    try:
        data = client().call("SYNO.ActiveBackup.Log", "list_log", 1,
                             {"offset": 0, "limit": limit, "filter": {}})
        return ok({"count": data.get("count"), "logs": data.get("logs", [])})
    except Exception as e:  # noqa: BLE001
        return err(e)


if __name__ == "__main__":
    log(f"starting; config target = {load_config().get('host') or '(unset)'}")
    mcp.run()
