#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the radarr MCP server against the live system.

Imports server.py, then calls each curated tool and prints the result shape.
Does NOT call any confirm-gated write tool. Run with:
    cd radarr-control && uv run --script mcp/_smoketest.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Import the server module (it's a uv-script; we need to import it as a module)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
# Skip the uv shebang by setting __name__ appropriately
spec.loader.exec_module(server)


def show(name: str, result):
    print(f"\n=== {name} ===")
    if isinstance(result, dict) and "error" in result:
        print(f"  ERROR: {result['error']}")
        return False
    # Compact dump
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("radarr_status",                 server.radarr_status),
    ("radarr_list_endpoints",         lambda: server.radarr_list_endpoints(search="movie", limit=8)),
    ("radarr_system_tasks",           server.radarr_system_tasks),
    ("radarr_system_backups",         server.radarr_system_backups),
    ("radarr_list_movies (compact)",  lambda: server.radarr_list_movies(page=1, page_size=5)),
    ("radarr_quality_profiles",       server.radarr_quality_profiles),
    ("radarr_root_folders",           server.radarr_root_folders),
    ("radarr_tags",                   server.radarr_tags),
    ("radarr_languages",              server.radarr_languages),
    ("radarr_notifications",          server.radarr_notifications),
    ("radarr_download_clients",       server.radarr_download_clients),
    ("radarr_indexers",               server.radarr_indexers),
    ("radarr_import_lists",           server.radarr_import_lists),
    ("radarr_custom_formats",         server.radarr_custom_formats),
    ("radarr_collections",            lambda: server.radarr_collections()),
    ("radarr_queue",                  server.radarr_queue),
    ("radarr_wanted_missing",         lambda: server.radarr_wanted_missing(page=1, page_size=3)),
    ("radarr_wanted_cutoff",          lambda: server.radarr_wanted_cutoff(page=1, page_size=3)),
    ("radarr_blocklist",              lambda: server.radarr_blocklist(page=1, page_size=3)),
    ("radarr_logs",                   lambda: server.radarr_logs(level="warn", page=1, page_size=3)),
    ("radarr_calendar",               lambda: server.radarr_calendar()),
    ("radarr_lookup_movies (dune)",   lambda: server.radarr_lookup_movies(term="dune", limit=3)),
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
