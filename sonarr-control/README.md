# sonarr-control

Full control of a Sonarr TV-series manager (v3+ REST API) from Claude Code / opencode.

Verified against **Sonarr 4.x** on the homelab NAS (`192.0.2.20:8989`).

## What this plugin does

A two-layer MCP server for Sonarr:

- **Generic passthrough** — `sonarr_call` reaches any `/api/v3/*` endpoint;
  `sonarr_list_endpoints` is the master index (pulled live from
  `/system/routes`, falling back to a hand-enumerated catalog — Sonarr does
  not publish OpenAPI).
- **Curated tools** (~70) for status, library, activity, commands, and config:

| Area | Tools |
|---|---|
| System | `sonarr_status`, `sonarr_logs`, `sonarr_log_files`, `sonarr_system_tasks`, `sonarr_system_backups`, `sonarr_system_routes`, `sonarr_system_restart`, `sonarr_system_shutdown`, `sonarr_filesystem` |
| Library | `sonarr_list_series`, `sonarr_get_series`, `sonarr_lookup_series`, `sonarr_add_series`, `sonarr_update_series`, `sonarr_delete_series`, `sonarr_series_bulk_edit`, `sonarr_series_bulk_delete`, `sonarr_episodes`, `sonarr_episode_monitor`, `sonarr_episode_files`, `sonarr_episode_file_delete`, `sonarr_toggle_season_monitored`, `sonarr_season_pass`, `sonarr_rename_preview` |
| Activity | `sonarr_calendar`, `sonarr_calendar_ics`, `sonarr_queue`, `sonarr_queue_delete`, `sonarr_queue_grab`, `sonarr_queue_bulk_delete`, `sonarr_history`, `sonarr_history_since`, `sonarr_wanted_missing`, `sonarr_wanted_cutoff`, `sonarr_blocklist`, `sonarr_blocklist_delete`, `sonarr_blocklist_bulk_delete`, `sonarr_release_search`, `sonarr_release_grab`, `sonarr_manual_import`, `sonarr_parse` |
| Commands | `sonarr_command`, `sonarr_command_status`, `sonarr_search_episode`, `sonarr_search_season`, `sonarr_refresh_series` |
| Config | `sonarr_quality_profiles`, `sonarr_quality_definitions`, `sonarr_language_profiles`, `sonarr_languages`, `sonarr_root_folders`, `sonarr_tags`, `sonarr_tag_details`, `sonarr_tag_create`, `sonarr_tag_delete`, `sonarr_notifications`, `sonarr_download_clients`, `sonarr_indexers`, `sonarr_import_lists`, `sonarr_import_exclusions`, `sonarr_delay_profiles`, `sonarr_release_profiles`, `sonarr_remote_path_mappings`, `sonarr_auto_tagging`, `sonarr_config_section`, `sonarr_update_config_section`, `sonarr_provider_test`, `sonarr_provider_action`, `sonarr_crud` |

**All writes are confirm-gated** (`confirm=True` required).

## Configuration

1. Create an API key in Sonarr under **Settings > General > Security > API Key**.
2. Store it in 1Password (vault: `Homelab`, item: `Sonarr API Key (NAS-Host)`),
   with the URL in the `serverurl` field.
3. Copy `config.example.json` → `config.local.json` (git-ignored).

```bash
op item get '<item-id>' --vault Homelab --field credential --reveal
```

Env vars (`SONARR_HOST`, `SONARR_PORT`, `SONARR_HTTPS`, `SONARR_URL_BASE`,
`SONARR_API_KEY`, `SONARR_VERIFY_SSL`, `SONARR_TIMEOUT`) override the file.

## Run

```bash
cd sonarr-control && uv run --script mcp/_smoketest.py
```

## Conventions encoded

- Auth: API key in the `X-Api-Key` header.
- POST/PUT expects the FULL object — write tools GET-merge-PUT internally.
- POST /command with `{"name": "<CommandName>", ...}` triggers async jobs
  (RefreshSeries, RescanSeries, SeriesSearch, EpisodeSearch, EpisodesSearch,
  SeasonSearch, DownloadedEpisodesScan, RenameSeries, Backup,
  MissingEpisodesSearch, RssSync).
- `/wanted/missing` and `/wanted/cutoff` return EPISODE records, not series.
- `/calendar` returns episodes (one per airing), each with its series embedded.

## Honesty notes (gap taxonomy)

- **Works (live-verified, GETs):** all reads in the smoke test pass against
  the live library (calendar showed real upcoming episodes today; lookup of
  "breaking bad" correctly matched the in-library series).
- **Method-verified, not live-executed:** confirm-gated writes (add/update/
  delete series, season-monitoring toggle, POST /command). The HTTP shape is
  correct; live execution requires explicit owner approval.
- **Hard limits:** Sonarr publishes no OpenAPI — the endpoint catalog is
  hand-enumerated from live probes (2026-07-19). `sonarr_call` reaches any
  future endpoint via the generic path.

Built with the **deep-integration-builder** methodology.
