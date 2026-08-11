#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the gitlab MCP server against the live instance.

Imports gitlab_server.py, verifies confirm-gating offline, then calls a set of
read-only curated tools and prints each result shape. Does NOT execute any
confirm-gated write. Exits 0 with a SKIP message when no config exists
(config.local.json or GITLAB_URL/GITLAB_TOKEN), so it is safe in CI. Run with:
    cd gitlab && uv run --script mcp/_smoketest.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# Import the server module (it's a uv-script; we need to import it as a module)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("gitlab_server", HERE / "gitlab_server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

# ------------------------------------------------------------------ #
# Offline checks: confirm-gating must refuse writes without confirm  #
# (these never touch the network)                                    #
# ------------------------------------------------------------------ #
gate_checks = [
    ("manage_project delete",       lambda: server.manage_project(action="delete", project="x")),
    ("manage_merge_request merge",  lambda: server.manage_merge_request(project="x", action="merge", iid=1)),
    ("branches delete",             lambda: server.branches(project="x", action="delete", name="main")),
    ("write_files commit",          lambda: server.write_files(project="x", branch="b", message="m", actions=[])),
    ("gitlab_rest non-GET",         lambda: server.gitlab_rest("DELETE", "/projects/1")),
    ("gitlab_graphql mutation",     lambda: server.gitlab_graphql("mutation { x }")),
    ("users delete",                lambda: server.users(action="delete", user_id=1)),
]
gate_fail = 0
for name, fn in gate_checks:
    result = fn()
    refused = isinstance(result, dict) and result.get("confirm_required")
    print(f"[{'GATE OK' if refused else 'GATE FAIL'}] {name}")
    if not refused:
        gate_fail += 1
if gate_fail:
    print(f"\n{gate_fail} confirm-gate check(s) FAILED — writes are not properly gated")
    sys.exit(1)

# ------------------------------------------------------------------ #
# Live checks: skip gracefully when unconfigured                     #
# ------------------------------------------------------------------ #
if not server.CONFIG["base_url"] or not server.CONFIG["token"]:
    print("\nSKIP: no config.local.json and no GITLAB_URL/GITLAB_TOKEN set — "
          "confirm-gate checks passed; live read-only checks need a configured instance.")
    sys.exit(0)


def show(name: str, result) -> bool:
    print(f"\n=== {name} ===")
    if isinstance(result, dict) and result.get("error"):
        print(f"  ERROR: {json.dumps(result, default=str)[:400]}")
        return False
    text = json.dumps(result, default=str, indent=2)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("gitlab_status",                server.gitlab_status),
    ("gitlab_api_search (runner)",   lambda: server.gitlab_api_search("runner")),
    ("list_projects (3)",            lambda: server.list_projects(limit=3)),
    ("list_merge_requests (3)",      lambda: server.list_merge_requests(limit=3, state="all")),
    ("list_issues (3)",              lambda: server.list_issues(limit=3, state="all")),
    ("groups list",                  lambda: server.groups(action="list")),
    ("users list",                   lambda: server.users(action="list", params={"per_page": 3})),
    ("todos_and_events (my_events)", lambda: server.todos_and_events(action="my_events")),
    ("templates (gitignores)",       lambda: server.templates(kind="gitignores", action="list")),
    ("search_gitlab (projects)",     lambda: server.search_gitlab(term="a", scope="projects", limit=3)),
    ("markdown render",              lambda: server.markdown("**smoke**")),
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

print(f"\n{'=' * 40}\n{ok} OK, {fail} FAIL (+{len(gate_checks)} gate checks OK)")
sys.exit(0 if fail == 0 else 1)
