#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Reversible write proof for the Tdarr MCP server.

Proves the write path by:
  1. Snapshot current backups.
  2. create_backup(confirm=True).
  3. Verify it appears in tdarr_backups.
  4. delete_backup(confirm=True) the new one.
  5. Verify the system is back to original state.

Fully reversible — no other state touched. Run after first deployment to
convert 'method-verified' writes to 'live-verified'.
"""
from __future__ import annotations
import sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)


def step(msg): print(f"\n=== {msg} ===")


step("0. snapshot current backups")
before = srv.tdarr_backups()
if not isinstance(before, list):
    print(f"  ERROR: tdarr_backups returned non-list: {before}")
    sys.exit(1)
print(f"  before: {len(before)} backups")

step("1. create_backup(confirm=True)")
r = srv.tdarr_create_backup(confirm=True)
print(f"  result: {r}")
if not (r is True or r == {"status": True} or r == True):
    print(f"  unexpected create response — proceeding if list grows anyway")

time.sleep(2)  # let the backup file land on disk

step("2. verify backup appears in tdarr_backups")
after = srv.tdarr_backups()
print(f"  after create: {len(after)} backups")
if not isinstance(after, list):
    print(f"  ERROR: non-list result: {after}")
    sys.exit(1)
new = [b for b in after if b not in before]
print(f"  new backups: {len(new)}")
if not new:
    print("  no new backup detected — create may not have completed; aborting")
    sys.exit(1)

target = new[0]
name = None
if isinstance(target, dict):
    name = target.get("name") or target.get("fileName") or target.get("file")
elif isinstance(target, str):
    name = target
print(f"  target name: {name}")
if not name:
    print(f"  ERROR: could not determine backup name from {target!r}; "
          f"delete it manually via the Tdarr UI")
    sys.exit(1)

step("3. delete_backup(name, confirm=True)")
r = srv.tdarr_delete_backup(name=name, confirm=True)
print(f"  result: {r}")

step("4. verify system restored to original state")
time.sleep(1)
final = srv.tdarr_backups()
print(f"  after delete: {len(final) if isinstance(final, list) else final}")
if isinstance(final, list) and target not in final:
    print("\n=== Tdarr backup write-path proof PASSED ===")
    print(f"    create ✓ / verify ✓ / delete ✓ / verify-gone ✓")
else:
    print("\n=== Tdarr backup write-path proof FAILED — backup still present ===")
    sys.exit(1)
