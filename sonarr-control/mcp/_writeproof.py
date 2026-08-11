#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
# ]
# ///
"""Reversible live-write proof for the sonarr MCP server.

Adds a throwaway series (Paw Patrol, NOT in the live library), verifies it
appears, deletes it (no file deletion), verifies it's gone.

SELF-CLEANING: any assertion failure still triggers the delete path, so a
test bug can't leave an orphan series in the library.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

THROWAWAY_TVDB = 272472  # Paw Patrol


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


step("0. discover quality + language profile + root folder")
qps = server.sonarr_quality_profiles()
lps = server.sonarr_language_profiles()
roots = server.sonarr_root_folders()
print(f"quality profiles: {[(p['id'], p['name']) for p in qps]}")
print(f"language profiles: {[(p['id'], p['name']) for p in lps]}")
print(f"roots: {[(r['id'], r['path']) for r in roots]}")
qp_id = qps[0]["id"]
lp_id = lps[0]["id"]
root_path = roots[0]["path"]
print(f"using quality_profile_id={qp_id} language_profile_id={lp_id} root_path={root_path!r}")

step("1. confirm throwaway is NOT in library (before add)")
series = server.sonarr_list_series(page=1, page_size=400, compact=True)
title_lc = "paw patrol"
matches = [s for s in series["series"] if title_lc in (s.get("title") or "").lower()]
print(f"matches in library for '{title_lc}': {len(matches)}")
assert not matches, "throwaway already in library — pick another"

added_id = None
try:
    step("2. sonarr_add_series(confirm=True) — monitored=False, search_for_missing=False")
    result = server.sonarr_add_series(
        tvdb_id=THROWAWAY_TVDB,
        quality_profile_id=qp_id,
        language_profile_id=lp_id,
        root_folder_path=root_path,
        monitored=False,
        search_for_missing=False,
        confirm=True,
    )
    print(f"add result: {result}")
    assert result.get("added"), f"add failed: {result}"
    added_id = result["series"]["id"]
    print(f"created series id: {added_id}")

    step("3. verify via sonarr_get_series")
    got = server.sonarr_get_series(added_id, include_episodes=False)
    print(f"  title: {got.get('title')}")
    print(f"  tvdbId: {got.get('tvdbId')}")
    print(f"  monitored: {got.get('monitored')}")
    print(f"  seasonCount: {len(got.get('seasons') or [])}")
    # Title from POST response may differ in case from the lookup; compare loosely.
    assert title_lc in (got.get("title") or "").lower(), \
        f"title mismatch: expected ~{title_lc}, got {got.get('title')!r}"
    assert got.get("tvdbId") == THROWAWAY_TVDB

    step("4. sonarr_delete_series(confirm=True) — delete_files=False")
    deleted = server.sonarr_delete_series(series_id=added_id, delete_files=False, confirm=True)
    print(f"delete result: {deleted}")
    assert deleted.get("deleted")
    added_id = None  # cleaned up; don't retry in finally

    step("5. verify via sonarr_get_series — should 404")
    got_after = server.sonarr_get_series(added_id or -1, include_episodes=False) if added_id else server.sonarr_get_series(result["series"]["id"], include_episodes=False)
    print(f"  after-delete get: {got_after}")
    assert "error" in got_after and "404" in got_after["error"], "expected 404 after delete"

    step("6. final library check")
    series_after = server.sonarr_list_series(page=1, page_size=400, compact=True)
    matches_after = [s for s in series_after["series"] if title_lc in (s.get("title") or "").lower()]
    print(f"matches in library after delete: {len(matches_after)}")
    assert not matches_after, "throwaway still in library"

    print("\n=== SONARR write-path proof: ADD ✓ / VERIFY ✓ / DELETE ✓ / VERIFY-GONE ✓ ===")
finally:
    # Safety net: if anything above failed AFTER the add succeeded, still delete.
    if added_id is not None:
        print(f"\n[CLEANUP] test failed after add; deleting orphan series {added_id}")
        try:
            server.sonarr_delete_series(series_id=added_id, delete_files=False, confirm=True)
            print(f"[CLEANUP] deleted {added_id}")
        except Exception as e:
            print(f"[CLEANUP] FAILED to delete {added_id}: {e}")
