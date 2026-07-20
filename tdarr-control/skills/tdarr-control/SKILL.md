---
name: tdarr-control
description: >-
  Control and administer a Tdarr distributed transcoding server via the tdarr
  MCP server. Use this whenever the user wants to inspect, configure, operate,
  troubleshoot, OR understand Tdarr — including ANY of: server status / health,
  node + worker management (list, restart, disconnect, alter worker limits,
  cancel jobs, kill workers), library scanning (search-db, scan files, kill
  file scanner), plugin + flow management (search, install, edit, delete, sync,
  update, flow templates), backups (status, list, create, delete), the powerful
  /cruddb (full CRUD on 8 internal collections), codec-exclude and
  plugin-include management, transcode-user-verdict, server + node logs. ALSO
  use this whenever the user asks ANY question about video transcoding,
  codecs (H.264/H.265/HEVC/AV1/VP9/Dolby), audio codecs (AAC/AC3/EAC3/DTS/
  TrueHD/FLAC), containers (MKV/MP4/AVI), subtitles (SRT/ASS/PGS), hardware
  acceleration (NVENC/QSV/VAAPI), ffmpeg encoder selection, CRF/CQ tuning,
  HDR preservation, building transcode workflows, picking community plugins
  (Migz/winsome/etc.), building Tdarr 2.x flows, OR anything else in the
  Tdarr/transcoding domain. Trigger this skill whenever the user says
  "Tdarr", "transcode", "convert to HEVC/H.265/H.264", "compress my library",
  "make files smaller", "shrink REMUX", "what codec", "NVENC vs CPU",
  "FFmpeg for Tdarr", "Migz plugin", "Tdarr flow", "is GPU being used",
  "what's transcoding now", "scan my library", or "why did this transcode
  fail" — do not answer from memory for facts; drive the live Tdarr server
  through the tools AND consult the deep references for codec/workflow
  knowledge.
---

# Tdarr control

This skill drives a real Tdarr transcoding server through the **`tdarr` MCP
server** (tools shown as `tdarr_*`). **LIVE-VERIFIED on Tdarr 2.84.01** at
`gh-nvidia:8265`. Auth: NONE by default (Tdarr trusts the LAN).

This skill is also your **Tdarr/transcoding knowledge base** — the references
cover codecs, hardware acceleration, workflow patterns, the plugin catalog,
and the flow system. Use them.

## Mental model

Tdarr is one POST-based HTTP API under `/api/v2/<endpoint>` (~67 endpoints).
Almost every endpoint takes POST with body `{"data": {...}}` — the client
wraps your params in `data` automatically.

Key domain concepts:
- **Library**: a configured media folder + transcode rules (plugins or flows).
- **Node**: a worker process (typically Docker container) that connects to the
  server and pulls transcode jobs. Has a `nodeID` and runs CPU/GPU workers.
- **Worker types** (live-confirmed on Tdarr 2.84.01): `transcodecpu`,
  `transcodegpu`, `healthcheckcpu`, `healthcheckgpu`.
- **Plugin**: JavaScript file that decides whether/how to transcode a file.
- **Flow**: Tdarr 2.x visual node-graph workflow (newer than plugins; can do
  branches + loops).
- **/cruddb**: powerful generic endpoint — full CRUD on 8 internal collections
  (FileJSONDB, LibrarySettingsJSONDB, StatisticsJSONDB, NodeJSONDB,
  SettingsGlobalJSONDB, StagedJSONDB, F2FOutputJSONDB, FlowsJSONDB).
- **Cache folder**: where transcodes-in-progress live before being moved to
  output (or replacing the original).
- **Tdarr ships with ffmpeg 7.1.4-Jellyfin + HandBrake** bundled.

Two layers of tools:
1. **Curated tools** — ergonomic one-shot calls for common jobs.
2. **Generic passthrough** — `tdarr_call` + `tdarr_list_endpoints`.

## Where to find what (the reference map)

| Question | Reference |
|---|---|
| "What codec should I use?" | `references/codecs.md` |
| "NVENC vs CPU? What ffmpeg command?" | `references/hardware-acceleration.md` |
| "How do I build a [transcode X] workflow?" | `references/workflows.md` |
| "What does plugin X do? Which should I install?" | `references/plugins.md` |
| "Tdarr 2.x flows vs plugin stacks?" | `references/flows.md` |
| "What API endpoints exist + what shapes?" | `references/api-map.md` |

**Read the relevant reference BEFORE answering** codec/workflow/plugin
questions — the docs have specific ffmpeg commands, plugin IDs, and decision
trees that beat guessing.

## Start here (operational)

For "what's happening on Tdarr right now?" → call **`tdarr_full_status`**:
status + nodes + DB statuses + perf/res stats in one composite call.

For "what file should I transcode?" → call `tdarr_search_db(string=".mkv",
greater_than_gb=5)` to find big files, then inspect via `tdarr_db(mode="getById",
collection="FileJSONDB", doc_id="<file_path>")`.

For "what plugins are available?" → `tdarr_search_plugins(string="Migz",
plugin_type="standard")`.

## Operational tool map

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
| Filescanner status | `tdarr_filescanner_status(db_name)` |
| Kill scanner (DANGER) | `tdarr_kill_file_scanner(db_name, confirm=, acknowledge="kill")` |
| Browse server FS | `tdarr_verify_folder_exists(path)`, `tdarr_get_subdirectories(path)` |
| Delete a file (DANGER) | `tdarr_delete_file(file_path=, confirm=)` |
| Search plugins | `tdarr_search_plugins(string=, plugin_type="standard")` |
| Search flow plugins | `tdarr_search_flow_plugins(string=, plugin_type="flow")` |
| Search flow templates | `tdarr_search_flow_templates(string=)` |
| Install community plugin | `tdarr_install_plugin(plugin_id=, confirm=)` |
| Read a plugin | `tdarr_read_plugin(plugin_id)` |
| Delete a plugin | `tdarr_delete_plugin(plugin_id=, confirm=)` |
| Sync/update all plugins | `tdarr_sync_plugins(confirm=)`, `tdarr_update_plugins(confirm=)` |
| Restart a node | `tdarr_restart_node(node_id=, confirm=)` |
| Disconnect a node (DANGER) | `tdarr_disconnect_node(node_id=, confirm=, acknowledge="disconnect")` |
| Worker limits | `tdarr_alter_worker_limit(node_id, worker_type, limit, confirm=)` |
| Cancel a worker item | `tdarr_cancel_worker_item(node_id, worker_type, confirm=)` |
| Kill a worker (DANGER) | `tdarr_kill_worker(node_id, worker_type, confirm=, acknowledge="kill")` |
| Backups | `tdarr_backup_status()`, `tdarr_backups()`, `tdarr_create_backup(confirm=)`, `tdarr_delete_backup(name, confirm=)` |
| Direct DB access | `tdarr_db(mode, collection, doc_id, obj, confirm=)` |
| DB collection list | `tdarr_collections()` |
| Toggle folder watch | `tdarr_toggle_folder_watch(library_id, confirm=)` |
| Codec excludes | `tdarr_add_video_codec_exclude(library_id, codec, confirm=)`, `tdarr_add_audio_codec_exclude(...)` |
| FFmpeg/HandBrake help | `tdarr_run_help_command(mode="ffmpeg", text="-decoders")` |

## Decision tree: which transcode workflow for this user request?

```
User wants...
│
├── "Make my library smaller" / "compress everything"
│   → Workflow 1 (Standardize-on-HEVC). For gh-nvidia (RTX 3060), use
│     MC93_Migz1FFMPEG (NVENC) at CQ 21, 10-bit. Skip files already HEVC/AV1.
│     See references/workflows.md.
│
├── "Make this play on Apple TV / web / old TV"
│   → Workflow 2 (Compatibility: H.264 + AAC in MP4).
│
├── "Convert DTS/TrueHD to something universal"
│   → Workflow 3 (Audio normalization: DTS/TrueHD → EAC3 640kbps).
│
├── "Clean up my library without quality loss"
│   → Workflow 4 (Remux + clean streams; no video re-encode).
│
├── "Shrink 4K HDR REMUXes without losing HDR"
│   → Workflow 6 (HDR preservation). MUST pass color_primaries/color_trc/
│     colorspace flags or HDR is stripped to washed-out SDR.
│
├── "What codec is this file?"
│   → tdarr_db(mode="getById", collection="FileJSONDB", doc_id="<path>")
│     OR tdarr_search_db(string="<filename>").
│
├── "Is Tdarr using my GPU?"
│   → tdarr_nodes() and inspect workerLimits.transcodegpu (should be >0).
│     Then tdarr_performance_stats() to see actual throughput.
│     Run tdarr_run_help_command(mode="ffmpeg", text="-encoders") and grep
│     for nvenc to verify ffmpeg was built with NVENC support.
│
├── "Which plugin should I install?"
│   → Use references/plugins.md. Default recommendation for gh-nvidia:
│     MC93_Migz1FFMPEG (NVENC HEVC) + the Migz2-6 cleanup suite.
│
├── "Build me a custom transcode plugin"
│   → See references/workflows.md "Building a custom plugin" for the template,
│     then tdarr_create_plugin(definition=..., confirm=True).
│
└── "Convert to AV1"
    → CAUTION: gh-nvidia's RTX 3060 (Ampere) has NO AV1 encode (NVENC AV1 is
      RTX 40+ Ada only). AV1 would require libsvtav1 (CPU, slow: single-digit
      fps at 1080p). Recommend HEVC instead — similar compression, much faster
      on this hardware.
```

## /cruddb — when to use it

The curated tools cover the common jobs. Reach for `tdarr_db` when you need:

- **Inspect anything** — `getAll` on any of the 8 collections to see raw state.
- **Find a file's transcode decision history** — `getById` on `FileJSONDB` with
  the file path as `docID`.
- **Read or modify the global settings** — `SettingsGlobalJSONDB` (worker pool
  config, default transcode config, etc.).
- **Inspect node worker_limits** — `NodeJSONDB`.
- **Inspect flows you've built** — `FlowsJSONDB` (raw JSON of the flow graph).
- **Fix a stuck record** — `update` to mutate a single doc.

Always `getAll` (or `getById`) first to see the shape before writing. See
`references/api-map.md` for the full /cruddb schema.

## gh-nvidia specifics

The plugin is configured against `gh-nvidia:8265` by default. Tdarr on this
box has access to:

- **NVIDIA RTX 3060** (12 GB VRAM) — 3rd-gen NVENC, hevc + h264 encode
  (NOT AV1 encode). Driver 595.
- **CPU** — multiple cores; useful for health-check workers and as a fallback
  transcoder.
- **Storage** — `/tank/media` (the library) and the Tdarr internal volumes.

Recommended defaults for this box:
- `workerLimits.transcodegpu`: 2-3 (start at 2, raise if VRAM allows).
- `workerLimits.transcodecpu`: 0-1 (the GPU is the right default).
- `workerLimits.healthcheckgpu`: 1.
- `workerLimits.healthcheckcpu`: 1-2.
- Default transcode target: HEVC NVENC `-preset p6 -tune hq -rc vbr -cq 21
  -pix_fmt yuv420p10le` (10-bit).

See `references/hardware-acceleration.md` for the full hardware analysis.

## Safety

- **Confirm-gate every write.** State the change, pass `confirm=true` only
  after approval.
- `tdarr_delete_file`, `tdarr_delete_unhealthy_files`, `remove-library-files`,
  and `set-all-status` are **irreversible**. Default to reads; explain
  consequences before passing confirm.
- DOUBLY-gated ops (`kill_worker`, `disconnect_node`, `kill_file_scanner`,
  `/cruddb` writes via `tdarr_db`) require `confirm=true` AND a typed
  `acknowledge` token. Never pass the acknowledge token without explicit owner
  approval AND a recovery plan.
- **Never transcode a file twice.** Every lossy → lossy transcode degrades
  quality. Always check the source codec first (`tdarr_db(mode="getById",
  collection="FileJSONDB", doc_id="<path>")`) — if it's already HEVC at
  reasonable bitrate, leave it alone.
- **Never strip HDR by accident.** HDR sources MUST have color_primaries/
  color_trc/colorspace flags in any ffmpeg command. See `references/workflows.md`
  Workflow 6.
- Never `removeAll` on any /cruddb collection as a "test" — it wipes the table.

## Honesty

- **LIVE-VERIFIED on Tdarr 2.84.01** (2026-07-20): 16/16 smoke tools pass +
  reversible backup create→list→delete proof PASSED.
- **DOC-VERIFIED only** (param shapes not yet exercised live):
  - `scan_files(scan_config)` — exact scanConfig shape.
  - `toggle_schedule(type)`, `transcode_user_verdict(verdict)`, and write
    modes of `tdarr_db` — always probe with `getAll`/`getById` first.
- **Hardware limits:** no AV1 encode on RTX 3060 (NVENC AV1 is RTX 40+).

See `references/api-map.md` for the full endpoint list and
`references/{codecs,hardware-acceleration,workflows,plugins,flows}.md` for the
deep domain knowledge.
