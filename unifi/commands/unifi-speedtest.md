---
description: Run a WAN speedtest on the gateway and report the result
---

# UniFi speedtest

Run an internet speedtest on the UniFi gateway and report the result.

1. Confirm with the user first — a speedtest saturates the WAN for ~30 seconds and
   can briefly affect active downloads/calls. If they're good, proceed.
2. Trigger it: `unifi_run_speedtest(confirm=True)`.
3. Poll `unifi_speedtest_status` until the run completes (it reports the run state
   along with results). Give it a few seconds between polls; don't hammer it.
4. Report **download Mbps, upload Mbps, and latency (ms)**, plus the timestamp and
   the WAN/ISP from `unifi_status` for context.

## Output

One clean line with down/up/latency, then a sentence of context (ISP, and whether
the numbers look healthy for that connection). If the test doesn't complete, say so
and show the last status rather than inventing a number.
