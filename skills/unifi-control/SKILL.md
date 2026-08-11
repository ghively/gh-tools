---
name: unifi-control
description: >-
  Control and administer a Ubiquiti UniFi console (UniFi OS) end-to-end via the
  unifi MCP server. Use this whenever the user wants to inspect, configure, or
  operate their UniFi / Ubiquiti / UniFi OS network — including the Dream Router,
  Dream Machine (UDM/UDR/UDW), Cloud Gateway, or a self-hosted Network
  controller — for ANY of: network health & internet/WAN status, UniFi devices
  (access points, switches, gateway) and their restart/locate/upgrade, connected
  and known clients (block/unblock/reconnect/rename), wireless networks (SSIDs),
  LAN/VLAN networks, the firewall (classic rules or zone-based policies), port
  forwarding, static & policy routes, traffic rules (block apps/domains), DPI,
  events & alarms, statistics & speedtests, guest hotspot/vouchers, RADIUS, DHCP,
  or anything else exposed by the UniFi Network API. Trigger this skill even when
  the user just names their UniFi gear or asks to "check the network", "who's on
  my wifi", "block this device", "restart the AP", "is the internet down", "port
  forward for my server", or "why is wifi slow" — do not answer from memory;
  drive the live console through the tools.
metadata:
  hermes:
    tags: [unifi, ubiquiti, unifi-os, network, wifi, firewall, mcp, homelab]
    category: infrastructure
    requires_tools: [unifi_status]
    config:
      - {key: unifi.host, prompt: UniFi console host/IP, default: 192.168.0.1}
required_environment_variables:
  - name: UNIFI_PASSWORD
    prompt: UniFi LOCAL admin password (cloud/SSO accounts with MFA cannot log in via the API)
    required_for: authenticating unifi_* calls
  - name: UNIFI_API_KEY
    prompt: UniFi Integration API key (only for official Integration API endpoints)
    required_for: official Integration API calls
    optional: true
version: 0.1.1
author: ghively
---

# UniFi Network control

This skill drives a real Ubiquiti UniFi console through the **`unifi` MCP server**
(tools are named `mcp__unifi__*`, shown to you as `unifi_*`). The target console,
auth, and behavior are already wired up — your job is to pick the right tool/API
and interpret results. Verified against a **UniFi Dream Router 7 (UDR7)**, UniFi
OS 4.x, Network application 10.4.x.

## Mental model

UniFi OS proxies the Network application under `/proxy/network/`. There are **three
API surfaces**, and the server reaches all of them:

1. **Classic v1** — `/proxy/network/api/s/{site}/…` with families:
   `stat/*` (read-only statistics), `rest/*` (CRUD config objects, each with an
   `_id`), `cmd/*` (imperative actions), `list/*`, `set/setting/{key}`.
2. **v2** — `/proxy/network/v2/api/site/{site}/…` — newer features: zone-based
   `firewall-policies`, `trafficrules`, `trafficroutes`, `clients`, and the
   unified `system-log` (events).
3. **UniFi OS host API** — `/api/…` (not site-scoped): `/api/system` (console
   hardware/firmware/apps), `/api/users/self`.

Auth is handled for you: the server logs in (local admin), holds the `TOKEN` JWT
cookie, and attaches the **`X-Csrf-Token`** header (required on every write, or the
box returns HTTP 403). The site is `default` unless configured otherwise.

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for common jobs. Prefer these.
2. **Generic passthrough** — `unifi_call` reaches *any* endpoint on any surface;
   `unifi_list_endpoints` is the searchable catalog of what's controllable.

**Golden rule:** if a curated tool exists, use it. Otherwise find the endpoint with
`unifi_list_endpoints`, then call it with `unifi_call`. Never guess a network fact —
read it from the console.

## Start here

For almost any request, call **`unifi_status`** first. It confirms the console is
reachable and returns model, firmware, uptime, WAN/ISP status, and device/client
counts in one shot. If it fails, the problem is connectivity/auth (see
Troubleshooting), not the task.

## Curated tools (use these first)

| Area | Tools |
|------|-------|
| Identity / health | `unifi_status`, `unifi_health`, `unifi_sysinfo`, `unifi_stat_report` |
| Devices (AP/switch/gw) | `unifi_devices` (pass a `mac` for detail) |
| Clients | `unifi_clients` (`active_only=True` connected / `False` known) |
| Wireless | `unifi_wlans` |
| Networks / VLANs | `unifi_networks` |
| Firewall | `unifi_firewall_rules` (classic), `unifi_firewall_policies` (zone-based v2), `unifi_firewall_zones` (v2), `unifi_firewall_groups` |
| Port forward / routing | `unifi_port_forwards`, `unifi_routes` (static), `unifi_traffic_routes` (policy/VPN v2) |
| Traffic control | `unifi_traffic_rules` (block apps/domains) |
| Diagnostics | `unifi_wifi_connectivity` (assoc/auth/DHCP/DNS success + failures), `unifi_dashboard` (rich overview) |
| Events / alerts | `unifi_events`, `unifi_alarms` |
| Guest hotspot | `unifi_vouchers` (list voucher codes) |
| Settings / RF | `unifi_settings`, `unifi_rogue_aps` |
| Speedtest | `unifi_run_speedtest`, `unifi_speedtest_status` |
| **Writes (confirm-gated)** | `unifi_client_block`/`_unblock`/`_reconnect`, `unifi_device_restart`/`_locate`/`_port_cycle`, `unifi_wlan_set_enabled`, `unifi_port_forward_set_enabled`, `unifi_traffic_rule_set_enabled`, `unifi_firewall_policy_set_enabled`, `unifi_voucher_create`, `unifi_alarm_archive` |
| Anything else | `unifi_call`, `unifi_list_endpoints`, `unifi_sites` |

## This console uses the ZONE-BASED firewall

On current UniFi (and this UDR7), classic `rest/firewallrule` is **empty** — the
firewall lives in the **v2 `firewall-policies`** API (`unifi_firewall_policies`,
85 policies on this box), acting between zones (`unifi_firewall_zones`). Don't
report "no firewall rules" from the classic tool; check policies. Traffic rules
(`unifi_traffic_rules`) are a separate, app/domain-oriented layer (e.g. "Block
YouTube for kids"), and traffic routes (`unifi_traffic_routes`) steer matched
traffic to an interface/VPN.

## Wi-Fi troubleshooting

For "why won't my device connect" / "Wi-Fi is flaky", lead with
**`unifi_wifi_connectivity`**: it reports the success ratio at each connect stage
(association → authentication → DHCP → DNS) plus the recent *failed* connection
events (which client, which AP, the failure reason). A low ratio pinpoints the
failing stage (e.g. DHCP failures → DHCP pool/relay problem; auth failures → PSK/
RADIUS). Combine with `unifi_dashboard` (Wi-Fi doctor, TX retries, radio density)
and per-client signal from `unifi_clients`.

**Live per-client ping** (`ping-start`/`ping/{mac}` v2) is **WebSocket-driven** —
the REST snapshot returns nulls, so there is no curated tool for it. If a user
needs live latency to one client, use the UI's client "Connection" panel; the
plugin covers WAN speed via `unifi_run_speedtest` and path health via
`unifi_wifi_connectivity`.

## Discovery-first workflow (for anything not curated)

Many capabilities (DPI, dynamic DNS, RADIUS, schedules, port profiles, VPN,
guest auth, WLAN/network **create**) have no curated tool. (Voucher list/create
and alarm archive now *are* curated — see the table above.) Do this:

1. **Find the endpoint.** `unifi_list_endpoints(filter="dpi")` →
   `rest/dpiapp`, etc.
2. **Read first** to learn the object shape: `unifi_call("rest/dpiapp")`.
3. **Act.** For `rest/*` objects: `POST` to create, `PUT rest/<name>/<_id>` to
   update, `DELETE rest/<name>/<_id>` to remove. For actions: `POST cmd/<mgr>`
   with `{"cmd": "...", ...}`. For v2: pass `surface="v2"`.

`references/api-map.md` is the full categorized endpoint list for this console.
`references/common-tasks.md` has copy-paste `unifi_call` recipes for the most
common non-curated jobs. `references/conventions.md` documents auth, CSRF, the
error vocabulary, object-CRUD patterns, and box-specific quirks — read it when a
call misbehaves.

## Parameters

`unifi_call(path, method, surface, params, json)`:
- `surface`: `"v1"` (site-relative classic), `"v2"` (site-relative v2), `"host"`
  (absolute `/api/...`), or `"auto"` (leading `/` → host, else → v1).
- Reads use `GET`; writes use `POST`/`PUT`/`DELETE` and get CSRF automatically.
- `params` → query string; `json` → request body. Example:

```
unifi_call("trafficrules", surface="v2")                       # read
unifi_call("rest/wlanconf/<id>", method="PUT", json={"enabled": false})
unifi_call("cmd/stamgr", method="POST", json={"cmd":"kick-sta","mac":"<mac>"})
```

## Object CRUD pattern (rest/*)

`rest/*` objects are full documents. To toggle one field safely, **read the object,
change the field, PUT the whole object back** — a bare `PUT {"enabled": false}`
works for simple flags but some objects validate the full body. The curated
`unifi_traffic_rule_set_enabled` already does read-modify-write; follow that pattern
for others.

⚠️ **Do NOT POST an empty/partial body to a `rest/*` create endpoint to "probe" it
— UniFi will create a junk sparse object.** To check a method exists safely, use a
`PUT` to a fake `_id` (returns `IdInvalid` = exists) or just read first.

## Safety — treat the console as production

This is the live gateway for the whole household/site. Be deliberate:

- **Reads are free.** Inspect freely to answer questions.
- **Confirm before writing or disrupting.** Before blocking a client, restarting a
  device, disabling a WLAN, or changing firewall/port-forward/traffic rules, state
  exactly what you're about to do and get a clear go-ahead. **Restarting the
  gateway or disabling the only WLAN can cut off the whole network — including your
  own access to the console.**
- **Write tools are confirm-gated.** Every mutating tool refuses unless called with
  `confirm=True`. That gate is a backstop, not a substitute for asking the user.
- **Prefer reversible steps** and read back after a change (re-list to verify it
  took effect). Report what actually happened, including failures — don't claim a
  success you didn't observe.

## Interpreting results

- Client/device `state`: `1` = connected/online for devices; clients in `stat/sta`
  are all currently connected. Known clients (`rest/user`) include offline ones.
- Byte counters (`rx_bytes`/`tx_bytes`, `*-r` = rate) are raw bytes — convert for
  humans. Signal is dBm (closer to 0 is stronger; −50 great, −75 weak).
- `stat/health` subsystems (`wan`/`wlan`/`lan`/`www`/`vpn`) each carry
  `status: ok|warning|error` — lead your health summary with any non-ok.
- Errors surface as `UniFi error: api.err.X` (classic) or a validation message
  (v2). `403` = CSRF/permission (server retries auth once), `404` = wrong path,
  `400`/`api.err.*` = the method exists but rejected the params.

## Troubleshooting

- **`unifi_status` fails / connection error:** the console may be unreachable, or
  `config.local.json` (host/credentials) is wrong. Confirm the host answers on
  https (default port 443 for UniFi OS; self-hosted controllers use 8443).
- **Login fails (HTTP 400/401):** wrong password, or the account is a **Ubiquiti
  cloud/SSO account** — those can't authenticate via the local API when MFA is on.
  Use a **local** admin account (UniFi OS → Admins → add a local-only admin).
- **A write returns 403:** the CSRF token wasn't accepted; the server re-auths and
  retries once. If it persists, the account may lack write permission (use a
  full-management admin).
- **`/api/system` occasionally times out:** it's a large payload; `unifi_status`
  already surfaces its key fields, so prefer that over calling it directly.
- **"No firewall rules":** this console uses the zone-based firewall — check
  `unifi_firewall_policies`, not `unifi_firewall_rules`.
