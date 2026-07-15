---
description: Library report or search — browse, find, and inspect media on the Emby server
argument-hint: e.g. "unwatched horror movies", "recently added", or a title to find
---

# Emby library query

Answer a library question using the `emby` MCP tools. Read-only.

Parse `$ARGUMENTS` into a query:

- A title or name → `emby_search(term)`; then `emby_item(id)` for the best match
  (codecs, resolution, path, watched state).
- "recently added" → `emby_items(sort_by="DateCreated", sort_order="Descending", limit=20)`.
- Genre/year/person/watched filters → `emby_items(...)` with the right params
  (`genres=`, `years=`, `person=`, `filters="IsUnplayed"`, `include_types=`).
- "continue watching" / "what should I watch next" → `emby_next_up()`; for
  recommendations `emby_call("GET", "/Movies/Recommendations", params='{"UserId":"<uid>"}')`.
- No arguments → overview: `emby_status` item counts + `emby_libraries()` +
  the 10 most recently added items.

Present results as a compact table (Name, Year, Type, Runtime, Watched, Id).
Include the item Id so follow-up actions (collections, metadata edits) are easy.
