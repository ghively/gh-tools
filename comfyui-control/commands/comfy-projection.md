---
description: Batch-generate projection-mapping visuals (stills + seamless mp4/GIF loops) for a 1080p rig, auto-delivered to the vpt9 library
argument-hint: <theme/vibe, e.g. "neon geometric pulses, cyan and magenta"> [count] [stills|loops|both] [evolve]
---

Batch-generate projection-mapping content for: **$ARGUMENTS**

Read the comfyui-control skill's `references/projection-mapping.md` AND
`references/projection-styles.md` FIRST (texture-research.md for methodology
questions) and follow their specs exactly. Match the theme to a style LoRA
from the installed arsenal and use its trigger word + the keyword bible
(`black background, background hex 000000, OLED wallpaper` cluster). Then:

1. **Scope**: from the arguments take the theme, count (default 4), and mode
   (default both). Ask only if the theme is missing. Venue matters: assume a
   dark venue (bright-on-black) unless the user says the surface is lit/outdoor
   (then go high-key bright instead). Vary palettes per clip, never per style.
2. `comfy_status` — VRAM headroom; warn that loops take minutes each.
3. **Stills**: `comfy_batch` with the reference's still template filled with
   the theme, `width=1344, height=768` (16:9 bucket), SDXL or SD3.5 per the
   prompting guide. Show thumbnails/paths + seeds.
4. **Loops** (forward-only, never boomerang): for each of 2–3 motion variants,
   prefer the style-control pipeline — SDXL still (checkpoint + LoRA + this
   clip's palette) → `comfy_img2video(still, steady-state motion prompt,
   loop=True)` → a true seamless-cycle mp4. Pure text→video alternative:
   `comfy_txt2video` then `comfy_loop_video(mp4)` (crossfade wrap). GIFs only
   on request: `comfy_to_gif(loop="none")` for true cycles. Cheap ambient
   variants: `comfy_animate_still` on a winning still (drift/pulse for
   ambience; tunnel only on self-similar sources).
5. **Evolve mode** (if "evolve" in the arguments, or offered after review —
   Electric Sheep style): treat each batch as a generation; the user's picks
   are the fitness function. Breed the next generation: recombine the
   winners' prompt fragments + palettes (crossover), jitter cfg/denoise/LoRA
   weight and reroll seeds via `comfy_rerun`/`comfy_img2img` (mutation).
   Iterate until the user calls it.
6. **Finish & auto-deliver**: `comfy_master_still` the winning stills (4x →
   exact 1920×1080 jpg). Then deliver to the vpt9 library WITHOUT asking
   (uploads are reversible): `comfy_library_collections` → reuse or create a
   ≤2-word `collection:<Theme>` → print the upload manifest (files,
   collection, tags) → `comfy_library_upload` each winner (mp4s + jpgs; loose
   tags `[mood, color(s), motion, loop]`) → report media ids (one
   `comfy_library_delete(media_ids, confirm=True)` undoes the batch).
   Copying to `/tank/projection-mapping` stays ask-first.

Report every local path, seed, media id, and which clips are true cycles
(img2video/animate_still) vs crossfade-wrapped.
