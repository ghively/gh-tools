# Tdarr diagnostics, health checks, and troubleshooting

How to detect, diagnose, and fix Tdarr issues. Built from the docs + live
config on Tdarr 2.x.

## Health checks — what they are and how they work

Tdarr has a separate health-check worker pool (`healthcheckcpu` +
`healthcheckgpu`) that detects corrupted media files WITHOUT transcoding
them. Two modes:

### Quick health check
- **Engine:** HandBrake `--scan`.
- **What it checks:** file headers + stream metadata. Doesn't decode frames.
- **Speed:** seconds per file.
- **Workers:** CPU only (HandBrake's `--scan` is CPU-only).
- **Catches:** missing streams, broken containers, totally-corrupt headers.

### Thorough health check
- **Engine:** FFmpeg frame-by-frame decode.
- **What it checks:** every single frame decodes without error.
- **Speed:** minutes per file (depends on bitrate + hardware).
- **Workers:** CPU or GPU.
- **Per-hardware ffmpeg args** (from docs):
  - **Any** (CPU): `-stats -v error`
  - **NVENC**: `-stats -v error -hwaccel nvdec -hwaccel_output_format cuda`
  - **VAAPI**: `-stats -v error -hwaccel vaapi -hwaccel_output_format vaapi`
  - **QSV**: `-stats -v error -hwaccel vaapi -hwaccel_output_format vaapi`
- **Custom args** (per node, live-confirmed): `thoroughHealthCheckCpuExtraArgs`
  and `thoroughHealthCheckGpuExtraArgs` for OUTPUT args; `...ExtraInputArgs`
  for INPUT args. Use these to add things like `-err_detect explode_err` for
  stricter checking.

**Set per-library:** Library settings → Health Check → Quick/Thorough.

**Trigger:** Library Options Button → "Requeue all items (health check)".
Or via `tdarr_call(method="POST", path="/api/v2/scan-files", data='{"scanConfig": {...}}')`.

## Statistics — Tdarr's analytics layer

`StatisticsJSONDB` is the analytics collection. `tdarr_db(mode="getAll",
collection="StatisticsJSONDB")` returns the current snapshot.

Key fields:
- `totalFileCount` — files scanned.
- `totalTranscodeCount` — successful transcodes since last reset.
- `totalHealthCheckCount` — health checks since last reset.
- `sizeDiff` — bytes saved (negative) or added (positive) by transcodes.
- `tdarrScore` — % of files in "Transcode: Not required" status (the
  "library health" metric; 100% = nothing left to do).
- `healthCheckScore` — % of files that passed health check.
- `table0Count / table1Count / table2Count` — counts in the 3 status tables
  (success / not required / error-cancelled — verify via UI).
- `pies` — pie-chart data for the Stats tab.
- `DBFetchTime` / `DBLoadStatus` / `DBQueue` — internal DB health indicators.

On a fresh Tdarr install (your state right now): all counts = 0, scores =
NaN. After your first transcodes these populate.

## Job reports — forensic per-transcode logs

Every transcode produces a job report containing:
- The plugin decision log (why each plugin chose what it chose).
- The full ffmpeg/HandBrake stdout/stderr.
- Timing + size before/after.

**Where to view:**
- Tdarr tab → Nodes section → on the worker currently processing.
- Tdarr tab → Staging section → Report column.
- Tdarr tab → Status section → each of the 7 status tables → Report column.
- Search tab → Report column.
- **Web report viewer:** `http://<tdarr-host>:8265/#/tools/report-viewer` —
  paste a shared report for formatted view.

**Storage:**
- Default path: `Tdarr/DB2/JobReports`. Override via `jobReportsPath`.
- Truncated by default to last 200 lines. Set `logFullCliOutput=true` in
  Staging section to keep full output (uses more disk; capped by
  `jobHistorySizeLimitGB=10`).

**MCP access:** `tdarr_list_footprint_reports(footprint_id=...)` lists reports
for a specific `footprintId`. A `footprintId` is Tdarr's content-hash for
grouping all transcode attempts of the same source file.

## Footprint reports (cross-history view)

A `footprintId` is Tdarr's way of grouping every transcode attempt of the
same source. Use `tdarr_list_footprint_reports(footprint_id="<id>")` to
fetch them.

Practical use: when a transcode fails repeatedly, the footprint shows every
attempt with its error — useful for "this file always fails" triage.

## Common troubleshooting — lookup table

Built from Tdarr's official troubleshooting page + community knowledge.

### `Tdarr_Node - Server not alive IP:xxx PORT:xxx`

Network/firewall. Check:
1. `curl http://<server-ip>:8266/api/v2/status` from the node host — should
   return `{"status":"good",...}`.
2. The node initiates an OUTBOUND Socket.IO connection; no inbound port
   required. Allow outbound to server port (default 8266).
3. If using `serverIP=localhost` from a Docker container, switch to the
   host LAN IP — `localhost` inside a container is the container itself.

### Tdarr Node keeps registering/reconnecting

The node's persistent Socket.IO connection is bouncing. Check:
- Same version on server + node (mismatched versions fail handshake).
- Firewall allows long-lived WebSocket/HTTP-polling on 8266.
- Proxies in between don't kill idle connections.

### "I can't see the Tdarr UI in browser, just `Tdarr_Server` text"

UI is on port 8265, server on 8266. Open `http://host:8265/`.

### `OpenEncodeSessionEx failed: out of memory`

NVIDIA GPU hit the NVENC session limit. Per-GPU limits at
<https://www.elpamsoft.com/?p=Plex-Hardware-Transcoding>. Driver 551.61+
(Windows) / 535.98+ (Linux) REMOVED the consumer-GPU cap for most cards —
upgrade driver if you're hitting this on RTX 20/30/40 series.

**Live workaround:** lower `workerLimits.transcodegpu`. NVENC needs ~200-500
MB VRAM per session; you can also be VRAM-bounded if other GPU workloads
(comfyui, ollama) are active.

### `CUDA_ERROR_NO_DEVICE: no CUDA-capable device`

GPU not visible to the container. Check:
1. `nvidia-smi` works on the host.
2. `docker exec -it <tdarr_node> nvidia-smi` works inside the container —
   if not, NVIDIA Container Toolkit install or container GPU passthrough is
   broken.
3. Container env includes `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`
   (the `video` bit is required for NVENC).
4. Container start includes `--gpus all` (Docker Run) or
   `deploy.resources.reservations.devices` (Compose).

### Workers running but files not getting transcoded

Three likely causes:
1. **`processLibrary` is OFF** for the library (per-library toggle in
   Source Options). Files leave the queue.
2. **All worker counts are zero** OR **schedule all zeros** with
   `scheduleEnabled=true`. Bump `workerLimits` or disable the schedule.
3. **`gpuSelect` is `-` (none)** and your plugin emits GPU keywords — no GPU
   worker will claim the job. Set `gpuSelect` to `nvenc` (or `any`).

Check all three via:
```python
tdarr_db(mode="getById", collection="NodeJSONDB", doc_id="<node_id>")
```

### Transcode always fails for one specific file

Likely:
- **Corrupted source** — run a health check (thorough) on the file. If it
  fails health check, the source is bad; you can't fix it via transcode.
- **NVENC can't decode the source** — rare but happens with exotic codecs
  (e.g. some MPEG-4 variants). Try CPU-only fallback (`libx265`) for that file.
- **HDR metadata missing** — if the source claims HDR but lacks the color
  flags, NVENC HEVC may fail. Use `-pix_fmt yuv420p` (drop to SDR) or fix
  the source first.

Use `tdarr_list_footprint_reports(footprint_id=...)` to see every attempt's
error.

### Cache disk full

`autoPauseIfCacheFull=true` should pause before this happens. If you're
already full:
1. `tdarr_status()` to confirm.
2. Look for orphaned cache files in the transcode-cache folder (from killed
   transcodes). Safe to delete — Tdarr regenerates.
3. Increase cache disk size, or lower `workerLimits` so fewer transcodes
   run in parallel.

### Stats aren't updating

- `StatisticsJSONDB` updates after each transcode completes. If no
  transcodes are completing, stats stay flat.
- Reset via Library Options Button → "Reset stats: This library" / "All".

### DB load status shows "Loading" for a long time

`DBLoadStatus` field in `StatisticsJSONDB`. On large libraries, the DB can
take minutes to load into memory after startup. If it sticks at "Loading"
indefinitely, the DB may be corrupt — use Library Options → "Scan (Fresh)"
to rebuild.

## Diagnostics flow (the "what's wrong" playbook)

When something's off, check in this order:

1. **`tdarr_status()`** — server up? version? uptime?
2. **`tdarr_nodes()`** — node connected?
3. **`tdarr_db(mode="getById", collection="NodeJSONDB", doc_id=...)`** —
   workerLimits sane? gpuSelect set? schedule all-zero?
4. **`tdarr_db_statuses()`** — library DBs loaded?
5. **`tdarr_db(mode="getAll", collection="StatisticsJSONDB")`** — total
   counts moving? `DBLoadStatus: Stable`?
6. **`tdarr_node_log(node_id=...)`** — recent node errors.
7. **`tdarr_server_log()`** — recent server errors.
8. **`tdarr_performance_stats()`** — throughput dropping?

Each step surfaces a different layer of the stack. The MCP tools give you
all of this in one shot via `tdarr_full_status()`.

## See also
- `advanced-features.md` — stall detector, auto-pause, notifications.
- `library-and-nodes.md` — full node + library config (where most "not
  transcoding" issues live).
- `hardware-acceleration.md` — NVENC session limits, GPU passthrough recipe.
