# comfyui-control

Deep Claude Code integration for ComfyUI (built against 0.26.0 on gh-nvidia).

- **MCP server** (`mcp/server.py`, self-provisioning via `uv run --script`):
  generic passthrough to all 46 HTTP routes + curated tools (status, models,
  node search, queue, history, logs, txt2img, raw workflow submit,
  upload/download, confirm-gated interrupt/cancel/free).
- **Skill** `comfyui-control`: tool map, generation guidance, safety rules,
  full API map + conventions + recipes in references.
- **Commands**: `/comfy-health`, `/comfy-generate`.

## Setup
1. `cp config.example.json config.local.json` and set `base_url` (git-ignored).
2. Install the plugin from this marketplace, `/reload-plugins`.
3. `uv` must be on PATH (the server installs its own deps on first launch).

Selftest without MCP: `COMFYUI_CONFIG=./config.local.json uv run --script mcp/server.py selftest`
(13 read-only checks against the live server).

ComfyUI has **no auth** — this plugin assumes a trusted LAN. Disruptive tools
require `confirm=True`; generation occupies the GPU shared with Ollama.
