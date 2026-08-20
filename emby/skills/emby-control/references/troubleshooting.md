# TROUBLESHOOTING.md — Emby Server Troubleshooting (Emby 4.7.x, Linux)

> **Live-verified deltas for media-host (4.7.x):** `GET /System/Logs` and
> `GET /System/Logs/Log?Name=...` both work (34 log files present).
> `GET /System/Logs/{Name}` and `/System/Logs/{Name}/Lines` 500 on this build —
> use the classic `?Name=` route (the `emby_logs` tool does). A 500 with
> "Object reference not set..." almost always means a NONEXISTENT entity id or
> missing dependency, not a server fault.

Official troubleshooting knowledge for Emby Server, with the REST endpoints an automation
can use for diagnostics. Emby-specific (not Jellyfin). Auth: `X-Emby-Token: <api key>`.

## 1. Where the logs live

Linux data folder is `/var/lib/emby`; logs are in **`/var/lib/emby/logs`**
(Dashboard → the three-dot menu → "View Server Info" shows the exact path; Dashboard → Logs
lists and downloads them).

Four log types (official article "Log Files"):

| File | Contents |
|---|---|
| `embyserver.txt` (rotated: `embyserver_<timestamp>.txt`) | Main server log |
| `ffmpeg-transcode-*.txt` / `ffmpeg-remux-*.txt` | One per transcode/remux session — the first place to look for playback failures |
| `hardware_detection-*.txt` | Hardware acceleration probe, written at every server startup |
| `quick-extract-*.txt` | Image (chapter/thumbnail) extraction |

- Rotation: a new log starts daily at midnight (configurable via the "Rotate log file"
  scheduled task).
- Debug logging is off by default; enable in Dashboard → Logs (API:
  `ServerConfiguration.EnableDebugLevelLogging`, see configuration.md; there is also a
  `RevertDebugLogging` auto-revert field on newer builds). Enable only while troubleshooting.
- Authentication failures are logged fail2ban-compatibly:
  `AUTH-ERROR: {source IP} - {error message}`.

Source: https://emby.media/support/articles/Log-Files.html
(markdown: https://github.com/EmbySupport/Emby.Docs/blob/master/Log-Files.md)

## 2. Reading logs via the API (SystemService)

On Emby 4.7:

- `GET /System/Logs` — list available log files (returns `Name`, `Size`, `DateCreated`,
  `DateModified`).
- `GET /System/Logs/Log?Name=embyserver.txt` — stream a log file's contents.

Current releases (4.8/4.9 reference) also expose `GET /System/Logs/Query`,
`GET /System/Logs/{Name}` and `GET /System/Logs/{Name}/Lines`; these 500/404 on 4.7.14 —
use the two classic endpoints above.

Other diagnostic endpoints:

- `GET /System/Info` — version, paths, pending restart flags. `GET /System/Info/Public` — unauthenticated liveness.
- `GET /System/Ping` (GET/POST) — liveness probe.
- `POST /System/Restart`, `POST /System/Shutdown`.
- `GET /System/ActivityLog/Entries?StartIndex=0&Limit=50&MinDate=2026-07-01` — the audit
  stream shown on the dashboard (playback starts/stops, logins, failed logins, task
  completions, plugin installs). Entries: `Id`, `Name`, `Overview`, `ShortOverview`, `Type`,
  `Date`, `UserId`, `Severity`.
- `GET /ScheduledTasks?IsHidden=false` — every task with `State` (Idle/Cancelling/Running),
  `CurrentProgressPercentage`, `LastExecutionResult` (Status, error message), `Triggers`, `Key`.
  Start/stop: `POST /ScheduledTasks/Running/{Id}` / `DELETE /ScheduledTasks/Running/{Id}`.
- `GET /Sessions` — live sessions incl. `TranscodingInfo` (see §4) and `PlayState`.
  Filters: `?ControllableByUserId=`, `?DeviceId=`, `?Id=`.

Sources:
- https://dev.emby.media/reference/RestAPI/SystemService.html
- https://dev.emby.media/reference/RestAPI/ActivityLogService.html
- https://dev.emby.media/reference/RestAPI/ScheduledTaskService.html
- https://dev.emby.media/reference/RestAPI/SessionsService.html
- 4.7-era log routes verified in the open-source lineage:
  https://github.com/MediaBrowser/Emby/blob/master/MediaBrowser.Api/System/SystemService.cs

## 3. Failure class: playback failures / transcode errors

Diagnosis flow (official guidance):

1. `GET /Sessions` while the failure reproduces — check `TranscodingInfo.TranscodeReasons`
   and `PlayState`. If nothing appears, the client never reached the server.
2. Pull the newest `ffmpeg-transcode-*.txt` via `/System/Logs`. The header shows the exact
   ffmpeg command line; errors at the bottom. Look for the selected decoder/encoder
   (`h264_vaapi`, `h264_nvenc`, `h264_qsv` = hardware; plain `libx264` = software).
3. Cross-check `embyserver.txt` around the same timestamp.

Common official remedies:

- **PGS/DVD (graphical) subtitles force heavy transcoding** — they must be burned in; most
  GPUs can't do that stage, so CPU spikes even with hw-accel on. Fix: use text subtitles
  (.srt) or disable subtitles. (Hardware-Acceleration-Overview FAQ.)
- **Bitrate limit transcodes** — the app's "Max streaming bitrate" (or server/user remote
  bitrate limits) below the file's bitrate forces transcode; raise limits or set app to Auto.
- **DVD/Blu-ray folder rips, ISO and 3D content cannot be transcoded** at all (official
  Transcoding article) — convert them.
- **"Transcode initialization failed"** — usually hardware acceleration failure: see §7.
- Transcoding temp dir full/not writable: check `EncodingOptions.TranscodingTempPath` and
  disk space; the folder must be dedicated (server purges it).

Sources:
- https://emby.media/support/articles/Transcoding.html
- https://emby.media/support/articles/Hardware-Acceleration-Overview.html

## 4. TranscodeReasons (Sessions API)

`GET /Sessions` → `TranscodingInfo.TranscodeReasons[]` explains *why* the server is
transcoding. Full enum (official OpenAPI spec): `ContainerNotSupported`,
`VideoCodecNotSupported`, `AudioCodecNotSupported`, `ContainerBitrateExceedsLimit`,
`AudioBitrateNotSupported`, `AudioChannelsNotSupported`, `VideoResolutionNotSupported`,
`UnknownVideoStreamInfo`, `UnknownAudioStreamInfo`, `AudioProfileNotSupported`,
`AudioSampleRateNotSupported`, `AnamorphicVideoNotSupported`, `InterlacedVideoNotSupported`,
`SecondaryAudioNotSupported`, `RefFramesNotSupported`, `VideoBitDepthNotSupported`,
`VideoBitrateNotSupported`, `VideoFramerateNotSupported`, `VideoLevelNotSupported`,
`VideoProfileNotSupported`, `AudioBitDepthNotSupported`, `SubtitleCodecNotSupported`,
`DirectPlayError`, plus (newer 4.x) `VideoRangeNotSupported`, `SubtitleContentOptionsEnabled`,
`ExternalAudioNotSupported`, `AudioDelayNotSupported`.

Source: OpenAPI `TranscodeReason` schema —
https://github.com/MediaBrowser/Emby.SDK/blob/master/Resources/OpenApi/openapi_v3.json

## 5. Failure class: library scan issues

- Trigger a scan: `POST /Library/Refresh`. Watch progress via
  `GET /ScheduledTasks` ("Scan media library" task, key `RefreshLibrary`) or per-library
  `RefreshProgress`/`RefreshStatus` in `GET /Library/VirtualFolders/Query`.
- **Linux permissions are the #1 cause**: Emby runs as the `emby` user; it must have read
  (and for NFO/artwork saving, write) access to media paths. Official Linux guidance: add
  `emby` to the group owning the media or fix ownership (`usermod -a -G <group> emby`,
  `chmod`/`chown`). See https://emby.media/support/articles/Linux-Unix-Permissions.html.
- Real-time monitoring (`LibraryOptions.EnableRealtimeMonitor`) only works on supported
  filesystems (inotify) — NFS/SMB mounts typically don't propagate events; rely on scheduled
  scans instead. Requires a server restart when toggled.
- New files not appearing despite scans: verify naming conventions
  (https://emby.media/support/articles/Movie-Naming.html, TV-Naming.html), check
  `Excluding-Files-Folders` rules (`.ignore` files), and check `embyserver.txt` during a scan
  for "Error retrieving file" / permission denied lines.
- Windows >256-char paths break scans (Library-Setup article) — not applicable to Linux but
  relevant for SMB-mounted Windows shares.

Sources:
- https://emby.media/support/articles/Library-Setup.html
- https://emby.media/support/articles/Linux-Unix-Permissions.html
- https://dev.emby.media/reference/RestAPI/LibraryService.html (`POST /Library/Refresh`)

## 6. Failure class: metadata / artwork problems

- Check per-library metadata settings first (`LibraryOptions`: metadata language/country,
  enabled fetchers and their order, `DownloadImagesInAdvance`).
- Wrong match: use Identify (dashboard) or `POST /Items/RemoteSearch/Apply/{Id}`; force
  re-fetch with `POST /Items/{Id}/Refresh?MetadataRefreshMode=FullRefresh&ImageRefreshMode=FullRefresh&ReplaceAllMetadata=true&ReplaceAllImages=true`.
- Artwork not updating on clients is often cached images: refresh images with the call above.
- Provider outages/rate limits appear in `embyserver.txt` as HTTP errors from
  themoviedb/thetvdb/omdb — transient; re-run refresh later.
- Local metadata wins only if "Prefer local metadata"/NFO readers are configured
  (`xbmcmetadata` named config + LibraryOptions `LocalMetadataReaderOrder`).

Sources:
- https://emby.media/support/articles/Identify.html
- https://emby.media/support/articles/Metadata-manager.html

## 7. Failure class: hardware acceleration failures

- Startup probe: read the newest `hardware_detection-*.txt` log. Note (Emby staff guidance):
  VAAPI errors in this log are EXPECTED and ignorable on NVIDIA-only systems — not every
  listed failure is your failure.
- NVIDIA on Linux: driver must come from NVIDIA (not distro packages), minimum version
  470.57; headless operation is supported (no monitor needed). Verify Emby's ffmpeg appears
  in `nvidia-smi` while transcoding.
- Intel VAAPI/QSV: drivers ship with Emby Server itself; ensure the `emby` user can access
  `/dev/dri/renderD128` (the default `EncodingOptions.VaapiDevice`) — membership in the
  `render`/`video` groups is the usual fix on Linux distros.
- AMD on Linux: install AMD's driver, do NOT choose "headless mode" during driver setup
  (it skips graphics driver install).
- Encoders: on Linux via VAAPI/QSV/NVENC, Emby 4.7-era hardware ENCODING is H.264-focused;
  decode covers H.264/HEVC/MPEG2/VC1/VP8/VP9 (per official Linux hw-accel article).
- Hardware transcoding requires an active **Emby Premiere** license — without it Emby
  silently uses software encoding. (media-host: Premiere is ACTIVE.)
- Windows-only but documented: hw-accel fails under active RDP sessions (Hwa-Fails-with-RDP).
- Verification via API: on current 4.8/4.9 servers `TranscodingInfo` includes
  `VideoDecoderIsHardware`, `VideoEncoderIsHardware`, `VideoDecoderHwAccel`,
  `VideoEncoderHwAccel`; on 4.7 rely on the ffmpeg-transcode log (encoder names ending in
  `_vaapi`/`_qsv`/`_nvenc`) and the dashboard's green "HW" badges on the active-stream card.

Sources:
- https://emby.media/support/articles/Hardware-Acceleration-on-Linux.html
- https://emby.media/support/articles/Hardware-Acceleration-Overview.html
- Staff thread: https://emby.media/community/topic/118520-how-to-check-hardware-acceleration/

## 8. Failure class: remote access problems

Ports: TCP 8096 (HTTP), TCP 8920 (HTTPS), UDP 7359 (LAN discovery).

Official checklist (Connectivity article):

1. `ServerConfiguration.EnableRemoteAccess` must be true, AND the user's
   `Policy.EnableRemoteAccess` must be true.
2. Compare the WAN IP the dashboard shows against canyouseeme.org; mismatch → VPN on the
   host, double NAT, or carrier-grade NAT (ISP address in 100.64.0.0–100.127.255.255 ⇒ cgNAT,
   port-forwarding impossible — use a tunnel/reverse proxy).
3. Double NAT: compare router WAN IP vs whatismyipaddress.com; fix by bridging the ISP modem
   or cascading forwards.
4. UPnP mapping (`EnableUPnP`) requires UPnP on in the router and an Emby restart; otherwise
   forward TCP 8096/8920 manually to a DHCP-reserved LAN IP.
5. Testing from inside the LAN can fail due to router NAT-loopback limits — test from
   cellular.
6. Local firewall: allow 8096/8920 (e.g. firewalld/ufw on Linux).
7. Dynamic IPs: set `WanDdns` (External domain) with a DDNS name.

Source: https://emby.media/support/articles/Connectivity.html

## 9. Failure class: database corruption

Symptoms: `SQLitePCL.pretty.SQLiteException` in embyserver.txt, especially
`Corrupt: database disk image is malformed`. Databases (in `/var/lib/emby/data` on Linux):
`library.db` (most corruption-prone), `users.db`, `authentication.db`, `activitylog.db`.
Causes: power loss/kill -9, or switching between beta and stable releases.

Official recovery order:

1. Restore from backup (preferred).
2. Stop Emby; delete stale `library.db-wal` / `library.db-shm`; restart.
3. `sqlite3 library.db "PRAGMA integrity_check;"` → if not "ok":
   `VACUUM;` then `REINDEX;`; if that fails use `.recover`:
   `.output recovered.sql` / `.recover` / then build a fresh db with `.read recovered.sql`,
   verify integrity, swap files, restart.
4. Last resort: rename `library.db` aside, restart (fresh database), recreate libraries
   (playstate/favorites can be restored from a backup made with the official Backup plugin).

Prevention: always stop the service cleanly (`sudo systemctl stop emby-server`), schedule
the Backup plugin, and don't run beta and stable against the same data folder.

Source: https://emby.media/support/articles/Corrupt-Database.html

## 10. Linux service quirks

- Service management: `sudo systemctl status|start|stop|restart emby-server`.
- "Restart" from the dashboard/API needs the packaged helper
  `/usr/lib/emby-server/restart.sh` (executable, launched via systemd). If dashboard restarts
  do nothing, verify the script and test with
  `sudo -u emby /usr/lib/emby-server/restart.sh`, comparing PIDs before/after.
- Data folder ownership: everything under `/var/lib/emby` must remain owned by `emby:emby`.

Source: https://emby.media/support/articles/Linux-Troubleshooting-Guide-and-FAQ.html

## Source index

- Log Files: https://emby.media/support/articles/Log-Files.html
- Transcoding: https://emby.media/support/articles/Transcoding.html
- HW accel (Linux): https://emby.media/support/articles/Hardware-Acceleration-on-Linux.html
- Connectivity: https://emby.media/support/articles/Connectivity.html
- Corrupt DB: https://emby.media/support/articles/Corrupt-Database.html
- Linux FAQ: https://emby.media/support/articles/Linux-Troubleshooting-Guide-and-FAQ.html
- All support articles (canonical md): https://github.com/EmbySupport/Emby.Docs
- REST reference: https://dev.emby.media/reference/RestAPI.html
