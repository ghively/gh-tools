#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "ruamel.yaml>=0.18",
# ]
# ///
"""Smoke test the searxng MCP server against the live instance.

Imports searxng_server.py, then calls each read-only tool and prints the result
shape. Does NOT call any confirm-gated write tool. Exits 0 (skip) when no
config.local.json / SEARXNG_* env is present. Run with:
    cd searxng-control && uv run --script mcp/_smoketest.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Skip gracefully when there is nothing to test against.
_here = Path(__file__).resolve().parent
_cfg_path = os.environ.get("SEARXNG_CONFIG") or str(_here.parent / "config.local.json")
if not os.path.exists(_cfg_path) and not os.environ.get("SEARXNG_BASE_URL"):
    print(f"SKIP: no config.local.json at {_cfg_path} and no SEARXNG_BASE_URL set.")
    sys.exit(0)
os.environ.setdefault("SEARXNG_CONFIG", _cfg_path)

# Import the server module (it's a uv-script; we need to import it as a module)
sys.path.insert(0, str(_here))
import importlib.util
spec = importlib.util.spec_from_file_location("server", _here / "searxng_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def show(name: str, result):
    print(f"\n=== {name} ===")
    if isinstance(result, str) and result.startswith("ERROR:"):
        print(f"  {result[:400]}")
        return False
    text = result if isinstance(result, str) else json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("searx_status",                server.searx_status),
    ("searx_endpoints",             server.searx_endpoints),
    ("searx_search (linux)",        lambda: server.searx_search(q="linux", limit=3)),
    ("searx_search (bing,mojeek)",  lambda: server.searx_search(q="linux", engines="bing,mojeek", limit=3)),
    ("searx_autocomplete",          lambda: server.searx_autocomplete(q="linu")),
    ("searx_config",                server.searx_config),
    ("searx_config (categories)",   lambda: server.searx_config(section="categories")),
    ("searx_engines (general)",     lambda: server.searx_engines(category="general", enabled_only=True)),
    ("searx_engine_errors",         server.searx_engine_errors),
    ("searx_stats",                 server.searx_stats),
    ("searx_health",                server.searx_health),
    ("searx_http (/healthz)",       lambda: server.searx_http(path="/healthz")),
]
if server.SSH_HOST:
    tools += [
        ("searx_settings_read (search)", lambda: server.searx_settings_read(section="search")),
        ("searx_settings_backups",       server.searx_settings_backups),
        ("searx_logs",                   lambda: server.searx_logs(lines=20)),
    ]
else:
    print("NOTE: no ssh_host configured; skipping config-layer read tools.")

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
