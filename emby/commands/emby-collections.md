---
description: Deep Emby collection management — create/populate by query, franchises, smart sync, reverse lookup, artwork
argument-hint: e.g. "make a Halloween collection", "find franchises", "sync X with horror", "which collections has Y"
---

# Emby collections

Full collection management via the `emby` MCP tools (reference:
emby-control skill, metadata-editing.md §4). Writes preview → approval →
confirm.

Parse `$ARGUMENTS`:

- **"list" / no args** → `emby_collection("list")` (with child counts); for a
  named collection `("items", collection_id)`.
- **Create from a query** (e.g. "Halloween collection from horror movies") →
  `emby_collection("create", name=..., genres="Horror", ...)` WITHOUT confirm
  first — it returns every matched title; show me, then confirm. (Explicit
  `item_ids` also works.)
- **"find franchises"** → `emby_collection("find_franchises")`. Present the
  candidate groups and WARN about name-collisions (remakes share titles —
  e.g. The Lorax 1972 vs 2012 group together). Create only the groups I
  approve, then `emby_refresh_item` each new collection to pull TMDb
  art/overview.
- **Smart sync** (e.g. "keep X updated with all horror") →
  `emby_collection("sync_query", collection_id=..., genres=...)` — preview
  lists what would be added (sync is add-only).
- **Reverse lookup** ("which collections is X in") → resolve the item via
  `emby_search`, then `emby_collection("for_item", item_ids=id)`.
- **Add/remove** → resolve names, preview, confirm; report new member count.
- **Finishing touches** → poster: `emby_images(collection_id, "search",
  image_type="Primary")` → show candidates → download my pick; overview/sort:
  `emby_update_item(collection_id, ...)`.

Always report the collection's member count after changes.
