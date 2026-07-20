---
name: tdarr-control
description: >-
  Control and administer a Tdarr distributed transcoding server via the tdarr
  MCP server, AND answer ANY question in the Tdarr / transcoding domain. Use
  this whenever the user wants to inspect, configure, operate, troubleshoot,
  OR understand Tdarr — including ANY of: server status / health, node +
  worker management (mapped/unmapped nodes, worker types, scheduling,
  per-hour limits, GPU/CPU routing, stall detection, auto-pause), library
  (source options, transcode cache, folder watch, file filter, hold-after-scan,
  closed-caption detection, containers), plugin + flow management (classic
  stacks, TypeScript flow plugins, global/library variables, templating),
  staging/review queue (autoAcceptTranscodes), F2F non-destructive test
  transcodes, backups, the powerful /cruddb (8 collections, full CRUD),
  health checks (quick/thorough, custom ffmpeg args, hwaccel per type),
  statistics + tdarrScore + healthCheckScore, job reports + footprint IDs,
  notifications (Discord webhook), auto-updates with plugin SHA pinning,
  authentication (auth=true + seededApiKey + tapi_ keys), codec-exclude and
  plugin-include management, transcode-user-verdict, server + node logs, OR
  anything else in the documented API. ALSO use this whenever the user asks
  ANY question about video transcoding, codecs (H.264/H.265/HEVC/AV1/VP9/
  Dolby), audio codecs (AAC/AC3/EAC3/DTS/TrueHD/FLAC), containers
  (MKV/MP4/AVI), subtitles (SRT/ASS/PGS), hardware acceleration (NVENC/QSV/
  VAAPI), ffmpeg encoder selection, CRF/CQ tuning, HDR preservation, building
  transcode workflows, picking community plugins (Migz/winsome/vdka/etc.),
  building Tdarr 2.x flows with variable templating, OR integrations
  (tdarr_inform from Sonarr/Radarr, tdarr_autoscan, Heimdall/Homer,
  Plex/Emby library-scan triggers). Trigger this skill whenever the user
  says "Tdarr", "transcode", "convert to HEVC/H.265/H.264", "compress my
  library", "make files smaller", "shrink REMUX", "what codec", "NVENC vs
  CPU", "FFmpeg for Tdarr", "Migz plugin", "Tdarr flow", "Tdarr auth",
  "Tdarr staging", "Tdarr schedule", "Tdarr notifications", "Tdarr health
  check", "Tdarr job reports", "Tdarr Pro", "Tdarr unmapped node", "is GPU
  being used", "what's transcoding now", "scan my library", "Tdarr
  statistics", or "why did this transcode fail" — do not answer from memory
  for facts; drive the live Tdarr server through the tools AND consult the
  deep references for codec/workflow/feature knowledge.
---

# Tdarr control

This skill drives a real Tdarr transcoding server through the **`tdarr` MCP
server** (tools shown as `tdarr_*`). **LIVE-VERIFIED on Tdarr 2.84.01** at
`gh-nvidia:8265`.

This skill is ALSO a deep Tdarr / transcoding knowledge base. **Read the
relevant reference before answering** codec/workflow/plugin/feature
questions — the docs have specific commands, plugin IDs, and decision trees
that beat guessing.

## Mental model

Tdarr is one POST-based HTTP API under `/api/v2/<endpoint>` (~67 endpoints).
Almost every endpoint takes POST with body `{"data": {...}}` — the client
wraps your params in `data` automatically.

### Core domain concepts

- **Library**: a media folder + transcode rules. Each library has source
  options, transcode cache, containers, a plugin stack OR flow, health-check
  config, and a schedule.
- **Node**: a worker process (typically Docker container) connecting to the
  server via outbound Socket.IO to port 8266. Types: **mapped** (same FS as
  server, or via path translators) and **unmapped** (Pro-only, downloads/
  uploads files independently).
- **Worker**: 4 types — `transcodecpu`, `transcodegpu`, `healthcheckcpu`,
  `healthcheckgpu`. GPU workers refuse CPU work (unless `allowGpuDoCpu=true`).
- **Plugin** (Classic): single JS file; Stage = Pre/Post-processing;
  Operation = Transcode or Filter.
- **Flow** (2.x): TypeScript-compiled directed graph; supports variable
  templating (`{{{args.inputFileObj._id}}}`, `{{{args.userVariables.library.X}}}`)
  and worker-type routing via tags.
- **Transcode cache**: REQUIRED per library; transcodes land here then
  REPLACE originals (or stage for review).
- **Staging section**: when `autoAcceptTranscodes=false` (default),
  transcodes await human accept/reject here before replacing.
- **Health check**: Quick (HandBrake `--scan`, CPU-only, headers) or
  Thorough (FFmpeg frame-by-frame, CPU or GPU).
- **/cruddb**: generic CRUD on 8 internal collections.
- **Tdarr ships with ffmpeg 7.1.4-Jellyfin + HandBrake**.

## Where to find what (the reference map)

| Question / Topic | Reference |
|---|---|
| What codec should I use? | `codecs.md` |
| NVENC vs CPU? FFmpeg command for HEVC/H.264/HDR? | `hardware-acceleration.md` |
| How do I build a [transcode X] workflow? | `workflows.md` |
| What does plugin X do? Which should I install? | `plugins.md` |
| Classic plugin stacks vs Tdarr 2.x flows? | `flows.md` |
| **Staging/review queue, F2F, hold-after-scan, schedules, notifications, auto-pause, stall detection, auto-updates, plugin pinning, queue ordering, resolution boundaries, Tdarr Pro** | **`advanced-features.md`** |
| Library + node config deep dive (source options, transcode cache, path translators, worker types, per-hour schedules, GPU select, health-check args) | `library-and-nodes.md` |
| Health checks (quick vs thorough), statistics, job reports, footprint IDs, troubleshooting | `diagnostics-and-health.md` |
| **Auth (auth=true, seededApiKey), Discord webhooks, tdarr_inform (Sonarr/Radarr), tdarr_autoscan, Plex/Emby scan triggers, Heimdall/Homer dashboards** | **`integrations.md`** |
| Full API endpoint catalog + param shapes | `api-map.md` |

## Advanced capabilities you might not know about (read this)

Before answering a Tdarr question, **skim this list** — many of these solve
problems users don't realize Tdarr has built in:

- **Staging / review queue** (`autoAcceptTranscodes=false`, default):
  transcodes don't replace originals until you accept them. Use when trying
  a new plugin or worrying about quality.
- **F2F (file-to-file)**: transcode to a SEPARATE output instead of
  replacing. Zero risk to source.
- **Hold-after-scan**: keep fresh files in "Hold" for N seconds so other
  tools (Sonarr/Radarr imports) finish first.
- **Auto-pause on cache full** (`autoPauseIfCacheFull=true`): stops
  runaway transcodes before they fill the disk.
- **Worker stall detector** (`workerStallDetector=true`): restart hung
  ffmpeg/NVENC processes automatically.
- **Schedules**: 24-element per-hour worker-limits array on each node.
  Pattern: GPU workers at night, none during the day.
- **Closed-caption scanner**: detect CEA-608/708 in video streams during
  scan; shows in Search tab.
- **Folder watch (polling vs FS events)**: polling is reliable but I/O-heavy;
  FS events are lighter but flaky on network shares. Hourly-scan fallback.
- **File scanner threads**: bump on SSDs for faster scans; keep at 1 on
  spinning disks.
- **Path translators**: server `/media` ↔ node `W:/media` mapping for
  cross-platform fleets. Env-var form must be base64-encoded JSON.
- **Unmapped nodes (Tdarr Pro)**: offload work to machines where share
  mapping is impossible; auto download/upload. Free tier caps at 10MB.
- **Tdarr Pro license** (`tdarrKey`): unlocks unlimited unmapped nodes.
- **Plugin pinning** (`pluginPinnedSha`): freeze community plugins at a
  specific commit for production stability.
- **Custom plugin repo** (`communityPluginRepo`): point at a fork or
  air-gapped zip mirror.
- **Notifications** (Discord webhook, per-event toggles): transcode
  success/error/cancelled, health-check success/error/cancelled, server
  started, server update ready, file entered review queue.
- **Tdarr Score + Health Check Score**: % of library in "Not required"
  status — your "how done am I" metric. Live in StatisticsJSONDB.
- **Job reports + footprint IDs**: forensic per-transcode logs; footprint ID
  groups all transcode attempts of the same source for "this file keeps
  failing" triage.
- **Quick vs thorough health checks**: quick uses HandBrake `--scan` (headers
  only, CPU); thorough uses FFmpeg frame-by-frame (CPU or GPU).
- **Per-node thorough-health-check custom ffmpeg args**:
  `thoroughHealthCheckCpuExtraArgs` / `...GpuExtraArgs` (output) and
  `...ExtraInputArgs` (input). Add stricter error detection.
- **Authentication**: `auth=true` on server, generate API keys via UI or
  `seededApiKey` env var (must start `tapi_`, ≥14 chars).
- **Resolution boundaries** (`resBoundaries`): configurable ranges for
  480p/576p/720p/1080p/1440p/4KUHD/DCI4K/8KUHD; tiered plugins pick up
  changes automatically.
- **Flow variable templating**: `{{{args.inputFileObj._id}}}`,
  `{{{args.userVariables.library.cq}}}` etc. — DRY flows with per-library
  values.
- **Flow worker routing**: `Worker Type` flow node routes work to nodes
  with matching tags. Essential for mixed-node fleets.
- **tdarr_inform** (Sonarr/Radarr/Whisparr webhook): push "new file"
  events to Tdarr without polling.
- **tdarr_autoscan**: alternative scan-trigger integration.
- **Bumped files**: re-queue files that couldn't get a worker slot instead
  of marking failed.
- **Queue ordering** (`queueSortType`, `prioritiseTranscodes/HealthChecks/
  Libraries`, `nodePriority`).
- **Library operations**: Scan Find New / Scan Fresh / Requeue all /
  Duplicate / Clear / Delete + Reset stats.
- **MCP plugin auth support**: `api_key` + configurable `api_key_header`
  in `config.local.json` for users who enable Tdarr auth.

Full details in `advanced-features.md`, `library-and-nodes.md`,
`diagnostics-and-health.md`, `integrations.md`.

## Start here (operational)

For "what's happening on Tdarr right now?" → **`tdarr_full_status`**:
status + nodes + DB statuses + perf/res stats in one composite call.

For "what file should I transcode?" → `tdarr_search_db(string=".mkv",
greater_than_gb=5)` to find big files, then inspect via
`tdarr_db(mode="getById", collection="FileJSONDB", doc_id="<file_path>")`.

For "what plugins are available?" → `tdarr_search_plugins(string="Migz",
plugin_type="standard")` (community plugins) or
`tdarr_search_flow_plugins(string="", plugin_type="flow")` (flow plugins).

For "what's configured?" → `tdarr_db(mode="getAll",
collection="SettingsGlobalJSONDB")` for global settings, OR
`tdarr_db(mode="getById", collection="NodeJSONDB", doc_id="<node_id>")` for
node config (workerLimits, schedule, gpuSelect, etc.).

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
| Statistics (Tdarr score, etc.) | `tdarr_db(mode="getAll", collection="StatisticsJSONDB")` |
| Global settings (all advanced features) | `tdarr_db(mode="getAll", collection="SettingsGlobalJSONDB")` |
| Node settings (workerLimits, schedule, gpuSelect) | `tdarr_db(mode="getById", collection="NodeJSONDB", doc_id=...)` |
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
| Footprint reports (per-file transcode history) | `tdarr_list_footprint_reports(footprint_id=...)` |
| Mark a file's verdict (transcode / ignore) | `tdarr_transcode_user_verdict(file_path, verdict=, confirm=)` |

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
│   → tdarr_db(mode="getById", collection="NodeJSONDB", doc_id=...).
│     Check gpuSelect (= '-'? not using GPU!), workerLimits.transcodegpu (>0?),
│     allowGpuDoCpu, schedule/scheduleEnabled.
│     Then tdarr_performance_stats() to see actual throughput.
│     Run tdarr_run_help_command(mode="ffmpeg", text="-encoders") and grep
│     for nvenc to verify ffmpeg was built with NVENC support.
│
├── "Tdarr isn't transcoding anything"
│   → Three likely causes (see diagnostics-and-health.md):
│     1. processLibrary=OFF for the library.
│     2. All workerLimits=0 OR schedule all-zero with scheduleEnabled=true.
│     3. gpuSelect='-' (no GPU) and plugin emits GPU keywords — no worker
│        will claim the job.
│
├── "Which plugin should I install?"
│   → Use references/plugins.md. Default recommendation for gh-nvidia:
│     MC93_Migz1FFMPEG (NVENC HEVC) + the Migz2-6 cleanup suite.
│
├── "Build me a custom transcode plugin"
│   → See references/workflows.md "Building a custom plugin" for the template,
│     then tdarr_create_plugin(definition=..., confirm=True).
│
├── "Configure Tdarr to notify me on Discord"
│   → Set notificationsDiscordWebhook + per-event toggles in
│     SettingsGlobalJSONDB. See integrations.md.
│
├── "Let Sonarr tell Tdarr when a new file is added"
│   → Install tdarr_inform. See integrations.md.
│
├── "Auto-pause if my cache SSD fills up"
│   → autoPauseIfCacheFull=true + autoPauseIfCacheFullThreshold=20.
│     See advanced-features.md.
│
├── "Schedule GPU workers to only run at night"
│   → Set scheduleEnabled=true + populate the 24-element schedule array
│     (00-08 night=3, 08-23 day=0, 23-24=3). See library-and-nodes.md.
│
├── "Convert to AV1"
│   → CAUTION: gh-nvidia's RTX 3060 (Ampere) has NO AV1 encode (NVENC AV1 is
│     RTX 40+ Ada only). AV1 would require libsvtav1 (CPU, slow: single-digit
│     fps at 1080p). Recommend HEVC instead — similar compression, much faster
│     on this hardware.
│
└── "How do I see what Tdarr decided about this file / why is it failing?"
    → tdarr_list_footprint_reports(footprint_id="<id>") for full history of
      attempts. Each report has the full plugin decision log + ffmpeg output.
      See diagnostics-and-health.md.
```

## gh-nvidia specifics (action items!)

The live audit found your `kind-koi` node has **`gpuSelect: '-'`** (no GPU
selected) and **all workerLimits = 0**. So nothing would actually transcode
even with a library + plugin stack configured. To get Tdarr working with
your RTX 3060:

1. Set `gpuSelect = "nvenc"` on the node.
2. Set `workerLimits.transcodegpu = 2`.
3. Verify GPU visibility: `docker exec -it tdarr_node nvidia-smi`.
4. Pick a library + plugin stack (`workflows.md`).
5. Run Scan (Find new) on the library.
6. Watch `tdarr_nodes()` + `tdarr_performance_stats()`.

See `library-and-nodes.md` for the full checklist.

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
- **Never transcode a file twice.** Always check the source codec first.
- **Never strip HDR by accident.** HDR sources MUST have color_primaries/
  color_trc/colorspace flags in any ffmpeg command. See `workflows.md` #6.
- Never `removeAll` on any /cruddb collection as a "test" — it wipes the table.
- **If `enableUnmappedNodes=true`, enable auth** (`auth=true` on server,
  generate API keys) — otherwise library files are downloadable by anyone
  with network access.

## Honesty

- **LIVE-VERIFIED on Tdarr 2.84.01**: 16/16 smoke tools pass + reversible
  backup create→list→delete proof PASSED. Live-confirmed: StatisticsJSONDB
  shape, NodeJSONDB shape (incl. schedule + workerLimits + gpuSelect +
  thoroughHealthCheckExtraArgs), SettingsGlobalJSONDB shape (incl. all
  advanced toggles), plugin search param shape (requires `pluginType`),
  delete-backup param shape (`name` not `fileName`), run-help-command shape
  (`mode` + `text`).
- **DOC-VERIFIED only** (param shapes not yet exercised live):
  - `scan_files(scan_config)` — exact scanConfig shape.
  - `toggle_schedule(type)`, `transcode_user_verdict(verdict)`, and write
    modes of `tdarr_db` — always probe with `getAll`/`getById` first.
- **Hardware limits**: no AV1 encode on RTX 3060 (NVENC AV1 is RTX 40+).

## See also
- `codecs.md` — full codec reference
- `hardware-acceleration.md` — NVENC + HDR + Docker GPU passthrough
- `workflows.md` — 6 canonical transcode patterns with real ffmpeg
- `plugins.md` — 107 community plugins organized by purpose
- `flows.md` — Tdarr 2.x flows with templating
- `advanced-features.md` — staging, F2F, schedules, notifications, auto-pause, etc.
- `library-and-nodes.md` — full library + node config
- `diagnostics-and-health.md` — health checks, job reports, troubleshooting
- `integrations.md` — auth, webhooks, tdarr_inform, dashboards
- `api-map.md` — full API reference
