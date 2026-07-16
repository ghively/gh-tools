---
description: Generate a video clip (or animated GIF) with LTX-Video
argument-hint: <what should happen in the shot; mention gif if wanted>
---

Generate a video from: **$ARGUMENTS**

1. Read the comfyui-control skill's references/video.md and prompting.md
   (LTXV section) first.
2. `comfy_status` — confirm VRAM headroom; warn that video takes minutes.
3. Rewrite the user's idea as a single-shot cinematic description (3–6
   sentences, present tense, explicit camera movement) — show them the prompt.
4. `comfy_txt2video(...)` — 768×512, 97 frames, cfg 3.0, steps 25 defaults;
   `gif=True` if they want a GIF (or run `comfy_to_gif` on the mp4 after).
5. Report the local mp4/gif paths and offer: more frames, different motion,
   or a reroll with the same seed family.
