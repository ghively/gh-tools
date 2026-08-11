---
description: Create and curate RomM collections (manual, smart, favorites)
argument-hint: what to build, e.g. "smart collection of unbeaten RPGs" or "top Mario games"
---

# RomM collection curation

Build or maintain collections with the `romm` MCP tools. Parse the goal from
`$ARGUMENTS`; ask if ambiguous.

1. **Survey what exists** — `romm_collections(kind="all")`; virtual
   collections via `romm_collections(kind="virtual", virtual_type=...)`
   (types: franchise, genre, company, mode, developer, publisher). Don't
   duplicate an existing or virtual collection — point the user at it
   instead.
2. **Manual collection** — gather candidates with `romm_roms` filters
   (search_term, genres, franchises, platform_id...), show the list, then:
   - `romm_collection_create(name, description, is_public=...)`
   - `romm_collection_roms(collection_id, "add", rom_ids=[...])`
3. **Smart collection** (auto-updating, rule-based) — translate the user's
   criteria into `/api/roms` filter JSON and create with
   `romm_smart_collection_create(name, filter_criteria_json=...)`, e.g.
   unbeaten RPGs: `'{"genres": ["Role-playing (RPG)"], "statuses":
   ["incomplete"]}'` (status vocabulary: incomplete, finished,
   completed_100, retired, never_playing). Verify the rule by running the
   same filters through `romm_roms` first and showing the match count.
4. **Favorites** — a manual collection created with `is_favorite=True`;
   membership drives the `favorite=True` filter in `romm_roms`.
5. **Maintenance** — rename/describe via `romm_collection_update(...,
   confirm=True)`; edit a smart collection's rule/name via
   `romm_smart_collection_update(..., confirm=True)`; delete via
   `romm_collection_delete(..., confirm=True)` (ROMs are never touched by
   collection deletes).

Always show the final collection (`romm_collection(id)`) as proof of what was
built.
