# tdarr-control

Control of a **Tdarr** distributed transcoding server (v2 API) from Claude Code / opencode.

**LIVE-VERIFIED on Tdarr 2.84.01** (2026-07-20). 16/16 smoke tools passed
against the live server at `gh-nvidia:8265`; reversible backup
create→list→delete write proof PASSED. The plugin was originally built
doc-only and verified live on first deployment — the smoke test
(`mcp/_smoketest.py`) and write proof (`mcp/_writeproof.py`) are how the gap
was closed. Tools added since that verification (`tdarr_libraries`,
`tdarr_staged_files`, `tdarr_create_plugin`, `tdarr_remove_*_codec_exclude`)
are in the smoke test but pending a live re-run.

## What this plugin does

Two-layer MCP server for Tdarr:

- **Generic passthrough** — `tdarr_call` reaches any documented `/api/v2/*`
  endpoint; `tdarr_list_endpoints` is the static catalog (built from the
  official API docs). 65 endpoints across system, library, plugins, nodes,
  backups, /cruddb, settings, and reports.
- **Curated tools** (50) for the common jobs:

| Area | Tools |
|---|---|
| Status | `tdarr_status`, `tdarr_full_status`, `tdarr_nodes`, `tdarr_db_statuses`, `tdarr_performance_stats`, `tdarr_res_stats`, `tdarr_server_log`, `tdarr_node_log` |
| Library | `tdarr_search_db`, `tdarr_libraries`, `tdarr_staged_files`, `tdarr_scan_files`, `tdarr_scan_individual_file`, `tdarr_filescanner_status`, `tdarr_verify_folder_exists`, `tdarr_get_subdirectories`, `tdarr_delete_file`, `tdarr_delete_unhealthy_files`, `tdarr_kill_file_scanner` |
| Plugins | `tdarr_search_plugins`, `tdarr_search_flow_plugins`, `tdarr_search_flow_templates`, `tdarr_read_plugin`, `tdarr_install_plugin`, `tdarr_create_plugin`, `tdarr_delete_plugin`, `tdarr_sync_plugins`, `tdarr_update_plugins`, `tdarr_verify_plugin` |
| Nodes | `tdarr_nodes`, `tdarr_restart_node`, `tdarr_disconnect_node`, `tdarr_alter_worker_limit`, `tdarr_poll_worker_limits`, `tdarr_cancel_worker_item`, `tdarr_kill_worker` |
| Backups | `tdarr_backup_status`, `tdarr_backups`, `tdarr_create_backup`, `tdarr_delete_backup` |
| DB (the powerful one) | `tdarr_db` (full CRUD on 8 collections), `tdarr_collections` |
| Library settings | `tdarr_toggle_folder_watch`, `tdarr_toggle_schedule`, `tdarr_add_video_codec_exclude`, `tdarr_remove_video_codec_exclude`, `tdarr_add_audio_codec_exclude`, `tdarr_remove_audio_codec_exclude`, `tdarr_run_help_command` |
| Reports | `tdarr_list_footprint_reports`, `tdarr_transcode_user_verdict` |

**All writes confirm-gated.** Disruptive ops (`kill_worker`, `disconnect_node`,
`kill_file_scanner`) and the `/cruddb` write modes are **doubly gated** —
`confirm=true` AND a typed `acknowledge="<token>"`.

## Configuration

1. **Deploy Tdarr.** Typical Docker on `gh-nvidia`:
   ```bash
   docker run -d --name tdarr -p 8265:8265 -p 8266:8266 \
     -e PUID=1000 -e PGID=1000 \
     -e NVIDIA_VISIBLE_DEVICES=all \
     -v /tank/media:/media \
     -v tdarr_server:/app/server \
     -v tdarr_configs:/app/configs \
     -v tdarr_logs:/app/logs \
     ghcr.io/haveagitgat/tdarr:latest
   ```
   (When you actually deploy, formalize this as an Ansible playbook under
   `~/gh-Nvidia/playbooks/projects/`.)
2. **Copy** `config.example.json` → `config.local.json` (git-ignored) and fill
   in `host`/`port` (Tdarr does not require an API key — the API trusts the LAN).
3. Optional: if you front Tdarr with an auth proxy, set `api_key` +
   `api_key_header` in `config.local.json`.

Env vars (`TDARR_HOST`, `TDARR_PORT`, `TDARR_HTTPS`, `TDARR_URL_BASE`,
`TDARR_API_KEY`, `TDARR_API_KEY_HEADER`, `TDARR_VERIFY_SSL`, `TDARR_TIMEOUT`)
override the file.

## Conventions encoded (per the docs)

- Base path `/api/v2/<endpoint>`. Endpoint names are kebab-case.
- Almost all endpoints are POST with body `{"data": {...}}`. The client wraps
  your params in `data` automatically — pass just the inner object.
- 4 endpoints are GET: `/status`, `/get-nodes`, `/download-plugins`,
  `/get-server-log`.
- **No auth** by default; Tdarr trusts the LAN like the *arr stack.
- `/cruddb` is the powerful generic DB endpoint — full CRUD on 8 collections.
  Reads (getById / getAll) are not gated; every write mode is doubly gated
  (`confirm=true` AND `acknowledge='<mode>'`, e.g. `acknowledge='removeAll'`).

## Honest gap taxonomy

- **LIVE-VERIFIED (reads, against Tdarr 2.84.01):** status, full_status, nodes,
  db_statuses, performance_stats, res_stats, backup_status, backups, search_db,
  search_plugins/flow_plugins/flow_templates (with `pluginType`), db getAll on
  StatisticsJSONDB/NodeJSONDB/SettingsGlobalJSONDB/LibrarySettingsJSONDB/FlowsJSONDB,
  run_help_command (`mode`+`text`).
- **LIVE-VERIFIED (writes):** create_backup + delete_backup (reversible write
  proof PASSED — `Backup-version-*.zip` created, verified, deleted, state restored).
- **DOC-VERIFIED only** (endpoint documented; call/param shape NOT exercised
  live — treat the payload as assumed):
  - `scan_files(scan_config)` — assumed `scanConfig` shape.
  - `toggle_schedule(type)` — assumed type values (probe a live record first).
  - `transcode_user_verdict(verdict)` — assumed verdict strings.
  - `tdarr_db(obj)` for write modes (insert/update) — shape varies per
    collection; always `getAll` first. (The READ modes are LIVE-VERIFIED.)
  - Note: `alter_worker_limit(worker_type)` is doc-built, but its worker_type
    enum is CONFIRMED live (`transcodecpu` / `transcodegpu` / `healthcheckcpu`
    / `healthcheckgpu`, from live NodeJSONDB.workerLimits).
- **added-post-verification** (written after the 2026-07-20 live run; in
  `mcp/_smoketest.py` but not yet re-run against live Tdarr):
  - `tdarr_libraries` (getAll LibrarySettingsJSONDB — underlying call
    live-observed, wrapper not re-run).
  - `tdarr_staged_files` (getAll StagedJSONDB — row shape not yet live-observed).
  - `tdarr_create_plugin` (assumed definition shape).
  - `tdarr_remove_video_codec_exclude` / `tdarr_remove_audio_codec_exclude`.
- **Not implemented (out of MVP scope):** WebSocket live updates (the Tdarr web
  UI uses Socket.IO — out of scope for MCP), `download-plugins` binary download,
  `client/{clientType}` (internal node↔server).

## What the live verification caught (vs the docs)

The Tdarr API docs at tdarr.readme.io are slightly stale; live-verification
caught three param-shape mismatches that were fixed:

- **`search-db`**: docs say `lessThanGB`/`greaterThanGB` are optional — server
  requires them. Curated tool now always sends sensible defaults.
- **`search-plugins` / `search-flow-plugins`**: docs omit the required
  `pluginType` field. Curated tool now sends `"standard"` / `"flow"`.
- **`delete-backup`**: docs use `fileName` — server wants `name`. Fixed.
- **`run-help-command`**: docs use `command`/`args` — server wants `mode`/`text`. Fixed.

Built with the **deep-integration-builder** methodology.
