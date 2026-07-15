---
description: Fix/curate Emby metadata — edit fields, re-identify wrong matches, artwork, subtitles
argument-hint: e.g. "fix the poster for Inception", "re-match X", "edit overview of Y"
---

# Emby metadata curation

Curate item metadata using the `emby` MCP tools (see the emby-control skill's
metadata-editing reference). Writes preview → my approval → confirm.

1. Resolve the target: `emby_search` for the named item; disambiguate with me
   if multiple matches. `emby_item(id)` to show current state.
2. Route by intent in `$ARGUMENTS`:
   - **Edit fields** (overview, genres, tags, rating, cast...) →
     `emby_update_item`. IMPORTANT: also add edited fields to `LockedFields`
     in the same patch so future refreshes don't overwrite my edit — mention
     you're doing this.
   - **Wrong match / re-identify** → `emby_identify(id, "search", ...)`;
     show me the candidates (name, year, provider ids); apply my pick with
     `replace_images` per my preference.
   - **Artwork** → `emby_images(id, "search", image_type=...)`; present the
     top candidates (provider, size, rating, url); `download` my pick. For
     bad art: `delete`.
   - **Subtitles** → `emby_subtitles(id, "search", language=...)`; show top
     results by download count; `download` my pick; verify with `list` after.
   - **Refresh from providers** → `emby_refresh_item` (warn that
     replace_all_metadata overwrites manual edits unless locked).
3. Verify after every write by re-reading, and show me before/after for the
   changed fields.
