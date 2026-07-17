---
description: Run a RomM library scan the right way (choose scan type, trigger, report results)
argument-hint: (optional) scan type or platform, e.g. "complete", "unmatched", "snes"
---

# RomM guided scan

Trigger and monitor a library scan with the `romm` MCP tools.

1. **Pre-flight** — `romm_status`: confirm `scan_trigger_available` is true.
   That only means `username`/`password` are *configured* in
   `config.local.json` — not that login will actually succeed (see step 3).
   If false, tell the user to add those fields; the API key alone can't mint
   the session scans need. Note `filesystem_platform_dirs` — if the folder
   the user expects isn't listed, the scan won't see it; check `romm_config`
   exclusions and the library mount first.
2. **Choose scan type** from `$ARGUMENTS` or ask:
   - `quick` — index new files only (default; cheap).
   - `unmatched` — retry identification of unidentified games.
   - `update` — refresh metadata of already-matched games.
   - `new_platforms` — only platform folders not yet in the DB.
   - `complete` — full rescan (heavy: re-hashes everything; warn first).
   - `hashes` — recompute file hashes only.
   If `$ARGUMENTS` names a platform, resolve its id via `romm_platforms` and
   pass `platform_ids=[id]`.
3. **Confirm with the user**, then `romm_scan(scan_type=..., platform_ids=...,
   confirm=True)`. It only blocks ~20s by default, not the whole scan — do
   not crank `wait_seconds` way up trying to "wait it out" in one call, that
   just leaves the user watching nothing happen. If it errors with
   `login failed (5xx)`, that's RomM's own backend rejecting the login, not a
   plugin/config problem — see the romm-control skill's troubleshooting map.
   Don't retry by hand-replaying the login yourself; report it to the user as
   server-side.
4. **Narrate progress** — if the first response has `"finished": false`, tell
   the user the scan has started, then call `romm_scan_status(wait_seconds=
   20)` in a loop. Each call returns only the NEW `new_events` since the last
   poll (e.g. "scanning platform: snes", "scanning rom: Super Metroid") —
   summarize a batch in one line per poll (don't dump every raw event) so the
   user sees steady progress instead of a long silent wait. Stop looping once
   a response has `"finished": true`.
5. **Report** — the final `stats` (platforms scanned/added, ROMs
   scanned/added/identified) from whichever call finished it. Then
   `romm_stats(include_platform_stats=True)` and `romm_roms(matched=False,
   limit=1)` to state the new unmatched count.
6. **Follow-ups** — if new games are unmatched, offer the `/romm:romm-match`
   workflow; if files were expected but not found, walk the library-structure
   checklist in the romm-control skill.
