---
description: Generate an image with ComfyUI (guided txt2img)
argument-hint: <prompt text, optionally "with sdxl", size, steps>
---

Generate an image from: **$ARGUMENTS**

1. If the request is empty or ambiguous, ask what to generate.
2. `comfy_status` first — confirm the server is up and note VRAM; warn if a
   generation is already running.
3. Pick the checkpoint: sd3.5_medium (default) unless the user says SDXL.
   Apply the sweet-spot settings from the comfyui-control skill.
4. `comfy_txt2img(...)` — then report the local image path(s) and seed.
5. Offer variations (same seed + tweaks, or new seed).
