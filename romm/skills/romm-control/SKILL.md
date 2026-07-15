---
name: romm-control
description: >-
  Control and administer a RomM ROM-library server end-to-end via the romm
  MCP server. Use this whenever the user wants to inspect, organize, operate,
  or troubleshoot their retro-game library — including ANY of: server status
  & stats, platforms (create/rename/delete, folder bindings), ROM search &
  browsing, ROM metadata editing & matching (IGDB/ScreenScraper/MobyGames/
  RetroAchievements/LaunchBox/Hasheous), library scans, collections (manual,
  smart, virtual), users & roles & permission groups & invite links, API
  keys, save files & save states & screenshots, BIOS/firmware, background
  tasks, config exclusions, play activity & sessions & playtime, game
  soundtracks/music, client feeds (Tinfoil/webRcade/PKGi), gamelist.xml or
  Pegasus exports, uploading or downloading ROM files, or anything else the
  RomM REST API exposes. Trigger this skill even when the user just says "my
  ROMs", "gh-nvidia roms", "check RomM", "scan my library", "add this to a
  collection", or "why isn't this game matched" — do not answer from memory;
  drive the live server through the tools.
---

# RomM server control

This skill drives a real RomM server through the **`romm` MCP server** (tools
are named `mcp__romm__*`, shown to you as `romm_*`). The target server, auth,
and behavior are already wired up — your job is to pick the right
tool/endpoint and interpret results. Verified against **RomM 5.0.0** on
gh-nvidia (`http://192.168.0.214:8095`).

## Mental model

RomM is a FastAPI app: one REST surface (~189 operations, 27 tags on 5.0.0)
rooted at `/api`, plus a Socket.IO channel for scans/logs/netplay/sync. Auth
is a RomM **API key** sent as `Authorization: Bearer rmm_...` — the MCP
server attaches it for you. Conventions the tools encode:

- Errors are FastAPI-style: `{"detail": "message"}` (or a list for 422
  validation errors).
- List endpoints (`/api/roms`, `/api/music/*`) return
  `{"items": [...], "total": n, "limit": .., "offset": ..}`; most others
  return bare arrays.
- ROM objects carry huge per-provider metadata blobs; `romm_rom` trims them
  unless `verbose=True`.
- ROM/collection edits are **multipart/form-data**, user edits and smart
  collections are **x-www-form-urlencoded**, most other writes are JSON —
  curated tools pick the right encoding; `romm_call` sends `form_body` as
  urlencoded (or multipart when `file_path` is attached).
- **Scans are NOT REST**: `POST /api/tasks/run/scan_library` is rejected by
  design ("cannot be run"). The UI fires the Socket.IO event `scan`, and the
  socket authenticates with the `romm_session` cookie from `POST /api/login`
  (HTTP Basic). `romm_scan` does that whole dance, but it needs the optional
  `username`/`password` fields in `config.local.json` — the API key cannot
  mint a session. Everything else works with just the API key.

Two layers of tools:

1. **Curated tools** (~50) for the common jobs — one call, correct params.
2. **Generic passthrough** for the long tail: `romm_endpoints(search=...)`
   to find any operation, `romm_schema(path, method)` for its exact
   parameters, `romm_call(method, path, ...)` to execute it. If a curated
   tool doesn't cover something, the passthrough almost certainly does.

## Common jobs → tools

| Job | Tool(s) |
|---|---|
| Health / version / what's enabled | `romm_status` |
| Library size, per-platform counts | `romm_stats(include_platform_stats=True)` |
| List/browse ROMs, filter anything | `romm_roms` (search_term, platform_id, matched, missing, duplicate, verified, genres, regions, statuses...) |
| One game's full detail | `romm_rom(id)`; files via `romm_rom_files` |
| Identify an unmatched game | `romm_match_search(rom_id)` → pick candidate → `romm_rom_update(id, provider_ids_json='{"igdb_id": N}', confirm=True)` |
| Fix name/summary/cover | `romm_rom_update` |
| Track play status/rating | `romm_rom_props` (status: incomplete/finished/completed_100/retired/never_playing) |
| Trigger a scan | `romm_scan(scan_type=...)` — needs username/password configured |
| Run maintenance task | `romm_task_run` (cleanup_orphaned_resources, cleanup_missing_roms, sync_folder_scan, recompute_save_content_hashes, update_switch_titledb, update_launchbox_metadata, convert_images_to_webp) |
| Collections | `romm_collections`, `romm_collection_create/update/delete`, `romm_collection_roms(action=add/remove)`, `romm_smart_collection_create` |
| Users & roles | `romm_users`, `romm_user_create/update/delete`, `romm_user_invite`; fine-grained perms via `romm_permissions` |
| API keys | `romm_api_keys` |
| Saves / states / firmware | `romm_saves`, `romm_states`, `romm_firmware` (+ `_delete`, `romm_firmware_upload`) |
| Who's playing what | `romm_activity`; history via `romm_play_sessions` |
| Game soundtracks | `romm_music(kind=tracks/albums/artists...)` |
| Handheld feeds (Tinfoil etc.) | `romm_feeds` |
| Export gamelist.xml / Pegasus | `romm_export` |
| Upload a ROM file | `romm_upload_rom(platform_id, file_path)` (chunked) |
| Download a ROM file | `romm_download_rom(rom_id, dest_dir)` |
| Folder-name → platform mapping | `romm_config_platform_binding`; exclusions via `romm_config_exclude` |
| Server logs | `romm_logs` |

## Full domain map (all 27 API tags — nothing outside this list exists)

Every tag from the server's OpenAPI spec, with its primary handle. Tags
marked (passthrough) have no curated tool — reach them with
`romm_endpoints(tag=...)` → `romm_schema` → `romm_call`.

| Tag | Handle |
|---|---|
| system, stats, logs | `romm_status`, `romm_stats`, `romm_logs` |
| platforms | `romm_platforms` / `_platform*` / `romm_supported_platforms` |
| roms, upload | `romm_roms`, `romm_rom*`, `romm_upload_rom`, `romm_download_rom` |
| search | `romm_match_search` (cover search needs SGDB server-side) |
| collections | `romm_collections` / `_collection*` / `romm_smart_collection_create` |
| users, permissions | `romm_users` / `_user*`, `romm_permissions` |
| client-tokens | `romm_api_keys` |
| saves, states | `romm_saves` / `romm_states` (+ `_delete`; upload via `romm_call` with `file_path`) |
| screenshots | list via `romm_rom` detail; CRUD via passthrough |
| firmware | `romm_firmware` / `_firmware_upload` / `_firmware_delete` |
| tasks | `romm_tasks` / `romm_task_run`; scans via `romm_scan` (Socket.IO) |
| config | `romm_config` / `_config_exclude` / `_config_platform_binding` |
| devices | `romm_devices` / `romm_device_delete`; register/update via passthrough |
| activity, play-sessions | `romm_activity`, `romm_play_sessions` |
| music | `romm_music` |
| feeds | `romm_feeds` |
| export | `romm_export` |
| auth | login/logout/token via passthrough (session flows; Basic creds) |
| device-auth | (passthrough) interactive client-pairing flow for emulator apps — approve/deny pending requests via `romm_call` |
| sync | (passthrough) device save-sync sessions: `GET /api/sync/sessions`, push-pull per device |
| netplay | (passthrough) `GET /api/netplay/list?game_id=` ; sessions are emulator-client Socket.IO flows |

## Library structure & scanning

RomM indexes a filesystem library. Two supported layouts (this server
auto-detected **structure A**):

- **A (preferred):** `library/roms/<platform_slug>/<game files>` and
  `library/bios/<platform_slug>/...`
- **B:** `library/<platform_slug>/roms/...`

Platform folder names must match a canonical slug (`romm_supported_platforms`
searches all 459) or be bound to one via `romm_config_platform_binding`.
After adding files: `romm_scan(scan_type="quick")` picks up new files;
`"unmatched"` retries identification; `"update"` refreshes metadata;
`"complete"` rescans everything. The filesystem watcher (if enabled in env)
auto-scans 5 minutes after changes.

Metadata sources on this install: **Hasheous + LibretroDB** (hash-based
matching, no API keys needed). IGDB/ScreenScraper/MobyGames/RetroAchievements/
SteamGridDB/LaunchBox etc. activate by adding their API credentials to the
server's environment — `romm_status` shows which are live.

## Safety rules (enforced in code, respect them in workflow too)

- Every destructive/disruptive tool requires `confirm=True`. **Always ask the
  user before setting it** and state exactly what will happen.
- `romm_rom_delete(delete_from_fs=True)`, `romm_firmware_delete(
  delete_from_fs=True)` and `romm_rom_update(fs_name=...)` touch files on
  disk — irreversible; double-confirm these.
- `romm_platform_delete` removes every ROM DB row for that platform.
- Prefer reversible proofs: create a test collection → verify → delete.
- Scans on a large library are heavy (hashing + metadata fetches); prefer
  `quick` over `complete` unless the user wants a full rebuild.

## Troubleshooting map

- **403 on everything** → API key invalid/revoked, or the key lacks the
  needed scope (`romm_api_keys(action="list")` shows scopes; this key has
  all 20 including users.write, tasks.run, logs.read).
- **"Task 'X' cannot be run"** → that task is scheduled-only (notably
  scan_library) — use `romm_scan` instead.
- **Game not identified** → check platform folder name is a canonical slug
  (`romm_supported_platforms`), then `romm_match_search` + `romm_rom_update`
  to hand-match; `romm_scan(scan_type="unmatched")` to bulk-retry.
- **0 platforms after adding files** → folder layout wrong (see structure A
  above) or volume not mounted into the container; `romm_status` shows
  `filesystem_platform_dirs` as RomM sees them; `romm_config` shows
  exclusions that may be eating folders.
- **Provider search returns nothing** → that provider isn't configured;
  `romm_status` lists enabled sources. Hasheous matches by file hash, so
  renamed/patched ROMs may need a known-good dump or a manual match.
- **Deep dives** → `romm_logs(limit=200)` streams the backend log ring
  buffer (same data as the UI's log viewer).

## Known 5.0.0 server quirks (verified live; tools already work around them)

- `GET /api/roms/{id}/files` takes a **file** id, not a ROM id, and 500s
  regardless — `romm_rom_files` reads the file list from the ROM detail
  instead.
- `GET /api/roms/{id}/notes` (list) 500s even though note add/update/delete
  work — `romm_rom_notes(action="list")` falls back to the `all_user_notes`
  array embedded in the ROM detail.
- `GET /api/search/roms` and `/api/search/cover` return 500 (not an empty
  list) when no text-search metadata provider (IGDB/SS/Moby) or SteamGridDB
  is configured — that's a server-config dependency, not an auth problem.
