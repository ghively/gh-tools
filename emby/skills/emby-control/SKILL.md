---
name: emby-control
description: >-
  Control and administer an Emby media server end-to-end via the emby MCP
  server. Use this whenever the user wants to inspect, configure, operate, or
  troubleshoot their Emby server — including ANY of: server status & health,
  media libraries (scan, add folders), movies/TV/music browsing & search,
  item metadata editing & artwork refresh, watched/favorite state, users &
  parental controls & passwords, active sessions ("who's watching"), remote
  playback control (play/pause/stop/message a TV), transcoding analysis ("why
  is this transcoding?"), server configuration & optimization, logs &
  troubleshooting, scheduled tasks, plugins (install/configure/remove),
  collections, playlists, sync/downloads, or anything else the Emby REST API
  exposes. Trigger this skill even when the user just says "my media server",
  "media-host", "check Emby", "what's playing", "add this to a collection", or
  "why is playback buffering" — do not answer from memory; drive the live
  server through the tools.
metadata:
  hermes:
    tags: [emby, media-server, movies, tv, streaming, transcoding, mcp, homelab]
    category: media
    requires_tools: [emby_status]
    config:
      - {key: emby.host, prompt: Emby server host/IP}
required_environment_variables:
  - name: EMBY_API_KEY
    prompt: Emby API key (Dashboard > Advanced > API Keys)
    required_for: authenticating emby_* calls (server-admin access)
version: 0.1.1
author: ghively
---

# Emby server control

This skill drives a real Emby media server through the **`emby` MCP server**
(tools are named `mcp__emby__*`, shown to you as `emby_*`). The target server,
auth, and behavior are already wired up — your job is to pick the right
tool/endpoint and interpret results. Verified against **Emby Server 4.7.x**
on Linux (server "media-host", Emby Premiere active). The live server is now
**4.9.5.0** but was not re-verified (no API key available) — the tools use
long-stable endpoints and self-discover the API from the live OpenAPI spec, so
they remain accurate; see the version-delta note in README before relying on
any 4.7-specific "hard limit" claim.

## Mental model

Emby is one REST surface (~484 operations, ~66 service domains on 4.7) rooted
at `http://host:8096`. Auth is an admin **API key** sent as the `X-Emby-Token`
header — the MCP server attaches it for you. Key conventions the tools encode:

- List queries return `{"Items": [...], "TotalRecordCount": n}`.
- Durations/positions are **ticks**: 1 tick = 100 ns (seconds × 10⁷). Curated
  tools humanize these for you.
- **Round-trip writes**: `POST /System/Configuration`, `/Items/{id}`,
  `/Users/{id}/Policy` etc. expect the FULL object — posting a partial object
  silently resets omitted fields. The curated write tools GET-merge-POST for
  you; never hand-POST a partial object through `emby_call`.
- User-scoped data (watched, resume, favorites) needs a `UserId`; tools
  default to the configured admin user, override with `user=`.
- Plugin settings on Emby 4.x live in **named config stores**
  (`/System/Configuration/{key}`, e.g. `opensubtitles`, `webhooks`,
  `cinemamode`, `dlna`) — NOT the legacy `/Plugins/{id}/Configuration` route,
  which 500s for most modern plugins. `emby_plugin_config` resolves this
  automatically.

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for common jobs. Prefer these.
2. **Generic passthrough** — `emby_call` reaches *any* endpoint;
   `emby_list_endpoints` searches the server's own live OpenAPI catalog.

**Golden rule:** if a curated tool exists, use it. Otherwise find the endpoint
with `emby_list_endpoints`, then call it with `emby_call`. Never guess a
library/server fact — read it from the server.

## Start here

For almost any request, call **`emby_status`** first: identity, version,
pending restart, item counts, connected sessions, and who's playing what
(with transcode flags).

## Tool map

| Job | Tool |
|---|---|
| Health snapshot | `emby_status` |
| Who's watching / sessions | `emby_sessions` (transcode reasons included) |
| Control a client (pause/stop/seek) | `emby_playback_control` |
| Start media on a device | `emby_play`; queue with `play_command` |
| Message a screen | `emby_send_message`; volume/home/etc `emby_send_command` |
| Why does X transcode? | `emby_playback_info` (+ `emby_sessions` live) |
| Browse/report on library | `emby_items` (filters, sort, paging), `emby_search` |
| Browse facets (genres/studios/artists/people/years) | `emby_categories` |
| "More like this" recommendations | `emby_similar` |
| Recently added ("Latest" row) | `emby_latest` |
| Item deep-dive (codecs, path, streams) | `emby_item` |
| Continue watching / next up | `emby_next_up` |
| Edit metadata | `emby_update_item` (round-trip merge; lock fields you edit!) |
| Fix a wrong match | `emby_identify` (search providers → apply) |
| Artwork (posters/backdrops) | `emby_images` (list/search/download/delete) |
| Subtitles | `emby_subtitles` (list/search/download/delete — Open Subtitles configured) |
| Library create/paths/options | `emby_library_manage` (full LibraryOptions round-trip) |
| Re-fetch metadata/art | `emby_refresh_item` |
| Watched/favorite flags | `emby_set_userdata` |
| Delete media (FILES!) | `emby_delete_item` — extreme care |
| Libraries & paths | `emby_libraries`; full scan `emby_scan_library` |
| Collections (deep: query-create, franchise finder, smart sync, reverse lookup) | `emby_collection` |
| Playlists | `emby_playlist` (action verbs) |
| Bulk metadata edit (query → one patch, auto-lock) | `emby_bulk_update` |
| Duplicate copies / quality versions | `emby_versions` (find_duplicates/merge/split) |
| Convert media / device sync (Premiere) | `emby_sync_jobs` |
| Missing episodes report | `emby_items(is_missing="true")` |
| Home screen / display customization | `emby_display_prefs` (per user, per client) |
| Task schedules (maintenance windows) | `emby_task_triggers` |
| Users, parental controls | `emby_users`, `emby_user`, `emby_update_user_policy` |
| Create/delete user, password | `emby_create_user`, `emby_delete_user`, `emby_set_user_password` |
| Server config read/write | `emby_get_config` / `emby_set_config` (named stores via `section`) |
| Restart / shutdown | `emby_restart_server` / `emby_shutdown_server` |
| Logs / troubleshooting | `emby_logs` (embyserver.txt, ffmpeg logs, hardware detection) |
| Audit trail | `emby_activity` |
| Maintenance tasks | `emby_scheduled_tasks`, `emby_run_task` |
| Known devices | `emby_devices` |
| Plugins installed / catalog | `emby_plugins`, `emby_packages` |
| Install/remove/configure plugin | `emby_install_plugin`, `emby_uninstall_plugin`, `emby_plugin_config` |
| Live TV overview | `emby_livetv_status` (start here for anything Live TV/IPTV) |
| IPTV tuners (M3U/HDHomeRun) | `emby_livetv_tuner` (list/add/delete) |
| Guide/EPG sources | `emby_livetv_guide_provider` (xmltv/embygn) |
| Channels / what's on | `emby_livetv_channels`, `emby_livetv_guide` |
| DVR: record/timers/recordings | `emby_livetv_dvr` |
| Anything else | `emby_list_endpoints` → `emby_call` |

## Safety rules (non-negotiable)

1. **Every write tool is confirm-gated** (`confirm=true`). Call it WITHOUT
   confirm first — it returns a preview of what would change. Show the user,
   get explicit approval, then re-run with `confirm=true`.
2. **`emby_delete_item` removes media FILES from disk.** Echo the exact name
   and path back to the user and require them to name the item before
   confirming. Never batch-delete without listing every casualty.
3. `emby_restart_server` / `emby_shutdown_server` drop every active stream —
   check `emby_sessions` first and warn if anyone is watching.
4. Playback control and on-screen messages interrupt real viewers; confirm
   the session belongs to the right person before sending.
5. Config writes: the tools round-trip the full object, but still show the
   user the preview diff (current vs. patch keys) before confirming.

## References

- `references/conventions.md` — auth, error vocabulary, ticks, round-trip
  writes, image URLs, verified server facts.
- `references/api-map.md` — all 66 service domains with per-domain audit
  status (works / dependency-gated / hard-limit) and the go-to endpoints.
- `references/common-tasks.md` — worked multi-step recipes (transcode
  triage, metadata repair, user onboarding, plugin lifecycle...).
- `references/configuration.md` — official configuration guidance mapped to
  API keys (networking, transcoding, library options, user policies).
- `references/troubleshooting.md` — official troubleshooting: logs, playback
  failures, scan issues, hw-accel verification, remote access.
- `references/optimization.md` — official performance guidance: hardware
  acceleration, throttling, scan scheduling, image extraction costs.
- `references/plugin-management.md` — plugin catalog management via API and
  a primer on developing Emby server plugins (C#/.NET).
- `references/livetv.md` — Live TV / IPTV: setup flow (tuner + guide +
  refresh), verified add-time playlist validation, DVR, channel management.
- `references/metadata-editing.md` — deep curation: every editable metadata
  field, LockedFields, identify flow, artwork flow, collection curation,
  subtitle management, library management, and the config depth map.
- `references/customization.md` — home screen layouts, web-UI theming/custom
  CSS, cinema intros, webhooks, the definitive library-type matrix
  (books/comics/audiobooks/games/mixed), auto-organize, task scheduling, and
  the pure-API config backup/restore recipe.
- `references/games-gamebrowser.md` — GameBrowser deep-dive: config-driven
  platform registration (NOT folder names), per-platform extension table,
  the no-internet-metadata reality since 2018 and working local-art paths.
