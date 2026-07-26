# Video / audio / container / subtitle codecs — the Tdarr codec encyclopedia

A practical reference for choosing input → output transcodes. Focused on
what Tdarr actually encounters in a media library and what ffmpeg/handbrake
encoders produce what.

## Mental model

A "video file" is three layers stacked:

1. **Container** (the wrapper) — MKV, MP4, AVI, MOV, TS. Holds streams +
   metadata + chapters. A `remux` changes the container without touching
   audio/video. Cheap and lossless.
2. **Streams** — one or more video streams, zero or more audio streams, zero
   or more subtitle streams, zero or more attachment/data streams. A
   `transcode` re-encodes a stream to a different codec.
3. **Codec** — how each stream is compressed (H.264, HEVC, AC3, TrueHD, ...).
   Each codec has its own encoder implementations (libx264 vs h264_nvenc vs
   h264_qsv all produce H.264 video).

When someone says "transcode this file to HEVC" they mean: keep the container
(or remux to MKV), re-encode the video stream with a HEVC encoder, and
optionally also re-encode/strip/copy audio + subtitles.

## Video codecs (in rough order of how often you'll see them)

### H.264 / AVC (most common, most compatible)
- **Year:** 2003. Universal support — every browser, TV, phone, console.
- **Encoders:**
  - `libx264` — software, best quality per bit, slow at higher presets.
  - `h264_nvenc` — NVIDIA NVENC hardware (your RTX 3060 has it). ~5-20x faster
    than libx264, slightly larger files at same quality.
  - `h264_qsv` — Intel QuickSync (for Intel iGPU nodes).
  - `h264_videotoolbox` — macOS.
  - `h264_vaapi` — Linux/AMD.
  - `h264_amf` — AMD Windows.
- **When to KEEP:** source is already H.264 at reasonable bitrate.
- **When to TRANSCODE TO:** maximum compatibility target (older TVs, web).
- **CRF range:** 16 (near-lossless) → 18 (visually-lossless) → 23 (default) → 28+ (small).
- **Pixel formats:** `yuv420p` (8-bit, universal), `yuv420p10le` (10-bit, better
  quality/size but limited player support).

### H.265 / HEVC (modern standard, ~50% smaller than H.264 at same quality)
- **Year:** 2013. ~30-50% bitrate reduction vs H.264 at same visual quality.
- **Encoders:**
  - `libx265` — software, slow but best compression. `medium`/`slow` presets
    are the sweet spot.
  - `hevc_nvenc` — NVIDIA hardware. Your RTX 3060 has 3rd-gen NVENC hevc.
  - `hevc_qsv`, `hevc_vaapi`, `hevc_videotoolbox`, `hevc_amf`.
- **When to KEEP:** source is HEVC at reasonable bitrate.
- **When to TRANSCODE TO:** size reduction (the #1 Tdarr use-case).
- **CRF range:** 18 → 20-23 (typical) → 28 (small). HEVC CRF ≈ H.264 CRF + 2-4
  for similar quality.
- **Caveats:** patent licensing — some browsers/older devices can't play HEVC.
  Emby/Plex/Jellyfin handle it fine via direct play or transcode-on-the-fly.

### AV1 (next-gen, royalty-free)
- **Year:** 2018. ~20-30% smaller than HEVC at same quality, but **much slower
  to encode** in software. Hardware decoders are now common on RTX 30/Arc/iGPU.
- **Encoders:**
  - `libsvtav1` — software, the modern default. `preset 4-8` is the practical
    range.
  - `av1_nvenc` — RTX 40+ only (RTX 3060 does NOT have AV1 NVENC; need RTX 40
    series or Arc).
  - `av1_qsv`, `av1_vaapi` — Intel/AMD.
- **When to KEEP:** source is AV1.
- **When to TRANSCODE TO:** long-term archival where you want maximum
  compression and can wait for slow encodes.
- **CRF range:** 23-35 typical.

### VP9 (Google's answer to HEVC)
- **Year:** 2013. Royalty-free, used heavily on YouTube. Roughly HEVC-class
  compression. Largely superseded by AV1.
- **When you'll see it:** WebM files, some anime fan-release groups.
- **Encoder:** `libvpx-vp9`. Slow.

### VP8 / Theora / VC-1 / MPEG-2 / MPEG-4 / DivX / Xvid / WMV
- **When you'll see them:** old DVD rips (MPEG-2), old WebM (VP8), HD-DVD/Blu-ray
  early era (VC-1), early-2000s downloads (DivX/Xvid).
- **When to TRANSCODE:** ALWAYS — these are obsolete and waste space. Target
  H.264 or HEVC.

### MPEG-4 Visual (DivX/Xvid) — should always be transcoded
Same category as above. Modern players may not even decode it.

## Audio codecs

### AAC (most compatible audio)
- **Variants:** AAC-LC (default), AAC-HE v1/v2 (for very low bitrates, e.g. podcasts).
- **Encoders:** `aac` (ffmpeg native, good), `libfdk_aac` (best quality but
  requires non-free ffmpeg build).
- **Use cases:** universal player support, web delivery, stereo music.
- **Typical bitrates:** 128 kbps stereo (transparent for most), 256-384 kbps
  5.1 surround.

### AC-3 / Dolby Digital (legacy surround)
- **Year:** 1991. The DVD/Blu-ray surround standard.
- **Max:** 5.1 channels, 640 kbps (DVD limited to 448).
- **Compatible:** with everything that handles DVD/Blu-ray/ATSC.
- **Encoder:** `ac3` (ffmpeg native).

### E-AC-3 / Dolby Digital Plus (modern surround)
- **Year:** 2005. Backwards-compatible extension of AC-3.
- **Max:** 7.1 channels, ~6 Mbps.
- **Use cases:** streaming services, modern Blu-ray, ATSC 3.0.
- **Common Tdarr target:** convert TrueHD/DTS → EAC3 for size + compatibility.

### Dolby TrueHD (lossless surround, Blu-ray)
- **Year:** 2005. Lossless compression, typically 5.1 or 7.1 + Atmos extension.
- **Size:** 3-6 Mbps.
- **Compatibility:** mostly Blu-ray players + premium receivers. NOT compatible
  with browsers/phones/Samsung TVs/etc.
- **Common Tdarr action:** transcode to EAC3 or AC3 for compatibility, or keep
  if you have an Atmos-capable receiver.

### DTS family
- **DTS (Core):** 1996. Lossy surround, ~1.5 Mbps. Compatible with most AVR/TVs.
- **DTS-HD HRA:** lossy extension, ~3-7 Mbps.
- **DTS-HD MA:** lossless, ~3-25 Mbps. Premium receiver required.
- **DTS:X:** object-based, similar market segment to Dolby Atmos.
- **DTS Express:** low-bitrate streaming variant.
- **Common Tdarr action:** DTS → EAC3 for compatibility (DTS isn't supported by
  many streaming players/ChromeCast/AppleTV for direct play).

### FLAC (lossless, mostly music)
- **Year:** 2001. Lossless audio, ~50-60% the size of WAV.
- **Compatibility:** good in MKV; spotty in MP4.
- **Use cases:** archival music, high-end movie audio.

### Vorbis / Opus
- **Vorbis:** legacy open-source audio, mostly in WebM.
- **Opus:** modern, royalty-free, lower-latency, better than AAC at low bitrates.
  Growing support; standard for WebRTC.

### MP3 / MP2 / PCM / WAV / ALAC / ATRAC / RealAudio
- **MP3:** universal, lossy, decent quality at 192+ kbps.
- **PCM/WAV:** uncompressed, huge. Convert to FLAC.
- **ALAC:** Apple Lossless (rare in video files).

### AC-4
- **Year:** 2015. Next-gen broadcast standard. Rarely seen in Tdarr libraries.

## Containers

### MKV (Matroska) — the Tdarr default
- Open standard, holds **any** combination of video/audio/subtitle streams.
- Supports multiple audio + subtitle tracks, chapters, attachments (fonts for
  ASS subs), cover art.
- **Best choice for:** libraries with varied codecs, multi-language content,
  subtitle-rich content, anime.
- **Caveat:** some older TVs (Samsung especially) refuse direct play of MKV.

### MP4 — the universal-compatible choice
- Holds H.264/H.265 video + AAC/AC3/EAC3 audio + tx3g/MP4-TTML subtitles.
- **Limitations:** doesn't support FLAC audio, doesn't support PGS/ASS
  subtitles well, doesn't support multiple audio tracks as cleanly as MKV.
- **Best choice for:** Apple devices, web playback, maximum portability.

### AVI — legacy
- Old Microsoft container. Limited codec support, no modern subtitles, no
  H.265. **Always remux to MKV or transcode.**

### MOV — Apple's container
- Same family as MP4 (both ISO base media file format). Usually fine.

### TS / M2TS — transport stream
- Broadcast/Blu-ray stream container. Often remux to MKV for tidiness.

### WebM
- Restricted VP8/VP9/AV1 + Vorbis/Opus. Modern but limited.

## Subtitle formats

### SRT (SubRip Text) — universal
- Plain text + timestamps. Works everywhere. **Convert other formats to SRT
  when possible.**

### ASS/SSA (Advanced SubStation Alpha)
- Rich formatting (fonts, colors, positioning, karaoke). Used by anime groups.
- **Caveat:** requires font attachments; some players render differently.
- Convert to SRT if you don't need the formatting (loses styling).

### PGS (Presentation Graphic Stream) — Blu-ray bitmap subtitles
- Image-based, no text. Players OCR them rarely. Large.
- **Tdarr action:** OCR to SRT (slow, imperfect) or keep as PGS.

### VobSub (SUB/IDX) — DVD bitmap subtitles
- Same idea as PGS but for DVDs. Usually convert to SRT.

### WebVTT
- Web-standard subtitle format, similar to SRT with extra metadata.

### Tx3g / MP4-TTML / CEA-608 / CEA-708
- MP4 broadcast subtitles. CEA-608/708 are "closed captions" (embedded in
  video user-data) — `x7ac_Remove_Closed_Captions` strips them.

## Choosing an output target — decision tree

```
What's your goal?
├── "Smaller files, keep quality"  → HEVC (libx265 medium CRF 20-22, or
│                                     hevc_nvenc if you have an NVIDIA GPU)
├── "Maximum compatibility"        → H.264 + AAC in MP4 (Apple/web safe)
├── "Long-term archival"           → AV1 libsvtav1 (slow but smallest)
├── "Don't transcode video, just   → Remux to MKV + clean audio/subs
│  clean up the file"
├── "Hardware compatibility (older → H.264 + AC3/AAC in MP4
│  TV, Chromecast, etc.)"
└── "Modern AV receiver + capable  → Keep HEVC/TrueHD/DTS-HD MA in MKV
    player"
```

## Bitrate / quality reference (1080p SDR, libx265 medium CRF)

| Source | Typical bitrate | After HEVC CRF 21 | Savings |
|---|---|---|---|
| Blu-ray REMUX (H.264 ~30 Mbps) | ~30 Mbps | ~6-10 Mbps | ~70% |
| Blu-ray encode (H.264 ~10 Mbps) | ~10 Mbps | ~4-6 Mbps | ~40% |
| WebDL (H.264 ~5 Mbps) | ~5 Mbps | ~3-4 Mbps | ~25% |
| Existing HEVC (any) | varies | don't transcode again | 0% |

**Never transcode a file twice.** Every lossy→lossy transcode degrades quality.
Check the source codec before transcode; if it's already HEVC at reasonable
bitrate, leave it alone.

## Codec compatibility matrix (common player → codec support)

| Player | H.264 | HEVC | AV1 | AAC | AC3 | EAC3 | TrueHD | DTS-HD MA | FLAC | MKV |
|---|---|---|---|---|---|---|---|---|---|---|
| Chrome | ✓ | ✓* | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| Safari | ✓ | ✓* | partial | ✓ | ✓ (macOS) | ✓ (macOS) | ✗ | ✗ | partial | partial |
| Firefox | ✓ | partial | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| Apple TV | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (tvOS 15+) | partial | ✓ |
| Chromecast | ✓ | ✓ (ultra+) | ✓ (with Google TV) | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ |
| Samsung TV | ✓ | ✓ | varies | ✓ | ✓ | ✓ | varies | varies | ✗ | varies |
| LG webOS TV | ✓ | ✓ | ✓ (2020+) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Emby/Plex/Jellyfin | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

✓* = platform-dependent (HEVC on Chrome needs hardware decoder or extension).

Emby/Plex/Jellyfin can play anything because they **transcode-on-the-fly** when
the client can't direct-play. That's separate from Tdarr's role — Tdarr
pre-processes files once for the library; the media servers handle last-mile
compatibility at view time.

## Recommended output targets by source

| Source pattern | Recommended transcode |
|---|---|
| MPEG-2 DVD rip | H.264 CRF 18 (libx264) or HEVC CRF 20 + AAC audio, MKV |
| H.264 Blu-ray REMUX (huge) | HEVC CRF 19-21 (NVENC if GPU, libx265 if CPU) + keep DTS/TrueHD or downmix to EAC3 |
| H.264 WebDL (already small) | Don't transcode. Maybe remux + clean subs/audio. |
| HEVC anything | Don't transcode. |
| AV1 | Don't transcode. |
| VP9/VP8 | H.264 or HEVC (better compatibility). |
| Old AVI/Xvid/DivX | H.264 CRF 17-18 (likely source is already lossy). |
| Anime (animation) | HEVC CRF 22-24 with tune grain or animation (handles flat colors well). |
| 4K HDR REMUX | Keep. If you must shrink: HEVC CRF 18-20 RF, preserve HDR metadata. |

## See also
- `hardware-acceleration.md` — encoder selection (NVENC vs QSV vs CPU) for your box.
- `workflows.md` — actual Tdarr plugin/flow patterns implementing these decisions.
- `plugins.md` — community plugin catalog implementing every transcode pattern above.
