# Library + node configuration deep dive

Everything you can configure per-library and per-node on Tdarr 2.x. Built
from the docs + live inspection of Tdarr 2.x config collections.

## Library anatomy

A library is one row in `LibrarySettingsJSONDB`. Each library has:

- **Name + ID** (`_id` is usually the library name).
- **Source folder** — where the media lives.
- **Transcode cache folder** — required; where transcodes land before
  replacing originals. Recommended: a cheap SSD.
- **Containers** — comma-separated file extensions Tdarr scans for
  (e.g. `mkv,mp4,avi`).
- **Transcode config** — plugin stack (1.x) or flow (2.x), plus output
  folder/replace-original decision.
- **Health check config** — quick/thorough, per-node hardware.
- **Schedule** — when workers process this library.
- **Source options** — folder watch, scanners, file filter, hold-after-scan.

## Library source options (per-library)

Every setting under Libraries → Options → Source Options:

| Setting | Type | Effect |
|---|---|---|
| `folderWatch` | bool | Auto-detect file adds/removes. |
| `processLibrary` | bool | Master ON/OFF for worker processing. If off, files leave the queue. |
| `scanOnStart` | bool | Scan when Tdarr starts; also enables hourly scan. |
| `closedCaptionScanner` | bool | Detect CEA-608/708 during scan. |
| `fileFilter` | str | Comma-separated path-substring exclusions. |
| `folderWatchScanInterval` | int | Seconds between polls (default 30). |
| `useFSEvents` | bool | Use OS file-system events instead of polling. Less I/O, unreliable on network shares. |
| `runHourlyScanFindNew` | bool | Hourly delta-scan fallback (use if FS events unreliable). |
| `fileScannerThreads` | int | Parallel scan threads (default 1; bump on SSDs). |
| `holdFilesAfterScanning` | bool + sec | Hold newly-scanned files for N sec before processing. |

## Library transcode cache

**Required.** Files transcode INTO the cache folder, then Tdarr COPIES them
back to the source folder, replacing the original.

Best practices:
- **Use a separate disk** from the source library — avoids read/write
  contention during transcodes.
- **Use an SSD** — transcode cache is heavy on small random writes; HDDs
  bottleneck hard.
- **Capacity** = at least as big as the largest file × max concurrent
  workers. For 4K REMUXes (~80GB) × 3 workers → 240GB minimum SSD.

## Library containers

The list of file extensions Tdarr will scan for. Default usually
`mkv,mp4,avi,mov,m4v,mpg,mpeg,ts,wmv,flv,vob,webm,m2ts`. Trim aggressively
if you only have one or two types — reduces scan time.

## Library transcode config

Each library has one transcode config (either plugin stack OR flow):

### Plugin stack (1.x, still fully supported)

A linear ordered list of plugins. Each file goes through every plugin in
order. A plugin can `continue`, `break` (stop the stack), `transcode`, or
`remove`. After a successful transcode, the file re-enters the stack from
the top until NO plugin wants to transcode it ("Transcode: Not required").

**Order matters:** put restrictive filters first (skip HEVC, skip 4K), then
specialists (audio converter), then broad transcoders (HEVC standardize),
then cleanup (clean audio/subs, reorder streams).

### Flow (2.x, recommended for new libraries)

A directed graph of nodes. Each node has 1 input handle and 1+ output
handles. See `flows.md` for the full system.

### Output decisions

Per-library choice of where the transcoded file goes:

- **Replace original** (default) — risky; no rollback. Pair with
  `autoAcceptTranscodes=false` to require review first.
- **Move to output folder** — non-destructive; original stays put.
- **Hold for review** — goes to Staging; you accept/reject manually.

## Library health check config

Per-library health check type:

- **Quick** — uses HandBrake `--scan`, headers only, CPU-only workers. Fast.
- **Thorough** — FFmpeg frame-by-frame. Slow but catches everything.

Health-check ffmpeg args (per node hardware type) — see
`diagnostics-and-health.md`.

## Node anatomy

A node is one row in `NodeJSONDB`. Key fields (live values from unraid-host's
`kind-koi` node in parens):

| Field | Purpose | Current value |
|---|---|---|
| `_id` | Node id | `kind-koi` |
| `workerLimits` | Current per-type worker counts | all 0 (idle) |
| `schedule` | 24-element per-hour worker limits | all 0 |
| `scheduleEnabled` | Use the schedule vs static workerLimits | False |
| `gpuSelect` | GPU type: `-` / `any` / `nvenc` / `vaapi` / `qsv` | **`-` (no GPU selected!)** |
| `nodeTags` | Tags for flow routing | `['mapped']` |
| `allowGpuDoCpu` | Let GPU workers also do CPU tasks | False |
| `maxGpuWorkers` | Cap on GPU workers | 100 |
| `nodePaused` | Pause state | False |
| `priority` | -1 (none) / 0 (highest) / 1 / 2 ... | 0 |
| `librariesToNotProcess` | Per-node library exclusions | (none) |
| `processPriority` | OS process priority | `normal` |
| `thoroughHealthCheck*ExtraArgs` | Custom ffmpeg output args | empty |
| `thoroughHealthCheck*ExtraInputArgs` | Custom ffmpeg input args | empty |
| `deleteCacheAnyStageError` | Cleanup on error | varies |
| `gpuSelect` | GPU type for hwaccel | `-` |

## Node types

### Mapped (default; what unraid-host has)

Same filesystem view as the server (or via `pathTranslators` mapping).
Required for any plugin that touches files via the server's filesystem
(extracting SRTs to the server's library, etc.).

### Unmapped (Tdarr Pro for full use)

Operates independently — downloads files from the server, processes them,
uploads results. No path-mapping needed.

**Free-tier limit:** 10MB video / 0.1MB other (basically unusable for real
media). Pro removes the cap.

**Caveats:**
- Only works with plugins that operate on the working file (audio/video
  transcode, remux). Plugins that create sidecar files (SRT extraction)
  leave those sidecars on the node, not the server.
- File-system operations (replace original, move to output) must run on a
  **mapped** node. The flow pattern: tag one node `unmapped` for transcode,
  then route to a `mapped` node for replace-original.

**Enable:** `enableUnmappedNodes=true` server-side, then `nodeType=unmapped`
+ `unmappedNodeCache=/cache` on the node.

## Path translators (for mapped nodes on mixed-platform fleets)

When server and node see the same files via different paths (e.g. server is
Linux `/media`, node is Windows `W:/media`), use `pathTranslators`:

```json
{
  "pathTranslators": [
    {"server": "/media", "node": "W:/media"},
    {"server": "/tv", "node": "Z:/television"}
  ]
}
```

As env var, must be **base64-encoded JSON** (Tdarr Node reads it literally
otherwise).

## Worker types (4)

| Type | Transcode arg pattern | Does |
|---|---|---|
| `transcodecpu` | No GPU keywords (nvenc/cuda/vaapi/qsv) | CPU-only transcodes |
| `transcodegpu` | GPU keywords present | GPU transcodes |
| `healthcheckcpu` | (health check args) | CPU health checks (quick + thorough) |
| `healthcheckgpu` | (health check args with GPU hwaccel) | GPU thorough health checks |

**Critical:** `transcodegpu` workers REFUSE to run a transcode whose
ffmpeg args don't contain a GPU keyword. So a plugin emitting
`-c:v hevc_nvenc` runs on GPU workers; one emitting `-c:v libx265` runs on
CPU workers. To let GPU workers also do CPU work, set `allowGpuDoCpu=true`.

**Starting workers via env vars:** `transcodegpuWorkers=2`,
`transcodecpuWorkers=1`, etc. — set as env vars on the node container;
Tdarr spins up that many workers on startup. UI can override after.

## Schedule (24-hour worker limits)

The 24-element `schedule` array lets you set per-hour worker counts:

```json
[
  {"_id": "00-01", "transcodegpu": 3, "transcodecpu": 0, ...},
  {"_id": "01-02", "transcodegpu": 3, "transcodecpu": 0, ...},
  ...
  {"_id": "08-09", "transcodegpu": 0, "transcodecpu": 0, ...},  // workday pause
  ...
  {"_id": "23-24", "transcodegpu": 3, "transcodecpu": 0, ...}
]
```

Common pattern: GPU-heavy at night, none during work hours.

`scheduleEnabled=false` makes Tdarr use `workerLimits` (a static dict)
instead. `ignoreSchedules=true` (global) overrides ALL schedules.

## unraid-host node setup checklist (action items from the live audit)

Your live node `kind-koi` currently has:
- `gpuSelect: '-'` — **no GPU selected**. Set to `nvenc` to use the RTX 3060.
- `workerLimits`: all zero. Set `transcodegpu` to 2 to start.
- `scheduleEnabled: False`. Either enable scheduling OR rely on `workerLimits`.
- `allowGpuDoCpu: False`. Fine for now (GPU work goes to GPU, CPU work waits).

To get Tdarr actually transcoding with your GPU:

1. **Set `gpuSelect` to `nvenc`** — via the UI (Node Options) or via
   `tdarr_update_node(node_id="kind-koi", updates='{"gpuSelect": "nvenc"}',
   confirm=True)`.
2. **Set `workerLimits.transcodegpu` to 2** — `tdarr_alter_worker_limit(
   node_id="kind-koi", worker_type="transcodegpu", limit=2, confirm=True)`.
3. **Verify GPU visibility in the container:**
   ```bash
   docker exec -it tdarr_node nvidia-smi
   docker exec -it tdarr_node ffmpeg -hide_banner -encoders | grep nvenc
   ```
4. **Pick a library + plugin stack** (see `workflows.md` for recommendations
   and `plugins.md` for the catalog). For unraid-host homelab: `MC93_Migz1FFMPEG`
   (NVENC HEVC) + the Migz cleanup suite.
5. **Run `Scan (Find new)`** on the library. Files appear in the transcode queue.
6. **Watch the queue drain** via `tdarr_nodes()` + `tdarr_performance_stats()`.

## See also
- `advanced-features.md` — staging/review, F2F, auto-pause, stall detection,
  notifications, auto-updates, plugin pinning, resolution boundaries.
- `diagnostics-and-health.md` — health check types, job reports, troubleshooting.
- `hardware-acceleration.md` — NVENC specifics for the RTX 3060.
