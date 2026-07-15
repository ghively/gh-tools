---
description: Identify and fix unmatched ROMs (hand-match against metadata providers)
argument-hint: (optional) platform or game name to focus on
---

# RomM metadata matching workflow

Fix games RomM couldn't identify, using the `romm` MCP tools.

1. **Collect the unmatched set** — `romm_roms(matched=False, limit=50)`
   (scope by `platform_id` if `$ARGUMENTS` names a platform; resolve via
   `romm_platforms`). If `$ARGUMENTS` names a game, `romm_roms(search_term=...)`.
2. **Check what sources can match** — `romm_status` → enabled metadata
   sources. Hash-based sources (Hasheous) only match known-good dumps; text
   search needs IGDB/ScreenScraper/Moby configured.
3. **For each unmatched ROM** (work in small batches, confirm each with the
   user):
   a. `romm_match_search(rom_id)` — candidates from enabled providers.
   b. If nothing: retry with a cleaned-up `search_term` (strip region tags,
      revision suffixes, scene names).
   c. Present the candidates (name, year, provider id); let the user pick.
   d. Apply: `romm_rom_update(rom_id, provider_ids_json='{"igdb_id": N}',
      confirm=True)` (or ss_id / moby_id / launchbox_id — whichever provider
      the candidate came from).
4. **Bulk retry option** — after fixing folder names or enabling a new
   provider, offer `romm_scan(scan_type="unmatched", confirm=True)` to re-run
   identification across everything.
5. **Truly unmatched leftovers** (homebrew, hacks, prototypes) — offer
   `romm_rom_update` to set a manual `name`/`summary`/`url_cover`, so the
   entry at least displays cleanly.

## Output

Running tally: matched N / skipped M / left unmatched K, with what was applied
for each fixed game.
