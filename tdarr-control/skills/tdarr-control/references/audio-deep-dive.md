# Audio handling — the comprehensive reference

Everything Tdarr + ffmpeg can do with audio. From analysis to normalization
to language routing to repair.

## Audio codec reference (compressed for context — see codecs.md for full)

| Codec | Lossless? | Max channels | Typical use | Compatibility |
|---|---|---|---|---|
| AAC-LC | lossy | 48 | Music + general | Universal |
| AAC-HE v1/v2 | lossy | 48 | Low-bitrate streaming | Good (mobile) |
| AC-3 (Dolby Digital) | lossy | 5.1 | DVD/Blu-ray/streaming | Universal (broadcast) |
| E-AC-3 (DD+) | lossy | 7.1 | Modern streaming | Apple TV, modern TVs |
| Dolby TrueHD | lossless | 7.1 + Atmos | Blu-ray REMUX | Premium AVRs only |
| DTS (Core) | lossy | 5.1 | DVD/Blu-ray | Most AVRs |
| DTS-HD HRA | lossy | 7.1 | Blu-ray | Premium AVRs |
| DTS-HD MA | lossless | 7.1 | Blu-ray REMUX | Premium AVRs |
| DTS:X | lossless + obj | 7.1.4+ | Object audio | Premium AVRs |
| FLAC | lossless | 8 | Music + archival | Good in MKV |
| PCM/WAV | uncompressed | 8 | Blu-ray PCM track | Universal (huge) |
| Vorbis | lossy | 255 | WebM/OGG | Web |
| Opus | lossy | 255 | VoIP/WebRTC | Modern web |
| MP3 | lossy | 5.1 (rare) | Legacy music | Universal |
| ALAC | lossless | 8 | Apple ecosystem | Apple devices |
| TrueHD ATMOS | lossless + obj | 7.1.4+ | 4K Blu-ray | Premium AVR + Atmos |
| AC-4 | lossy | 7.1 | Next-gen broadcast | Very rare in libraries |

## Bitrate reference (target if transcoding)

| Codec | Stereo music | 5.1 surround | 7.1 surround | Atmos |
|---|---|---|---|---|
| AAC-LC | 192-256 kbps | 384-512 kbps | 640 kbps | n/a |
| AC-3 | 192 kbps | 384-448 kbps (DVD max 448) | 640 kbps max | n/a |
| E-AC-3 | 192-256 kbps | 384-768 kbps | 1024-2048 kbps | 1024-2048 kbps |
| TrueHD | n/a | 1500-3000 kbps | 2000-5000 kbps | 3000-6000 kbps |
| DTS core | n/a | 768-1536 kbps | n/a | n/a |
| DTS-HD MA | n/a | 1500-5000 kbps | 2000-10000 kbps | 3000-15000 kbps |
| FLAC | 800-1000 kbps | 2000-4000 kbps | 3000-6000 kbps | n/a |

**Rule of thumb for compatibility transcodes:** stereo → AAC 192-256 kbps;
surround → EAC3 640 kbps (universal AVR/AppleTV/Chromecast support).

## Audio analysis in Tdarr (flow nodes)

These flow-plugin nodes inspect audio streams:

| Node | What it checks | Use case |
|---|---|---|
| `checkAudioCodec` | Codec name (AAC/AC3/DTS/...) | Find DTS files for compat transcode |
| `checkAudioBitrate` | Stream bitrate | Find low-quality or oversized audio |
| `checkChannelCount` | Channel count (2/6/8) | Find surround vs stereo, validate expected layout |
| `checkStreamsCount` | Total stream count | Catch bloated multi-audio files |
| `checkStreamProperty` | Generic stream-property filter | Custom audio checks |

Combined: filter files with DTS audio AND >5.1 channels → flag for EAC3
downmix transcode.

## Audio-normalization flow nodes

### `normalizeAudio` (audio category)

Built-in audio normalization flow node. Wraps ffmpeg's `loudnorm` filter
for EBU R128 loudness normalization (broadcast standard, used by Netflix /
BBC / most major streamers).

### `ffmpegCommandNormalizeAudio` (ffmpegCommand category)

Lower-level normalization with explicit ffmpeg args. Use for full control.

## FFmpeg audio filters reference

### `loudnorm` — EBU R128 loudness normalization (the modern standard)

EBU R128 specifies integrated loudness of **-23 LUFS** (broadcast) or
**-16 LUFS** (music streaming — Spotify/Apple Music target).

**2-pass loudnorm** (the accurate way):
```bash
# Pass 1: measure
ffmpeg -i input.mkv -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -

# Parse the output JSON for measured_I, measured_TP, measured_LRA, measured_thresh, target_offset

# Pass 2: apply with measured values
ffmpeg -i input.mkv -af loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=<measured_I>:measured_TP=<measured_TP>:measured_LRA=<measured_LRA>:measured_thresh=<measured_thresh>:offset=<target_offset>:linear=true:print_format=summary output.mkv
```

This is what `NIfPZuCLU_2_Pass_Loudnorm_Audio_Normalisation` plugin does.

**Single-pass loudnorm** (faster, less accurate):
```bash
ffmpeg -i input.mkv -af loudnorm=I=-16:TP=-1.5:LRA=11 -c:v copy output.mkv
```
Dynamic mode (default) — adapts to content. Good enough for casual use.

### `dynaudnorm` — dynamic audio normalizer

Smoothes volume dynamically — boosts quiet parts, limits loud parts.
Different from loudnorm (which targets integrated loudness).

```bash
ffmpeg -i input.mkv -af dynaudnorm=f=150:g=15:p=0.9 -c:v copy output.mkv
```

Use for content with extreme dynamic range (e.g., action movies with
quiet dialogue + loud explosions) when watching on small speakers.

### `acompressor` — dynamic range compression

Reduces dynamic range — makes loud quieter, quiet louder. Useful for
night-time listening or noisy environments.

```bash
ffmpeg -i input.mkv -af acompressor=threshold=-20dB:ratio=4:attack=5:release=50 -c:v copy output.mkv
```

### `volume` — simple gain

```bash
ffmpeg -i input.mkv -af volume=2.0 -c:v copy output.mkv   # +6dB
ffmpeg -i input.mkv -af volume=0.5 -c:v copy output.mkv   # -6dB
ffmpeg -i input.mkv -af "volume=-3dB" -c:v copy output.mkv
```

### `silenceremove` — strip silent sections

```bash
# Remove all silence >1sec below -50dB
ffmpeg -i input.mkv -af silenceremove=stop_periods=-1:stop_duration=1:stop_threshold=-50dB -c:v copy output.mkv
```

Use for podcasts/music with long pauses.

### `aresample` — sample rate conversion

```bash
ffmpeg -i input.mkv -af aresample=48000 -c:v copy output.mkv
```

Always resample to 48000 for video files (broadcast standard).

### `pan` — channel downmix/upmix with custom coefficients

```bash
# 5.1 → stereo with custom mix
ffmpeg -i input.mkv -af "pan=stereo|FL=0.5*FC+FL+0.707*BL+0.707*SL|FR=0.5*FC+FR+0.707*BR+0.707*SR" -c:v copy output.mkv
```

Use when default `-ac 2` downmix sounds wrong.

## Downmix reference

### Surround → stereo

Simple: `-ac 2` (ffmpeg default mix).
Custom (preferred for film): `-af "pan=stereo|FL=FL+0.707*FC+0.707*BL+0.707*SL|FR=FR+0.707*FC+0.707*BR+0.707*SR"`.

Mix coefficients (ITU-R BS.775):
- L/R: pass-through
- Center: 0.707 (-3 dB) to L+R
- LFE: usually dropped (or 0.707 to L+R if you want the rumble)
- Surround (BL/BR or SL/SR): 0.707 to L+R

### 7.1 → 5.1

```bash
ffmpeg -i input.mkv -af "pan=5.1|FL=FL|FR=FR|FC=FC|LFE=LFE|BL=0.5*BL+0.5*SL|BR=0.5*BR+0.5*SR" output.mkv
```

### Atmos / DTS:X → flat surround

Object audio is encoded as the base 7.1 channel layout + object metadata.
Dropping to 7.1 (or 5.1) loses the object positioning but preserves the
channel bed. Use `-c:a eac3 -ac 6` (or 8) — the encoder drops object
metadata automatically.

## Audio codec conversion patterns

### DTS/TrueHD → EAC3 for compatibility (THE common case)

```bash
# Keep video as-is, transcode audio
ffmpeg -i input.mkv \
  -c:v copy \
  -map 0:v -map 0:a:0 \
  -c:a:0 eac3 -b:a:0 640k \
  -map 0:s? \
  output.mkv
```

This is what `MC93_Migz5ConvertAudio` plugin does.

### Lossless → FLAC for archival

```bash
ffmpeg -i input.mkv \
  -c:v copy \
  -c:a flac -compression_level 8 \
  -map 0:v -map 0:a \
  output.mkv
```

### PCM/WAV → FLAC (lossless, ~50% smaller)

```bash
ffmpeg -i input.mkv -c:v copy -c:a flac -map 0 output.mkv
```

### Multi-audio → keep one

```bash
ffmpeg -i input.mkv \
  -map 0:v:0 -map 0:a:0 -map 0:s? \
  -c copy \
  output.mkv
```

Keeps first video + first audio + all subtitles.

### Strip commentary tracks

Commentary tracks usually have `title=Commentary` or are tagged
`commentary=1`. Use `MC93_Migz3CleanAudio` plugin or:

```bash
# Use ffprobe to identify commentary tracks, then build -map args
# to drop them
```

## Language handling

### Set default audio stream

```bash
ffmpeg -i input.mkv \
  -map 0:v:0 -map 0:a:m:language:eng -map 0:a -map 0:s? \
  -disposition:a:0 default -disposition:a:1 none \
  -c copy \
  output.mkv
```

This is what `c0r1_SetDefaultAudioStream` does.

### Reorder audio by language preference

`076a_re_order_audio_streams` plugin (and `MC93_Migz6OrderStreams`) put
preferred languages first.

### Keep native + English, drop rest

`henk_Keep_Native_Lang_Plus_Eng` plugin. Common for foreign-film libraries.

## Audio health checks

FFmpeg `astats` filter analyzes audio for problems:

```bash
# Detect clipped audio (DC offset, clipping)
ffmpeg -i input.mkv -af astats=metadata=1:reset=1 -f null - 2>&1 | grep -E "( clipping|DC_offset)"

# Detect silent tracks
ffmpeg -i input.mkv -af volumedetect -f null - 2>&1 | grep -E "(mean_volume|max_volume)"
# mean_volume of -91 dB = silent
```

Use the `runCli` flow node to run these checks during a flow, then
`requireReview` on files that fail.

## Dolby Atmos considerations

TrueHD Atmos = base 7.1 TrueHD stream + Atmos extension (object metadata).
Most Tdarr transcoding scenarios:

1. **Keep Atmos intact:** `-c:a copy` — works if container supports it
   (MKV does). Compatible with Apple TV 4K, NVidia Shield, premium AVRs.
2. **Drop to plain TrueHD:** `-c:a truehd -dtshd_fallback` or similar.
   Loses Atmos but keeps lossless 7.1.
3. **Downmix to EAC3 7.1:** `-c:a eac3 -b:a 1.5M -ac 8`. Massive size
   reduction, loses Atmos positioning, keeps 7.1 surround.

Never try to "transcode Atmos to Atmos smaller" — there's no easy way to
re-encode object audio.

## Audio pitfalls to avoid

1. **Don't transcode audio twice.** AAC → AAC = generational loss. Always
   transcode from the lossless/lossy original.
2. **Don't upmix.** Stereo → 5.1 via "upmixing" plugins sounds worse than
   just playing stereo through a surround receiver's Pro Logic mode.
3. **Don't convert AAC to AC3.** Both are lossy; you waste bitrate. Pick
   ONE lossy format and stick with it.
4. **Watch out for sync.** If you transcode audio + video, the audio
   timestamp must stay aligned. Use `-c:v copy` when only transcoding audio.
5. **Channel layout matters.** A 5.1 source downmixed to stereo with bad
   coefficients sounds wrong (dialogue too quiet or effects too loud).
   Test with real content.
6. **Sample rate should be 48 kHz** for video. Don't resample to 44.1 kHz
   (CD quality) — it's a TV/film anti-pattern.
7. **Normalize at transcode time, not after.** If you `loudnorm` after a
   DTS→EAC3 transcode, you've already lost quality. Do `loudnorm` in the
   same ffmpeg pass.

## Recommended audio strategies by use case

| Goal | Strategy |
|---|---|
| Compatibility (Apple TV / web / Chromecast) | AAC 256kbps stereo + EAC3 640kbps 5.1 |
| Archival (lossless) | FLAC 5.1/7.1 (or keep TrueHD/DTS-HD MA) |
| Library-size reduction | EAC3 640 kbps 5.1 (saves 80% vs TrueHD) |
| Loudness uniformity | 2-pass loudnorm to -16 LUFS |
| Multi-language library | Keep native + English AAC; drop commentary |
| Mixed device fleet | Two audio tracks: AAC stereo + EAC3 5.1 |

## See also
- `codecs.md` — full codec reference (audio + video + containers).
- `media-analysis.md` — damage detection + analysis flow nodes.
- `flow-plugin-catalog.md` — full flow-node catalog (audio nodes + everything else).
- `workflows.md` — workflow patterns (incl. audio normalization).
