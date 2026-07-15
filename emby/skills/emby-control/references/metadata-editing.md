# Deep metadata, artwork, collections & library management (live-verified)

The complete toolkit for curating an Emby library. Everything here was
verified against gh-media (4.7.14.0). All writes preview-then-confirm.

## 1. Editing an item's metadata — `emby_update_item`

Round-trips the FULL item object with your patch merged (never hand-POST a
partial object). Editable fields (the dashboard metadata editor's surface):

| Field | Shape / notes |
|---|---|
| `Name`, `OriginalTitle`, `SortName`, `ForcedSortName` | strings |
| `Overview` | string (plot) |
| `Genres` | `["Horror", "Comedy"]` — replaces the whole list |
| `Tags` | `["kids-safe", "holiday"]` — great for policy `BlockedTags` parental control |
| `Studios` | `[{"Name": "A24"}]` |
| `People` | `[{"Name": "...", "Role": "...", "Type": "Actor"|"Director"|"Writer"}]` — replaces cast |
| `OfficialRating` | "PG-13", "TV-MA"... (drives parental controls) |
| `CustomRating`, `CommunityRating`, `CriticRating` | strings / floats |
| `ProductionYear`, `PremiereDate`, `EndDate` | int / ISO date |
| `ProviderIds` | `{"Imdb": "tt...", "Tmdb": "...", "Tvdb": "..."}` — controls matching |
| `TagLines` | `["..."]` |
| `LockedFields` | e.g. `["Name", "Overview", "Genres"]` — **protects your manual edits from being overwritten by future refreshes**; also `IsLocked: true` locks everything |
| `PreferredMetadataLanguage`, `PreferredMetadataCountryCode` | per-item override |

**Golden workflow for manual edits**: patch the field AND add it to
`LockedFields` in the same call, or a later `emby_refresh_item` will undo you.

Bulk editing pattern: `emby_items(...)` to collect ids → loop
`emby_update_item(id, patch, confirm=true)` (one user approval for the batch,
but list every affected item first).

## 2. Fixing a wrong match — `emby_identify`

1. `emby_identify(id, "providers")` — which external ids apply (IMDb/TMDb/TVDB).
2. `emby_identify(id, "search", name=..., year=...)` — or exact:
   `provider_ids='{"Imdb": "tt1375666"}'`. Returns candidates with posters.
3. Show the user the candidates; then
   `emby_identify(id, "apply", result_json=<chosen candidate verbatim>,
   replace_images=..., confirm=true)`. This rewrites metadata (and optionally
   art) from the new match; a refresh is queued automatically.

## 3. Artwork — `emby_images`

- `list` — what the item has (Primary/Backdrop/Logo/Thumb + dimensions).
- `providers` → `search` (per `image_type`, optionally per provider; results
  carry Url/size/language/community rating) → present top candidates →
  `download(url, confirm=true)` to adopt one.
- `delete(image_type, index)` — remove bad art (Backdrops are indexed).
- Works on ANY item type **including collections** (BoxSets), seasons, people.
- Upload from arbitrary URL not in providers: same `download` action — Emby
  fetches whatever URL you give it.

## 4. Collections — deep curation (`emby_collection`)

Collections ARE items (Type=BoxSet), so the whole metadata toolkit applies.

| Action | What it does |
|---|---|
| `list` / `items` | Browse collections / one collection's contents |
| `for_item` | Reverse lookup: which collections contain item X (verified: `ListItemIds` query) |
| `create` | New collection from explicit `item_ids` OR directly from a query (`genres="Horror"` → preview shows every matched title first) |
| `add` / `remove` | Membership edits (returns new member count) |
| `sync_query` | Smart-collection refresh: adds every query match not yet a member (add-only; preview lists them) |
| `find_franchises` | Scans movie names for uncollected franchises (e.g. sequels). NAME-HEURISTIC: same-title remakes (The Lorax 1972/2012) collide — always review with the user before creating. TMDb collection names are NOT exposed by Emby 4.7 (the `TmdbCollectionName` field is 4.8+ — verified absent) |

Finishing touches after create: `emby_refresh_item(collection_id)` pulls TMDb
collection artwork/overview when the members map to a known TMDb collection;
or set manually — poster `emby_images(collection_id, "search"/"download")`,
overview/sort `emby_update_item(collection_id, '{"Overview": ...,
"ForcedSortName": ...}')`.

## 4b. Duplicates & versions (`emby_versions`)

- `find_duplicates` — groups movies sharing a TMDb/IMDb id (found 5 real
  groups on gh-media: two downloaded copies each). Options per group:
  **merge** them into one entry with quality versions
  (`POST /Videos/MergeVersions` — files untouched, reversible with `split`),
  or `emby_delete_item` the redundant copy (removes the FILE).
- `list` — versions of a merged item. `split` — un-merge.

## 4c. Bulk metadata editing (`emby_bulk_update`)

One patch applied to every item matching an emby_items-style query. Preview
(no confirm) returns the full affected list — ALWAYS show it. `lock_edited`
(default true) adds patched fields to each item's `LockedFields` so refreshes
don't undo the batch. List fields (Genres/Tags/Studios) REPLACE per item —
to append a tag, this is still safe (the patch is the same for all), but to
merge per-item lists you must loop `emby_update_item` instead.

## 4d. Conversion & sync jobs (`emby_sync_jobs`) — Premiere

- `targets` — devices + the two conversion targets: `originalmediafolder`
  (converted file saved next to original) and `originalmediafolderreplace`
  (REPLACES the original file — warn loudly).
- `create(target_id, item_ids, quality/container/bitrate)` — e.g. pre-convert
  transcode-heavy items to H.264 MP4 so every client direct-plays.
- `jobs` / `cancel` — monitor and manage (conversion runs as the
  "Convert media" scheduled task).

## 4e. Missing episodes

`emby_items(include_types="Episode", is_missing="true", fields="SeriesName")`
— episodes the metadata providers say exist but aren't on disk (125 tracked on
gh-media). Group by SeriesName for a "gaps report". Users only see these if
their display preference "Display missing episodes" is on.

## 5. Subtitles — `emby_subtitles`

- `list` — current streams (embedded + external, with Index and Path).
- `search(language="eng")` — queries Open Subtitles (configured on gh-media);
  results ranked by download count.
- `download(subtitle_id, confirm=true)` — fetches next to the media file
  (per-library `SaveSubtitlesWithMedia`); appears as a new external stream.
- `delete(index, confirm=true)` — external streams only.
- Automatic downloads: per-library `LibraryOptions.SubtitleDownloadLanguages`
  + `SkipSubtitlesIfEmbeddedSubtitlesPresent` etc. via
  `emby_library_manage("update_options", ...)`.

## 6. Library management — `emby_library_manage`

- `create(name, collection_type, path)` — types: movies, tvshows, music,
  musicvideos, homevideos, boxsets, playlists, books, or mixed ("").
- `add_path` / `remove_path` — folders can live on multiple disks/shares.
- `rename`, `delete` (media files stay on disk; Emby metadata is removed).
- `get_options` / `update_options(options_patch)` — the full LibraryOptions
  object round-tripped. High-value keys (all present on gh-media's build):
  `EnableRealtimeMonitor`, `EnableChapterImageExtraction`,
  `ExtractChapterImagesDuringLibraryScan`, `EnableMarkerDetection` (intro
  markers), `DownloadImagesInAdvance`, `SaveLocalMetadata` (NFO),
  `PreferredMetadataLanguage`, `MetadataCountryCode`,
  `SubtitleDownloadLanguages`, `RequirePerfectSubtitleMatch`,
  `SaveSubtitlesWithMedia`, `AutomaticRefreshIntervalDays`,
  `TypeOptions` (per-type fetcher order — which provider wins).

## 7. Config depth map (where every setting lives)

| Area | Read | Write |
|---|---|---|
| Server-wide | `emby_get_config()` | `emby_set_config(patch)` |
| Transcoding | `emby_get_config("encoding")` | `emby_set_config(patch, "encoding")` |
| Per-library | `emby_library_manage("get_options", name)` | `..."update_options"` |
| Per-user permissions | `emby_user(u)` → Policy | `emby_update_user_policy` |
| Per-user preferences (languages, subtitle mode, autoplay) | `emby_user(u)` → Configuration | `emby_call("POST", "/Users/{id}/Configuration", body=<full merged obj>)` |
| Per-plugin | `emby_plugin_config(name)` | `emby_plugin_config(name, patch)` |
| Notifications | `emby_get_config("notifications")` | `emby_set_config(patch, "notifications")` |
| Live TV | `emby_get_config("livetv")` + `emby_livetv_status` | livetv tools |
| Per-item | `emby_item(id)` | `emby_update_item` |
