---
description: Show who/what is on the network, with usage, signal, and connection details
argument-hint: (optional) a name/IP/MAC to focus on, or "wifi" / "wired"
---

# Who's on my UniFi network

Report the clients on the network using the `unifi` MCP tools. Read-only.

1. `unifi_clients(active_only=True)` — the currently-connected clients.
2. If `$ARGUMENTS` names a client (substring of name/IP/MAC), focus on it and pull
   its device detail; otherwise summarize all.
3. Group by **wired vs wifi**. For wifi clients, include the AP/ESSID and signal
   (dBm) and flag weak ones (worse than ~−75). For all, show IP, MAC, uptime, and
   session data (rx/tx bytes → human units).
4. Sort by data usage (heaviest first) so the top talkers are obvious.
5. If asked about a device that "should be online" but isn't listed, check
   `unifi_clients(active_only=False)` (known/offline clients) and say when it was
   last seen.

## Output

A short table of the top clients (name, wired/wifi, IP, signal, usage), then a
one-line summary (N connected: X wifi / Y wired). Note anything unusual (an unknown
device, a client hammering bandwidth, a very weak signal). Suggest — but do not
perform — actions like blocking or reconnecting; those need explicit confirmation.
