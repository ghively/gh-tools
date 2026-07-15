# UniFi Network API map (this console)

Enumerated from the UDR7's own UI bundles and confirmed with live probes. Paths are
relative to the site unless marked. Reach any of them with
`unifi_call(path, method, surface, json=...)`.

## Surfaces

| Surface | Prefix | Use |
|---------|--------|-----|
| `v1` | `/proxy/network/api/s/{site}/` | classic stat/rest/cmd/list/set |
| `v2` | `/proxy/network/v2/api/site/{site}/` | firewall-policies, traffic rules/routes, clients, system-log |
| `host` | `/` (absolute) | `/api/system`, `/api/users/self`, `/api/auth/*` |
| `integration` | `/proxy/network/integration/v1/` | official API — **needs an API key** (401 with cookie) |

## v1 — statistics (read-only, GET unless noted)

| Path | Returns |
|------|---------|
| `stat/health` | per-subsystem health (wan/wlan/lan/www/vpn) |
| `stat/sysinfo` | controller version/build/uptime |
| `stat/device` / `stat/device/{mac}` | full device state (AP/switch/gw) |
| `stat/device-basic` | lightweight device list |
| `stat/sta` | active clients (connected stations) |
| `stat/guest` | guest/hotspot authorizations |
| `stat/rogueap` | neighboring/rogue APs (RF scan) |
| `stat/spectrum-scan` | per-AP RF spectrum scan |
| `stat/current-channel` | allowed/used channels |
| `stat/ccode` | country codes (207) |
| `stat/portforward` | active port-forward state |
| `stat/report/{5minutes\|hourly\|daily}.{site\|ap\|user\|gw}` | time-series (POST with `{attrs:[...]}`) |
| `stat/sdn` | UI cloud account status |
| `stat/voucher` | hotspot vouchers |
| `stat/fwupdate/latest-version` | firmware availability |

## v1 — config objects (rest/*: GET list · POST create · PUT `<path>/<_id>` · DELETE `<path>/<_id>`)

| Path | Object |
|------|--------|
| `rest/user` | known clients (rename, fixed-IP, group, note) |
| `rest/usergroup` | client bandwidth groups |
| `rest/device` | per-device config (PUT only) |
| `rest/networkconf` | networks / VLANs / WAN |
| `rest/wlanconf` | wireless networks (SSIDs) |
| `rest/firewallrule` | classic firewall rules (empty on this box) |
| `rest/firewallgroup` | firewall address/port groups |
| `rest/portforward` | port-forwarding rules |
| `rest/routing` | static routes |
| `rest/dhcpoption` | custom DHCP options |
| `rest/dynamicdns` | dynamic DNS |
| `rest/dpiapp` / `rest/dpigroup` | DPI application filters / groups |
| `rest/portconf` | switch port profiles |
| `rest/scheduletask` | scheduled tasks |
| `rest/account` | RADIUS accounts |
| `rest/hotspotop` / `rest/hotspotpackage` | hotspot operators / packages |
| `rest/setting` (GET) · `set/setting/{key}` (POST) | site settings by section |

## v1 — actions (POST `cmd/{mgr}` with `{"cmd": "...", ...}`)

| Manager | Commands (verified routing) |
|---------|------------------------------|
| `cmd/stamgr` | `block-sta`, `unblock-sta`, `kick-sta` (reconnect), `authorize-guest` (`+minutes`), `unauthorize-guest`, `forget-sta` |
| `cmd/devmgr` | `restart`, `force-provision`, `set-locate`, `unset-locate`, `adopt`, `speedtest`, `speedtest-status`, `upgrade` |
| `cmd/firewall` | firewall manager ops |
| `cmd/backup` | `list-backups`, `delete-backup`, … |
| `cmd/sitemgr` | `add-site`, `update-site`, `delete-site` |
| `cmd/hotspot` | voucher/guest ops |
| `cmd/system`, `cmd/cfgmgr` | system / config-manager ops |

`list/alarm` (GET or POST `{archived:false}`) — alarms.

## v2 — modern features

| Path | Object | Notes |
|------|--------|-------|
| `firewall-policies` | zone-based firewall (85 here) | the ACTIVE firewall; curated `unifi_firewall_policies` |
| `firewall/zone` | firewall zones (7) | curated `unifi_firewall_zones` |
| `trafficrules` | block/allow by app/domain/IP | curated `unifi_traffic_rules`; read-modify-write full object on PUT |
| `trafficroutes` | policy routes (VPN/WAN steering) | curated `unifi_traffic_routes` |
| `wifi-connectivity` | connect-quality diagnostics | curated `unifi_wifi_connectivity`; assoc/auth/DHCP/DNS ratios + failures |
| `aggregated-dashboard` | rich overview snapshot | curated `unifi_dashboard`; large payload |
| `clients/active`, `clients/history` | clients (richer v2 shape) | v1 `stat/sta`+`rest/user` also cover clients |
| `system-log/all` | unified events (POST `{pageNumber,pageSize}`) | curated `unifi_events` |
| `ping/{mac}`, `ping-start`, `ping-stop` | live per-client path ping | **WebSocket-driven** — REST snapshot returns nulls; not curated |
| `device-tags` | device tags | |
| `sites/overview` | cross-site overview | |

## host (absolute `/api/...`)

| Path | Returns |
|------|---------|
| `/api/system` | console hardware, firmware, apps, storage, WAN, ports (large; can be slow) |
| `/api/users/self` | logged-in admin (roles/permissions) |
| `/api/auth/login`, `/api/auth/logout` | session (handled by the server) |

## Not present / hard limits on this console

- **UniFi Protect / Access / Talk / Connect / InnerSpace**: not installed on this
  UDR7 (the app list shows only the Network controller). Their `/proxy/<app>/`
  paths return the UniFi OS shell, not an API. Would require installing the app
  (and compatible hardware, e.g. cameras for Protect).
- **Integration API v1**: reachable but returns 401 with cookie auth — needs an
  API key (Network → Settings → Control Plane → Integrations). Optional; the
  classic + v2 surfaces already cover everything below it.
- **SSH-only / console-OS operations** (e.g. `unifi-os` shell, `set-inform` from a
  device) are not part of the HTTP API.
