# OPTIMIZATION.md — Emby Server Performance & Optimization (Emby 4.7.14.0, Linux)

> **Live facts for gh-media:** Premiere is ACTIVE (hardware transcoding is
> licensed). Transcode temp is `/var/emby-transcode-temp`. Check current
> encoding settings with `emby_get_config("encoding")`; live transcode load
> with `emby_sessions(active_only=true)` (Transcoding block includes
> HardwareAccel and Reasons when the server reports them).

Official performance guidance and the API knobs that implement it. Emby-specific (not
Jellyfin). Config writes follow the round-trip rule (see configuration.md §3).

## 1. Hardware acceleration — the biggest win

Enable GPU decode/encode so transcodes don't saturate the CPU. On Linux Emby supports
NVIDIA NVDEC/NVENC, VAAPI and Intel QuickSync (official Hardware-Acceleration articles).
**Hardware transcoding requires Emby Premiere.**

Setup (Linux):
- NVIDIA: install the official driver from nvidia.com (not distro repos), ≥ 470.57;
  headless is supported. Decoders: H.264/H.265/MPEG2/MPEG4/VC1/VP8/VP9; encoder: H.264
  (4.7-era Linux guidance).
- Intel VAAPI/QSV: drivers are bundled with Emby Server; ensure the `emby` user can open
  `/dev/dri/renderD128` (default `EncodingOptions.VaapiDevice`) — add to `render`/`video`
  groups if needed. Docker: pass `--device /dev/dri`.
- AMD VAAPI: install AMD driver, never "headless mode" during install.
- Dashboard: Transcoding → hardware decoder/encoder options (Auto is the official default
  recommendation; per-codec decode toggles map to `HardwareDecodingCodecs` +
  `EnableHardwareEncoding` in the `encoding` named config — `GET/POST
  /System/Configuration/encoding`).

Verification:
1. Start a forced transcode, then read the newest `ffmpeg-transcode-*.txt` log
   (`GET /System/Logs/Log?Name=...`): hardware pipelines show `h264_vaapi` / `h264_qsv` /
   `h264_nvenc` as decoder/encoder; `libx264` means software.
2. `hardware_detection-*.txt` (written at startup) lists what the server detected. Staff
   note: VAAPI errors there are normal on NVIDIA-only boxes.
3. `nvidia-smi` should list Emby's ffmpeg while transcoding (NVIDIA).
4. Dashboard active-stream card shows green hardware badges.
5. Newer 4.8/4.9 servers additionally expose `VideoDecoderIsHardware` /
   `VideoEncoderIsHardware` / `VideoDecoderHwAccel` / `VideoEncoderHwAccel` in
   `GET /Sessions` → `TranscodingInfo`; on 4.7.14 prefer the log method.

Sources:
- https://emby.media/support/articles/Hardware-Acceleration-Overview.html
- https://emby.media/support/articles/Hardware-Acceleration-on-Linux.html
- https://emby.media/support/articles/Hardware-Acceleration-with-Docker.html
- https://emby.media/community/topic/118520-how-to-check-hardware-acceleration/

## 2. Kill unnecessary transcodes at the source (TranscodeReasons)

Poll `GET /Sessions` and inspect `TranscodingInfo.TranscodeReasons[]` (full enum in
troubleshooting.md §4). Typical fixes per reason:

- `ContainerBitrateExceedsLimit` → raise the app's "Max streaming bitrate" (Auto), the
  user policy `RemoteClientBitrateLimit`, or server `RemoteClientBitrateLimit`. Also check
  `LocalNetworkSubnets`: if your LAN isn't listed, LAN clients are treated as remote and
  capped.
- `SubtitleCodecNotSupported` → PGS/VOBSUB burn-in; prefer SRT/ASS text subs.
- `VideoCodecNotSupported`/`ContainerNotSupported` → store media as H.264/HEVC in MP4/MKV,
  or pre-convert with Emby's Convert feature.
- `AudioCodecNotSupported`/`AudioChannelsNotSupported` → audio-only transcode is cheap; OK.
- `DirectPlayError` → check network path mapping / permissions.

`TranscodingInfo` also exposes `CurrentCpuUsage`, `AverageCpuUsage`, `CompletionPercentage`
and `CurrentThrottle` (newer builds) for live load monitoring.

Source: OpenAPI `TranscodingInfo`/`TranscodeReason` schemas —
https://github.com/MediaBrowser/Emby.SDK/blob/master/Resources/OpenApi/openapi_v3.json

## 3. Transcoding settings (named config `encoding`)

`GET /System/Configuration/encoding` → modify → `POST /System/Configuration/encoding`:

- `EnableThrottling` (default true) + `ThrottleDelaySeconds` (default ~180): once the
  transcode buffer is far ahead of playback, ffmpeg is throttled to save CPU/IO. Keep on;
  disable only when diagnosing stutter blamed on throttle resume.
- `EncodingThreadCount`: -1 (Auto) is the official recommendation ("should remain on Auto").
- `H264Crf` (default 23; lower = better quality & more bitrate) and `H264Preset`
  (faster preset = less CPU per stream, larger output; `veryfast` is a common choice for
  many concurrent streams).
- `DownMixAudioBoost` (default 2) — only affects downmixed audio loudness.
- `TranscodingTempPath` — put on a fast disk (SSD/tmpfs) that is NOT the media disk;
  dedicate the folder (Emby purges it). Cleaned by the hidden "Clean Transcode Directory"
  scheduled task.
- `EnableSubtitleExtraction` — allows pre-extracting embedded text subs instead of
  transcode-time burn-in.

Sources:
- https://emby.media/support/articles/Transcoding.html
- https://github.com/MediaBrowser/Emby.Common/blob/master/MediaBrowser.Model/Configuration/EncodingOptions.cs

## 4. Library scan & task scheduling

Scans, chapter-image extraction and metadata refreshes are IO/CPU heavy. Official model:
they run as Scheduled Tasks with five trigger types — Daily, Weekly, Interval, On startup,
On wake (https://emby.media/support/articles/Scheduled-Tasks.html).

Via API:
- `GET /ScheduledTasks?IsHidden=false` — find tasks (match by `Key`, e.g. `RefreshLibrary`
  for "Scan media library"; names/keys vary by plugins installed).
- `POST /ScheduledTasks/{Id}/Triggers` — body is the FULL array of `TaskTriggerInfo`
  objects: `{"Type":"DailyTrigger","TimeOfDayTicks":108000000000}` (03:00; ticks =
  100-ns units, 1 h = 36 000 000 000), `{"Type":"IntervalTrigger","IntervalTicks":...}`,
  `{"Type":"WeeklyTrigger","DayOfWeek":"Sunday","TimeOfDayTicks":...}`,
  `{"Type":"StartupTrigger"}`, `{"Type":"SystemEventTrigger","SystemEvent":"WakeFromSleep"}`.
  Optional `MaxRuntimeTicks` caps a run. POSTing `[]` disables automatic runs.
- Kick a scan off-hours yourself: `POST /Library/Refresh`.

Recommendations (official + staff practice): schedule the library scan nightly instead of
short intervals; enable per-library `EnableRealtimeMonitor` where the filesystem supports
inotify so new files appear without full scans; leave `LibraryMonitorDelaySeconds` at
default unless mass file operations cause scan storms.

Source: https://dev.emby.media/reference/RestAPI/ScheduledTaskService.html

## 5. Chapter images / thumbnail extraction cost

Chapter-image and thumbnail extraction decodes every video — one of the most expensive
background jobs (it gets its own `quick-extract-*.txt` logs).

- Per-library `LibraryOptions`: `EnableChapterImageExtraction` and
  `ExtractChapterImagesDuringLibraryScan`. Official guidance: keep extraction OUT of the
  library scan (leave `ExtractChapterImagesDuringLibraryScan=false`) so scans stay fast, and
  let the dedicated scheduled task do it overnight — or disable extraction entirely on
  low-power hardware.
- `ServerConfiguration.ImageExtractionTimeoutMs` bounds a stuck extraction.
- `DownloadImagesInAdvance` (per library) front-loads artwork downloads during the scan
  instead of on first browse — a trade-off: slower scans, snappier clients.

Sources:
- https://emby.media/support/articles/Library-Setup.html
- OpenAPI `LibraryOptions` schema (Emby.SDK)

## 6. Database & data folder on SSD

Emby's SQLite databases (`/var/lib/emby/data/library.db` etc.) are latency-sensitive; large
libraries on spinning disks make the whole UI slow. Official/staff guidance:

- Keep the entire data folder (`/var/lib/emby`) on an SSD. Media can stay on HDDs/NAS.
- `CachePath` and `MetadataPath` (ServerConfiguration) can be relocated — move them to fast
  storage too, or off a small system disk.
- Tuning fields in ServerConfiguration: `DatabaseCacheSizeMB` (raise on RAM-rich servers),
  `EnableSqLiteMmio`, `OptimizeDatabaseOnShutdown` (keep on), `VacuumDatabaseOnStartup`
  (one-shot compaction after big deletes; expensive on huge DBs).
- The "Optimize database" scheduled task performs online maintenance — keep it scheduled.

Sources:
- https://emby.media/support/articles/Server-Data-Folder.html
- Community DB-tuning threads: https://emby.media/community/topic/129691-database-cache-size/,
  https://emby.media/community/topic/137280-emby-database-cache-analysis-row-advice/

## 7. Network tuning

- Define `LocalNetworkSubnets` correctly so LAN traffic bypasses remote limits.
- `RemoteClientBitrateLimit` (server-wide) and per-user `Policy.RemoteClientBitrateLimit`:
  cap WAN streams to what your uplink can carry; prevents one 4K remote stream from forcing
  buffer-storms and repeated transcode restarts.
- `SimultaneousStreamLimit` (server) / `Policy.SimultaneousStreamLimit` (per user) bound
  concurrency (Premiere feature).
- Prefer Direct Play end-to-end: "Optional network paths" (path substitution /
  `PathSubstitutions`) lets LAN apps open media straight from the file share, removing the
  server from the data path entirely
  (https://emby.media/support/articles/Optional-Network-Paths.html).
- Reverse proxy: set `IsBehindProxy` so real client IPs are honored (X-Forwarded-For),
  keeping remote-vs-LAN classification (and fail2ban log data) correct.
- IPv6: `DisableOutgoingIPv6` / network-protocol toggle exists for broken v6 environments.

Source: https://emby.media/support/articles/Hosting-Settings.html

## 8. Quick health-check recipe (API)

1. `GET /System/Info` — version, restart-pending.
2. `GET /ScheduledTasks` — nothing unexpectedly `Running` during peak hours; check
   `LastExecutionResult.Status == "Completed"`.
3. `GET /Sessions` — count `TranscodingInfo != null` sessions; collect `TranscodeReasons`.
4. `GET /System/ActivityLog/Entries?Limit=25` — recent errors/failed logins.
5. `GET /System/Logs` — abnormal log sizes (a multi-GB embyserver.txt usually means an
   error loop; enable debug logging only temporarily).

## Source index

- Transcoding: https://emby.media/support/articles/Transcoding.html
- HW accel overview / Linux / Docker: https://emby.media/support/articles/Hardware-Acceleration-Overview.html,
  .../Hardware-Acceleration-on-Linux.html, .../Hardware-Acceleration-with-Docker.html
- Scheduled Tasks: https://emby.media/support/articles/Scheduled-Tasks.html
- Library Setup: https://emby.media/support/articles/Library-Setup.html
- Hosting/Network settings: https://emby.media/support/articles/Hosting-Settings.html
- REST reference: https://dev.emby.media/reference/RestAPI.html
- OpenAPI spec: https://github.com/MediaBrowser/Emby.SDK/tree/master/Resources/OpenApi
