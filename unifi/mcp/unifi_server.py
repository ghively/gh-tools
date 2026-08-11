#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""UniFi Network (UniFi OS) MCP server.

Exposes a Ubiquiti UniFi console to Claude through the Model Context Protocol.
Tested against a UniFi Dream Router 7 (UDR7) running UniFi OS 4.x with the
Network application 10.4.x. The design is two-layered, mirroring the Synology
plugin in this repo:

* A GENERIC passthrough (`unifi_call` / `unifi_list_endpoints`) that can reach
  *any* Network endpoint across all three API surfaces UniFi OS exposes — the
  classic v1 API (`/proxy/network/api/s/{site}/...`), the newer v2 API
  (`/proxy/network/v2/api/site/{site}/...`), and the UniFi OS host API
  (`/api/...`). This is what makes "control everything" true rather than
  aspirational.
* CURATED tools for the common jobs (health, devices, clients, networks, WLANs,
  firewall, port-forwards, events, statistics) so day-to-day tasks are one call.

Auth model (proven live): POST /api/auth/login {username,password} sets a TOKEN
JWT cookie; the CSRF token is the `csrfToken` claim inside that JWT (and is also
returned as the X-Updated-Csrf-Token response header). It must be sent as the
`X-Csrf-Token` header on every mutating (POST/PUT/DELETE) request, or the box
returns HTTP 403 Forbidden. The classic API wraps results as
{"meta": {"rc": "ok"|"error", "msg": "api.err.X"}, "data": [...]}.

All logging goes to stderr; stdout is reserved for the MCP protocol.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP


def log(*a: Any) -> None:
    print("[unifi-mcp]", *a, file=sys.stderr, flush=True)


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
    if os.environ.get("UNIFI_CONFIG"):
        candidates.append(Path(os.environ["UNIFI_CONFIG"]))
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
        "host": env.get("UNIFI_HOST", cfg.get("host", "")),
        "port": int(env.get("UNIFI_PORT", cfg.get("port", 443)) or 443),
        "https": _truthy(env.get("UNIFI_HTTPS"), cfg.get("https", True)),
        "username": env.get("UNIFI_USERNAME", cfg.get("username", "")),
        "password": env.get("UNIFI_PASSWORD", cfg.get("password", "")),
        "api_key": env.get("UNIFI_API_KEY", cfg.get("api_key", "")),
        "site": env.get("UNIFI_SITE", cfg.get("site", "default")),
        "verify_ssl": _truthy(env.get("UNIFI_VERIFY_SSL"), cfg.get("verify_ssl", False)),
        "timeout": float(env.get("UNIFI_TIMEOUT", cfg.get("timeout", 30)) or 30),
    }
    return out


# --------------------------------------------------------------------------- #
# UniFi error vocabulary                                                      #
# --------------------------------------------------------------------------- #
# The classic API signals failure with meta.rc == "error" and a symbolic
# meta.msg like "api.err.NoSiteContext". These are the ones seen in the wild;
# unknown codes are passed through verbatim so nothing is hidden.
API_ERR_HELP = {
    "api.err.Invalid": "Invalid parameters for this method.",
    "api.err.InvalidObject": "The request body/params were rejected (wrong shape).",
    "api.err.LoginRequired": "Not authenticated — session expired or missing.",
    "api.err.NoSiteContext": "The site does not exist or is not in context.",
    "api.err.ApGroupMissing": "This WLAN write needs an ap_group_ids array.",
    "api.err.NoPermission": "The logged-in account lacks permission for this.",
    "api.err.IdInvalid": "The object _id in the path/body does not exist.",
}


class UniFiError(RuntimeError):
    def __init__(self, msg: str, http_status: int = 0, path: str = ""):
        self.rc_msg = msg
        self.http_status = http_status
        help_txt = API_ERR_HELP.get(msg, "")
        ctx = f" [{path}]" if path else ""
        detail = f" — {help_txt}" if help_txt else ""
        http = f" (HTTP {http_status})" if http_status else ""
        super().__init__(f"UniFi error: {msg}{http}{detail}{ctx}")


# --------------------------------------------------------------------------- #
# UniFi client                                                                #
# --------------------------------------------------------------------------- #
class UniFiClient:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        scheme = "https" if cfg["https"] else "http"
        port = cfg["port"]
        # Omit :443 for tidy URLs; keep explicit ports otherwise.
        host = cfg["host"]
        if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
            self.origin = f"{scheme}://{host}"
        else:
            self.origin = f"{scheme}://{host}:{port}"
        self._http = httpx.Client(
            verify=cfg["verify_ssl"],
            timeout=cfg["timeout"],
            follow_redirects=False,
        )
        self.csrf: Optional[str] = None
        self.logged_in = False
        self._lock = threading.RLock()

    # -- prefixes --------------------------------------------------------- #
    @property
    def site(self) -> str:
        return self.cfg.get("site") or "default"

    def _v1(self, site: Optional[str] = None) -> str:
        return f"/proxy/network/api/s/{site or self.site}"

    def _v2(self, site: Optional[str] = None) -> str:
        return f"/proxy/network/v2/api/site/{site or self.site}"

    # -- auth ------------------------------------------------------------- #
    @staticmethod
    def _csrf_from_jwt(token: str) -> Optional[str]:
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("csrfToken")
        except Exception:  # noqa: BLE001
            return None

    def _refresh_csrf(self, r: httpx.Response) -> None:
        # UniFi OS rotates/echoes the CSRF token on responses; keep the latest.
        for h in ("x-updated-csrf-token", "x-csrf-token"):
            if h in r.headers:
                self.csrf = r.headers[h]
                return
        tok = self._http.cookies.get("TOKEN")
        if tok:
            c = self._csrf_from_jwt(tok)
            if c:
                self.csrf = c

    def login(self) -> dict:
        cfg = self.cfg
        if not cfg["host"]:
            raise UniFiError("api.err.LoginRequired", path="config: host is empty")
        r = self._http.post(
            f"{self.origin}/api/auth/login",
            json={"username": cfg["username"], "password": cfg["password"],
                  "rememberMe": False},
        )
        if r.status_code != 200:
            body = r.text[:200]
            raise UniFiError("api.err.LoginRequired", r.status_code,
                             f"login failed: {body}")
        self._refresh_csrf(r)
        self.logged_in = True
        try:
            who = r.json()
        except Exception:  # noqa: BLE001
            who = {}
        log(f"logged in as {cfg['username']} "
            f"(csrf {'ok' if self.csrf else 'none'})")
        return {"username": who.get("username"), "full_name": who.get("full_name"),
                "roles": [ro.get("system_key") for ro in who.get("roles", [])]}

    def ensure_session(self) -> None:
        with self._lock:
            if not self.logged_in:
                self.login()

    def logout(self) -> None:
        if not self.logged_in:
            return
        try:
            self._http.post(f"{self.origin}/api/auth/logout",
                            headers=self._headers(mutating=True))
        except Exception:  # noqa: BLE001
            pass
        self.logged_in = False
        self.csrf = None

    # -- core call -------------------------------------------------------- #
    def _headers(self, mutating: bool) -> dict:
        h = {"Accept": "application/json"}
        if self.cfg.get("api_key"):
            h["X-API-KEY"] = self.cfg["api_key"]
        if mutating and self.csrf:
            h["X-Csrf-Token"] = self.csrf
        return h

    def _parse(self, r: httpx.Response, path: str) -> Any:
        self._refresh_csrf(r)
        # Non-2xx: try to surface the symbolic error, else raw text.
        text = r.text
        body: Any = None
        if text:
            try:
                body = r.json()
            except Exception:  # noqa: BLE001
                body = None
        if isinstance(body, dict) and isinstance(body.get("meta"), dict):
            meta = body["meta"]
            if meta.get("rc") == "error":
                raise UniFiError(meta.get("msg", "unknown"), r.status_code, path)
            # classic wrapper: unwrap data
            if r.status_code < 400:
                return body.get("data", body)
        if r.status_code >= 400:
            msg = ""
            if isinstance(body, dict):
                msg = (body.get("message") or body.get("error")
                       or (body.get("meta") or {}).get("msg") or "")
            raise UniFiError(msg or f"HTTP {r.status_code}", r.status_code, path)
        # v2 / host API: return JSON as-is (may be dict or list).
        if body is not None:
            return body
        return {"raw": text[:2000]} if text else {}

    def call(
        self,
        path: str,
        method: str = "GET",
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        _retried: bool = False,
    ) -> Any:
        """Raw request against an absolute UniFi OS path (must start with '/').

        `path` is anything under the console origin, e.g.
        '/proxy/network/api/s/default/stat/health' or
        '/proxy/network/v2/api/site/default/trafficrules' or '/api/system'.
        """
        self.ensure_session()
        if not path.startswith("/"):
            path = "/" + path
        mutating = method.upper() != "GET"
        url = f"{self.origin}{path}"
        try:
            r = self._http.request(
                method.upper(), url,
                params=params or None,
                json=json_body if mutating else None,
                headers=self._headers(mutating),
            )
            # A rotated/expired session shows up as 401; re-auth once.
            if r.status_code == 401 and not _retried:
                log("401 — re-authenticating and retrying once")
                self.logged_in = False
                self.csrf = None
                self.login()
                return self.call(path, method, params, json_body, _retried=True)
            return self._parse(r, path)
        except httpx.HTTPError as e:
            raise UniFiError(f"transport error: {e}", path=path)

    # Convenience wrappers around the three surfaces.
    def v1(self, sub: str, method: str = "GET", params: Optional[dict] = None,
           json_body: Optional[dict] = None) -> Any:
        return self.call(f"{self._v1()}/{sub.lstrip('/')}", method, params, json_body)

    def v2(self, sub: str, method: str = "GET", params: Optional[dict] = None,
           json_body: Optional[dict] = None) -> Any:
        return self.call(f"{self._v2()}/{sub.lstrip('/')}", method, params, json_body)

    def cmd(self, mgr: str, payload: dict) -> Any:
        """Classic action endpoint: POST /api/s/{site}/cmd/{mgr} {cmd, ...}."""
        return self.v1(f"cmd/{mgr}", "POST", json_body=payload)


# --------------------------------------------------------------------------- #
# Endpoint catalog (enumerated from the live UDR7's own UI bundles + probes)  #
# Used by unifi_list_endpoints so the model can discover the passthrough      #
# surface the same way synology_list_apis works.                              #
# --------------------------------------------------------------------------- #
ENDPOINT_CATALOG = [
    # (relative-path-under-site, surface, methods, description)
    ("stat/health", "v1", "GET", "Per-subsystem health (wlan/wan/lan/www/vpn)"),
    ("stat/sysinfo", "v1", "GET", "Controller/site system info"),
    ("stat/device", "v1", "GET/POST", "Full UniFi device (AP/switch/gateway) state"),
    ("stat/device-basic", "v1", "GET", "Lightweight device list (mac/state/model)"),
    ("stat/sta", "v1", "GET", "Active clients (stations) currently connected"),
    ("stat/guest", "v1", "GET", "Guest/hotspot authorizations"),
    ("stat/rogueap", "v1", "GET", "Neighboring/rogue APs seen in scans"),
    ("stat/spectrum-scan", "v1", "GET", "RF spectrum scan results (per AP)"),
    ("stat/current-channel", "v1", "GET", "Allowed/used radio channels"),
    ("stat/ccode", "v1", "GET", "Country codes"),
    ("stat/portforward", "v1", "GET", "Active port-forward state"),
    ("stat/report/{interval}.{scope}", "v1", "GET/POST",
     "Time-series stats; interval=5minutes|hourly|daily, scope=site|ap|user|gw"),
    ("stat/sdn", "v1", "GET", "Cloud (SDN/UI account) status"),
    ("stat/fwupdate/latest-version", "v1", "GET", "Latest firmware availability"),
    ("rest/user", "v1", "GET/POST/PUT/DELETE", "Known clients (user objects)"),
    ("rest/usergroup", "v1", "GET/POST/PUT/DELETE", "Client bandwidth groups"),
    ("rest/device", "v1", "GET/PUT", "UniFi device config (per _id)"),
    ("rest/networkconf", "v1", "GET/POST/PUT/DELETE", "Networks / VLANs / WAN"),
    ("rest/wlanconf", "v1", "GET/POST/PUT/DELETE", "Wireless networks (SSIDs)"),
    ("rest/firewallrule", "v1", "GET/POST/PUT/DELETE", "Firewall rules (classic)"),
    ("rest/firewallgroup", "v1", "GET/POST/PUT/DELETE", "Firewall address/port groups"),
    ("rest/portforward", "v1", "GET/POST/PUT/DELETE", "Port-forwarding rules"),
    ("rest/routing", "v1", "GET/POST/PUT/DELETE", "Static routes"),
    ("rest/dhcpoption", "v1", "GET/POST/PUT/DELETE", "Custom DHCP options"),
    ("rest/dynamicdns", "v1", "GET/POST/PUT/DELETE", "Dynamic DNS configs"),
    ("rest/dpiapp", "v1", "GET/POST/PUT/DELETE", "DPI application filters"),
    ("rest/dpigroup", "v1", "GET/POST/PUT/DELETE", "DPI groups"),
    ("rest/portconf", "v1", "GET/POST/PUT/DELETE", "Switch port profiles"),
    ("rest/scheduletask", "v1", "GET/POST/PUT/DELETE", "Scheduled tasks"),
    ("rest/account", "v1", "GET/POST/PUT/DELETE", "RADIUS accounts"),
    ("rest/hotspotop", "v1", "GET/POST/PUT/DELETE", "Hotspot operators"),
    ("rest/hotspotpackage", "v1", "GET/POST/PUT/DELETE", "Hotspot packages"),
    ("rest/setting", "v1", "GET", "All site settings (grouped by key)"),
    ("set/setting/{key}", "v1", "POST", "Write a settings section by key"),
    ("list/alarm", "v1", "GET/POST", "Alarms (unarchived by default)"),
    ("cmd/stamgr", "v1", "POST",
     "Client actions: block-sta, unblock-sta, kick-sta, authorize-guest, unauthorize-guest, forget-sta"),
    ("cmd/devmgr", "v1", "POST",
     "Device actions: restart, force-provision, set-locate, unset-locate, adopt, speedtest, speedtest-status, upgrade, power-cycle (PoE port)"),
    ("cmd/firewall", "v1", "POST", "Firewall manager actions"),
    ("cmd/backup", "v1", "POST", "Backup: list-backups, delete-backup, etc."),
    ("cmd/system", "v1", "POST", "System-level commands"),
    ("cmd/sitemgr", "v1", "POST", "Site management: add-site, update-site, delete-site"),
    ("cmd/hotspot", "v1", "POST", "Hotspot/voucher actions"),
    ("cmd/cfgmgr", "v1", "POST", "Config manager"),
    ("stat/voucher", "v1", "GET", "Hotspot vouchers"),
    # ---- v2 API ---- #
    ("clients/active", "v2", "GET", "Active clients (v2 richer shape)"),
    ("clients/history", "v2", "GET", "Historical/known clients (v2)"),
    ("trafficrules", "v2", "GET/POST/PUT/DELETE", "Traffic rules (block/allow by app/domain)"),
    ("trafficroutes", "v2", "GET/POST/PUT/DELETE", "Policy-based traffic routes (VPN/WAN steering)"),
    ("firewall-policies", "v2", "GET/POST/PUT/DELETE", "Zone-based firewall policies (new UI)"),
    ("firewall/zone", "v2", "GET/POST/PUT/DELETE", "Firewall zones (curated: unifi_firewall_zones)"),
    ("system-log/all", "v2", "POST", "Unified system log / events (paged)"),
    ("wifi-connectivity", "v2", "GET", "Wi-Fi connect-quality diagnostics (curated: unifi_wifi_connectivity)"),
    ("aggregated-dashboard", "v2", "GET", "Rich overview snapshot (curated: unifi_dashboard)"),
    ("device-tags", "v2", "GET/POST/PUT/DELETE", "Device tags"),
    ("sites/overview", "v2", "GET", "Overview across all sites"),
    ("port-forwarding", "v2", "GET/POST/PUT/DELETE", "Port forwards (v2 shape)"),
    ("ping/{mac}, ping-start/{mac}, ping-stop/{mac}", "v2", "GET/POST",
     "Live per-client path ping — WEBSOCKET-DRIVEN; REST returns nulls, results stream over wss. Not curated."),
    # ---- UniFi OS host API (not site-scoped) ---- #
    ("/api/system", "host", "GET", "Console hardware/firmware/apps/storage/WAN state"),
    ("/api/users/self", "host", "GET", "The logged-in admin account"),
    ("/proxy/network/integration/v1/sites", "integration", "GET",
     "Official Integration API (needs an API key, not cookie auth)"),
]


# --------------------------------------------------------------------------- #
# MCP wiring                                                                   #
# --------------------------------------------------------------------------- #
mcp = FastMCP("unifi")
_client: Optional[UniFiClient] = None
_client_lock = threading.Lock()


def client() -> UniFiClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = UniFiClient(load_config())
        return _client


def ok(data: Any) -> dict:
    return {"success": True, "data": data}


def err(e: Exception) -> dict:
    return {"success": False, "error": str(e)}


def _aslist(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return [data] if data else []


# ===========================================================================
# Generic / discovery
# ===========================================================================
@mcp.tool()
def unifi_status() -> dict:
    """Connection + console identity check. Call this FIRST for any request to
    confirm the UniFi console is reachable and authenticated. Returns the console
    model, firmware, uptime, WAN/ISP status, active-client and device counts, and
    the configured site."""
    try:
        c = client()
        c.ensure_session()
        system = c.call("/api/system")
        if not isinstance(system, dict):
            system = {}
        health = _aslist(c.v1("stat/health"))
        subs = {h.get("subsystem"): h for h in health if isinstance(h, dict)}
        wan = subs.get("wan", {})
        wlan = subs.get("wlan", {})
        hw = system.get("hardware", {}) if isinstance(system, dict) else {}
        return ok({
            "reachable": True,
            "host": c.cfg["host"],
            "logged_in_as": c.cfg["username"],
            "site": c.site,
            "console_name": (system or {}).get("name"),
            "model": hw.get("shortname") or hw.get("name"),
            "firmware": hw.get("firmwareVersion") or (system or {}).get("ucore_version"),
            "uptime_seconds": (system or {}).get("uptime"),
            "wan_ip": wan.get("wan_ip"),
            "isp": wan.get("isp_name"),
            "wan_status": wan.get("status"),
            "num_devices": wan.get("num_adopted"),
            "num_active_clients": wlan.get("num_user"),
            "gateway_cpu_pct": (wan.get("gw_system-stats") or {}).get("cpu"),
            "gateway_mem_pct": (wan.get("gw_system-stats") or {}).get("mem"),
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_list_endpoints(filter: str = "") -> dict:
    """Search the UniFi Network endpoint catalog (the master list of what can be
    controlled through the passthrough). `filter` is a case-insensitive substring,
    e.g. "firewall", "client", "wlan", "device", "route". Returns each endpoint's
    relative path, which surface it lives on (v1 / v2 / host / integration), the
    HTTP methods, and what it does. Feed a path to `unifi_call`."""
    try:
        f = filter.lower()
        rows = [
            {"path": p, "surface": s, "methods": m, "description": d}
            for (p, s, m, d) in ENDPOINT_CATALOG
            if f in p.lower() or f in d.lower() or f in s.lower()
        ]
        return ok({"count": len(rows), "endpoints": rows,
                   "note": "Paths without a leading '/' are relative to the site "
                           "(v1: /proxy/network/api/s/{site}/, v2: "
                           "/proxy/network/v2/api/site/{site}/). unifi_call with "
                           "surface= resolves them for you."})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_call(path: str, method: str = "GET", surface: str = "auto",
               params: Optional[dict] = None, json: Optional[dict] = None) -> dict:
    """THE universal tool — call any UniFi Network / UniFi OS endpoint. This reaches
    every controllable feature, including ones without a curated wrapper.

    `surface` controls how `path` is resolved:
      - "v1"   -> prefixes /proxy/network/api/s/{site}/  (classic API)
      - "v2"   -> prefixes /proxy/network/v2/api/site/{site}/
      - "host" -> no prefix; call an absolute UniFi OS path like /api/system
      - "auto" (default) -> if path starts with '/', treated as host/absolute;
                otherwise treated as a v1 site-relative path.

    `method` is GET/POST/PUT/DELETE. For writes the CSRF token is attached
    automatically. `params` become the query string; `json` becomes the request
    body. Examples:
      unifi_call("stat/health")                          # v1 auto
      unifi_call("trafficrules", surface="v2")
      unifi_call("/api/system", surface="host")
      unifi_call("rest/wlanconf/<id>", method="PUT", json={"enabled": false})

    Reads are safe. Writes (POST/PUT/DELETE) change the live network — confirm with
    the user first."""
    try:
        c = client()
        s = surface.lower()
        if s == "v1":
            data = c.v1(path, method, params, json)
        elif s == "v2":
            data = c.v2(path, method, params, json)
        elif s == "host":
            data = c.call(path if path.startswith("/") else "/" + path, method, params, json)
        else:  # auto
            if path.startswith("/"):
                data = c.call(path, method, params, json)
            else:
                data = c.v1(path, method, params, json)
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_sites() -> dict:
    """List the sites on this console (most home consoles have just 'default').
    Shows each site's name, description, and device count."""
    try:
        data = _aslist(client().call("/proxy/network/api/self/sites"))
        return ok([{"name": s.get("name"), "desc": s.get("desc"),
                    "role": s.get("role"), "device_count": s.get("device_count")}
                   for s in data if isinstance(s, dict)])
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Health & statistics
# ===========================================================================
@mcp.tool()
def unifi_health() -> dict:
    """Per-subsystem health: WAN (internet/ISP/latency), WLAN (wifi clients/APs),
    LAN (wired), WWW, and VPN. Each reports an ok/warning/error status plus counts.
    The fastest way to answer "is the network healthy?"."""
    try:
        data = _aslist(client().v1("stat/health"))
        return ok(data)
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_sysinfo() -> dict:
    """Network application system info (version, build, hostname, uptime, and
    controller-level details)."""
    try:
        return ok(_aslist(client().v1("stat/sysinfo")))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_stat_report(interval: str = "hourly", scope: str = "site",
                      attrs: Optional[list] = None) -> dict:
    """Time-series statistics. `interval` is 5minutes | hourly | daily; `scope` is
    site | ap | user | gw. `attrs` selects columns (default: bytes, wan-tx_bytes,
    wan-rx_bytes, num_sta). Useful for bandwidth/usage trends and dashboards."""
    try:
        body = {"attrs": attrs or ["bytes", "wan-tx_bytes", "wan-rx_bytes",
                                    "num_sta", "time"]}
        data = client().v1(f"stat/report/{interval}.{scope}", "POST", json_body=body)
        return ok(_aslist(data))
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Devices (APs, switches, gateway)
# ===========================================================================
@mcp.tool()
def unifi_devices(mac: str = "") -> dict:
    """List UniFi devices (access points, switches, the gateway/router) with model,
    name, IP, state (1=connected), version, uptime, and load. Pass a `mac` to get
    the full detail for one device."""
    try:
        c = client()
        sub = f"stat/device/{mac}" if mac else "stat/device"
        data = _aslist(c.v1(sub))
        if mac:
            return ok(data)
        slim = [{
            "name": d.get("name") or d.get("model"),
            "model": d.get("model"), "type": d.get("type"),
            "mac": d.get("mac"), "ip": d.get("ip"),
            "state": d.get("state"), "adopted": d.get("adopted"),
            "version": d.get("version"), "uptime": d.get("uptime"),
            "num_sta": d.get("num_sta"),
            "cpu": (d.get("system-stats") or {}).get("cpu"),
            "mem": (d.get("system-stats") or {}).get("mem"),
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "devices": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Clients (stations)
# ===========================================================================
@mcp.tool()
def unifi_clients(active_only: bool = True) -> dict:
    """List clients. `active_only=True` (default) returns currently-connected
    stations (name, IP, MAC, wired/wifi, AP/uplink, signal, tx/rx rate, usage).
    `active_only=False` returns all KNOWN clients (the user database), including
    offline ones."""
    try:
        c = client()
        if active_only:
            data = _aslist(c.v1("stat/sta"))
            slim = [{
                "name": d.get("name") or d.get("hostname") or d.get("mac"),
                "mac": d.get("mac"), "ip": d.get("ip"),
                "wired": d.get("is_wired"),
                "network": d.get("network"),
                "signal": d.get("signal"), "essid": d.get("essid"),
                "uptime": d.get("uptime"),
                "rx_bytes": d.get("rx_bytes"), "tx_bytes": d.get("tx_bytes"),
                "blocked": d.get("blocked", False),
            } for d in data if isinstance(d, dict)]
            return ok({"count": len(slim), "clients": slim})
        data = _aslist(c.v1("rest/user"))
        slim = [{
            "name": d.get("name") or d.get("hostname"),
            "mac": d.get("mac"), "oui": d.get("oui"),
            "is_wired": d.get("is_wired"),
            "blocked": d.get("blocked", False),
            "use_fixedip": d.get("use_fixedip"), "fixed_ip": d.get("fixed_ip"),
            "usergroup_id": d.get("usergroup_id"), "note": d.get("note"),
            "_id": d.get("_id"),
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "clients": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Networks / WLANs
# ===========================================================================
@mcp.tool()
def unifi_networks() -> dict:
    """List configured networks (LAN/VLAN/WAN/VPN): name, purpose, subnet, VLAN id,
    DHCP range, and enabled state. Includes the object _id needed for edits."""
    try:
        data = _aslist(client().v1("rest/networkconf"))
        slim = [{
            "_id": d.get("_id"), "name": d.get("name"),
            "purpose": d.get("purpose"), "enabled": d.get("enabled", True),
            "vlan": d.get("vlan"), "subnet": d.get("ip_subnet"),
            "dhcp_enabled": d.get("dhcpd_enabled"),
            "dhcp_start": d.get("dhcpd_start"), "dhcp_stop": d.get("dhcpd_stop"),
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "networks": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_wlans() -> dict:
    """List wireless networks (SSIDs): name, enabled state, security, band, guest
    flag, VLAN, and the _id needed for edits. Password/PSK is included by the API
    but omit it from summaries unless asked."""
    try:
        data = _aslist(client().v1("rest/wlanconf"))
        slim = [{
            "_id": d.get("_id"), "name": d.get("name"),
            "enabled": d.get("enabled", True),
            "security": d.get("security"), "wpa_mode": d.get("wpa_mode"),
            "is_guest": d.get("is_guest"), "hide_ssid": d.get("hide_ssid"),
            "networkconf_id": d.get("networkconf_id"),
            "ap_group_ids": d.get("ap_group_ids"),
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "wlans": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Firewall / port-forward / routing / traffic
# ===========================================================================
@mcp.tool()
def unifi_firewall_rules() -> dict:
    """List classic firewall rules (rulesets like WAN_IN, LAN_IN): name, action,
    enabled, ruleset, and index. Empty on consoles using only the newer zone-based
    firewall — see unifi_firewall_policies for those."""
    try:
        data = _aslist(client().v1("rest/firewallrule"))
        return ok({"count": len(data), "rules": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_firewall_groups() -> dict:
    """List firewall groups (address/port groups referenced by rules)."""
    try:
        data = _aslist(client().v1("rest/firewallgroup"))
        return ok({"count": len(data), "groups": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_firewall_policies() -> dict:
    """List zone-based firewall policies (the modern UniFi firewall UI). This is the
    v2 API used by current Network versions."""
    try:
        data = client().v2("firewall-policies")
        lst = _aslist(data)
        return ok({"count": len(lst), "policies": lst})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_port_forwards() -> dict:
    """List port-forwarding rules: name, enabled, WAN port -> LAN host:port,
    protocol, and the _id for edits."""
    try:
        data = _aslist(client().v1("rest/portforward"))
        slim = [{
            "_id": d.get("_id"), "name": d.get("name"),
            "enabled": d.get("enabled", True), "proto": d.get("proto"),
            "src": d.get("src"), "dst_port": d.get("dst_port"),
            "fwd": d.get("fwd"), "fwd_port": d.get("fwd_port"),
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "port_forwards": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_routes() -> dict:
    """List static routes configured on the gateway."""
    try:
        data = _aslist(client().v1("rest/routing"))
        return ok({"count": len(data), "routes": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_traffic_rules() -> dict:
    """List traffic rules (block/allow traffic by app, domain, IP, or category —
    e.g. 'Block YouTube for kids'). This is the v2 API."""
    try:
        data = _aslist(client().v2("trafficrules"))
        slim = [{
            "_id": d.get("_id"), "description": d.get("description"),
            "action": d.get("action"), "enabled": d.get("enabled"),
            "matching_target": d.get("matching_target"),
            "domains": [x.get("domain") for x in d.get("domains", [])],
        } for d in data if isinstance(d, dict)]
        return ok({"count": len(slim), "traffic_rules": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# Events / alarms / settings
# ===========================================================================
@mcp.tool()
def unifi_events(limit: int = 20) -> dict:
    """Recent network events/log entries (client connects/disconnects, device
    events, admin actions, WAN transitions) from the unified system log, newest
    first."""
    try:
        data = client().v2("system-log/all", "POST",
                            json_body={"pageNumber": 0, "pageSize": limit})
        rows = data.get("data", []) if isinstance(data, dict) else _aslist(data)
        slim = [{
            "category": e.get("category"), "event": e.get("event"),
            "key": e.get("key"), "timestamp": e.get("timestamp"),
            "message": e.get("message") or e.get("message_raw"),
        } for e in rows if isinstance(e, dict)]
        return ok({"count": len(slim),
                   "total": data.get("total_element_count") if isinstance(data, dict) else None,
                   "events": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_alarms(include_archived: bool = False) -> dict:
    """List alarms (actionable alerts). By default only unarchived (open) alarms."""
    try:
        body = {} if include_archived else {"archived": False}
        data = _aslist(client().v1("list/alarm", "POST", json_body=body))
        return ok({"count": len(data), "alarms": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_settings(key: str = "") -> dict:
    """Read site settings. With no `key`, returns every settings section (grouped by
    key: mgmt, guest_access, ntp, dhcp, usg, etc.). With a `key`, returns just that
    section. Read-only; use unifi_call POST set/setting/{key} to write."""
    try:
        data = _aslist(client().v1("rest/setting"))
        if key:
            data = [s for s in data if isinstance(s, dict) and s.get("key") == key]
        return ok({"count": len(data), "settings": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_rogue_aps() -> dict:
    """List neighboring/rogue access points detected in RF scans (BSSID, SSID,
    channel, signal, security). Useful for RF planning and security."""
    try:
        data = _aslist(client().v1("stat/rogueap"))
        return ok({"count": len(data), "aps": data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_wifi_connectivity() -> dict:
    """Wi-Fi connection-quality diagnostics (v2) — the primary tool for "why won't
    clients connect / why is Wi-Fi flaky". Returns the success ratios for each stage
    of association (association / authentication / DHCP / DNS), the total connection
    attempts and failure count, latency summary, and the RECENT FAILED connection
    events per client (client, AP, failure reason, time). Healthy is ~100% across
    all ratios with no failures. Read-only."""
    try:
        d = client().v2("wifi-connectivity")
        if not isinstance(d, dict):
            return ok(d)
        attempts = d.get("attempts", {})
        failures = []
        for grp in d.get("event_groups", []):
            if not isinstance(grp, dict):
                continue
            cl = grp.get("client", {}) or {}
            for ev in grp.get("events", []):
                if isinstance(ev, dict) and ev.get("failure_reason") not in (None, "SUCCESS"):
                    failures.append({
                        "client": cl.get("name") or cl.get("hostname") or cl.get("mac"),
                        "mac": cl.get("mac"), "ap_mac": ev.get("ap_mac"),
                        "failure_reason": ev.get("failure_reason"),
                        "start_time": ev.get("start_time"),
                    })
        return ok({
            "attempts": attempts,
            "total_clients": d.get("total_clients"),
            "latencies": d.get("latencies"),
            "failed_event_count": len(failures),
            "failed_events": failures[:50],
        })
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_firewall_zones() -> dict:
    """List firewall zones (v2) — the security zones (Internal, External, Gateway,
    VPN, Hotspot, etc.) that the zone-based firewall policies act between. Shows each
    zone's name, key, whether it's a default zone, and how many networks are in it.
    Pairs with unifi_firewall_policies (policies are rules between two zones)."""
    try:
        data = _aslist(client().v2("firewall/zone"))
        slim = [{
            "_id": z.get("_id"), "name": z.get("name"),
            "zone_key": z.get("zone_key"), "default_zone": z.get("default_zone"),
            "network_count": len(z.get("network_ids") or []),
            "network_ids": z.get("network_ids"),
        } for z in data if isinstance(z, dict)]
        return ok({"count": len(slim), "zones": slim})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_traffic_routes() -> dict:
    """List policy-based traffic routes (v2) — per-client/network routing overrides,
    e.g. "send this device's traffic over the VPN" or WAN steering. Distinct from
    static routes (unifi_routes): these match on clients/apps/domains and steer to an
    interface. Empty if none configured."""
    try:
        data = _aslist(client().v2("trafficroutes"))
        slim = [{
            "_id": r.get("_id"), "description": r.get("description"),
            "enabled": r.get("enabled"),
            "matching_target": r.get("matching_target"),
            "network_id": r.get("network_id"),
            "next_hop": r.get("next_hop"),
        } for r in data if isinstance(r, dict)]
        return ok({"count": len(slim), "traffic_routes": slim or data})
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_dashboard() -> dict:
    """The aggregated overview dashboard (v2) — a single rich snapshot the UI home
    page uses: internet/WAN routability & activity, Wi-Fi doctor & connectivity
    summary, ISP metrics, most-active clients/APs/apps, radio activity/density, TX
    retries, upgradable device count, and traffic identification. Best one-call
    situational overview for diagnosis. Read-only; the payload is large."""
    try:
        d = client().v2("aggregated-dashboard")
        if isinstance(d, dict):
            return ok({"sections": list(d.keys()), "dashboard": d})
        return ok(d)
    except Exception as e:  # noqa: BLE001
        return err(e)


# ===========================================================================
# WRITE / action tools — all confirm-gated. Each changes the live network.
# ===========================================================================
def _require_confirm(confirm: bool, what: str) -> Optional[dict]:
    if not confirm:
        return {"success": False,
                "error": f"Refused: this will {what}. Re-call with confirm=True "
                         f"after the user has explicitly approved."}
    return None


@mcp.tool()
def unifi_client_block(mac: str, confirm: bool = False) -> dict:
    """Block a client from the network by MAC (cmd/stamgr block-sta). The device
    loses connectivity until unblocked. Confirm-gated."""
    guard = _require_confirm(confirm, f"BLOCK client {mac} from the network")
    if guard:
        return guard
    try:
        return ok(client().cmd("stamgr", {"cmd": "block-sta", "mac": mac.lower()}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_client_unblock(mac: str, confirm: bool = False) -> dict:
    """Unblock a previously-blocked client by MAC (cmd/stamgr unblock-sta).
    Confirm-gated (it changes access control, though it restores connectivity)."""
    guard = _require_confirm(confirm, f"UNBLOCK client {mac}")
    if guard:
        return guard
    try:
        return ok(client().cmd("stamgr", {"cmd": "unblock-sta", "mac": mac.lower()}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_client_reconnect(mac: str, confirm: bool = False) -> dict:
    """Force a wireless client to reconnect (cmd/stamgr kick-sta). Briefly drops the
    client so it re-associates. Confirm-gated."""
    guard = _require_confirm(confirm, f"force client {mac} to reconnect (brief drop)")
    if guard:
        return guard
    try:
        return ok(client().cmd("stamgr", {"cmd": "kick-sta", "mac": mac.lower()}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_device_restart(mac: str, confirm: bool = False) -> dict:
    """Restart a UniFi device (AP/switch/gateway) by MAC (cmd/devmgr restart). The
    device and anything downstream of it drops during the reboot. RESTARTING THE
    GATEWAY TAKES THE WHOLE NETWORK OFFLINE. Confirm-gated."""
    guard = _require_confirm(confirm, f"RESTART device {mac} (downstream drops during reboot)")
    if guard:
        return guard
    try:
        return ok(client().cmd("devmgr", {"cmd": "restart", "mac": mac.lower()}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_device_locate(mac: str, on: bool = True, confirm: bool = False) -> dict:
    """Flash a device's locate LED on/off (cmd/devmgr set-locate / unset-locate).
    Harmless but physically visible; confirm-gated for consistency."""
    guard = _require_confirm(confirm, f"toggle locate LED on device {mac}")
    if guard:
        return guard
    try:
        cmd = "set-locate" if on else "unset-locate"
        return ok(client().cmd("devmgr", {"cmd": cmd, "mac": mac.lower()}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_wlan_set_enabled(wlan_id: str, enabled: bool, confirm: bool = False) -> dict:
    """Enable or disable a wireless network (SSID) by its _id (PUT rest/wlanconf).
    Disabling a WLAN disconnects every client on it. Get the _id from unifi_wlans.
    Confirm-gated."""
    guard = _require_confirm(confirm,
                             f"{'ENABLE' if enabled else 'DISABLE'} WLAN {wlan_id} "
                             f"({'clients on it disconnect' if not enabled else 'brings SSID up'})")
    if guard:
        return guard
    try:
        return ok(client().v1(f"rest/wlanconf/{wlan_id}", "PUT",
                              json_body={"enabled": enabled}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_port_forward_set_enabled(pf_id: str, enabled: bool, confirm: bool = False) -> dict:
    """Enable or disable a port-forwarding rule by its _id (PUT rest/portforward).
    Get the _id from unifi_port_forwards. Confirm-gated (changes what's exposed to
    the internet)."""
    guard = _require_confirm(confirm,
                             f"{'ENABLE' if enabled else 'DISABLE'} port-forward {pf_id}")
    if guard:
        return guard
    try:
        return ok(client().v1(f"rest/portforward/{pf_id}", "PUT",
                              json_body={"enabled": enabled}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_traffic_rule_set_enabled(rule_id: str, enabled: bool, confirm: bool = False) -> dict:
    """Enable or disable a traffic rule by its _id (v2 PUT trafficrules). Get the
    _id from unifi_traffic_rules. Confirm-gated."""
    guard = _require_confirm(confirm,
                             f"{'ENABLE' if enabled else 'DISABLE'} traffic rule {rule_id}")
    if guard:
        return guard
    try:
        # v2 rules require the full object on PUT; fetch, patch enabled, send back.
        rules = _aslist(client().v2("trafficrules"))
        target = next((r for r in rules if isinstance(r, dict) and r.get("_id") == rule_id), None)
        if not target:
            return {"success": False, "error": f"No traffic rule with _id {rule_id}"}
        target["enabled"] = enabled
        return ok(client().v2(f"trafficrules/{rule_id}", "PUT", json_body=target))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_firewall_policy_set_enabled(policy_id: str, enabled: bool,
                                      confirm: bool = False) -> dict:
    """Enable or disable a zone-based firewall policy by its _id (v2 PUT
    firewall-policies). Get the _id from unifi_firewall_policies. Uses
    read-modify-write (v2 requires the full object on PUT). Confirm-gated
    (changes what traffic is allowed between zones)."""
    guard = _require_confirm(confirm,
                             f"{'ENABLE' if enabled else 'DISABLE'} firewall policy {policy_id}")
    if guard:
        return guard
    try:
        policies = _aslist(client().v2("firewall-policies"))
        target = next((p for p in policies
                       if isinstance(p, dict) and p.get("_id") == policy_id), None)
        if not target:
            return {"success": False, "error": f"No firewall policy with _id {policy_id}"}
        if target.get("predefined"):
            return {"success": False,
                    "error": f"Firewall policy {policy_id} is predefined (system-managed) "
                             f"and cannot be toggled via the API."}
        target["enabled"] = enabled
        return ok(client().v2(f"firewall-policies/{policy_id}", "PUT", json_body=target))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_device_port_cycle(mac: str, port_idx: int, confirm: bool = False) -> dict:
    """Power-cycle a PoE switch port (cmd/devmgr power-cycle) — reboots whatever is
    powered by that port (camera, AP, phone). `mac` is the SWITCH's MAC, `port_idx`
    the port number. Find both via unifi_devices(mac=...) -> port_table.
    Confirm-gated."""
    guard = _require_confirm(confirm,
                             f"POWER-CYCLE port {port_idx} on switch {mac} "
                             f"(the powered device reboots)")
    if guard:
        return guard
    try:
        return ok(client().cmd("devmgr", {"cmd": "power-cycle",
                                          "mac": mac.lower(),
                                          "port_idx": int(port_idx)}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_run_speedtest(confirm: bool = False) -> dict:
    """Trigger a WAN speedtest on the gateway (cmd/devmgr speedtest). Non-disruptive
    but uses bandwidth for ~30s. Poll results with unifi_speedtest_status.
    Confirm-gated."""
    guard = _require_confirm(confirm, "run a WAN speedtest (uses bandwidth ~30s)")
    if guard:
        return guard
    try:
        return ok(client().cmd("devmgr", {"cmd": "speedtest"}))
    except Exception as e:  # noqa: BLE001
        return err(e)


@mcp.tool()
def unifi_speedtest_status() -> dict:
    """Get the latest/ongoing speedtest status and result (cmd/devmgr
    speedtest-status): download/upload Mbps, latency, and run state. Read-only."""
    try:
        return ok(client().cmd("devmgr", {"cmd": "speedtest-status"}))
    except Exception as e:  # noqa: BLE001
        return err(e)


if __name__ == "__main__":
    log(f"starting; config target = {load_config().get('host') or '(unset)'}")
    mcp.run()
