---
name: tdarr-control
description: >-
  Control and administer a Tdarr distributed transcoding server via the tdarr
  MCP server. Use this whenever the user wants to inspect, configure, operate,
  or troubleshoot Tdarr — including ANY of: server status / health, node +
  worker management (list, restart, disconnect, alter worker limits, cancel
  jobs, kill workers), library scanning (search-db, scan files, kill file
  scanner), plugin management (search, install, edit, delete, sync, update),
  backups (status, list, create, delete), the powerful /cruddb (full CRUD on
  8 internal collections), codec-exclude and plugin-include management,
  transcode-user-verdict, flow plugins/templates, server + node logs, OR
  anything else the documented /api/v2 surface exposes. Trigger this skill
  whenever the user says "Tdarr", "transcode", "my media library health",
  "what's transcoding now", "scan my library", "is GPU being used", or "why
  did this transcode fail" — do not answer from memory; drive the live Tdarr
  server through the tools.
---

# Tdarr control

This skill drives a real Tdarr transcoding server through the **`tdarr` MCP
server** (tools shown as `tdarr_*`). The plugin is **DOC-VERIFIED — built
from the official tdarr.readme.io/reference API docs (v2.25.01+)**. Tdarr is
not deployed on this homelab yet; the plugin will fail every call against
the live server until it is. See README for the first-deployment checklist.

Auth model: **NONE** by default — Tdarr trusts the LAN like the *arr stack.
Optional `api_key` (passed via configurable header) supports auth-proxy fronting.

## Mental model

Tdarr is a single POST-based HTTP API under `/api/v2/<endpoint>` (~67 endpoints).
Endpoint names are kebab-case. Almost every endpoint takes POST with body
`{"data": {...}}` — the MCP client wraps your params in `data` automatically.
4 endpoints are GET: `/status`, `/get-nodes`, `/download-plugins`,
`/get-server-log`.

Key concepts:

- **Library**: a configured media folder + transcode rules. Has a `libraryID`.
- **Node**: a worker process (local or remote) that connects to the server and
  pulls transcode jobs. Each has a `nodeID` and runs CPU and/or GPU workers.
- **Plugin**: a JavaScript file that decides whether/how to transcode a file.
  Community plugins live on HaveAGitGat/Tdarr_Plugins; "flow plugins" are the
  newer Tdarr 2.x system.
- **/cruddb**: the powerful generic endpoint — full CRUD on 8 internal
  collections. Reads (getById/getAll) are not confirm-gated; writes ARE.
- **Worker**: a slot on a node currently processing a file. Can be cpu/gpu
  /transcode type. `kill_worker` aborts the active transcode.

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for common jobs. Prefer these.
2. **Generic passthrough** — `tdarr_call` reaches *any* documented endpoint;
   `tdarr_list_endpoints` searches the static catalog.

**Golden rule:** if a curated tool exists, use it. Otherwise find the endpoint
with `tdarr_list_endpoints`, then call it with `tdarr_call`. Never guess.

## Start here

For almost any request, call **`tdarr_full_status`** first: status + nodes +
DB statuses + perf/res stats in one call. Then drill down.

## Tool map

| Job | Tool |
|---|---|
| Full health snapshot | `tdarr_full_status()` |
| Liveness only | `tdarr_status()` (cheapest) |
| Connected nodes | `tdarr_nodes()` |
| Library health | `tdarr_db_statuses()` |
| Throughput | `tdarr_performance_stats()` |
| CPU/memory | `tdarr_res_stats()` |
| Server log (tail) | `tdarr_server_log()` |
| Per-node log | `tdarr_node_log(node_id)` |
| Search files | `tdarr_search_db(string=, less_than_gb=, greater_than_gb=)` |
| Scan files (write) | `tdarr_scan_files(scan_config=, confirm=)` |
| Scan one file (write) | `tdarr_scan_individual_file(file_path=, confirm=)` |
| Filescanner status | `tdarr_filescanner_status(db_name)` |
| Kill scanner (DANGER) | `tdarr_kill_file_scanner(db_name, confirm=, acknowledge="kill")` |
| Browse server FS | `tdarr_verify_folder_exists(path)`, `tdarr_get_subdirectories(path)` |
| Delete a file (DANGER) | `tdarr_delete_file(file_path=, confirm=)` |
| Search plugins | `tdarr_search_plugins(string=)` |
| Install community plugin | `tdarr_install_plugin(plugin_id=, confirm=)` |
| Read a plugin | `tdarr_read_plugin(plugin_id)` |
| Delete a plugin | `tdarr_delete_plugin(plugin_id=, confirm=)` |
| Sync/update all plugins | `tdarr_sync_plugins(confirm=)`, `tdarr_update_plugins(confirm=)` |
| Restart a node | `tdarr_restart_node(node_id=, confirm=)` |
| Disconnect a node (DANGER) | `tdarr_disconnect_node(node_id=, confirm=, acknowledge="disconnect")` |
| Worker limits | `tdarr_alter_worker_limit(node_id, worker_type, limit, confirm=)` |
| Cancel a worker item | `tdarr_cancel_worker_item(node_id, worker_type, confirm=)` |
| Kill a worker (DANGER) | `tdarr_kill_worker(node_id, worker_type, confirm=, acknowledge="kill")` |
| Backups | `tdarr_backup_status()`, `tdarr_backups()`, `tdarr_create_backup(confirm=)`, `tdarr_delete_backup(file_name, confirm=)` |
| Direct DB access | `tdarr_db(mode, collection, doc_id, obj, confirm=)` |
| DB collection list | `tdarr_collections()` |
| Toggle folder watch | `tdarr_toggle_folder_watch(library_id, confirm=)` |
| Codec excludes | `tdarr_add_video_codec_exclude(library_id, codec, confirm=)`, `tdarr_add_audio_codec_exclude(...)` |
| FFmpeg/HandBrake help | `tdarr_run_help_command(command="ffmpeg", args="-decoders")` |

## /cruddb — when to use it

The curated tools cover the common jobs. Reach for `tdarr_db` when you need:

- **Inspect anything** — `getAll` on any of the 8 collections to see raw state.
- **Fix a stuck record** — `update` to mutate a single doc (e.g. unstick a
  file's `healthCheck` status).
- **Bulk operations** not covered elsewhere — `removeAll` to wipe a table
  (DANGEROUS — confirm-gated).

Collections:
- **FileJSONDB** — one row per scanned file (the most useful for inspection).
- **LibrarySettingsJSONDB** — per-library settings.
- **StatisticsJSONDB** — per-node + per-plugin transcode statistics.
- **NodeJSONDB** — registered nodes.
- **SettingsGlobalJSONDB** — global server settings.
- **StagedJSONDB** — files staged for processing.
- **F2FOutputJSONDB** — F2F (file-to-file) outputs.
- **FlowsJSONDB** — Tdarr 2.x flow definitions.

Always `getAll` first to see the shape before writing.

## Safety

- **Confirm-gate every write.** State the change to the user, pass `confirm=true`
  only after approval.
- `tdarr_delete_file`, `tdarr_delete_unhealthy_files`, `remove-library-files`,
  and `set-all-status` are **irreversible**. Default to reads; explain
  consequences before passing confirm.
- DOUBLY-gated ops (`kill_worker`, `disconnect_node`, `kill_file_scanner`,
  `/cruddb` writes via `tdarr_db`) require `confirm=true` AND a typed
  `acknowledge` token. Never pass the acknowledge token without explicit owner
  approval AND a recovery plan.
- Never `removeAll` on any collection as a "test" — it wipes the table.

## Honesty

- **DOC-VERIFIED** — every tool's call shape is from the official API docs.
- **NOT LIVE-VERIFIED** — Tdarr is not deployed on this homelab. Run
  `_smoketest.py` after first deployment; the param shapes that fail are
  candidates for fixing in the curated tools.
- **Hard limits:** no live route-table introspection (Tdarr has no equivalent
  of the *arr stack's `/system/routes`); the static catalog may drift from
  future Tdarr versions. `tdarr_call` still reaches any new endpoint.

See `references/api-map.md` for the full endpoint list with param shapes.
