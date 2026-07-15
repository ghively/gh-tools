---
description: Snapshot every Emby configuration surface to local JSON (or restore from a snapshot)
argument-hint: (optional) "restore <folder>" | a note for the snapshot
---

# Emby configuration backup / restore

Pure-API config snapshot using the `emby` MCP tools (reference:
emby-control skill, customization.md §8).

## Backup (default)

1. Create a local folder `emby-backup-<YYYY-MM-DD-HHmm>/` in the plugin
   directory (it's git-ignored via `*.local.json`? No — use
   `emby/backups/<stamp>/`, and ensure `backups/` is in .gitignore; add it if
   missing). NEVER commit backups — they contain credentials (e.g. the
   opensubtitles store holds a recoverable password).
2. Dump, one JSON file each:
   - `system.json` — `emby_get_config()`
   - `store-<key>.json` — every named store: `encoding`, `livetv`,
     `notifications`, `subtitles`, `dlna`, `branding`, `devices`, plus each
     plugin store from `emby_plugin_config()` (the page list)
   - `user-<name>.json` — `emby_user(u)` for every user (Policy +
     Configuration), plus `emby_display_prefs(u)` as `prefs-<name>.json`
   - `library-<name>.json` — `emby_library_manage("get_options", ...)` +
     the library's Locations from `emby_libraries()`
   - `livetv.json` — `emby_livetv_status()` (tuners + guide providers)
   - `scheduled-tasks.json` — `emby_scheduled_tasks()` with triggers
   - `manifest.json` — server name/version/id (`emby_status`), timestamp,
     the optional note from `$ARGUMENTS`
3. Report the folder path and file count. Suggest also installing the
   official "Server Configuration Backup" plugin for DB/watch-history
   coverage (this snapshot covers configuration only).

## Restore ("restore <folder>")

1. Read `manifest.json`, confirm the target server matches (server Id) — warn
   loudly if not.
2. Show me a diff summary per domain (current vs snapshot) BEFORE writing
   anything.
3. Restore only the domains I approve, each via the normal confirm-gated
   write tools (round-trip merge). Order: system config → named stores →
   library options → user policies/configs → display prefs → task triggers →
   Live TV sources.
4. Verify each domain by re-reading; report what changed.
