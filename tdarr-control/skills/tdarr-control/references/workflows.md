# Tdarr workflows — the canonical patterns

Real-world transcoding workflows you can build in Tdarr. Each one names the
community plugin(s) that implement it OR the ffmpeg commands underneath.
Use this to choose plugins / build custom flows / write new plugins.

## How Tdarr decides what to do

Every file in a library goes through a **plugin stack** (Tdarr 1.x) or a
**flow** (Tdarr 2.x). Each plugin/flow-node returns one of:

- `continue` — pass to the next plugin/flow-node.
- `break` — stop the stack; this file is done for this run.
- `transcode` — run my ffmpeg/HandBrake command on this file.
- `remove` — delete the file.
- `filter` — stop AND remove this file from the queue (filter nodes only).

The decision happens once per file per scan. After a transcode succeeds, the
output file is re-scanned; if it still matches a "transcode" rule, the file
keeps getting processed until it's "done" (no plugin wants it).

This is why **plugin order matters**: put restrictive filters first, then
specialist transcoders, then broad cleanups last.

## The 6 canonical workflows

### 1. Standardize-on-HEVC (the #1 Tdarr use-case)

**Goal:** shrink the library by converting everything (H.264 + older codecs)
to HEVC, keeping audio + subtitles untouched.

**Plugin stack:**
1. `00td_filter_by_codec` — filter out files that are already HEVC/AV1 (don't
   re-transcode).
2. `00td_filter_by_resolution` — optional cap (e.g. skip 4K, only process
   1080p).
3. `MC93_Migz1FFMPEG` — NVIDIA HEVC NVENC transcode (recommended for unraid-host).
   OR `MC93_Migz1FFMPEG_CPU` if no GPU.
   OR `s7x9_winsome_h265_nvenc` (alternative).
   OR `vdka_Tiered_NVENC_CQV_BASED_CONFIGURABLE` (per-resolution CQ values).
4. `MC93_Migz3CleanAudio` + `MC93_Migz4CleanSubs` — strip unwanted audio/subs.
5. `MC93_Migz6OrderStreams` — order streams (video first, then audio, then subs).

**Underlying ffmpeg (NVENC HEVC):**
```bash
ffmpeg -i input.mkv \
  -c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 21 -pix_fmt yuv420p10le \
  -c:a copy -c:s copy \
  -map 0 \
  output.mkv
```

**Outcome:** 30-70% smaller files with negligible quality loss. Don't run this
on sources that are already HEVC.

### 2. Maximum compatibility (everything → H.264 + AAC in MP4)

**Goal:** ensure every file plays on every device (Apple TV, web, older TVs).

**Plugin stack:**
1. Filter: skip files that are already H.264 + AAC in MP4.
2. `00td_action_handbrake_basic_options` OR `a8hc_HaveAGitGat_HandBrake_H264_VeryFast1080p30`.
3. `00td_action_standardise_audio_stream_codecs` — convert all audio to AAC.
4. `00td_action_remux_container` — wrap in MP4.
5. `00td_action_re_order_all_streams_v2` — order streams.

**ffmpeg:**
```bash
ffmpeg -i input.mkv \
  -c:v h264_nvenc -preset p6 -tune hq -rc vbr -cq 20 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  -c:s mov_text \
  -map 0 \
  output.mp4
```

**Outcome:** Universal compatibility. Larger files than HEVC. Use only when you
need Apple/web/old-TV playability.

### 3. Audio normalization (DTS/TrueHD → EAC3 for compatibility)

**Goal:** preserve video, convert incompatible audio to widely-supported EAC3.

**Plugin stack:**
1. `00td_filter_by_codec` — only files with DTS/TrueHD audio.
2. `MC93_Migz5ConvertAudio` — convert DTS → EAC3, keep other audio.
3. (optionally) `MC93_Migz3CleanAudio` — remove duplicate audio tracks.

**ffmpeg:**
```bash
ffmpeg -i input.mkv \
  -c:v copy \
  -c:a eac3 -b:a 640k \
  -map 0:v -map 0:a:0 -map 0:s? \
  output.mkv
```

**Outcome:** Audio works on browsers/Chromecast/AppleTV. ~1/4 the audio bitrate
of TrueHD with no audible quality loss for most content.

### 4. Remux-only (cleanup without re-encoding video)

**Goal:** tidy up a library without re-encoding (fast, lossless). Useful for
mixed-source libraries where you don't want quality loss but want consistent
containers + clean streams.

**Plugin stack:**
1. `00td_action_remux_container` (or `MC93_Migz1Remux`) — wrap in MKV.
2. `MC93_Migz2CleanTitle` — strip metadata noise.
3. `MC93_Migz3CleanAudio` / `MC93_Migz4CleanSubs` — remove unwanted audio/subs.
4. `MC93_Migz6OrderStreams`.

**ffmpeg:**
```bash
ffmpeg -i input.mp4 \
  -c copy \
  -map 0:v -map 0:a:0 -map 0:s? \
  output.mkv
```

**Outcome:** Identical quality, smaller file (often 1-5% from metadata cleanup),
universal MKV handling. Processes at GB/sec — extremely fast.

### 5. Subtitle extraction (PGS/ASS → SRT for indexing/search)

**Goal:** get text subtitles out of image-based formats so media servers can
index/search/display them.

**Plugin stack:**
1. `078d_Output_embedded_subs_to_SRT_and_remove` or
   `rr01_drpeppershaker_extract_subs_to_SRT`.
2. (optionally) `x7ab_Remove_Subs` after extraction.

**Note:** PGS → SRT conversion requires OCR (Tesseract), which is slow and
imperfect. ASS → SRT is just text-format conversion, fast and clean.

### 6. 4K HDR preservation (high-quality archival)

**Goal:** shrink 4K REMUXes without losing HDR or video quality.

**Plugin stack:**
1. Filter: only 4K HDR sources.
2. `s710_nick_h265_nvenc_4K` — 4K-targeted NVENC HEVC with HDR preservation.
3. Keep all audio + subs.

**ffmpeg (HDR-preserving NVENC HEVC):**
```bash
ffmpeg -i input.mkv \
  -c:v hevc_nvenc -preset p7 -tune hq -rc vbr -cq 18 -pix_fmt p010le \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  -b:v 0 \
  -c:a copy -c:s copy \
  -map 0 \
  output.mkv
```

**Critical:** the three color flags are what makes it HDR10. Omit them and the
result is washed-out SDR. Use `-pix_fmt p010le` (10-bit) — required for HDR.

**Outcome:** ~50-70% smaller than the REMUX with visually-identical HDR quality.
Plays on Apple TV 4K, NVidia Shield, modern TVs.

## Common add-on plugins (stack on top of any workflow)

| Plugin | Effect |
|---|---|
| `MC93_Migz2CleanTitle` | Strip metadata "title" fields (cleans up display in some media servers) |
| `MC93_MigzImageRemoval` | Remove embedded cover-art images (smaller files, no album-art spam in players) |
| `MC93_Migz3CleanAudio` | Remove unwanted audio tracks (configurable keep-list) |
| `MC93_Migz4CleanSubs` | Remove unwanted subtitle tracks (configurable keep-list) |
| `MC93_Migz5ConvertAudio` | Convert specific audio codecs (DTS→EAC3 etc.) |
| `MC93_Migz6OrderStreams` | Order streams: video → audio → subtitles → attachments |
| `00td_action_re_order_all_streams_v2` | Generic stream reorder |
| `sdd3_Remove_Commentary_Tracks` | Drop commentary audio tracks |
| `x7ac_Remove_Closed_Captions` | Strip CEA-608/708 (embedded in video user-data) |
| `MC93_MigzPlex_Autoscan` / `TD01_TOAD_Autoscan` / `goof1_URL_Plex_Refresh` | Trigger Plex/Emby library scan after transcode |

## "First transcode" decision tree (which workflow for which source)

```
Source file pattern
│
├── Already HEVC or AV1
│   └── Don't transcode. Maybe Workflow 4 (remux + clean).
│
├── H.264 REMUX (Blu-ray, ~25-35 Mbps)
│   └── Workflow 1 (standardize-on-HEVC). Expect 60-75% size reduction.
│
├── H.264 WebDL (~5 Mbps)
│   └── Probably skip. Already small. Maybe Workflow 4 (remux + clean) if messy.
│
├── MPEG-2 / MPEG-4 / VC-1 / DivX / Xvid / VP8
│   └── Workflow 1 or 2. Always transcode (these are obsolete).
│
├── VP9
│   └── Workflow 1 (HEVC) for compatibility, or leave alone.
│
├── H.264 with DTS/TrueHD audio + need broader compat
│   └── Workflow 3 (audio normalization) + Workflow 4 (remux).
│
├── 4K HDR REMUX
│   └── Workflow 6 (HDR preservation) — don't accidentally strip HDR.
│
└── Old AVI / weird container
    └── Workflow 4 (remux to MKV) + Workflow 1 or 2 (transcode).
```

## Building a custom plugin

If no community plugin fits, write one. Tdarr plugin structure (JavaScript,
Node.js):

```javascript
// Tdarr_Plugin_<random_id>_<Author>_<Description>.js
class tdarrPlugin {
  constructor() { this.details = {}; }

  // Handbrake or ffmpeg?
  init() {
    this.details = {
      id: 'Tdarr_Plugin_xxxx_My_Plugin',
      Stage: 'Pre-processing',
      Name: 'My Custom HEVC Transcode',
      Type: 'Video',
      Operation: 'Transcode',
      Description: 'HEVC NVENC with custom CRF',
      Version: '1.00',
      Tags: 'ffmpeg,video',
      Inputs: {
        cq: { tooltip: 'CQ value (default 21)', def: '21' },
      },
    };
  }

  // The decision function — return what Tdarr should do
  plugin(file, librarySettings, inputs) {
    const response = { container: '.',  // keep same container
                       processFile: false,
                       handBrakeMode: false,
                       FFmpegMode: true,
                       reQueueAfter: true,
                       infoLog: '' };

    // Skip if already HEVC
    if (file.ffProbeData.streams.some(s =>
        s.codec_name === 'hevc' && s.codec_type === 'video')) {
      response.infoLog += 'File is already HEVC, skipping.\n';
      return response;
    }

    // Transcode
    response.processFile = true;
    response.FFmpegOperation = `-c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq ${inputs.cq || 21} -pix_fmt yuv420p10le -c:a copy -c:s copy`;
    response.infoLog += `Transcoding to HEVC at CQ ${inputs.cq || 21}.\n`;
    return response;
  }
}

module.exports = tdarrPlugin;
```

Install via `tdarr_create_plugin(definition, confirm=True)` or the UI's plugin
editor. Verify with `tdarr_verify_plugin(plugin_id)`.

## Workflow tuning knobs

These are the dials to turn when adjusting a workflow:

| Knob | Range | Effect |
|---|---|---|
| `CRF`/`CQ` value | 16-30 | Lower = better quality + bigger file. Default 21 (HEVC) / 18 (H264). |
| `preset` | p1-p7 (NVENC) / ultrafast-placebo (libx265) | Higher = better quality per bit + slower. |
| `-pix_fmt` | `yuv420p` (8-bit) / `yuv420p10le` (10-bit) / `p010le` (10-bit HDR) | 10-bit has better banding + similar size; use 8-bit only for old-device compat. |
| Audio target | copy / AAC / EAC3 / AC3 / FLAC | copy is fastest; AAC/EAC3 widest compatibility. |
| Subtitle target | copy / mov_text / SRT | mov_text for MP4; copy for MKV. |
| Max concurrent GPU workers | 1-4 (RTX 3060) | Higher = more parallelism; watch VRAM. |
| Output folder | same-as-source / separate / replace | Replace is risky (no rollback); separate is safe but doubles storage transiently. |

## See also
- `codecs.md` — full codec reference for choosing input → output.
- `hardware-acceleration.md` — encoder selection (NVENC focus).
- `plugins.md` — the community plugin catalog (every workflow above maps to one or more listed plugins).
- `flows.md` — Tdarr 2.x's newer visual flow system.
