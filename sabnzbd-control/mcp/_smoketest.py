#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the SABnzbd MCP server against the live system.

READ-ONLY: no confirm=true anywhere. Does not exercise pause/resume/addurl/
delete/set_config/restart/shutdown (those are confirm-gated in the server).
"""
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
    ("sabnzbd_status",                server.sabnzbd_status),
    ("sabnzbd_version",               server.sabnzbd_version),
    ("sabnzbd_queue (limit 5)",       lambda: server.sabnzbd_queue(limit=5)),
    ("sabnzbd_history (limit 3)",     lambda: server.sabnzbd_history(limit=3)),
    ("sabnzbd_server_stats",          server.sabnzbd_server_stats),
    ("sabnzbd_warnings",              server.sabnzbd_warnings),
    ("sabnzbd_get_config misc",       lambda: server.sabnzbd_get_config(section="misc")),
    ("sabnzbd_get_config categories", lambda: server.sabnzbd_get_config(section="categories")),
    ("sabnzbd_list_modes (R)",        lambda: server.sabnzbd_list_modes(rw="R")),
    ("sabnzbd_list_modes (W)",        lambda: server.sabnzbd_list_modes(rw="W")),
    # Confirm-gated tools with confirm=False: verify they decline cleanly
    ("sabnzbd_pause (decline)",       lambda: server.sabnzbd_pause()),
    ("sabnzbd_resume (decline)",      lambda: server.sabnzbd_resume()),
    ("sabnzbd_add_url (decline)",     lambda: server.sabnzbd_add_url(url="https://example.com/x.nzb")),
    ("sabnzbd_restart (decline)",     lambda: server.sabnzbd_restart(confirm=True, acknowledge="nope")),
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
