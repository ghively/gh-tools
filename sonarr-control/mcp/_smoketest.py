#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the sonarr MCP server against the live system."""
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
    if isinstance(result, dict) and "error" in result:
        print(f"  ERROR: {result['error']}")
        return False
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("sonarr_status",                 server.sonarr_status),
    ("sonarr_list_endpoints",         lambda: server.sonarr_list_endpoints(search="series", limit=8)),
    ("sonarr_system_tasks",           server.sonarr_system_tasks),
    ("sonarr_system_backups",         server.sonarr_system_backups),
    ("sonarr_list_series (compact)",  lambda: server.sonarr_list_series(page=1, page_size=5)),
    ("sonarr_quality_profiles",       server.sonarr_quality_profiles),
    ("sonarr_language_profiles",      server.sonarr_language_profiles),
    ("sonarr_root_folders",           server.sonarr_root_folders),
    ("sonarr_tags",                   server.sonarr_tags),
    ("sonarr_notifications",          server.sonarr_notifications),
    ("sonarr_download_clients",       server.sonarr_download_clients),
    ("sonarr_indexers",               server.sonarr_indexers),
    ("sonarr_import_lists",           server.sonarr_import_lists),
    ("sonarr_queue",                  server.sonarr_queue),
    ("sonarr_wanted_missing",         lambda: server.sonarr_wanted_missing(page=1, page_size=3)),
    ("sonarr_wanted_cutoff",          lambda: server.sonarr_wanted_cutoff(page=1, page_size=3)),
    ("sonarr_blocklist",              lambda: server.sonarr_blocklist(page=1, page_size=3)),
    ("sonarr_logs",                   lambda: server.sonarr_logs(level="warn", page=1, page_size=3)),
    ("sonarr_calendar",               lambda: server.sonarr_calendar()),
    ("sonarr_lookup_series",          lambda: server.sonarr_lookup_series(term="breaking bad", limit=3)),
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
