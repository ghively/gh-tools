#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the romarr MCP server against the live system."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def show(name: str, result):
    print(f"\n=== {name} ===")
    if isinstance(result, dict) and result.get("error"):
        print(f"  ERROR: {result['error']}")
        return False
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 900:
        text = text[:900] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("romarr_status",                server.romarr_status),
    ("romarr_health",                server.romarr_health),
    ("romarr_system_counts",         server.romarr_system_counts),
    ("romarr_config",                server.romarr_config),
    ("romarr_endpoints",             lambda: server.romarr_endpoints(search="collection", limit=10)),
    ("romarr_platforms",             server.romarr_platforms),
    ("romarr_library",               lambda: server.romarr_library()),
    ("romarr_wanted_missing",        server.romarr_wanted_missing),
    ("romarr_calendar",              server.romarr_calendar),
    ("romarr_tags",                  server.romarr_tags),
    ("romarr_frontend_formats",      server.romarr_frontend_formats),
    ("romarr_queue",                 server.romarr_queue),
    ("romarr_history",               server.romarr_history),
    ("romarr_blocklist",             server.romarr_blocklist),
    ("romarr_collections",           server.romarr_collections),
    ("romarr_indexers",              server.romarr_indexers),
    ("romarr_indexer_schema",        server.romarr_indexer_schema),
    ("romarr_download_clients",      server.romarr_download_clients),
    ("romarr_download_client_schema", server.romarr_download_client_schema),
    ("romarr_libraries",             server.romarr_libraries),
    ("romarr_library_schema",        server.romarr_library_schema),
    ("romarr_connection_schema",     server.romarr_connection_schema),
    ("romarr_metadata_schema",       server.romarr_metadata_schema),
    ("romarr_hub_status",            server.romarr_hub_status),
    ("romarr_hub_plugins",           server.romarr_hub_plugins),
    ("romarr_hub_catalogue",         server.romarr_hub_catalogue),
    ("romarr_backup (masked)",       lambda: server.romarr_backup()),
    ("romarr_logs",                  lambda: server.romarr_logs(limit=10)),
    ("romarr_search",                lambda: server.romarr_search(game="mario")),
    ("romarr_release",               lambda: server.romarr_release(game="Super Mario World", platform="snes")),
    ("romarr_command (dry, no confirm)", lambda: server.romarr_command(name="Search")),
    ("romarr_request (dry, no confirm)", lambda: server.romarr_request(title="test")),
    # Round 2: remaining reads + safe write-probes (confirm=False never mutates)
    ("romarr_export",                 lambda: server.romarr_export(kind="library", fmt="json")),
    ("romarr_manual_import",          lambda: server.romarr_manual_import()),
    ("romarr_library_config",         lambda: server.romarr_library_config(library_id="1b105619315a")),
    ("romarr_library_test (probe)",   lambda: server.romarr_library_test({})),
    ("romarr_indexer_test (probe)",   lambda: server.romarr_indexer_test({})),
    ("romarr_download_client_test (probe)", lambda: server.romarr_download_client_test({})),
    ("romarr_hub_source_check",       lambda: server.romarr_hub_source_check(url="https://github.com/BlizzHacker/rom-hub")),
    ("romarr_metadata_lookup (probe)", lambda: server.romarr_metadata_lookup({})),
    ("romarr_collection_plan (probe)", lambda: server.romarr_collection_plan({})),
    ("romarr_release_grab (dry, no confirm)", lambda: server.romarr_release_grab(release_id="x")),
    ("romarr_restore (dry, no confirm)", lambda: server.romarr_restore(backup={})),
    ("romarr_collection_start (dry, no confirm)", lambda: server.romarr_collection_start(plan={})),
    ("romarr_collection_step (dry, no confirm)", lambda: server.romarr_collection_step(batch_id="x")),
    ("romarr_collection_control (dry, no confirm)", lambda: server.romarr_collection_control(batch_id="x", action="pause")),
    ("romarr_connection_test (dry, no confirm)", lambda: server.romarr_connection_test()),
    ("romarr_hub_plugin (dry, no confirm)", lambda: server.romarr_hub_plugin(plugin_id="x", action="install")),
    ("romarr_import (dry, no confirm)", lambda: server.romarr_import(payload={})),
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
    except Exception as e:
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

print(f"\n{'='*40}\n{ok} OK, {fail} FAIL")
sys.exit(0 if fail == 0 else 1)
