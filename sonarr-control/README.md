# sonarr-control

Full control of a Sonarr TV-series manager (v3+ REST API) from Claude Code / opencode.

Verified against **Sonarr 4.0.18.2978** on the homelab NAS (`192.168.0.133:8989`).

## What this plugin does

A two-layer MCP server for Sonarr:

- **Generic passthrough** — `sonarr_call` reaches any `/api/v3/*` endpoint;
  `sonarr_list_endpoints` is the hand-enumerated master index (Sonarr does
  not publish OpenAPI).
- **Curated tools** (~24) for status, library, activity, commands, and config:

| Area | Tools |
|---|---|
| System | `sonarr_status`, `sonarr_logs`, `sonarr_system_tasks`, `sonarr_system_backups` |
| Library | `sonarr_list_series`, `sonarr_get_series`, `sonarr_lookup_series`, `sonarr_add_series`, `sonarr_update_series`, `sonarr_delete_series`, `sonarr_episodes`, `sonarr_episode_files`, `sonarr_toggle_season_monitored` |
| Activity | `sonarr_calendar`, `sonarr_queue`, `sonarr_history`, `sonarr_wanted_missing`, `sonarr_wanted_cutoff`, `sonarr_blocklist` |
| Commands | `sonarr_command`, `sonarr_command_status`, `sonarr_search_episode`, `sonarr_search_season`, `sonarr_refresh_series` |
| Config | `sonarr_quality_profiles`, `sonarr_language_profiles`, `sonarr_root_folders`, `sonarr_tags`, `sonarr_notifications`, `sonarr_download_clients`, `sonarr_indexers`, `sonarr_import_lists` |

**All writes are confirm-gated** (`confirm=True` required).

## Configuration

1. Create an API key in Sonarr under **Settings > General > Security > API Key**.
2. Store it in 1Password (vault: `Gregory`, item: `Sonarr API Key (GH-Storage)`),
   with the URL in the `serverurl` field.
3. Copy `config.example.json` → `config.local.json` (git-ignored).

```bash
op item get '<item-id>' --vault Gregory --field credential --reveal
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
  (RefreshSeries, SeriesSearch, EpisodeSearch, EpisodesSearch, SeasonSearch,
  DownloadedEpisodesScan, RenameSeries, Backup, MissingEpisodesSearch, RssSync).
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
