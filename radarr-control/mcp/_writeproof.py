#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0",
#   "httpx>=0.27",
# ]
# ///
"""Reversible live-write proof for the radarr MCP server.

Adds a throwaway movie (12 Angry Men 1957, NOT in the live library), verifies
it appears, deletes it (no file deletion), verifies it's gone. Drives the
ACTUAL MCP server tools, not raw HTTP — proves the write path of the plugin.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util
spec = importlib.util.spec_from_file_location("server", Path(__file__).resolve().parent / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

THROWAWAY_TMDB = 389  # 12 Angry Men (1957)
THROWAWAY_TITLE = "12 Angry Men"


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


# 0. Setup: discover profile + root folder
step("0. discover quality profile + root folder")
profiles = server.radarr_quality_profiles()
roots = server.radarr_root_folders()
print(f"profiles: {[(p['id'], p['name']) for p in profiles]}")
print(f"roots: {[(r['id'], r['path']) for r in roots]}")
profile_id = profiles[0]["id"]
root_path = roots[0]["path"]
print(f"using profile_id={profile_id} root_path={root_path!r}")

# 1. Confirm throwaway is NOT in library
step("1. confirm throwaway is NOT in library (before add)")
movies = server.radarr_list_movies(page=1, page_size=200, compact=True)
matches = [m for m in movies["movies"] if THROWAWAY_TITLE.lower() in (m.get("title") or "").lower()]
print(f"matches in library for '{THROWAWAY_TITLE}': {len(matches)}")
assert not matches, "throwaway already in library — pick another"

# 2. Add (with confirm=True)
step("2. radarr_add_movie(confirm=True) — search_for_movie=False (no download)")
result = server.radarr_add_movie(
    tmdb_id=THROWAWAY_TMDB,
    quality_profile_id=profile_id,
    root_folder_path=root_path,
    monitored=False,                  # don't monitor — won't trigger anything
    minimum_availability="released",
    search_for_movie=False,           # NO search — won't touch download clients
    confirm=True,
)
print(f"add result: {result}")
assert result.get("added"), f"add failed: {result}"
added_id = result["movie"]["id"]
print(f"created movie id: {added_id}")

# 3. Verify it appears in the library
step("3. verify via radarr_get_movie")
got = server.radarr_get_movie(added_id)
print(f"  title: {got.get('title')}")
print(f"  tmdbId: {got.get('tmdbId')}")
print(f"  monitored: {got.get('monitored')}")
print(f"  hasFile: {got.get('hasFile')}")
assert got.get("title") == THROWAWAY_TITLE
assert got.get("tmdbId") == THROWAWAY_TMDB

# 4. Delete (no file deletion — irreversible otherwise)
step("4. radarr_delete_movie(confirm=True) — delete_files=False")
deleted = server.radarr_delete_movie(movie_id=added_id, delete_files=False, confirm=True)
print(f"delete result: {deleted}")
assert deleted.get("deleted")

# 5. Verify it's gone (GET should 404)
step("5. verify via radarr_get_movie — should 404")
got_after = server.radarr_get_movie(added_id)
print(f"  after-delete get: {got_after}")
assert "error" in got_after and "404" in got_after["error"], "expected 404 after delete"

# 6. Final library check: should not be in list
step("6. final library check")
movies_after = server.radarr_list_movies(page=1, page_size=200, compact=True)
matches_after = [m for m in movies_after["movies"] if THROWAWAY_TITLE.lower() in (m.get("title") or "").lower()]
print(f"matches in library for '{THROWAWAY_TITLE}' after delete: {len(matches_after)}")
assert not matches_after, "throwaway still in library — delete didn't fully clean up"

print("\n=== RADARR write-path proof: ADD ✓ / VERIFY ✓ / DELETE ✓ / VERIFY-GONE ✓ ===")
