# Hardware acceleration for Tdarr transcoding

Practical guide to picking the right encoder for your hardware. Focused on
**gh-nvidia (RTX 3060)** but covers every option.

## The hardware-acceleration decision

Every modern video encoder has BOTH a software implementation (`libx264`,
`libx265`, `libsvtav1`) and usually several hardware implementations
(`h264_nvenc`, `hevc_nvenc`, `h264_qsv`, etc.). The choice is a tradeoff:

| | Software (libx*) | Hardware (NVENC/QSV/VAAPI) |
|---|---|---|
| **Quality at same bitrate** | Best (1-2 CRF better) | Slightly worse (~5-10% larger for same quality) |
| **Speed** | Slow (1-15 fps on 4K HEVC) | Fast (50-200+ fps on 1080p HEVC) |
| **CPU usage** | 100% on all cores | ~0% CPU; work is on the GPU/iGPU |
| **Power** | High CPU power | Lower system power |
| **Flexibility** | Every option available | Subset of options |
| **Reliability** | Rock-solid | Driver/version-sensitive |

For Tdarr specifically, hardware is almost always right — you're batch-processing
a library, and you'd rather have 100 files done overnight than 10 done perfectly.

## What gh-nvidia has

Per the homelab context (`~/gh-Nvidia/inventory/group_vars/gpu_hosts.yml`):
- **GPU:** NVIDIA RTX 3060 (12 GB VRAM, ~3rd-gen NVENC + 5th-gen NVDEC)
- **Driver:** 595 (proprietary)
- **Container toolkit:** installed (NVIDIA Container Toolkit)
- **CUDA:** installed

The RTX 3060 has:
- **One NVENC encoder** of Ampere generation (3rd-gen). Supports H.264, H.265
  (8-bit + 10-bit), AV1 *decode* (no AV1 encode — that's RTX 40 series "Ada").
- **One NVDEC decoder** of 5th-gen. Decodes everything including AV1.
- **No AV1 encode capability.** If you want AV1 out, you must use `libsvtav1`
  (software, slow). On this hardware, target HEVC rather than AV1.

## NVENC encoder names (the ones you'll actually use)

| Codec | Encoder | Notes |
|---|---|---|
| H.264 | `h264_nvenc` | RTX 3060 fully supported. |
| HEVC | `hevc_nvenc` | RTX 3060 fully supported, including 10-bit + B-frames. |
| AV1 | (none) | RTX 3060 cannot encode AV1. Use `libsvtav1` for software (slow). |
| VP9 | (none) | NVENC never supported VP9 encode. Use `libvpx-vp9`. |

## NVENC preset / tuning reference

NVENC presets changed in ffmpeg 4.4+ to the p1-p7 scale (newer Turing+ GPUs):

| Preset | Quality | Speed | Use case |
|---|---|---|---|
| `p1` | fastest | fastest | live streaming |
| `p2` | fast | fast | low-latency |
| `p4` | default | balanced | default |
| `p6` | high quality | slower | offline transcoding (Tdarr's sweet spot) |
| `p7` | highest quality | slowest | archival |

Tune options:
- `-tune hq` — high quality (use this for Tdarr library transcodes).
- `-tune ll` — low latency (live streaming, not Tdarr).
- `-tune ull` — ultra-low latency (not Tdarr).
- `-tune lossless` — lossless (huge files; not for normal library use).

Rate control:
- `-rc vbr -cq <N>` — constant quality (VBR with a quality floor). **This is
  what Tdarr should use** — equivalent of CRF in libx264/libx265. CQ values
  track CRF: 20-22 for HEVC, 18-20 for H.264.
- `-rc cbr -b:v <N>` — constant bitrate (not recommended for archival).
- `-rc vbr -b:v <N> -maxrate <N>` — constrained VBR.

## Canonical NVENC ffmpeg commands (copy-paste ready)

These are the snippets you'll plug into Tdarr custom plugins or pass to
`tdarr_call` for custom transcodes.

### HEVC NVENC, balanced quality (the #1 Tdarr pattern)

```bash
ffmpeg -i input.mkv \
  -c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 21 \
  -pix_fmt yuv420p10le -b:v 0 \
  -c:a copy -c:s copy \
  -map 0 -map -0:d \
  output.mkv
```

Notes:
- `-cq 21` is the quality knob. 18 = near-lossless (big files), 23 = smaller.
- `-pix_fmt yuv420p10le` = 10-bit (better banding/quality per bit). Use
  `yuv420p` for 8-bit if player compatibility matters.
- `-b:v 0` lets the VBR-CQ mode work properly (no ceiling).
- `-c:a copy -c:s copy` keeps audio + subtitles untouched.
- `-map 0 -map -0:d` keeps all streams except data streams.

### HEVC NVENC, 8-bit for compatibility

```bash
ffmpeg -i input.mkv \
  -c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 20 \
  -pix_fmt yuv420p -b:v 0 \
  -c:a copy -c:s copy \
  -map 0 \
  output.mkv
```

### H.264 NVENC (for max compatibility — older devices, web)

```bash
ffmpeg -i input.mkv \
  -c:v h264_nvenc -preset p6 -tune hq -rc vbr -cq 21 \
  -pix_fmt yuv420p -b:v 0 \
  -c:a aac -b:a 192k \
  -c:s mov_text \
  -map 0 -map -0:d \
  output.mp4
```

Note: container is now `.mp4`, audio transcoded to AAC, subtitles converted to
mov_text (MP4's text subtitle format). This is the "Apple device safe" pattern.

### HEVC NVENC, HDR preservation

For HDR10 sources, you must preserve the color metadata:

```bash
ffmpeg -i input.mkv \
  -c:v hevc_nvenc -preset p6 -tune hq -rc vbr -cq 20 \
  -pix_fmt p010le -b:v 0 \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc \
  -c:a copy -c:s copy \
  -map 0 \
  output.mkv
```

Notes:
- `-pix_fmt p010le` is 10-bit (REQUIRED for HDR).
- `-color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc` = HDR10
  BT.2020 + SMPTE ST 2084 (PQ) transfer. If you omit these, you strip HDR
  metadata and the result plays as washed-out SDR.
- Dolby Vision is a different beast — it requires profile-aware tooling
  (`dovi_conv` / `dovi_pipeline`) and isn't a simple ffmpeg flag. Generally,
  keep DV sources as-is.

## Hardware encoder selection by GPU

| Hardware | Encoder flag | Tdarr plugin prefix |
|---|---|---|
| NVIDIA RTX/GTX (Pascal+) | `*_nvenc` | "NVENC" / "GPU" / "FFMPEG_NVENC" |
| Intel iGPU (QuickSync) | `*_qsv` | "QSV" / "QSVHEVC" |
| Linux + AMD/Intel (VAAPI) | `*_vaapi` | "VaapiHEVC" |
| Apple Silicon | `*_videotoolbox` | "VideoToolbox" |
| AMD Windows (AMF) | `*_amf` | "AMF" |
| Pure software (libx*) | `libx264`/`libx265`/`libsvtav1` | "FFMPEG_CPU" |

If a Tdarr node has no GPU, fall back to libx* software. The plugin catalog has
both flavors for every common pattern (e.g. `MC93_Migz1FFMPEG` = NVENC,
`MC93_Migz1FFMPEG_CPU` = libx265).

## Docker / container GPU passthrough

For Tdarr in Docker to use NVENC, you need:

1. **NVIDIA Container Toolkit installed on the host** (you have it).
2. **The container image built with NVIDIA support** — the official
   `ghcr.io/haveagitgat/tdarr:latest` image includes the NVIDIA runtime hooks.
3. **GPU passthrough at container start:**
   ```bash
   docker run -d --gpus all \
     --name tdarr_node \
     -e NVIDIA_VISIBLE_DEVICES=all \
     -e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
     ...
   ```
   The key env vars are `NVIDIA_DRIVER_CAPABILITIES=video` (must include
   `video` for NVENC) and `--gpus all`.
4. **Verify inside the container:**
   ```bash
   docker exec -it tdarr_node nvidia-smi
   docker exec -it tdarr_node ffmpeg -encoders | grep nvenc
   ```
   The ffmpeg build Tdarr ships already has `--enable-nvenc`.

If `nvidia-smi` doesn't list the GPU inside the container, NVENC calls will
silently fall back to software or fail. Always verify after deploy.

## NVENC session limits

NVIDIA consumer GPUs (RTX 3060 included) historically had a **3 concurrent
NVENC session limit**. NVIDIA officially **removed this limit** in driver
551.61+ (Windows) / 535.98+ (Linux) for most cards. With your driver 595,
there is no session cap — set `workerLimits.transcodegpu` to whatever your
GPU can handle (typically 2-4 for HEVC at 1080p, 1-2 for 4K).

If you hit "OpenEncodeSessionEx failed: out of memory" errors, lower the
worker limit. NVENC needs ~200-500 MB VRAM per session, independent of source
resolution.

## CPU encoder fallbacks (when GPU is busy or absent)

| Encoder | Speed (4K HEVC) | Quality | Use when |
|---|---|---|---|
| `libx265 -preset ultrafast` | ~10-15 fps | baseline | quick + dirty |
| `libx265 -preset medium` | ~1-3 fps | sweet spot | archival, CPU-only node |
| `libx265 -preset slow` | ~0.3-1 fps | best | final archival (overnight batch) |
| `libx264 -preset veryfast` | ~60+ fps | good | H.264 compatibility transcodes |

CPU encoding is the fallback when:
- No GPU available.
- You want the absolute smallest file and can wait.
- You're processing 1 file and don't care about throughput.

## What to do on gh-nvidia specifically

Given RTX 3060 + driver 595:

- **Default transcode target:** HEVC via `hevc_nvenc -preset p6 -tune hq -rc vbr -cq 21`.
- **Set `workerLimits.transcodegpu` to 2-3** initially; monitor with `nvidia-smi -l 1`.
- **10-bit output by default** (`-pix_fmt yuv420p10le`) — better banding, similar
  size, plays on every device that handles HEVC.
- **Do not target AV1** (no NVENC AV1 on Ampere) — if you absolutely want AV1,
  it'll be CPU `libsvtav1` at single-digit fps. Not worth it on this box.
- **CPU workers (`transcodecpu`): keep low (0-1)** unless you have a specific
  need. CPU encoding competes with NVENC for media file I/O and machine
  learning workloads; on the 3060 box, GPU is the right default.

Use `tdarr_db(mode="getAll", collection="NodeJSONDB")` to read the current
`workerLimits` for your node, and `tdarr_alter_worker_limit(node_id,
"transcodegpu", N, confirm=True)` to change them.

## Benchmarking on first deploy

Run this once after Tdarr deploys to baseline your hardware:

```bash
# Get a small test file
ffmpeg -f lavfi -i testsrc2=duration=10:size=1920x1080:rate=30 -c:v \
  libx264 -crf 18 /tmp/test_1080p.mkv

# Time NVENC HEVC
time ffmpeg -i /tmp/test_1080p.mkv -c:v hevc_nvenc -preset p6 -tune hq \
  -rc vbr -cq 21 /tmp/test_out.mkv

# Time libx265 (compare)
time ffmpeg -i /tmp/test_1080p.mkv -c:v libx265 -preset medium -crf 21 \
  /tmp/test_x265.mkv

# Compare sizes
ls -la /tmp/test*.mkv
```

You should see NVENC ~10-50x faster than libx265 medium, with NVENC output
~5-15% larger for the same quality. That's the expected tradeoff and why NVENC
wins for library-scale Tdarr work.

## See also
- `codecs.md` — full codec reference (what to choose at the strategy level).
- `workflows.md` — actual Tdarr plugin/flow patterns implementing these commands.
