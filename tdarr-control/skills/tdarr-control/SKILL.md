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
metadata:
  hermes:
    tags: [tdarr, transcoding, ffmpeg, handbrake, media, mcp, homelab]
    category: media
    requires_tools: [tdarr_status]
    config:
      - {key: tdarr.host, prompt: Tdarr host/IP, default: gh-nvidia}
      - {key: tdarr.port, prompt: Tdarr port, default: 8265}
required_environment_variables:
  - name: TDARR_API_KEY
    prompt: Auth-proxy token (only if Tdarr sits behind nginx-basic-auth/Authentik)
    required_for: tdarr_* calls when Tdarr is fronted by an auth proxy
    optional: true
version: 0.5.0
author: ghively
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

Tdarr is one POST-based HTTP API under `/api/v2/<endpoint>` (65 endpoints).
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
| What does classic plugin X do? Which should I install? | `plugins.md` |
| Classic plugin stacks vs Tdarr 2.x flows? | `flows.md` |
| **Full flow-node catalog (85+ nodes: audio/video/file/ffmpegCommand/tools/automations)** | **`flow-plugin-catalog.md`** |
| **Media analysis / damage detection / validation / forensics (health checks, status tables, footprint IDs, stream filters)** | **`media-analysis.md`** |
| **Audio deep dive (codecs, normalization, downmix, language, Atmos, ffmpeg filters, bitrate reference)** | **`audio-deep-dive.md`** |
| **Staging/review queue, F2F, hold-after-scan, schedules, notifications, auto-pause, stall detection, auto-updates, plugin pinning, queue ordering, resolution boundaries, Tdarr Pro** | **`advanced-features.md`** |
| Library + node config deep dive (source options, transcode cache, path translators, worker types, per-hour schedules, GPU select, health-check args) | `library-and-nodes.md` |
| Health checks (quick vs thorough), statistics, job reports, footprint IDs, troubleshooting | `diagnostics-and-health.md` |
| **Auth (auth=true, seededApiKey), Discord webhooks, tdarr_inform (Sonarr/Radarr), tdarr_autoscan, Plex/Emby scan triggers, Heimdall/Homer dashboards** | **`integrations.md`** |
| Full API endpoint catalog + param shapes | `api-map.md` |

## Advanced capabilities you might not know about (read this)

Before answering a Tdarr question, **skim this list** — many of these solve
problems users don't realize Tdarr has built in:

**Analysis / damage detection:**
- **Quick health check** — HandBrake `--scan` (headers-only, CPU, fast).
- **Thorough health check** — FFmpeg frame-by-frame; configurable via
  `thoroughHealthCheckCpuExtraArgs` etc. for stricter checking (`-err_detect
  explode_err`).
- **8 status tables** — every file's last outcome (transcode success/not-
  required/error/cancelled, health check success/error/cancelled, staged/held).
- **Tdarr Score + Health Check Score** — "% library in 'Not Required'" metric.
- **Footprint IDs** — content-hash that groups every transcode attempt of a
  source; use `tdarr_list_footprint_reports` for forensic history.
- **Stream-property filters** — `checkVideoCodec/AudioCodec`, `checkVideoBitrate
  /AudioBitrate/OverallBitrate`, `checkVideoResolution`, `checkChannelCount`,
  `check10Bit`, `checkHdr`, `CheckVideoFramerate` — all flow nodes.
- **Validation after transcode** — `compareFileSizeRatio` (output should be
  0.3-1.5x source), `compareFileDurationRatio` (should be ~1.0 — catches desync),
  `compareFileSizeRatioLive` (mid-transcode bail-out).
- **WorkerVerdictHistoryJSONDB** — per-file decision history (transcode
  outcomes over time).
- **Custom validation via runCli** — run any ffprobe/ffmpeg astats/silencedetect
  in a flow.
- **Closed-caption scanner** — detect CEA-608/708 in video streams during scan.

**Audio capabilities:**
- **Audio normalization** — `normalizeAudio` flow node + `ffmpegCommandNormalizeAudio`
  for 2-pass EBU R128 loudnorm (-16 LUFS streaming / -23 broadcast).
- **Downmix** — 5.1/7.1 → stereo via `-ac 2` or custom `pan` filter with mix
  coefficients. Atmos → 7.1 (drops object metadata, keeps channel bed).
- **Codec conversion** — DTS/TrueHD → EAC3 (THE compatibility transcode),
  PCM/WAV → FLAC (lossless compression), any → AAC (universal).
- **Language routing** — keep native + English (`henk_Keep_Native_Lang_Plus_Eng`),
  set default stream (`c0r1_SetDefaultAudioStream`), reorder by language
  (`076a_re_order_audio_streams`).
- **Commentary removal** — strip director's commentary tracks (`sdd3_Remove_
  Commentary_Tracks`).
- **Silent/clipping detection** — ffmpeg `volumedetect`, `astats`, `silencedetect`
  via runCli.
- **Atmos preservation** — `-c:a copy` keeps Atmos metadata; transcoding
  loses object audio permanently.

**Workflow + operations:**
- **Staging / review queue** (`autoAcceptTranscodes=false`, default):
  transcodes don't replace originals until you accept them.
- **F2F (file-to-file)**: transcode to a SEPARATE output, zero risk to source.
- **Hold-after-scan**: keep fresh files in "Hold" for N seconds so other
  tools finish first.
- **Auto-pause on cache full** (`autoPauseIfCacheFull=true`).
- **Worker stall detector** (`workerStallDetector=true`).
- **Schedules**: 24-element per-hour worker-limits array on each node.
- **Path translators**: server `/media` ↔ node `W:/media` for cross-platform.
- **Unmapped nodes (Tdarr Pro)**: offload work to machines where share
  mapping is impossible.
- **Plugin SHA pinning** (`pluginPinnedSha`).
- **Custom plugin repo** (`communityPluginRepo`).
- **Notifications** — built-in Discord webhook; `apprise` flow node supports
  100+ services.
- **Library operations**: Scan Find New / Fresh / Requeue all / Duplicate /
  Clear / Delete + Reset stats.
- **Tdarr Pro license** (`tdarrKey`) — unlocks unlimited unmapped nodes.
- **Bumped files** — re-queue files that couldn't get a worker slot.
- **Queue ordering** (`queueSortType`, `prioritiseTranscodes/HealthChecks/
  Libraries`, `nodePriority`).
- **Resolution boundaries** (`resBoundaries`) — configurable for tiered plugins.

**Power-user flow nodes (the 85+ node catalog):**
- `webRequest` — call ANY HTTP endpoint (Emby/Plex/Bazarr/Autobrr/webhooks).
- `apprise` — single URL → 100+ notification services (Discord/Slack/Telegram/
  ntfy/email/SMS).
- `customFunction` — run arbitrary JS in a flow.
- `runCli` — run any shell command on the node.
- `runMkvpropedit` — fast metadata edits without re-encoding.
- `setFlowVariable` / `checkFlowVariable` / `arithmeticFlowVariable` —
  variables + math.
- `tagsWorkerType` / `tagsRequeue` — node routing (mapped/unmapped/GPU/CPU).
- `detectNonTdarrNvenc` — avoid GPU contention (ComfyUI/Ollama + Tdarr).
- `preventSleepWhileEncoding` — keep machine awake during transcodes.
- `pauseUnpauseAllNodes` — global pause from a flow.
- `failFlow` / `onFlowError` / `resetFlowError` — explicit error handling.
- `goToFlow` / `waitTimeout` — loops, retries, polling.
- `applyRadarrOrSonarrNamingPolicy` — auto-rename per *arr conventions.
- `notifyRadarrOrSonarr` — trigger *arr rescan.
- `unpack` — RAR/ZIP extraction.
- `checkForHardlinks` — hardlink detection.
- `calculateFileHash` — content hashing for dedup/change-tracking.
- `replaceOriginalFile` — the post-transcode replacement step.
- Variable templating: `{{{args.inputFileObj._id}}}`,
  `{{{args.userVariables.library.cq}}}`.

Full details in the relevant references — especially
`flow-plugin-catalog.md`, `media-analysis.md`, `audio-deep-dive.md`,
`advanced-features.md`.

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
| List libraries + their settings | `tdarr_libraries()` |
| Staging/review queue (staged transcodes) | `tdarr_staged_files(limit=)` |
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
| Create a local plugin | `tdarr_create_plugin(definition=, confirm=)` |
| Delete a plugin | `tdarr_delete_plugin(plugin_id=, confirm=)` |
| Sync/update all plugins | `tdarr_sync_plugins(confirm=)`, `tdarr_update_plugins(confirm=)` |
| Restart a node | `tdarr_restart_node(node_id=, confirm=)` |
| Disconnect a node (DANGER) | `tdarr_disconnect_node(node_id=, confirm=, acknowledge="disconnect")` |
| Worker limits | `tdarr_alter_worker_limit(node_id, worker_type, limit, confirm=)` |
| Cancel a worker item | `tdarr_cancel_worker_item(node_id, worker_type, confirm=)` |
| Kill a worker (DANGER) | `tdarr_kill_worker(node_id, worker_type, confirm=, acknowledge="kill")` |
| Backups | `tdarr_backup_status()`, `tdarr_backups()`, `tdarr_create_backup(confirm=)`, `tdarr_delete_backup(name, confirm=)` |
| Direct DB access (writes DOUBLY gated) | `tdarr_db(mode, collection, doc_id, obj, confirm=, acknowledge="<mode>")` |
| DB collection list | `tdarr_collections()` |
| Toggle folder watch | `tdarr_toggle_folder_watch(library_id, confirm=)` |
| Codec excludes | `tdarr_add_video_codec_exclude(library_id, codec, confirm=)`, `tdarr_add_audio_codec_exclude(...)`, `tdarr_remove_video_codec_exclude(...)`, `tdarr_remove_audio_codec_exclude(...)` |
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
│   → Use references/plugins.md (classic) or references/flow-plugin-catalog.md
│     (flows). Default recommendation for gh-nvidia:
│     MC93_Migz1FFMPEG (NVENC HEVC) + the Migz2-6 cleanup suite.
│
├── "Build me a custom transcode plugin"
│   → See references/workflows.md "Building a custom plugin" for the template,
│     then tdarr_create_plugin(definition=..., confirm=True).
│
├── "Configure Tdarr to notify me on Discord"
│   → Set notificationsDiscordWebhook + per-event toggles in
│     SettingsGlobalJSONDB. OR use the `apprise` flow node for 100+ services.
│     See integrations.md.
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
├── "How do I see what Tdarr decided about this file / why is it failing?"
│   → tdarr_list_footprint_reports(footprint_id="<id>") for full history of
│      attempts. Each report has the full plugin decision log + ffmpeg output.
│      See diagnostics-and-health.md.
│
├── "Find corrupted files in my library"
│   → Run thorough health checks: Library Options → Requeue all (health check)
│     with thorough mode enabled. Check table5Count in StatisticsJSONDB for
│     the corruption count. For stricter checking, set
│     thoroughHealthCheckCpuExtraArgs='-err_detect explode_err'. See
│     media-analysis.md.
│
├── "Find files below quality threshold (low bitrate)"
│   → Build a flow: checkVideoBitrate(min=1000000) → requireReview(). See
│     media-analysis.md.
│
├── "Validate that my last transcode run actually worked"
│   → Flow nodes compareFileSizeRatio(min=0.3, max=1.5) +
│     compareFileDurationRatio(min=0.99, max=1.01). On failure → requireReview.
│
├── "Normalize audio loudness across my library"
│   → Use normalizeAudio flow node OR ffmpegCommandNormalizeAudio OR
│     NIfPZuCLU_2_Pass_Loudnorm_Audio_Normalisation plugin. Target -16 LUFS
│     (streaming) or -23 LUFS (broadcast). See audio-deep-dive.md.
│
├── "Downmix 5.1 to stereo / convert DTS to EAC3"
│   → See audio-deep-dive.md for the ffmpeg commands. Plugin:
│     MC93_Migz5ConvertAudio (DTS→EAC3) or b39x_the1poet_surround_sound_to_ac3.
│
├── "Keep only English + native audio, drop commentary"
│   → Plugin: henk_Keep_Native_Lang_Plus_Eng + sdd3_Remove_Commentary_Tracks.
│
├── "Detect silent audio tracks or clipping"
│   → Use runCli flow node with `ffmpeg -af volumedetect` (silent) or
│     `ffmpeg -af astats` (clipping). See audio-deep-dive.md.
│
├── "Preserve Dolby Atmos during transcode"
│   → Use `-c:a copy` (don't transcode Atmos audio). Any audio transcode
│     loses object metadata permanently. See audio-deep-dive.md.
│
├── "Tone-map HDR → SDR properly"
│   → Use ffmpegCommandHdrToSdr flow node (proper color conversion). NEVER
│     just strip color flags — that produces washed-out SDR. See
│     media-analysis.md + workflows.md.
│
├── "Detect variable-framerate files (VFR causes sync issues)"
│   → CheckVideoFramerate flow node, OR runCli with ffprobe comparing
│     avg_frame_rate vs r_frame_rate.
│
├── "Avoid GPU contention between Tdarr and ComfyUI/Ollama"
│   → Use detectNonTdarrNvenc flow node + waitTimeout loop. See
│     flow-plugin-catalog.md.
│
├── "Send a custom webhook on transcode success"
│   → webRequest flow node (POST any HTTP) OR apprise flow node (100+
│     notification services). Templating: {{{args.inputFileObj._id}}}.
│
├── "Trigger Emby library rescan after transcode"
│   → webRequest flow node → POST http://emby:8096/Library/Refresh?api_key=...
│     with the Emby API key as a library variable. See integrations.md.
│
└── "Run arbitrary code / custom logic in a flow"
    → customFunction flow node (arbitrary JS) OR runCli (any shell command).
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
  `acknowledge` token (for `tdarr_db` the token is the mode name, e.g.
  `acknowledge="removeAll"`). Never pass the acknowledge token without
  explicit owner approval AND a recovery plan.
- **Never transcode a file twice.** Always check the source codec first.
- **Never strip HDR by accident.** HDR sources MUST have color_primaries/
  color_trc/colorspace flags in any ffmpeg command. See `workflows.md` #6.
- Never `removeAll` on any /cruddb collection as a "test" — it wipes the table.
- **If `enableUnmappedNodes=true`, enable auth** (`auth=true` on server,
  generate API keys) — otherwise library files are downloadable by anyone
  with network access.

## Honesty

Three verification buckets. Trust a tool only as far as its bucket allows.

**LIVE-VERIFIED on Tdarr 2.84.01** (exercised against the live server on
2026-07-20; smoke-test reads + reversible backup write proof PASSED):
- Reads: `tdarr_status`, `tdarr_full_status`, `tdarr_nodes`,
  `tdarr_db_statuses`, `tdarr_performance_stats`, `tdarr_res_stats`,
  `tdarr_backup_status`, `tdarr_backups`, `tdarr_search_db`,
  `tdarr_search_plugins`, `tdarr_search_flow_plugins`,
  `tdarr_search_flow_templates`, `tdarr_run_help_command`, and `tdarr_db`
  READ modes (getAll/getById) on StatisticsJSONDB, NodeJSONDB,
  SettingsGlobalJSONDB, LibrarySettingsJSONDB, FlowsJSONDB.
- Writes: `tdarr_create_backup` + `tdarr_delete_backup` (reversible
  create→list→delete proof PASSED).
- Param shapes corrected against the live API: `search-db` requires
  `lessThanGB`/`greaterThanGB`; `search-plugins` requires `pluginType`;
  `delete-backup` wants `name` (not `fileName`); `run-help-command` wants
  `mode`+`text` (not `command`+`args`); `alter_worker_limit` worker_type enum
  confirmed as `transcodecpu`/`transcodegpu`/`healthcheckcpu`/`healthcheckgpu`
  (from live NodeJSONDB.workerLimits).

**DOC-VERIFIED only** (built from the docs, call/param shape NOT exercised
live — the endpoint is documented but treat the payload as assumed):
- `scan_files(scan_config)` — assumed scanConfig shape.
- `toggle_schedule(type)`, `transcode_user_verdict(verdict)` — assumed
  enum/string values; probe a live record first.
- `tdarr_db` WRITE modes (insert/update) — per-collection `obj` shape varies
  and is not live-verified; always `getAll`/`getById` first.
- Plus the remaining doc-built tools: `tdarr_server_log`, `tdarr_node_log`,
  `tdarr_scan_individual_file`, `tdarr_filescanner_status`,
  `tdarr_verify_folder_exists`, `tdarr_get_subdirectories`,
  `tdarr_delete_file`, `tdarr_delete_unhealthy_files`,
  `tdarr_kill_file_scanner`, `tdarr_read_plugin`, `tdarr_install_plugin`,
  `tdarr_delete_plugin`, `tdarr_sync_plugins`, `tdarr_update_plugins`,
  `tdarr_verify_plugin`, `tdarr_restart_node`, `tdarr_disconnect_node`,
  `tdarr_alter_worker_limit`, `tdarr_poll_worker_limits`,
  `tdarr_cancel_worker_item`, `tdarr_kill_worker`, `tdarr_toggle_folder_watch`,
  `tdarr_add_video_codec_exclude`, `tdarr_add_audio_codec_exclude`,
  `tdarr_list_footprint_reports`.

**added-post-verification** (written after the 2026-07-20 live run; present in
`mcp/_smoketest.py` but NOT yet re-run against live Tdarr):
- `tdarr_libraries` (getAll LibrarySettingsJSONDB — the underlying call was
  live-observed, but this wrapper tool has not been re-run).
- `tdarr_staged_files` (getAll StagedJSONDB — row shape not yet live-observed).
- `tdarr_create_plugin(definition)` — assumed body shape.
- `tdarr_remove_video_codec_exclude`, `tdarr_remove_audio_codec_exclude`.

**Hardware limits**: no AV1 encode on RTX 3060 (NVENC AV1 is RTX 40+).

## See also
- `codecs.md` — full codec reference
- `hardware-acceleration.md` — NVENC + HDR + Docker GPU passthrough
- `workflows.md` — 6 canonical transcode patterns with real ffmpeg
- `plugins.md` — 107 classic community plugins organized by purpose
- `flows.md` — Tdarr 2.x flows with templating
- **`flow-plugin-catalog.md` — full 85+ flow-node catalog**
- **`media-analysis.md` — damage detection, validation, forensics**
- **`audio-deep-dive.md` — comprehensive audio handling**
- `advanced-features.md` — staging, F2F, schedules, notifications, auto-pause, etc.
- `library-and-nodes.md` — full library + node config
- `diagnostics-and-health.md` — health checks, job reports, troubleshooting
- `integrations.md` — auth, webhooks, tdarr_inform, dashboards
- `api-map.md` — full API reference
