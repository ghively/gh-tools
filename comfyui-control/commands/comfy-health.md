---
description: ComfyUI health check — server, GPU/VRAM, queue, recent failures
---

Run a ComfyUI health check using the comfyui MCP tools:

1. `comfy_status` — report version, VRAM free/total, queue state.
2. `comfy_queue` + `comfy_history(max_items=5)` — any stuck or failed runs?
3. `comfy_logs(tail_chars=2000)` — scan for ERROR/Traceback lines.
4. `comfy_models("checkpoints")` — confirm models are visible (catches a broken
   bind mount immediately).

Summarize: healthy/degraded, VRAM headroom, anything failing and why. If the
server is unreachable, check the container (`docker ps --filter name=comfyui`)
and report that instead.
