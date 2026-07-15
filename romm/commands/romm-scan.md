---
description: Run a RomM library scan the right way (choose scan type, trigger, report results)
argument-hint: (optional) scan type or platform, e.g. "complete", "unmatched", "snes"
---

# RomM guided scan

Trigger and monitor a library scan with the `romm` MCP tools.

1. **Pre-flight** — `romm_status`: confirm `scan_trigger_available` is true
   (if false, tell the user to add `username`/`password` to the plugin's
   `config.local.json` — RomM only exposes scans over Socket.IO with a session
   login; the API key alone cannot do it). Note `filesystem_platform_dirs` —
   if the folder the user expects isn't listed, the scan won't see it; check
   `romm_config` exclusions and the library mount first.
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
   confirm=True, wait_seconds=300)`.
4. **Report** — the returned stats (platforms scanned/added, ROMs
   scanned/added/identified). Then `romm_stats(include_platform_stats=True)`
   and `romm_roms(matched=False, limit=1)` to state the new unmatched count.
5. **Follow-ups** — if new games are unmatched, offer the `/romm:romm-match`
   workflow; if files were expected but not found, walk the library-structure
   checklist in the romm-control skill.
