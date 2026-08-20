---
name: sonarr-control
description: >-
  Control and administer a Sonarr TV-series manager instance via the sonarr
  MCP server. Use this whenever the user wants to inspect, configure,
  operate, or troubleshoot their Sonarr — including ANY of: server status,
  listing / searching / adding / updating / deleting series, per-season and
  per-episode operations (toggle season monitoring, list episodes, episode
  files), wanted missing/cutoff (per-episode), upcoming calendar (per-airing),
  active download queue, history (incl. per-series), blocklist, quality
  profiles, language profiles (Sonarr-specific), root folders, tags,
  notifications, download clients, indexers, import lists, application logs,
  system tasks, system backups, OR triggering commands (RefreshSeries,
  SeriesSearch, SeasonSearch, EpisodeSearch, EpisodesSearch,
  DownloadedEpisodesScan, RenameSeries, Backup, MissingEpisodesSearch,
  RssSync, etc.). Trigger this skill whenever the user says "Sonarr", "my TV
  shows", "what aired today", "what's missing", "search for show X", "add
  show Y", or "monitor season N of Z" — do not answer from memory; drive
  the live Sonarr server through the tools.
metadata:
  hermes:
    tags: [sonarr, tv, series, media, servarr, mcp, homelab, usenet, torrent]
    category: media
    requires_tools: [sonarr_status]
    config:
      - {key: sonarr.host, prompt: Sonarr host/IP, default: 192.0.2.20}
      - {key: sonarr.port, prompt: Sonarr port, default: 8989}
required_environment_variables:
  - name: SONARR_API_KEY
    prompt: Sonarr API key (Settings > General > Security > API Key)
    required_for: authenticating sonarr_* calls to the /api/v3 REST surface
version: 0.3.0
author: ghively
---

# Sonarr control

This skill drives a real Sonarr TV-series manager through the **`sonarr`
MCP server** (tools shown as `sonarr_*`). Verified against **Sonarr
4.x** on the homelab NAS (`192.0.2.20:8989`, "NAS-Host").
Auth = `X-Api-Key` header (admin API key in 1Password "Homelab" vault).

## Mental model

Sonarr is one REST surface under `/api/v3/<resource>` (~470 operations on
4.x, discovered live via `/system/routes`). Key conventions:

- All writes need the FULL object (PUT /series/{id} resets omitted fields).
  Write tools GET-merge-PUT internally; use `sonarr_update_series(patch=)`,
  never hand-PUT a partial object through `sonarr_call`.
- Commands (`RefreshSeries`, `SeriesSearch`, etc.) are ASYNC — POST
  /command returns a job object; poll with `sonarr_command_status(id)`.
- `/wanted/missing` and `/wanted/cutoff` return EPISODE records (one per
  missing episode), not series — each references its `seriesId`.
- `/calendar` returns EPISODES (one per airing), each with the series
  embedded.
- All writes are **confirm-gated**: pass `confirm=true` only after the user
  explicitly approved.

Two layers: curated tools (prefer), generic passthrough
(`sonarr_call` / `sonarr_list_endpoints` — Sonarr has no OpenAPI; the index
comes live from `/system/routes`, with a hand-enumerated fallback catalog).

**Golden rule:** if a curated tool exists, use it. Otherwise find it with
`sonarr_list_endpoints` then call it with `sonarr_call`. Never guess.

## Start here

Call **`sonarr_status`** first: identity, version, totalSeries,
monitoredSeries, queue summary, health warnings, disks.

## Tool map

| Job | Tool |
|---|---|
| Health snapshot | `sonarr_status` |
| Browse library | `sonarr_list_series(monitored=, page=, page_size=)` |
| One series (with episodes) | `sonarr_get_series(series_id, include_episodes=)` |
| Episodes of a series/season | `sonarr_episodes(series_id, season_number=)` or `sonarr_episodes(episode_ids=[...])` |
| Episode files | `sonarr_episode_files(series_id)` |
| Search for new shows | `sonarr_lookup_series(term="breaking bad")` |
| Add a series (write) | `sonarr_add_series(tvdb_id, quality_profile_id, root_folder_path, ...)` |
| Edit a series (write) | `sonarr_update_series(series_id, patch=)` |
| Bulk-edit series (write) | `sonarr_series_bulk_edit(series_ids, monitored=, quality_profile_id=, ...)` |
| Toggle season monitoring (write) | `sonarr_toggle_season_monitored(series_id, season_number, monitored, confirm=)` |
| Bulk season monitoring (write) | `sonarr_season_pass(series_ids, monitored, confirm=)` |
| Toggle episode monitoring (write) | `sonarr_episode_monitor(episode_ids, monitored, confirm=)` |
| Delete a series (write) | `sonarr_delete_series(series_id, delete_files=, confirm=)` |
| Bulk-delete series (write) | `sonarr_series_bulk_delete(series_ids, delete_files=, confirm=)` |
| Delete an episode file (write) | `sonarr_episode_file_delete(episode_file_id, confirm=)` |
| Preview renames | `sonarr_rename_preview(series_ids)` |
| What's missing (per ep) | `sonarr_wanted_missing()` |
| What's upgradeable | `sonarr_wanted_cutoff()` |
| Upcoming episodes | `sonarr_calendar(start=, end=)` (`.ics` feed: `sonarr_calendar_ics`) |
| Active downloads | `sonarr_queue(page=, page_size=)` |
| Remove / retry queue items (write) | `sonarr_queue_delete`, `sonarr_queue_grab`, `sonarr_queue_bulk_delete` |
| Interactive release search | `sonarr_release_search(episode_id=)` or `(series_id=, season_number=)` |
| Grab a specific release (write) | `sonarr_release_grab(guid, indexer_id, confirm=)` |
| Recent activity | `sonarr_history(series_id=, event_type=)`, `sonarr_history_since(since=)` |
| Auto-rejected releases | `sonarr_blocklist()` (remove: `sonarr_blocklist_delete`, `sonarr_blocklist_bulk_delete`) |
| Parse a release title | `sonarr_parse(title=)` |
| Manual import (write) | `sonarr_manual_import(folder, import_mode=, confirm=)` |
| Logs | `sonarr_logs(level="warn")`, `sonarr_log_files()` |
| Scheduled tasks | `sonarr_system_tasks()` |
| DB backups | `sonarr_system_backups()` |
| Browse server filesystem | `sonarr_filesystem(path=)` |
| Live API route table | `sonarr_system_routes()` |
| Restart / shutdown (write, double-gated) | `sonarr_system_restart`, `sonarr_system_shutdown` |

## Commands (trigger async jobs)

`sonarr_command(name=, series_ids=, episode_ids=, season_number=, confirm=)`
plus conveniences:

- `RefreshSeries` — re-scan disk + refresh metadata.
- `RescanSeries` — disk rescan only (no metadata refresh).
- `SeriesSearch` — search indexers for monitored missing episodes of a series.
- `SeasonSearch` — search for ALL episodes in a series+season (requires
  `series_ids=[X]` and `season_number=N`).
- `EpisodeSearch` / `EpisodesSearch` — search for specific `episode_ids`.
- `MissingEpisodesSearch` — search for ALL monitored missing episodes (heavy).
- `DownloadedEpisodesScan` — scan drone factory / completed downloads.
- `RefreshMonitoredDownloads` — sync with download clients (idempotent).
- `RenameSeries` — rename files using the configured renaming schema.
- `Backup`, `RssSync`, `ApplicationUpdate`.

Convenience wrappers: `sonarr_search_episode`, `sonarr_search_season`,
`sonarr_refresh_series`.

## Configuration tools

Read-only:

- `sonarr_quality_profiles()` — needed before `add_series`.
- `sonarr_language_profiles()` — Sonarr-specific; pass `language_profile_id`
  to `add_series`. Also `sonarr_languages()` for the raw language list.
- `sonarr_root_folders()`, `sonarr_tags()`, `sonarr_tag_details()`,
  `sonarr_notifications()`.
- `sonarr_download_clients()`, `sonarr_indexers()`, `sonarr_import_lists()`,
  `sonarr_import_exclusions()`.
- `sonarr_quality_definitions()`, `sonarr_delay_profiles()`,
  `sonarr_release_profiles()`, `sonarr_remote_path_mappings()`,
  `sonarr_auto_tagging()`, `sonarr_config_section(section=)`.

Writes (confirm-gated):

- `sonarr_update_config_section(section, patch=)` — GET-merge-PUT.
- `sonarr_tag_create(label)`, `sonarr_tag_delete(tag_id)`.
- `sonarr_crud(resource, action, id=, data=)` — unified CRUD for the long
  tail of config entities (notifications, download clients, indexers, import
  lists, metadata, profiles, root folders, remote path mappings, ...).
- `sonarr_provider_test(provider_type, definition)` — test a provider config
  without saving; `sonarr_provider_action` for provider-specific actions.

## Adding a series — workflow

```
sonarr_lookup_series(term="the last of us")
  → tvdb_id, also note seasonCount
sonarr_quality_profiles()    → profile id (e.g. HD-1080p)
sonarr_language_profiles()   → language profile id
sonarr_root_folders()        → exact path (e.g. /volume2/Media/TV)
sonarr_add_series(
    tvdb_id=..., quality_profile_id=..., root_folder_path="...",
    language_profile_id=..., monitored=True,
    season_count=1,           # monitor only S1
    series_type="standard",
    search_for_missing=True,  # trigger initial search
    confirm=True
)
```

State to the user before passing `confirm=True`:
- Which series, from where (TVDB id).
- How many seasons you'll monitor.
- Root folder, quality + language profile.
- Whether you'll trigger an initial search.

## Safety

- **Confirm-gate every write.** `DELETE /series/{id}` with `delete_files=true`
  removes episode files from disk — irreversible.
- `POST /command` triggers active work (indexer queries, disk scans). Even
  "harmless" commands hit external services — say what you'll do first.
- Never run a "test" write without explicit owner approval.

## Honesty

- **Live-verified (reads):** all GETs in the smoke test pass; calendar
  correctly showed today's real airings.
- **Method-verified (writes):** the HTTP shape is correct; live execution
  awaits explicit owner approval.
- **Hard limits:** no OpenAPI; catalog hand-enumerated as of 2026-07-19.

See `references/api-map.md` for the full endpoint list.
