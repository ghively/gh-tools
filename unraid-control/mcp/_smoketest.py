#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "websockets>=12",
#   "paramiko>=3.4",
# ]
# ///
"""Smoke test the unraid MCP server against the live system.

Imports unraid_server.py, then calls each curated READ tool and prints the
result shape. Does NOT call any confirm-gated write tool, and skips the SSH
layer unless SSH credentials are configured. If no config.local.json (or
UNRAID_HOST/UNRAID_API_KEY env) exists, only the offline schema tools run and
the live portion is skipped gracefully (exit 0). Run with:
    cd unraid-control && uv run --script mcp/_smoketest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Import the server module (it's a uv-script; we need to import it as a module)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "unraid_server.py")
server = importlib.util.module_from_spec(spec)
# Skip the uv shebang by setting __name__ appropriately
spec.loader.exec_module(server)


def show(name: str, result):
    print(f"\n=== {name} ===")
    if isinstance(result, dict) and not result.get("success", True):
        print(f"  ERROR: {result.get('error')}")
        return False
    # Compact dump
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


# Offline tools (bundled schema only — no server needed).
offline_tools = [
    ("unraid_schema_search (docker)",  lambda: server.unraid_schema_search(filter="dockerContainerStats", limit=3)),
    ("unraid_schema_type",             lambda: server.unraid_schema_type(name="DockerMutations")),
]

cfg = server.load_config()

# Live read-only tools — no confirm-gated writes, nothing disruptive.
live_tools = [
    ("unraid_status",                  server.unraid_status),
    ("unraid_info",                    server.unraid_info),
    ("unraid_vars",                    server.unraid_vars),
    ("unraid_metrics",                 server.unraid_metrics),
    ("unraid_registration",            server.unraid_registration),
    ("unraid_config_status",           server.unraid_config_status),
    ("unraid_system_time",             server.unraid_system_time),
    ("unraid_logs_list",               server.unraid_logs_list),
    ("unraid_notifications",           lambda: server.unraid_notifications(type="UNREAD", limit=5)),
    ("unraid_array",                   server.unraid_array),
    ("unraid_disks",                   server.unraid_disks),
    ("unraid_assignable_disks",        server.unraid_assignable_disks),
    ("unraid_parity_history",          server.unraid_parity_history),
    ("unraid_docker_containers",       server.unraid_docker_containers),
    ("unraid_docker_networks",         server.unraid_docker_networks),
    ("unraid_vms",                     server.unraid_vms),
    ("unraid_shares",                  server.unraid_shares),
    ("unraid_me",                      server.unraid_me),
    ("unraid_api_keys",                server.unraid_api_keys),
    ("unraid_api_key_roles_catalog",   server.unraid_api_key_roles_catalog),
    ("unraid_network_interfaces",      server.unraid_network_interfaces),
    ("unraid_ups",                     server.unraid_ups),
    ("unraid_ups_config",              server.unraid_ups_config),
    ("unraid_settings",                server.unraid_settings),
    ("unraid_plugins",                 server.unraid_plugins),
    ("unraid_installed_unraid_plugins", server.unraid_installed_unraid_plugins),
    ("unraid_plugin_install_operations", server.unraid_plugin_install_operations),
    ("unraid_rclone_settings",         server.unraid_rclone_settings),
]
# SSH layer is opt-in — only probe it when credentials are configured.
if server._ssh_configured(cfg):
    live_tools.append(("unraid_ssh_test", server.unraid_ssh_test))
else:
    print("(SSH credentials not configured — skipping unraid_ssh_test)")

ok = 0
fail = 0
for name, fn in offline_tools:
    try:
        result = fn()
        if show(name, result):
            ok += 1
        else:
            fail += 1
    except Exception as e:
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

if not cfg.get("host") or not cfg.get("api_key"):
    print(f"\n{'='*40}\n{ok} OK, {fail} FAIL (offline schema tools only)")
    print("No config.local.json / UNRAID_HOST+UNRAID_API_KEY found — "
          "skipping live smoke test. Copy config.example.json to "
          "config.local.json to enable it.")
    sys.exit(0 if fail == 0 else 1)

for name, fn in live_tools:
    try:
        result = fn()
        if show(name, result):
            ok += 1
        else:
            fail += 1
    except Exception as e:
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

print(f"\n{'='*40}\n{ok} OK, {fail} FAIL")
sys.exit(0 if fail == 0 else 1)
