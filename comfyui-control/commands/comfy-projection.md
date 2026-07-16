---
description: Batch-generate projection-mapping visuals (stills + seamless GIF/video loops) for a 1080p rig
argument-hint: <theme/vibe, e.g. "neon geometric pulses, cyan and magenta"> [count] [stills|loops|both]
---

Batch-generate projection-mapping content for: **$ARGUMENTS**

Read the comfyui-control skill's `references/projection-mapping.md` AND
`references/projection-styles.md` FIRST and follow their specs exactly. Match
the theme to a style LoRA from the installed arsenal (fractal, neon, wireframe,
sacred-geometry, psychedelic) and use its trigger word + the keyword bible
(`black background, background hex 000000, OLED wallpaper` cluster). Then:

1. **Scope**: from the arguments take the theme, count (default 4), and mode
   (default both). Ask only if the theme is missing. Venue matters: assume a
   dark venue (bright-on-black) unless the user says the surface is lit/outdoor
   (then go high-key bright instead).
2. `comfy_status` — VRAM headroom; warn that loops take minutes each.
3. **Stills**: `comfy_batch` with the reference's still template filled with
   the theme, `width=1344, height=768` (16:9 bucket), SDXL or SD3.5 per the
   prompting guide. Show thumbnails/paths + seeds.
4. **Loops**: for each of 2–3 motion variants of the theme, `comfy_txt2video`
   (768×512, 97 frames, cfg 3.0, static-camera seamless-motion prompt from the
   reference), then `comfy_to_gif(mp4, fps=15, width=960, palindrome=True)`
   for a seamless boomerang GIF. Offer full-res mp4 for quality-critical use.
5. **Finish**: offer to 4x-upscale the winning stills (1080p master), copy the
   final set to `/tank/projection-mapping`, and tag + upload to the vpt9 media
   library per projection-mapping.md's tagging section (exiftool XMP
   `dc:Subject` embed → POST /api/media; stills must be converted png→jpg
   first). Ask before copying/uploading.

Report every local path, seed, and which variants loop seamlessly vs merely
repeat.
