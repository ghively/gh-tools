---
description: Generate a coherent multi-face texture set for 3D-effect projection mapping (master canvas → per-face variants → phase-locked motion), auto-delivered to the vpt9 library
argument-hint: <theme> [faces=4] [cube|facade] [motion]
---

Build a multi-face projection texture set for: **$ARGUMENTS**

Read `references/projection-mapping.md` (multi-face section),
`references/projection-styles.md`, and `references/texture-research.md`
first. The goal: N stylistically-coherent but distinct textures that map
onto the faces/zones of one 3D object so the object reads as a single
sculpted thing (the "3D effect"). Principle: **master canvas + crops/
variants** — one texture field's grain, stroke, and motion language shared
by every face.

1. **Scope**: theme, face count (default 4; cubes often want 5–6), target
   shape (cube → square faces 1024×1024; facade → 16:9 1920×1080), optional
   motion. Ask only if the theme is missing.
2. Pick the style LoRA + trigger, ONE palette for the whole set (the
   per-clip color rule applies per SET here — faces must match each other),
   and the five-part prompt structure from texture-research.md (surface
   logic → mark-making → lighting → motion rule → palette discipline).
3. **Master field**: `comfy_txt2img` (theme + LoRA + explicit palette;
   `hires_scale=1.5` if fine detail matters). Show it; confirm before
   spending N face runs.
4. **Faces**: for each face, `comfy_img2img(master, base prompt + face
   modifier, denoise≈0.5, same checkpoint/LoRA/cfg, fresh seed)`. Face
   modifiers differentiate roles: "dense core pattern" / "radiating
   variant" / "sparse accent lines" / "large focal medallion" / "fine
   border detail". Identical palette words in every prompt.
5. **Master each face**: `comfy_master_still(face, width=height=1024)` for
   cubes, `1920×1080` for facades. Show the set as a family.
6. **Motion** (optional): `comfy_animate_still` on every face with the SAME
   duration + fps — identical frame counts loop PHASE-LOCKED on the rig,
   which is what sells the 3D effect. Suggested: drift or pulse at
   intensity 0.4–0.8 for ambience; vary the motion per face only if asked.
   True-cycle outputs — never re-crossfade.
7. **Auto-deliver**: `comfy_library_collections` → reuse/create a ≤2-word
   `collection:<Theme>` → print the upload manifest → `comfy_library_upload`
   every face (jpgs + motion mp4s, shared loose tags + a face tag like
   "face-1") → report media ids. /tank copies ask-first.

For breeding a better set from a good one, use /comfy-projection's evolve
mode on the master, then re-derive faces.

Report: master seed/path, each face's seed/path/media id, and the
phase-lock parameters (duration, fps, frame count).
