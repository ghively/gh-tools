# comfyui-control

Deep Claude Code integration for ComfyUI (built against 0.26.0 on gh-nvidia).

- **MCP server** (`mcp/server.py`, self-provisioning via `uv run --script`):
  generic passthrough to all 46 HTTP routes + curated tools — status, models,
  node search, queue, history, logs; txt2img (LoRA, latent hires-fix),
  img2img, inpaint, upscale, batch; LTX-Video txt2video + **img2video with
  first/last-frame-pinned seamless cycles**; **parametric still animation**
  (zoom/rotate/drift/pulse/kaleido/tunnel — mathematically exact loops, no
  GPU); seamless mp4/GIF looping with optional loop-aware interpolation;
  1080p mastering (4x → exact-raster jpg); **vpt9 media-library
  integration** (list collections, tagged upload, gated delete);
  HuggingFace/Civitai model management; PNG workflow extract/remix; raw
  workflow submit; confirm-gated interrupt/cancel/free/install.
- **Skill** `comfyui-control`: tool map, generation guidance, safety rules,
  full API map + conventions + projection/texture/loop methodology in
  references (including the owner's texture-research doc).
- **Commands**: `/comfy-health`, `/comfy-generate`, `/comfy-video`,
  `/comfy-projection` (batch stills + loops, evolve mode, auto-delivery),
  `/comfy-texture-set` (coherent multi-face sets for 3D-effect mapping).

## Setup
1. `cp config.example.json config.local.json` and set `base_url`
   (git-ignored). Optional: `library_url` for the vpt9 media library,
   `models_dir`/`custom_nodes_dir`/`compose_file` for host-side management,
   `civitai_token` for gated Civitai downloads.
2. Install the plugin from this marketplace, `/reload-plugins`.
3. `uv` must be on PATH (the server installs its own deps on first launch).
   `ffmpeg`/`ffprobe` needed for the loop/motion/mastering tools.

Smoke test against the live system (read-only, no generation jobs, skips
cleanly when `config.local.json` is absent): `uv run --script mcp/_smoketest.py`

Selftest without MCP: `COMFYUI_CONFIG=./config.local.json uv run --script mcp/server.py selftest`
(25 checks; the graph-wiring, motion-math, and gate checks are offline-safe —
checks that hit the ComfyUI host, HuggingFace, or the library fail as
expected when run off-LAN).

ComfyUI has **no auth** — this plugin assumes a trusted LAN. Disruptive tools
require `confirm=True`; vpt9 library uploads are reversible (delete is
gated); generation occupies the GPU shared with Ollama.
