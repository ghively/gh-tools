#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0,<2.0.0", "httpx>=0.27"]
# ///
"""Live smoke test: exercise every read tool + safe write-probes against the
configured UniFi console. Prints a compact PASS/FAIL line per tool. No mutations."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("UNIFI_CONFIG", str(Path(__file__).resolve().parent.parent / "config.local.json"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import unifi_server as U  # noqa: E402


def show(name, res):
    if isinstance(res, dict) and res.get("success"):
        d = res["data"]
        if isinstance(d, dict):
            keys = list(d)
            cnt = d.get("count")
            hint = f"count={cnt}" if cnt is not None else f"keys={keys[:6]}"
        elif isinstance(d, list):
            hint = f"list[{len(d)}]"
        else:
            hint = str(d)[:60]
        print(f"PASS  {name:34} {hint}")
    else:
        print(f"FAIL  {name:34} {res.get('error') if isinstance(res, dict) else res}")


# ---- reads ----
show("unifi_status", U.unifi_status())
show("unifi_sites", U.unifi_sites())
show("unifi_health", U.unifi_health())
show("unifi_sysinfo", U.unifi_sysinfo())
show("unifi_devices", U.unifi_devices())
show("unifi_clients(active)", U.unifi_clients(active_only=True))
show("unifi_clients(known)", U.unifi_clients(active_only=False))
show("unifi_networks", U.unifi_networks())
show("unifi_wlans", U.unifi_wlans())
show("unifi_firewall_rules", U.unifi_firewall_rules())
show("unifi_firewall_groups", U.unifi_firewall_groups())
show("unifi_firewall_policies", U.unifi_firewall_policies())
show("unifi_firewall_zones", U.unifi_firewall_zones())
show("unifi_port_forwards", U.unifi_port_forwards())
show("unifi_routes", U.unifi_routes())
show("unifi_traffic_rules", U.unifi_traffic_rules())
show("unifi_traffic_routes", U.unifi_traffic_routes())
show("unifi_events", U.unifi_events(limit=5))
show("unifi_alarms", U.unifi_alarms())
show("unifi_settings", U.unifi_settings())
show("unifi_rogue_aps", U.unifi_rogue_aps())
show("unifi_wifi_connectivity", U.unifi_wifi_connectivity())
show("unifi_dashboard", U.unifi_dashboard())
show("unifi_stat_report", U.unifi_stat_report())
show("unifi_speedtest_status", U.unifi_speedtest_status())
show("unifi_list_endpoints('firewall')", U.unifi_list_endpoints("firewall"))

# ---- write-tools should REFUSE without confirm (safety gate proof) ----
r = U.unifi_client_block("00:11:22:33:44:55")
print(f"{'PASS' if not r.get('success') else 'FAIL'}  "
      f"{'unifi_client_block gate':34} refused-without-confirm={not r.get('success')}")
r = U.unifi_device_restart("00:11:22:33:44:55")
print(f"{'PASS' if not r.get('success') else 'FAIL'}  "
      f"{'unifi_device_restart gate':34} refused-without-confirm={not r.get('success')}")
