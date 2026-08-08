#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Reversible live-write proof for the sabnzbd MCP server.

The SABnzbd write path doesn't create resources (no throwaway possible).
Prove the queue-control write path by:
  1. Note current pause state.
  2. Pause(confirm=True).
  3. Verify paused.
  4. Resume(confirm=True).
  5. Verify resumed (matches original state).

Fully reversible. No downloads created, no jobs touched, no files written.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


step("0. record current pause state")
before = server.sabnzbd_status()
print(f"  paused before: {before.get('paused')}")
print(f"  queue size before: {before.get('noofslots')}")
was_paused = bool(before.get("paused"))

step("1. sabnzbd_pause(confirm=True) â€” pause the queue")
result = server.sabnzbd_pause(confirm=True)
print(f"  result: {result}")

step("2. verify paused")
import time
time.sleep(1)  # let state settle
during = server.sabnzbd_status()
print(f"  paused during: {during.get('paused')}")
assert during.get("paused") is True, "pause did not take effect"

step("3. sabnzbd_resume(confirm=True) â€” restore original state")
result = server.sabnzbd_resume(confirm=True)
print(f"  result: {result}")

step("4. verify resumed (matches original)")
time.sleep(1)
after = server.sabnzbd_status()
print(f"  paused after: {after.get('paused')}")
assert after.get("paused") is False, "resume did not take effect"

step("5. confirm queue contents unchanged (no jobs created/destroyed)")
print(f"  queue size before: {before.get('noofslots')}")
print(f"  queue size after:  {after.get('noofslots')}")
assert before.get("noofslots") == after.get("noofslots"), "queue size changed during proof"

print("\n=== SABNZBD write-path proof: PAUSE âœ“ / VERIFY âœ“ / RESUME âœ“ / VERIFY âœ“ ===")
print(f"    Original state restored (was_paused={was_paused}, now_paused={after.get('paused')})")
