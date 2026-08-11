#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the synology MCP server against the live NAS.

Imports synology_server.py, then calls each curated READ-ONLY tool and prints the
result shape. Does NOT call any confirm-gated or write tool. Run with:
    cd synology-nas && uv run --script mcp/_smoketest.py

Exits 0 with a notice (no failure) when no config.local.json / SYNOLOGY_* env is
present, so it is safe in checkouts without credentials.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Import the server module (it's a uv-script; we need to import it as a module)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("synology_server", HERE / "synology_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

cfg = server.load_config()
if not (cfg.get("host") and cfg.get("username") and cfg.get("password")):
    print("No config.local.json (and no SYNOLOGY_HOST/USERNAME/PASSWORD env) found; "
          "skipping live smoke test.", file=sys.stderr)
    sys.exit(0)


def show(name: str, result) -> bool:
    print(f"\n=== {name} ===")
    if isinstance(result, dict) and not result.get("success", True):
        print(f"  ERROR: {result.get('error')}")
        return False
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("synology_status",                server.synology_status),
    ("synology_list_apis (Core.System)", lambda: server.synology_list_apis(filter="Core.System", limit=8)),
    ("synology_system_info",           server.synology_system_info),
    ("synology_utilization",           server.synology_utilization),
    ("synology_logs",                  lambda: server.synology_logs(limit=5)),
    ("synology_storage",               server.synology_storage),
    ("synology_packages_list",         server.synology_packages_list),
    ("synology_services_list",         server.synology_services_list),
    ("synology_fs_shares",             server.synology_fs_shares),
    # list whatever share actually exists rather than assuming /home (the
    # user-home service may be disabled, which returns DSM error 408)
    ("synology_fs_list (first share)", lambda: server.synology_fs_list(
        folder_path=server.synology_fs_shares()["data"]["shares"][0]["path"], limit=5)),
    ("synology_users_list",            server.synology_users_list),
    ("synology_groups_list",           server.synology_groups_list),
    ("synology_shares_list",           server.synology_shares_list),
    ("synology_downloads_list",        server.synology_downloads_list),
    ("synology_containers_list",       server.synology_containers_list),
    ("synology_images_list",           server.synology_images_list),
    ("synology_projects_list",         server.synology_projects_list),
    ("synology_package_available",     server.synology_package_available),
    ("synology_dsm_update_check",      server.synology_dsm_update_check),
    ("synology_scheduler_list",        server.synology_scheduler_list),
    ("synology_firewall_status",       server.synology_firewall_status),
    ("synology_backup_hyper_tasks",    server.synology_backup_hyper_tasks),
    ("synology_backup_active_devices", server.synology_backup_active_devices),
    ("synology_backup_active_logs",    lambda: server.synology_backup_active_logs(limit=5)),
]

ok = 0
fail = 0
for name, fn in tools:
    try:
        result = fn()
        if show(name, result):
            ok += 1
        else:
            fail += 1
    except Exception as e:  # noqa: BLE001
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

print(f"\n{'=' * 40}\n{ok} OK, {fail} FAIL")
sys.exit(0 if fail == 0 else 1)
