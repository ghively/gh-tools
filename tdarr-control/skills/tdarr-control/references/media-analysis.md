# Tdarr media analysis — damage detection, validation, and forensic capabilities

How Tdarr inspects media files for damage, quality issues, and metadata
mismatches. The plugin/flow catalog has dozens of analysis nodes I
previously didn't surface.

## The two layers of analysis

Tdarr has two distinct analysis systems:

1. **Health checks** — built-in ffmpeg/handbrake-level file integrity check.
   Catches actual file corruption.
2. **Stream-property filters** — ffprobe-derived metadata filters + size/
   duration comparisons. Catch configuration issues, "wrong" codecs, failed
   transcodes that produced wrong output, etc.

Both run as worker jobs and populate the status tables + statistics.

## The 8 status tables (live-confirmed)

`StatisticsJSONDB.table0Count` through `table7ViewableCount` — Tdarr tracks
every file's last outcome across 8 buckets:

| Table | Bucket | Color | What it means |
|---|---|---|---|
| table0 | Transcode Success | green | Transcode completed successfully |
| table1 | Transcode Not Required | grey | No plugin/flow wanted to transcode (good terminal state) |
| table2 | Transcode Error | red | ffmpeg/HandBrake returned non-zero |
| table3 | Transcode Cancelled | yellow | Cancelled by user or worker-kill |
| table4 | Health Check Success | green | Health check passed |
| table5 | Health Check Error | red | Health check found corruption |
| table6 | Health Check Cancelled | yellow | Health check was cancelled |
| table7 | Staged / Held | blue | Awaiting accept/reject in staging, OR held post-scan |

The **Tdarr Score** = `table1Count / totalFileCount` × 100 (the % of files
in "Not Required" state = your "library is done" metric).

The **Health Check Score** = `table4Count / totalHealthCheckCount` × 100.

## Health check types (revisited with what they actually catch)

### Quick health check

- **Engine:** HandBrake `--scan`.
- **What it actually checks:** parses file headers, validates stream
  metadata, confirms container structure. Does NOT decode video frames.
- **What it catches:**
  - Truncated/cut-off files (last frame index present in header vs actual).
  - Broken container indexes (missing moov atom in MP4, broken EBML in MKV).
  - Missing declared streams (header says 3 audio tracks, only 2 present).
  - Outright corrupt headers (file starts as media but is partially garbage).
- **What it MISSES:** frame-level corruption, encoding errors, audio gaps,
  desync, anything that requires decoding to detect.
- **Speed:** sub-second per file (typically 100-500ms).
- **Workers:** CPU only.

### Thorough health check

- **Engine:** FFmpeg frame-by-frame decode.
- **Default args** (per node hardware):
  - CPU/Any: `-stats -v error`
  - NVENC: `-stats -v error -hwaccel nvdec -hwaccel_output_format cuda`
  - VAAPI/QSV: `-stats -v error -hwaccel vaapi -hwaccel_output_format vaapi`
- **Custom args** (per node, live-confirmed):
  - `thoroughHealthCheckCpuExtraArgs` / `thoroughHealthCheckGpuExtraArgs` —
    ADD args to the output side.
  - `thoroughHealthCheckCpuExtraInputArgs` / `thoroughHealthCheckGpuExtraInputArgs` —
    ADD args to the INPUT side (before `-i`).
- **What it catches (everything Quick catches, plus):**
  - Frame decode errors (corrupted motion vectors, missing reference frames).
  - Macroblock corruption (visible as green/gray blocks).
  - Audio decode errors (DTS frame corruption, AAC gap artefacts).
  - Truncated video streams (EOF before declared duration).
  - Codec-specific errors (H.264 NAL unit violations, HEVC tile mismatches).
  - Subtitle decode errors (rare but possible with malformed ASS).
- **What it MISSES (still):**
  - **Perceptual quality issues** — blocky low-bitrate video looks fine to
    ffmpeg. Use bitrate filters (`checkOverallBitrate`,
    `checkVideoBitrate`) to catch those.
  - **HDR correctness** — health check decodes successfully but HDR might
    be stripped/mismatched. Use `checkHdr` flow node to validate.
  - **Audio/video desync** — frames decode, audio decodes, but they're out
    of sync. Hard to detect automatically; use `compareFileDurationRatio`
    as a proxy (if durations diverge after transcode, something's wrong).
- **Speed:** minutes per file (depends on bitrate + decoder speed).
- **Workers:** CPU or GPU.

### Stricter thorough health checks (using custom args)

Add these to `thoroughHealthCheck*ExtraArgs` for more rigorous checking:

| Extra arg | Effect |
|---|---|
| `-err_detect explode_err` | Abort on ANY error (default continues past errors) |
| `-err_detect careful` | Stricter error detection (balanced) |
| `-err_detect aggressive` | Very strict (more false positives) |
| `-x265 log-level debug` | Detailed HEVC decode logging (noisy) |
| `-debug:v 1` | Debug-level video decode info |

**Recommended for production:** `-err_detect explode_err` — catches errors
the default mode glosses over. Set via `NodeJSONDB.thoroughHealthCheckCpuExtraArgs`.

## Stream-property filters (the analysis flow nodes)

These flow-plugin nodes inspect ffprobe metadata to filter files — useful
for catching "the file plays but it's misconfigured." All live-confirmed
in the flow catalog at `FlowPluginsTs/CommunityFlowPlugins/`:

### Video analysis nodes (8)

| Node | Filters by | Use case |
|---|---|---|
| `checkVideoCodec` | Video codec (H.264/HEVC/AV1/...) | Skip-already-HEVC, find old codecs |
| `checkVideoResolution` | Resolution class (480p/720p/1080p/4K) | Find SD content in HD library |
| `checkVideoFramerate` | Framerate (23.976/24/25/30/60) | Find mixed-framerate libraries |
| `check10Bit` | 10-bit vs 8-bit detection | HDR/banding checks |
| `checkHdr` | HDR10/Dolby Vision detection | HDR workflow gating |
| `checkOverallBitrate` | Total file bitrate | Find oversized files |
| `checkVideoBitrate` | Video stream bitrate | Find low-quality encodes |
| `runHealthCheck` | Run a health check inline in flow | Conditional health-check during flow |

### Audio analysis nodes (4)

| Node | Filters by | Use case |
|---|---|---|
| `checkAudioCodec` | Audio codec (AAC/AC3/DTS/...) | Find incompatible audio |
| `checkAudioBitrate` | Audio stream bitrate | Find over/under-sized audio |
| `checkChannelCount` | Channel count (2.0/5.1/7.1) | Find surround content |
| (use `normalizeAudio` action) | — | Apply loudness normalization |

### File-property analysis nodes (26 in `file/` category)

The most useful for damage/quality validation:

| Node | What it does | Use case |
|---|---|---|
| `checkFileSize` | Filter by file size | Find oversized files (REMUXes) |
| `compareFileSize` | Compare to a reference | Validate transcode output |
| `compareFileSizeRatio` | Output size vs source ratio | Catch failed transcodes (ratio too small/large) |
| `compareFileSizeRatioLive` | Same, live during transcode | Mid-transcode bail-out |
| `compareFileDurationRatio` | Output duration vs source | **Catch A/V desync** — duration divergence is a major red flag |
| `checkStreamsCount` | Number of streams | Validate expected stream count |
| `checkStreamProperty` | Generic stream-property filter | Custom validation |
| `checkFileChanged` | Detect modification | Cache-invalidation |
| `calculateFileHash` | SHA/hash of file content | Dedup, change-tracking |
| `checkForHardlinks` | Hardlink detection | Storage management |
| `checkFileVariationExists` | Look for variants | Detect duplicates |

**The killer combo for "did the transcode succeed?":**
`compareFileSizeRatio` (output should be 0.3x-1.5x source typically) +
`compareFileDurationRatio` (should be ~1.0; 0.99-1.01 is safe). If either
is wildly off, the transcode failed silently.

## Detecting specific kinds of damage

### "This file is corrupted" → thorough health check
- Run thorough health check on the library.
- Files in **table5 (Health Check Error)** are corrupt.
- Action: re-download, restore from backup, or delete (`tdarr_delete_file`
  with confirm).

### "This file plays but the transcode keeps failing"
- Check footprint reports: `tdarr_list_footprint_reports(footprint_id=...)`.
- Likely causes:
  - Exotic codec NVENC can't decode → fall back to CPU worker.
  - HDR flag missing → fix with `ffmpegCommandHdrToSdr` or skip.
  - Variable framerate (VFR) → some encoders choke; add `-vsync cfr`.
  - Audio sample rate mismatch → use `-ar 48000` to normalize.

### "This REMUX is huge"
- Use `checkOverallBitrate` to filter files above ~20 Mbps.
- Then transcode with HEVC NVENC `-cq 21` (typically 60-75% size reduction).

### "This file has 8 audio tracks and I only want 2"
- Use `checkStreamsCount` + `checkAudioCodec` to identify.
- Strip with `MC93_Migz3CleanAudio` or `ffmpegCommandRemoveStreamByProperty`.

### "This file claims HDR but looks washed out"
- The transcode stripped HDR metadata. Use `checkHdr` to detect HDR sources.
- For HDR sources, the ffmpeg command MUST include `-color_primaries bt2020
  -color_trc smpte2084 -colorspace bt2020nc` AND `-pix_fmt p010le`. See
  `workflows.md` Workflow 6.
- Use `ffmpegCommandHdrToSdr` flow node for INTENTIONAL HDR→SDR conversion
  (proper tone-mapping, not just flag stripping).

### "These files have variable framerates"
- VFR files cause sync issues after transcode.
- Detect with `CheckVideoFramerate` (filter for non-standard rates) OR
  via ffprobe `avg_frame_rate` vs `r_frame_rate` mismatch.
- Force CFR during transcode: `-fpsmax 23.976 -vsync cfr`.

### "I want to detect newly-added files automatically"
- Enable folder-watch with FS events on the library.
- OR install `tdarr_inform` for Sonarr/Radarr/Whisparr webhook integration
  (no polling, no FS events needed).
- Use `holdAfterScanning` to debounce.

### "Is this file smaller than it should be?"
- `checkOverallBitrate` flow node — anything under 1 Mbps at 1080p is suspect.
- `compareFileSizeRatio` after transcode — output should be 0.3-1.5x source.

## Footprint IDs (forensic transcode history)

Every file gets a `footprintId` — a content-hash that persists across
transcodes. So if a file fails transcode, gets requeued, fails again, all
those attempts share a footprint.

Use `tdarr_list_footprint_reports(footprint_id="<id>")` to fetch every
attempt + its job report. Each report has the full ffmpeg output, plugin
decision log, and timing.

Invaluable for "this file always fails" triage — see the actual error
across multiple attempts.

## WorkerVerdictHistoryJSONDB

A **NEW collection I missed** in earlier versions: every worker verdict
(transcode/not-required/failed/etc.) is logged here per file per attempt.
Use `tdarr_db(mode="getAll", collection="WorkerVerdictHistoryJSONDB")` to
inspect — useful for "what did Tdarr decide about this file over time?"

## The 8 → 12 collections I should have mentioned

Earlier I said "8 collections" accessible via /cruddb. Live inspection of
`get-db-statuses` reveals 12+:

| Collection | Purpose |
|---|---|
| `FileJSONDB` | Per-file scanned data (the main one) |
| `LibrarySettingsJSONDB` | Library configs |
| `StatisticsJSONDB` | Aggregate stats per library |
| `NodeJSONDB` | Nodes + their config |
| `SettingsGlobalJSONDB` | Global server settings |
| `StagedJSONDB` | Staged files awaiting review |
| `F2FOutputJSONDB` | File-to-file output tracking |
| `FlowsJSONDB` | Defined flows |
| `VariablesJSONDB` | Global + library variables for flow templating |
| `UsersJSONDB` | User accounts (when auth=true) |
| `ApiKeysJSONDB` | API keys (when auth=true) |
| `WorkerVerdictHistoryJSONDB` | Per-file decision history |

All accessible via `tdarr_db(mode=, collection=, ...)`.

## ffprobe data exposed to plugins

Every file scanned by Tdarr has full ffprobe JSON available to plugins/
flows at `args.inputFileObj.mediaInfo` (or `file.ffProbeData` in classic
plugins). This includes:

- `format.duration`, `format.size`, `format.bit_rate`, `format.tags`
- `streams[]` with per-stream:
  - `codec_name`, `codec_long_name`, `codec_type`, `codec_tag_string`
  - `width`, `height` (video)
  - `pix_fmt`, `color_space`, `color_transfer`, `color_primaries` (video, HDR)
  - `channels`, `channel_layout`, `sample_rate`, `bits_per_sample` (audio)
  - `bit_rate`, `nb_frames`, `r_frame_rate`, `avg_frame_rate`
  - `tags.language`, `tags.title`, `tags.DEFAULT` (lang/default flags)

Flow templating exposes this: `{{{args.inputFileObj.mediaInfo.track.0.CodecID}}}`.

## Analysis playbook (concrete recipes)

### "Audit my library for problems"

```python
# 1. What's the overall health?
tdarr_db(mode="getAll", collection="StatisticsJSONDB")
# Look at: totalFileCount, table0Count (success), table2Count (error),
# table5Count (health check error), tdarrScore

# 2. What files are in the error tables?
tdarr_call(method="POST", path="/api/v2/search-db",
           data='{"string":"", "lessThanGB":100000, "greaterThanGB":0}')
# Filter client-side for files in error states

# 3. For a specific failing file, get its transcode history
tdarr_list_footprint_reports(footprint_id="<id>")

# 4. Run health checks on the library
# (via the UI's Library Options → Requeue all items (health check),
#  or via /api/v2/scan-files with scanConfig)
```

### "Find all files below quality threshold"

```python
# Use the flow system to mark + filter
# Flow:
#   inputFile
#   → checkVideoBitrate(min=1000000)  # 1 Mbps minimum for 1080p
#   → requireReview()  # push to staging for inspection
```

### "Validate that my last transcode run actually worked"

```python
# Flow run after transcode completes:
#   compareFileSizeRatio(min=0.3, max=1.5)  # output should be reasonable
#   compareFileDurationRatio(min=0.99, max=1.01)  # duration preserved
#   → on failure: requireReview() + notify via Discord webhook
```

### "Detect silent audio tracks"

FFmpeg analysis via `runCli` flow node:
```bash
ffmpeg -i <file> -af silencedetect=n=-50dB:d=10 -f null -
```
Output shows silent segments; flag files with silent audio for review.

## See also
- `audio-deep-dive.md` — comprehensive audio handling (codecs, channels,
  normalization, language).
- `flow-plugin-catalog.md` — the full 85+ flow-node catalog.
- `diagnostics-and-health.md` — health check reference + troubleshooting.
- `workflows.md` — actual transcode workflows.
