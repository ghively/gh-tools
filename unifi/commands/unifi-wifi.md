---
description: Review wireless networks (SSIDs), AP load, client signal, and RF neighborhood
argument-hint: (optional) an SSID name to focus on
---

# UniFi Wi-Fi review

Review the wireless setup using the `unifi` MCP tools. Read-only unless the user
explicitly asks for a change (which must be confirmed).

1. **SSIDs** — `unifi_wlans`: list each wireless network, enabled state, security
   (WPA mode), guest flag, and which network/VLAN it maps to. Do not print PSKs
   unless asked.
2. **APs** — `unifi_devices`: for each access point, show client count (`num_sta`),
   version, and load.
3. **Client signal** — `unifi_clients(active_only=True)`: bucket wifi clients by
   signal quality (good ≥ −60, ok −60…−72, weak < −72 dBm) and list the weak ones
   with their AP.
4. **RF neighborhood** — `unifi_rogue_aps`: summarize how congested the channels are
   (count of nearby APs per band / strong co-channel neighbors).
5. If `$ARGUMENTS` names an SSID, focus the report on it.

## Output

Lead with a one-line verdict on the wireless health. Then: SSID table, per-AP load,
weak-signal clients, and RF congestion notes. Offer concrete, **optional**
suggestions (e.g. "AP X is on a congested channel", "guest SSID has no client
isolation") — but make no changes without explicit confirmation.
