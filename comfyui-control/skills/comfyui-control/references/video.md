# Video generation (LTX-Video on the 3060)

Live-verified 2026-07-15: 768×512×97f mp4 + GIF in ~85s wall on a fresh
container. NOTE: video is the job most sensitive to the cgroup-RAM OOM
(optimization.md §4) — if SamplerCustom OOMs with an empty GPU, restart the
comfyui service and re-run; verified to clear it.

## What's installed
- **ltx-video-2b-v0.9.5.safetensors** (checkpoints/) — LTX-Video 2B, the
  right size for 12GB VRAM. Uses the **already-installed** t5xxl_fp8 encoder
  (shared with SD3.5) via `CLIPLoader(type=ltxv)`.
- Full LTXV + WAN 2.x node suites are in core. WAN models are NOT installed —
  WAN 14B doesn't fit 12GB unquantized; a GGUF quant via `UnetLoaderGGUF`
  (ComfyUI-GGUF installed) is the path if ever wanted.

## comfy_txt2video
- `frames` must be **8n+1** (auto-corrected): 97 ≈ 4s @ 24fps, 121 ≈ 5s,
  161 ≈ 6.7s. 768×512 is the sweet spot; portrait 512×768 works.
- CFG ~3.0, steps 25 (LTXVScheduler handles the sigma shaping).
- `gif=True` → also renders an animated GIF (ffmpeg two-pass palette,
  12fps/480px default — tune with comfy_to_gif on the mp4 for other sizes).
- Output lands as mp4 in output/video/ server-side and is downloaded to
  output_dir automatically.
- Prompting: see prompting.md — long, single-shot, cinematic descriptions
  with explicit camera movement.

## Graph shape (for comfy_generate customization)
CheckpointLoaderSimple(ltx) → CLIPLoader(t5xxl, ltxv) → CLIPTextEncode ×2 →
LTXVConditioning(frame_rate) → EmptyLTXVLatentVideo → LTXVScheduler(sigmas) →
SamplerCustom(euler) → VAEDecode → CreateVideo(fps) → SaveVideo(mp4/h264).

Image-to-video exists too: `LTXVImgToVideo` replaces the empty latent — wire
via comfy_generate with a LoadImage feeding it (see comfy_nodes
node_class=LTXVImgToVideo for exact inputs).

## Animated GIFs
- Any local video → `comfy_to_gif(video_path, fps=12, width=480)`.
- Server-side alternatives: `SaveAnimatedWEBP` / `SaveAnimatedPNG` nodes
  (no native GIF node in core) — swap for SaveVideo in a custom graph when a
  browser-friendly loop beats an mp4.
