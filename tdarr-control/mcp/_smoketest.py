#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the Tdarr MCP server.

**Plugin was LIVE-VERIFIED on Tdarr 2.x (2026-07-20).** This is the
re-verification harness. If Tdarr is not reachable from where you run it
(e.g. an offline session, or config.local.json not filled in), every network
tool fails with a connection error — that's environmental, not a plugin bug.

Run it whenever you want to re-confirm against a live server:

    cd tdarr-control && uv run --script mcp/_smoketest.py

Its current job is to close the "added-post-verification" gap — the tools
written after the 2026-07-20 run (tdarr_libraries, tdarr_staged_files, and the
confirm-gated create_plugin / remove_*_codec_exclude) that have not yet been
re-run live. Write tools are NOT called here (confirm-gated in the server) —
use _writeproof.py after the read paths pass.
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
        err = str(result['error'])[:120]
        print(f"  ERROR: {err}")
        # A connection error means Tdarr isn't deployed yet — that's expected
        if "ConnectError" in err or "Connection" in err or "Errno" in err:
            print("  (Tdarr probably isn't deployed yet — see README)")
        return False
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 600:
        text = text[:600] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("tdarr_status",              server.tdarr_status),
    ("tdarr_full_status",         server.tdarr_full_status),
    ("tdarr_nodes",               server.tdarr_nodes),
    ("tdarr_db_statuses",         server.tdarr_db_statuses),
    ("tdarr_performance_stats",   server.tdarr_performance_stats),
    ("tdarr_res_stats",           server.tdarr_res_stats),
    ("tdarr_backup_status",       server.tdarr_backup_status),
    ("tdarr_backups",             server.tdarr_backups),
    ("tdarr_search_db",           lambda: server.tdarr_search_db(string=".mkv", limit=3)),
    ("tdarr_search_plugins",      lambda: server.tdarr_search_plugins(string="")),
    ("tdarr_search_flow_plugins", lambda: server.tdarr_search_flow_plugins(string="")),
    ("tdarr_collections",         server.tdarr_collections),
    ("tdarr_libraries",           server.tdarr_libraries),
    ("tdarr_staged_files",        lambda: server.tdarr_staged_files(limit=3)),
    ("tdarr_list_endpoints",      lambda: server.tdarr_list_endpoints(rw="R")),
    # Confirm-gated (decline path)
    ("tdarr_create_backup(decline)",  server.tdarr_create_backup),
    ("tdarr_kill_worker(decline)",    lambda: server.tdarr_kill_worker(node_id="x", worker_type="cpu")),
    ("tdarr_db(removeAll,decline)",   lambda: server.tdarr_db(mode="removeAll", collection="FileJSONDB")),
]

ok = 0
fail = 0
not_deployed = 0
for name, fn in tools:
    try:
        result = fn()
        if show(name, result):
            ok += 1
        else:
            # Check if it's a connection error (Tdarr not deployed)
            if isinstance(result, dict) and "error" in result:
                if any(s in str(result['error']) for s in ("ConnectError", "Connection", "Errno", "timed out")):
                    not_deployed += 1
            fail += 1
    except Exception as e:
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

print(f"\n{'='*50}")
print(f"{ok} OK, {fail} FAIL")
if not_deployed:
    print(f"\nOf the failures, {not_deployed} are connection errors — Tdarr is "
          f"not reachable from here right now (offline session or config not "
          f"filled in). Re-run where the server is reachable to re-confirm.")
    print("The plugin was LIVE-VERIFIED on Tdarr 2.x; connection errors "
          "here are environmental. See README's gap taxonomy.")
sys.exit(0 if fail == 0 else 1)
