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

## comfy_img2video (image-to-video, FLF seamless cycles)
`comfy_img2video(image, prompt, loop=True)` — the curated i2v path. Graph
(verified against 0.x nodes_lt.py): LoadImage → LTXVPreprocess
(jpeg-degrade to match LTXV training) → the txt2video trunk with
`LTXVAddGuide(frame_idx=0)` pinning the still as frame one and, with
loop=True, a second `LTXVAddGuide(frame_idx=-1)` (negative = from the end)
pinning the SAME image as the last frame → `LTXVCropGuides` after the
sampler strips the guide latents (mandatory) → VAEDecode → mp4.
- True seamless cycle — no crossfade. Write STEADY-STATE motion prompts
  (mid-cycle at start/end); progressive verbs break closure.
- `strength` 0.7–1.0 (default 0.9; 1.0 can over-anchor to near-static).
- Best style control: SDXL still w/ checkpoint+LoRA stack → img2video.
- Same VRAM footprint class as txt2video; the cgroup-OOM signature
  (optimization.md §4) applies.

## Loops & GIFs
- Seamless loop from ANY clip: `comfy_loop_video(mp4)` → forward-only
  crossfade wrap as h264 **yuv420p** mp4 (vpt9-ready; ~40x smaller than
  GIF); `format="both"` adds a GIF; `interpolate_fps=` = loop-aware motion
  interpolation (slow), applied after the wrap.
- GIF-only: `comfy_to_gif(video_path, fps=12, width=480)`.
- True cycles (img2video loop=True, comfy_animate_still) must NOT be
  re-crossfaded — `comfy_to_gif(..., loop="none")`.
- Parametric motion from stills (no GPU): `comfy_animate_still` — see
  projection-mapping.md.
- Server-side alternatives: `SaveAnimatedWEBP` / `SaveAnimatedPNG` nodes
  (no native GIF node in core) — swap for SaveVideo in a custom graph when a
  browser-friendly loop beats an mp4.
