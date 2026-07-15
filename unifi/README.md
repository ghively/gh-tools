# unifi-network — full UniFi (UniFi OS) control for Claude Code

A Claude Code plugin that gives Claude complete, authenticated control of a Ubiquiti
UniFi console over the Network API. Built and tested against a **UniFi Dream Router 7
(UDR7)** running **UniFi OS 4.x** with the **Network application 10.4.x**.

## What's inside

- **MCP server** (`mcp/unifi_server.py`) — logs in to UniFi OS (JWT cookie + CSRF
  token, auto re-login) and exposes:
  - **Generic passthrough** (`unifi_call`, `unifi_list_endpoints`, `unifi_sites`)
    reaching **every endpoint** across all three surfaces — the classic v1 API,
    the modern v2 API (zone firewall, traffic rules, events), and the UniFi OS host
    API (`/api/*`).
  - **~35 curated tools** for health, devices, clients, wireless, networks/VLANs,
    firewall (classic + zone-based + zones), port forwarding, static & policy
    routing, traffic rules, Wi-Fi connectivity diagnostics, an aggregated
    dashboard, events, alarms, settings, statistics, and speedtests.
  - **Confirm-gated write tools** — block/unblock/reconnect a client, restart/locate
    a device, enable/disable a WLAN, port-forward, or traffic rule, and run a
    speedtest. Every mutating tool refuses unless called with `confirm=True`.
- **Skill** (`skills/unifi-control/`) — teaches Claude how to drive the server, with
  a categorized **API map** of this console, verified **task recipes**, and the
  **auth/conventions** reference (CSRF, error vocabulary, the zone-firewall quirk,
  and the safe write-probe rule).
- **Commands** (`commands/`) — `/unifi-health`, `/unifi-clients`, `/unifi-wifi`,
  `/unifi-firewall`, `/unifi-speedtest`.

## Setup

1. **Credentials.** Copy `config.example.json` → `config.local.json` and fill in your
   console host, username, and password. Use a **local** admin account — Ubiquiti
   cloud/SSO accounts with MFA cannot authenticate via the local API. Create one in
   UniFi OS → **Admins & Users → Add Admin → "Restrict to local access only"** with
   Full Management. `config.local.json` is git-ignored. Any field can instead be set
   via environment variables (`UNIFI_HOST`, `UNIFI_PORT`, `UNIFI_HTTPS`,
   `UNIFI_USERNAME`, `UNIFI_PASSWORD`, `UNIFI_API_KEY`, `UNIFI_SITE`,
   `UNIFI_VERIFY_SSL`), which override the file.
2. **Runtime.** The MCP server launches via [`uv`](https://docs.astral.sh/uv/)
   (`uv run --script`), which auto-provisions its dependencies (`mcp`, `httpx`) in a
   cached environment — no manual `pip install`. `uv` must be on PATH.
3. **Load the plugin** in Claude Code, then reload/restart. Ask Claude to "check the
   network" or run `/unifi-health`.

## Security notes

- The password lives only in `config.local.json` (git-ignored) or your environment.
- UniFi OS uses a self-signed cert on the LAN, so certificate verification is off by
  default (`verify_ssl: false`). Set it true if you've installed a trusted cert.
- All mutating tools require `confirm=True`, and the skill instructs Claude to
  confirm any write/disruptive action with you first. Restarting the gateway or
  disabling the only WLAN can take the whole network — and your console access —
  offline, so writes are deliberate.

## Coverage notes (this console)

- **The firewall is zone-based.** Classic `rest/firewallrule` is empty on this box;
  the active firewall is the v2 `firewall-policies` API (85 policies). Use
  `unifi_firewall_policies`, not `unifi_firewall_rules`.
- **Events** are served by the v2 `system-log/all` endpoint (`unifi_events`); the
  old classic `stat/event` returns 404 here.
- **`/api/system`** is a large payload that can occasionally time out under load —
  `unifi_status` surfaces its key fields, so prefer it.
- **Live per-client ping/traceroute is WebSocket-driven** in UniFi, not REST — the
  REST snapshot returns nulls, so there's no curated ping tool. WAN speed
  (`unifi_run_speedtest`) and Wi-Fi path health (`unifi_wifi_connectivity`) are
  covered; continuous latency to a single client stays a UI/WS-only operation.
- **Only the Network app is installed.** UniFi Protect/Access/Talk/Connect are not
  provisioned on this UDR7; controlling them would require installing the app (and
  compatible hardware).
- **Official Integration API** (`/proxy/network/integration/v1/`) is reachable but
  needs an API key (not cookie auth). It's optional — the classic + v2 surfaces
  already cover everything. Set `api_key` in config to enable it.

See `skills/unifi-control/references/` for the full API map and details.
