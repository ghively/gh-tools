#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Smoke test the opencode MCP server against a live `opencode serve`.

Imports server.py, then calls the curated READ-ONLY tools and prints the result
shape. Does NOT call any confirm-gated write tool, does NOT run any model
(no oc_prompt / oc_acp_*), and does NOT spawn opencode. Run with:
    cd opencode-control && uv run --script mcp/_smoketest.py

Exits 0 with a note if no server is reachable (e.g. no config.local.json and
nothing listening on the default port) — that is not a failure of this plugin.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Import the server module (it's a uv-script; we need to import it as a module)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def show(name: str, result) -> bool:
    print(f"\n=== {name} ===")
    text = result if isinstance(result, str) else str(result)
    bad = text.startswith("Cannot reach") or text.startswith("HTTP ")
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    if bad:
        print("  ^^ FAIL")
    return not bad


async def main() -> int:
    # Gate on reachability first — everything HTTP needs a live server.
    status = await server.oc_status()
    if isinstance(status, str) and status.startswith("Cannot reach"):
        print(status)
        print("\nNo opencode server reachable — skipping smoketest (this is OK).")
        print("Start one with `opencode serve --port 4096` (or oc_server(action='start')) "
              "and set base_url in config.local.json, then re-run.")
        return 0
    status_ok = show("oc_status", status)

    tools = [
        ("oc_server (status)",     lambda: server.oc_server(action="status")),
        ("oc_discover (session)",  lambda: server.oc_discover(query="session", limit=10)),
        ("oc_schema",              lambda: server.oc_schema("session.prompt")),
        ("oc_sessions",            lambda: server.oc_sessions(limit=5)),
        ("oc_agents",              server.oc_agents),
        ("oc_commands",            server.oc_commands),
        ("oc_skills",              server.oc_skills),
        ("oc_models",              server.oc_models),
        ("oc_providers",           server.oc_providers),
        ("oc_config_get (merged)", lambda: server.oc_config_get(scope="merged")),
        ("oc_mcp (status)",        lambda: server.oc_mcp(action="status")),
        ("oc_tools (ids)",         server.oc_tools),
        ("oc_resources",           server.oc_resources),
        ("oc_diagnostics",         server.oc_diagnostics),
        ("oc_projects (list)",     lambda: server.oc_projects(action="list")),
        ("oc_projects (current)",  lambda: server.oc_projects(action="current")),
        ("oc_worktree (list)",     lambda: server.oc_worktree(action="list")),
        ("oc_find (text)",         lambda: server.oc_find("TODO", kind="text", limit=5)),
        ("oc_file (list root)",    lambda: server.oc_file()),
        ("oc_vcs (status)",        lambda: server.oc_vcs(action="status")),
        ("oc_permissions (list)",  lambda: server.oc_permissions(action="list")),
        ("oc_questions (list)",    lambda: server.oc_questions(action="list")),
        ("oc_pty (shells)",        lambda: server.oc_pty(action="shells")),
        ("oc_pty (list)",          lambda: server.oc_pty(action="list")),
        ("oc_events (2s)",         lambda: server.oc_events(seconds=2.0, limit=10)),
    ]

    ok, fail = (1, 0) if status_ok else (0, 1)
    for name, fn in tools:
        try:
            if show(name, await fn()):
                ok += 1
            else:
                fail += 1
        except Exception as e:  # noqa: BLE001
            print(f"\n=== {name} ===\n  EXCEPTION: {e}")
            fail += 1

    print(f"\n{'=' * 40}\n{ok} OK, {fail} FAIL")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
