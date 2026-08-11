# emby — full Emby server control for Claude Code

A Claude Code plugin that gives Claude deep, honest control of an **Emby media
server**: an MCP server with a generic passthrough reaching the server's entire
REST surface (~484 operations, discovered live from its own OpenAPI spec) plus
54 curated tools, a control skill with official-docs references, and
slash-command workflows. Built and live-verified against **Emby Server 4.7.14.0**
on Linux following the deep-integration-builder methodology in this repo.

## What's inside

```
emby/
├── .claude-plugin/plugin.json     plugin manifest
├── .mcp.json                      MCP server registration (uv run --script)
├── mcp/emby_server.py             the MCP server (self-provisioning via uv)
├── mcp/_smoketest.py              live verification: every read for real,
│                                  every write gate proven to hold
├── config.example.json            copy to config.local.json (git-ignored)
├── skills/emby-control/           control skill
│   ├── SKILL.md
│   └── references/
│       ├── conventions.md         auth, errors, ticks, round-trip writes
│       ├── api-map.md             all 66 domains, audited: works/dep-gated/hard-limit
│       ├── common-tasks.md        multi-step recipes
│       ├── configuration.md       official config guidance mapped to API keys
│       ├── troubleshooting.md     logs, playback, scans, hw-accel, remote access
│       ├── optimization.md        performance: hw-accel, throttling, DB, network
│       ├── plugin-management.md   plugin API + Emby plugin development primer
│       ├── livetv.md              Live TV / IPTV setup, guide, DVR
│       ├── metadata-editing.md    deep curation: fields, identify, artwork, subs
│       ├── customization.md       home screens, theming, webhooks, backups
│       └── games-gamebrowser.md   GameBrowser plugin deep-dive
└── commands/
    ├── emby-health.md             /emby-health — full health report
    ├── emby-sessions.md           /emby-sessions — now playing + transcode analysis
    ├── emby-library.md            /emby-library — search/browse/report
    ├── emby-maintenance.md        /emby-maintenance — scan/restart/tasks, viewer-safe
    ├── emby-plugin.md             /emby-plugin — catalog/install/configure/remove
    ├── emby-livetv.md             /emby-livetv — status/IPTV setup/guide/DVR
    ├── emby-metadata.md           /emby-metadata — edit/identify/artwork/subtitles
    ├── emby-collections.md        /emby-collections — deep collection management
    ├── emby-backup.md             /emby-backup — full config snapshot/restore
    ├── emby-user.md               /emby-user — onboarding with presets (kid/guest/...)
    └── emby-plugin-dev.md         /emby-plugin-dev — scaffold/build/deploy C# plugins
```

## Setup

1. Create an API key on the server: Dashboard → Advanced → API Keys.
2. `cp config.example.json config.local.json` and fill in `host` and `api_key`
   (git-ignored; env vars `EMBY_HOST`, `EMBY_API_KEY`, ... override).
3. Requires [uv](https://docs.astral.sh/uv/) — the server self-provisions its
   Python dependencies on first run.
4. Verify: `uv run --script mcp/_smoketest.py` — exercises every tool against
   your live server with zero mutations.

## Two layers

- **Curated tools** (54: `emby_status`, `emby_items`, `emby_sessions`,
  `emby_playback_control`, `emby_set_config`, `emby_plugin_config`,
  `emby_identify`, `emby_images`, `emby_subtitles`, `emby_library_manage`,
  `emby_bulk_update`, `emby_versions`, `emby_sync_jobs`, deep
  `emby_collection` (query-create/smart-sync/franchise-finder/reverse-lookup),
  6 Live TV tools, ...) encode the correct params and Emby's gotchas —
  notably **round-trip writes** (Emby resets omitted fields on partial POSTs)
  and **named config stores** (the working plugin-settings mechanism on 4.x;
  the legacy per-plugin route 500s).
- **Generic passthrough** (`emby_call` + `emby_list_endpoints`) reaches every
  other operation, searchable from the server's own live OpenAPI catalog.

## Safety model

Every mutating tool is confirm-gated in code: called without `confirm=true` it
returns a preview (current values, what would change) and changes nothing.
`emby_delete_item` deletes actual media files and says so loudly. The smoketest
proves all 44 gate checks hold.

## Honest coverage notes (audited 2026-07)

- **Works** (live-verified): system/config/logs/tasks/activity, users & policies,
  the whole library surface, sessions & remote control, media info, plugins &
  catalog, collections, playlists, sync (Premiere active), images, DLNA profiles.
- **Live TV**: 6 curated tools; setup write path proven live and REVERSIBLY
  (tuner add → enabled → delete → restored). Unconfigured until an IPTV
  playlist / guide source is added — then /emby-livetv does the whole setup.
- **Dependency-gated**: Emby Connect (server not linked).
- **Hard limits on 4.7.14**: legacy `/Plugins/{id}/Configuration` (all modern
  plugins 500 — named stores used instead), `/Items/{id}/DeleteInfo` (500 NRE),
  newer 4.8+ routes (`/System/Configuration/Partial`, `/System/Logs/Query`).
