# Tdarr advanced features (the catalog you didn't know existed)

Surfaces every Tdarr capability beyond basic transcode. Built from the
official docs + live inspection of `SettingsGlobalJSONDB` + `NodeJSONDB` on
Tdarr 2.x. Each feature names where to find/configure it.

## Staging / review queue (the "accept-before-replace" pattern)

**What:** When `autoAcceptTranscodes = false` (default), every successful
transcode goes to the **Staging section** for human review BEFORE replacing
the original. You can accept (replace) or reject (discard transcode, keep
original) each one.

**Where:** `Tdarr tab → Staging section`. Toggle globally via
`SettingsGlobalJSONDB.autoAcceptTranscodes`.

**Why use it:**
- New plugin / flow — verify quality before letting it touch your library.
- Verifying a transcode didn't introduce A/V desync or banding.
- Catching HDR-stripped-to-SDR mistakes before they replace good REMUXes.

**Staging limits:** `stagedFileLimit` (default 100) — Tdarr pauses new
transcodes when staging reaches this many files. Bump it for batch runs.

**Notify on review:** `notificationsRequireReview: true` fires a Discord
notification when files enter the review queue.

**MCP tools:** `tdarr_db(mode="getAll", collection="StagedJSONDB")` to list
staged files; the `transcode-user-verdict` endpoint accepts/rejects.

## F2F (file-to-file) — non-destructive test transcodes

**What:** Transcode to a separate output file instead of replacing the
source. Stored in `F2FOutputJSONDB`.

**Why use it:** testing a plugin on a real file without risk. Output never
auto-replaces anything.

**Where:** per-library "Output folder" setting (separate from source).

## Hold-after-scanning (debounce for fresh files)

**What:** when `holdFilesAfterScanning` is enabled with a duration,
newly-scanned files wait in the **Hold** section for N seconds before
becoming eligible for processing.

**Why use it:** if Sonarr/Radarr/HandBrake or another tool is still writing
or modifying the file, you don't want Tdarr grabbing it mid-write. The hold
gives the upstream tool time to finish.

**Where:** per-library Source Options → "Hold files after scanning?".

**MCP:** `holdCheckerInterval` (default 300 sec) governs how often held
files get re-checked.

## Auto-pause on cache full (storage protection)

**What:** `autoPauseIfCacheFull = true` + `autoPauseIfCacheFullThreshold`
(default 20) pauses ALL nodes when the transcode-cache disk has less than
N% free space.

**Why use it:** prevents a runaway transcode loop from filling the cache
SSD and crashing the system.

**Where:** Global settings.

## Worker stall detector (watchdog for hung workers)

**What:** `workerStallDetector = true` + `workerStallDetectorInterval`
(default 300 sec) detects workers that haven't made progress in N seconds
and restarts them.

**Why use it:** NVENC/ffmpeg can hang on a corrupted frame and sit forever.
The stall detector reclaims the worker slot.

**Where:** Global settings.

## Closed-caption scanner (CEA-608/708 detection)

**What:** `closedCaptionScanner = true` per-library causes Tdarr to detect
embedded closed captions during scan. The result shows in the Search tab's
"Closed Captions" column.

**Why use it:** identify files that need `x7ac_Remove_Closed_Captions`
before they confuse media servers (some display both CC and subs).

**Where:** per-library Source Options → Scanners.

## Folder-watch modes (polling vs FS events)

**Two modes:**
- **Polling (default):** every `folderWatchScanInterval` (30 sec default),
  Tdarr walks the source folder checking for changes. Disk-intensive.
- **File-system events:** OS pushes events (inotify/FSEvents/ReadDirectoryChangesW).
  Less disk I/O but **unreliable on network/remote folders** (NFS, SMB).

**Where:** per-library Source Options → "Folder watch: Use file system events".

**Fallback:** "Run an hourly Scan (Find new)" if your folder watcher is
flaky.

## File scanner threads (SSD speedup)

**What:** `fileScannerThreads` per-library sets parallelism for library
scans. Default is 1 (serial).

**Why use it:** on fast SSDs (or your ZFS tank with ARC hot), bumping to
3-5 can cut scan time on a 10k-file library from hours to minutes.

**Caveat:** on spinning disks or network shares, more threads = more seeks
= SLOWER. Keep at 1 for SMR/HDD/NFS.

## File filter (exclusion list)

**What:** comma-separated substrings; any file PATH containing one is
skipped. Example: `grab,.index,User/AppData,-trailer,.mp4`.

**Where:** per-library Source Options → File filter.

## Schedules (per-hour worker limits)

**What:** each node has a 24-element `schedule` array (one bucket per hour,
"00-01" through "23-24"). Each bucket has its own per-worker-type limit.
With `scheduleEnabled=true`, Tdarr uses the current hour's limits instead
of `workerLimits`.

**Why use it:** "transcode GPU workers = 3 at night, 0 during the day"
without manual toggling. Combined with `ignoreSchedules` global override
for "do it now anyway".

**Where:** Node Options → Schedule (UI) or `NodeJSONDB.schedule` (DB).

**MCP:** Read via `tdarr_db(mode="getById", collection="NodeJSONDB",
doc_id="<node_id>")`. Modify via `tdarr_update_node(...)`.

## Library processing toggles

Per-library and per-node toggles that gate processing:

- **`Process Library`** (per-library): if OFF, files are removed from queues.
  Workers idle for this library.
- **`librariesToNotProcess`** (per-node): opt a node out of specific libraries.
  Useful when one node is for "slow archive" libraries and another is for
  "fast urgent" libraries.
- **`ignoreSchedules`** (global): override ALL schedules immediately.
- **`pauseAllNodes` / `softPauseAllNodes`** (global): emergency stop.

## Notifications (Discord webhook)

**What:** Tdarr posts to a Discord webhook on configurable events:
- `notificationsTranscodeSuccess/Error/Cancelled`
- `notificationsHealthcheckSuccess/Error/Cancelled`
- `notificationsServerStarted`
- `notificationsServerUpdateReady`
- `notificationsRequireReview` (staging queue)
- `notificationsCustomText` — prepend custom text to every notification.

**Where:** Global settings → notificationsDiscordWebhook + per-event toggles.

**Not implemented:** Slack/Pushover/Telegram-native — use the Discord webhook
with a relay bridge if you need them.

## Auto-updates (server + nodes + plugins)

**What:**
- `autoUpdateServer=true` + `autoUpdateServerVersion: "latest"` — auto-update
  the server. `killAllProcessesDuringUpdate=true` interrupts active transcodes
  (set false to defer).
- `autoUpdateNodes=true` — push updates to nodes.
- `pluginAutoUpdate=true` + `pluginCurrentSha` / `pluginLatestKnownSha` /
  `pluginPinnedSha` — auto-update community plugins from the GitHub repo.
  **Pin a SHA to freeze plugin versions** (reproducibility for production
  libraries).

**Custom plugin repo:** `communityPluginRepo` — point at a fork or air-gapped
mirror (URL must point to a zip archive matching the repo layout).

## Statistics (Tdarr's analytics layer)

**What:** `StatisticsJSONDB` tracks per-library, per-node, and per-plugin
transcode counts, size deltas, scores. Top-level fields:
- `totalFileCount`, `totalTranscodeCount`, `totalHealthCheckCount`
- `sizeDiff` (bytes saved/added)
- `tdarrScore` ( % of files in the library that wouldn't need transcoding —
  the "Tdarr score" of how done you are)
- `healthCheckScore`
- `table0Count/1/2` — counts in each status table
- `DBFetchTime` / `DBLoadStatus` / `DBQueue` — internal DB health

**Where:** Stats tab in UI, OR `tdarr_db(mode="getAll", collection="StatisticsJSONDB")`.

**Reset:** Library Options Button → "Reset stats: This library" / "Reset stats: All".

## Job reports (per-transcode forensic logs)

**What:** Each transcode/health-check produces a detailed job report
containing the full ffmpeg/HandBrake output, plugin decision logs, and
timing. Default keeps last 200 lines per report; `logFullCliOutput=true`
keeps full output (uses more disk; capped by `jobHistorySizeLimitGB`).

**Where to view:**
- Tdarr tab → Nodes section → current Worker
- Tdarr tab → Staging section → Report column
- Tdarr tab → Status section → each of the 7 status tables
- Search tab → Report column
- Web report viewer: `/#/tools/report-viewer` — paste a shared report

**Storage:** `jobReportsPath` defaults to `Tdarr/DB2/JobReports`. Custom path
is supported for putting reports on a separate volume.

**MCP:** `tdarr_list_footprint_reports(footprint_id=...)` to find reports
for a specific file (footprintId is Tdarr's content-hash for grouping a
file's history across transcodes).

## Library operations (the "Library Options" button)

Each library has these operations accessible from the libraries tab + via
the API:

| Op | Effect |
|---|---|
| Scan (Find new) | Delta scan: add new files, drop removed ones. Fast. |
| Scan (Fresh) | Clear DB + full rescan. Slow; use if DB is corrupt. |
| Requeue all (transcode) | Put every library file back in transcode queue. |
| Requeue all (health check) | Put every file back in health-check queue. |
| Reset stats: This library | Zero per-library stats. |
| Reset stats: All | Zero ALL library stats. |
| Duplicate library | Clone settings to a new library. |
| Clear library | Wipe DB; files on disk untouched. |
| Delete library | Remove from Tdarr; files untouched. |

## Backup management

- `backupLimit` (default 30) — keep last N backups; older are auto-pruned.
- `tdarr_create_backup(confirm=True)` — manual backup now.
- Backups include DBs + global settings + per-library config. **They do NOT
  include the files themselves or staged transcodes.**
- `tdarr_delete_backup(name, confirm=True)` to remove.
- `tdarr_backup_status()` / `tdarr_backups()` to inspect.

## Resolution boundaries (the tiered-plugin foundation)

**What:** `resBoundaries` defines width/height ranges for each resolution
class (480p / 576p / 720p / 1080p / 1440p / 4KUHD / DCI4K / 8KUHD).

**Why care:** tiered plugins (vdka_Tiered_*, DOOM_NVENC_Tiered, iiDrakeii)
use these boundaries to pick per-resolution CRF/CQ values. If you customise
the boundaries (e.g. treat 1440p as 1080p), the tiered plugins pick up the
change automatically.

**Where:** Global settings (visible in `SettingsGlobalJSONDB.resBoundaries`).

## Process priority (OS-level)

**What:** `processPriority: "normal"` (default). Set to `low`/`below_normal`
to yield CPU to other services; `high`/`realtime` to starve them.

**Where:** Global setting + per-node override (`NodeJSONDB.processPriority`).

## Tdarr Pro (paid tier)

**What:** `tdarrKey` activates Tdarr Pro. Unlocks:
- **Unlimited unmapped nodes** (free tier caps at 10MB video / 0.1MB other —
  effectively unusable for transcoding).
- Priority support.

Unmapped nodes let you offload processing to machines where share-mapping is
inconvenient (e.g. a remote VPS, a friend's PC). The node downloads the file,
processes it, and uploads the result automatically. `enableUnmappedNodes`
must be true server-side.

## Bumped files (requeue after worker-starvation)

**What:** `enableBumpedFiles=true` (default) — if a file couldn't get a
worker slot (e.g. all GPU workers busy), it gets "bumped" back into the
queue instead of being marked failed.

## Queue ordering

`queueSortType` controls queue ordering: `noSort` (FIFO), or sort by size /
resolution / etc. Plus three priority flags:
- `prioritiseTranscodes` / `prioritiseHealthChecks` — one queue jumps ahead.
- `prioritiseLibraries` — first library in the list goes first.
- `nodePriority` — `NodeJSONDB.priority` (lower = higher prio) routes work.

## Plugin variable templating (flows only)

**What:** in flow plugin inputs, you can template `args.inputFileObj`,
`args.userVariables.global.*`, `args.userVariables.library.*`. Examples:
- `{{{args.inputFileObj._id}}}` — current file path.
- `{{{args.inputFileObj.mediaInfo.track.0.BitRate}}}` — first track bitrate.
- `{{{args.userVariables.library.quality}}}` — per-library quality var.

**Why care:** define ONE flow that uses different ffmpeg CQ values per
library, or one webhook notifier that includes the filename. DRY.

**Where:** Tools tab for global vars; Libraries tab for library vars.

## See also
- `library-and-nodes.md` — full library + node config reference.
- `diagnostics-and-health.md` — health checks, job reports, troubleshooting.
- `integrations.md` — auth, webhooks, tdarr_inform, dashboards.
- `flows.md` — Tdarr 2.x flows with templating.
