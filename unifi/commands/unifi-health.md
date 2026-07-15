---
description: Full health check of the UniFi network (internet/WAN, devices, wifi, clients, alarms, events)
argument-hint: (optional) an area to focus on, e.g. "wifi" or "internet"
---

# UniFi network health check

Produce a concise health report for the UniFi console using the `unifi` MCP tools.
If `$ARGUMENTS` names a focus area, weight the report toward it, but always cover
the basics (internet + devices). This is **read-only** — make no changes.

1. **Identity & internet** — `unifi_status` (model, firmware, uptime, WAN IP, ISP,
   up/down, gateway CPU/mem, client/device counts).
2. **Subsystem health** — `unifi_health`. Flag any subsystem (`wan`/`wlan`/`lan`/
   `www`/`vpn`) whose `status` is not `ok`.
3. **Devices** — `unifi_devices`. List each AP/switch/gateway with state; flag any
   not connected (`state != 1`), and note the busiest (highest `num_sta`) and any
   high CPU/mem.
4. **Clients** — `unifi_clients(active_only=True)` for the current count; call out
   any wifi client with a weak signal (worse than about −75 dBm).
5. **Alarms & events** — `unifi_alarms` (open alerts) and `unifi_events(limit=20)`
   (recent notable events: WAN transitions, device disconnects, repeated client
   drops).
6. **RF (if focus is wifi)** — `unifi_rogue_aps` count and any strong nearby
   co-channel APs.

## Output

Lead with an overall verdict: **Healthy / Needs attention / Critical**. Then a short
bulleted summary grouped by the sections above, with anything abnormal at the top
and a concrete recommended action. Convert bytes/epoch to human units. Do not make
any changes.
