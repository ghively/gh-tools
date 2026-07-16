---
name: comfyui-control
description: Drive the ComfyUI generation server (gh-nvidia :8188) via the comfyui MCP server — images (txt2img/img2img/inpaint/upscale/LoRA/batch), LTX-Video + animated GIFs, model downloads from HuggingFace/Civitai, PNG workflow extraction & remixing, custom-node installs, websocket progress, plus raw API passthrough. Use whenever the user wants to generate or edit images/video, manage models, or script ComfyUI.
---

# Controlling ComfyUI

The `comfyui` MCP server (this plugin) talks to ComfyUI at the host in
`config.local.json` (currently `http://192.168.0.214:8188`, ComfyUI 0.26.0,
RTX 3060 12GB, `--lowvram`, no auth on the trusted LAN).

**Read the reference that matches the job before non-trivial work:**
`references/prompting.md` (per-model prompt language — SD3.5 vs SDXL vs LTXV
differ a lot), `references/models-guide.md` (encyclopedia of image/video model
families: what fits this 12GB card, what to download, loader wiring),
`references/optimization.md` (3060 timings, VRAM/RAM rules, the OOM
signature), `references/video.md` (LTXV + GIF), `references/projection-mapping.md`
(research-backed specs + prompt templates for projection/VJ content — REQUIRED
before any projection-mapping job), `references/projection-styles.md` (the
style ARSENAL: installed LoRAs + triggers, ranked checkpoints, keyword bible,
loop recipes — read together with projection-mapping.md), `references/api-map.md`
(all 46 routes), `references/conventions.md`, `references/common-tasks.md`.

## Tool map

| Job | Tool |
|---|---|
| Health/VRAM/queue snapshot | `comfy_status` |
| Model folders / files (+sizes) | `comfy_models(folder?, detailed?)` |
| Find node classes / schemas | `comfy_nodes(search / node_class)` |
| Queue, finished runs, log tail | `comfy_queue`, `comfy_history`, `comfy_logs` |
| Text→image (LoRA via `loras=`) | `comfy_txt2img` |
| Restyle / vary an image | `comfy_img2img(image, prompt, denoise)` |
| Regenerate a masked region | `comfy_inpaint(image, mask, prompt)` |
| 4x upscale | `comfy_upscale` (4x-UltraSharpV2 installed) |
| N seed-variations of one prompt | `comfy_batch(prompt, count)` |
| Text→video (LTX-Video) | `comfy_txt2video(..., gif=True for GIF)` |
| Any video file → animated GIF | `comfy_to_gif` (crossfade = forward-only seamless loop, the default) |
| Projection-mapping content batch | `/comfy-projection` workflow (stills + seamless loops) |
| Any custom workflow graph | `comfy_generate(workflow_json)` |
| Extract recipe from a ComfyUI PNG | `comfy_png_workflow(png_path)` |
| Remix/re-run a PNG's workflow | `comfy_rerun(png_path, seed/prompt/overrides)` |
| Search downloadable models | `comfy_model_search(query, source=hf/civitai)` |
| Download into the live store | `comfy_model_download(folder, hf_repo+hf_file or url)` |
| Delete a model file | `comfy_model_delete` — needs `confirm=True` |
| Install a custom-node pack | `comfy_install_node(git_url)` — needs `confirm=True`, restarts service |
| Upload / download files | `comfy_upload_image`, `comfy_download_output` |
| Stop / cancel / unload | `comfy_interrupt`, `comfy_cancel`, `comfy_free` — all need `confirm=True` |
| ANYTHING else | `comfy_discover(search)` → `comfy_call(method, path, …)` |

Generation tools return local file paths plus **per-node timings** (websocket-
sourced) — report both. All artifacts land in `output_dir` (`~/comfy-outputs`).

## Installed inventory (2026-07-15)
Checkpoints: `sd3.5_medium` (default; TripleCLIP auto-wired), `sd_xl_base_1.0`,
`ltx-video-2b-v0.9.5`. LoRAs: 3 SDXL icon packs. Upscaler: `4x-UltraSharpV2`.
Encoders: clip_g/clip_l/t5xxl_fp8. Node packs: ComfyUI-GGUF, rgthree-comfy
(828 classes). Model store on host: `/mnt/NVME/ai-models/comfyui/models`.

## Safety rules
- **Ask before generating** unless the user just asked for it — the GPU is
  shared with Ollama. Video runs are minutes, not seconds; say so.
- `confirm=True` tools need explicit user approval each time. Custom-node
  installs run third-party code — the user must name/approve the specific repo.
- Model downloads: prefer **.safetensors** (never .pt/.pth/.ckpt pickles
  unless the user insists), respect the disk-space guard, and quote sizes
  before multi-GB pulls.
- Writes via passthrough (`/userdata`, `/settings`, `/history {clear}`) also
  deserve a user check — no auth layer exists to stop a mistake.
- Never dump `/object_info` raw (1.4 MB); use `comfy_nodes`.
- OOM with empty GPU = container RAM pressure — see optimization.md §4;
  restart the service, don't fight it.
