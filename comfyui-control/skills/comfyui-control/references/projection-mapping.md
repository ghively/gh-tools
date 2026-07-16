# Projection-mapping content (research-backed, 2026-07)

Guidance for batch-generating stills and GIF/video loops to feed a projection
rig (Gene's: vpt9 control-panel, 1080p projector, gh-nvidia renders).
Read together with `projection-styles.md` (style arsenal + motion map) and
`texture-research.md` (the owner's methodology doc: sampler matrix, anti-trope
prompting, loop taxonomy, Electric Sheep lore).

## The physics that drive every choice
A projector ADDS light — **pure black = the projector is off on that surface**.
So in a dark venue, content on a true-black background self-masks: only the
bright shapes land on the object. That's why the canonical mapping look is
bright, bold motion on black.

## Style traits that read well (dark venue — the default)
- **Bold shapes, high contrast, saturated brights on true black** (`#000`).
  Avoid fine gradients and subtle textures — they band and vanish.
- Geometry that hugs edges: outlines, wireframes, scan-lines, particle bursts,
  liquid metal, neon tubes — content that emphasizes the surface's structure.
- No small text, no intricate detail — it smears on 3D surfaces and distance.
- Motion should read at a glance: sweeps, pulses, orbits, cascades.
- **Outdoor / lit surfaces invert the rule**: dark art disappears — go
  high-key bright, photographic/cinematic, and match the surface tone.

## Delivery specs (1080p rig)
- Deliver at the projector's EXACT resolution — **1920×1080** — to avoid
  resampling artifacts. `comfy_master_still(image)` does the whole finishing
  pass: 4x upscale → scale-to-cover + center-crop to exactly 1920×1080 → jpg
  (library-ready). Generate at an SDXL 16:9-ish bucket (**1344×768**) first;
  `hires_scale=1.5-2.0` on comfy_txt2img adds the latent-space hires-fix
  (upscale latent → low-denoise re-sample → tiled decode) when the master
  needs more real detail rather than just pixels.
- Loops: VJ standard is **10–60s seamless**; 30fps video, or 12–18fps GIF.
- **mp4-first**: `comfy_loop_video(mp4)` → seamless forward-only loop as
  h264 yuv420p (~40x smaller than GIF, the library's required pixel format);
  gif only when the workflow wants it (`format="both"`).

## Why black-on-bright content is ALSO the ideal GIF payload
GIF = 256 colors/frame. Smooth gradients dither and band; but bold saturated
shapes on flat black use a tiny palette — sharp result, small file. Rules:
- 12–15fps is plenty for abstract loops; bayer dithering (the comfy_to_gif
  default) beats error-diffusion for flat-color content.
- **Seamlessness**: `comfy_to_gif(...)` (crossfade default) makes ANY clip a
  forward-only seamless loop — the tail blends into the head, no reversal
  (owner preference: never boomerang/palindrome).
  Prompting "seamless looping motion, static camera" helps the raw clip too.
- GIF at full 1920 wide gets heavy (tens of MB); 960×540 GIFs scale fine on a
  1080p projector for abstract content. Go full-res mp4 when quality matters.

## Prompt template (stills, SDXL or SD3.5)
> {SUBJECT — e.g. "flowing liquid chrome ribbons", "geometric neon
> wireframe tunnels", "cascading particle waterfalls"}, glowing vivid
> {COLORS} on a pure black background, high contrast, bold shapes, clean
> edges, VJ loop aesthetic, projection mapping visual, centered composition
Negative: `gray background, washed out, low contrast, photo, text, watermark,
noise, film grain`

## Prompt template (LTXV loops)
> {SUBJECT} glowing {COLORS} against a pure black void. The shapes
> {CYCLICAL MOTION — pulse rhythmically / rotate slowly / flow in waves}.
> Static camera, seamless looping motion, high contrast, bold graphic
> shapes, VJ projection visual, sharp and clean.

## Seamless cycles: comfy_img2video (FLF) — the loop workhorse
`comfy_img2video(image, prompt, loop=True)` pins the input still as BOTH the
first and last frame via LTXV keyframe guides — a mathematically closed cycle,
no crossfade ghosting. This unlocks the best style-control pipeline:
**SDXL still (checkpoint + LoRA + palette) → img2video → seamless mp4.**
- Prompt rule (the Cassidy Curtis / Electric Sheep lesson — loops must match
  velocity, not just position): describe motion that is MID-CYCLE at start
  and end — "rotates continuously", "circulates in a constant current" —
  never "begins to…" or progressive verbs (unfold/grow/bloom break closure).
- `strength` 0.7–1.0 tunes guide anchoring (1.0 can over-anchor → near
  static; default 0.9). If a cycle won't converge: `loop=False` +
  `comfy_loop_video` crossfade is the honest fallback.

## Parametric motion: comfy_animate_still (no GPU)
Turns any still into an exactly-looping clip by driving one parameter around
a closed cycle (frame N ≡ frame 0 by construction): rotate/rotate_ccw (full
revolutions), zoom_in/zoom_out (breathing log-zoom), drift (mirror-tile
scroll — doubles as a seamless-tiling texture generator), pulse
(brightness/saturation breathe), kaleido (mirror symmetry + spin), tunnel
(perpetual zoom, crossfade-wrapped — SELF-SIMILAR sources only). Motion↔style
map in projection-styles.md. Never re-crossfade these outputs.

## Multi-face texture sets (the /comfy-texture-set command)
For a "3D effect" on mapped objects (cube faces, facade zones): generate ONE
master texture field, then derive faces as `comfy_img2img(master, base
prompt + per-face modifier, denoise≈0.5)` — a coherent family with distinct
faces (master-canvas + crops keeps grain/stroke/motion language consistent).
Finish each face with `comfy_master_still` (square for cubes, 16:9 for
facades). **Phase-lock**: animate every face with the same duration+fps →
identical frame count → the faces loop in sync on the rig.

## Tiling seams
No core node guarantees seamless spatial tiling. Either use
`comfy_animate_still(motion="drift")`'s mirror tile (seamless by
construction), or verify/repair: wrap-offset the image by 50% in both axes,
inpaint the visible seam cross with `comfy_inpaint`, offset back.

## Two loop pipelines — pick by INTENT, not by "better" (owner doctrine)
- **Painterly/abstract washes ("v1 vibe")**: `comfy_txt2video` +
  `comfy_loop_video` — pure t2v produces flowing, texture-like, ambient
  motion (fields, billows, washes). The owner explicitly likes this
  aesthetic; it is the right tool for mood/atmosphere content. The full
  100-clip vibe-library was made this way — the COMPLETE recipe (templates,
  100 subject+palette pairs, seeds) ships with the plugin in
  `references/v1-vibe-recipes.md`; the on-host record is
  `/tank/projection-mapping/demos/manifest.json`.
- **Composed subjects (FLF)**: SDXL still (LoRA+palette) →
  `comfy_img2video(loop=True)` — a *thing* with strong composition
  (a stag, a medallion, a stained-glass owl) in a mathematically closed
  cycle. Demos in `/tank/projection-mapping/demos-flf/`, library tag `flf`.
A good show programs BOTH: t2v washes as the ambient floor, FLF subjects as
the peaks (see the energy-ladder doctrine in projection-styles.md).

## Batch workflow (the /comfy-projection command automates this)
1. `comfy_batch(prompt, count=4-8, width=1344, height=768)` — seed variations.
2. Review; `comfy_master_still` winners (4x upscale + exact 1080p jpg).
3. For loops: pick the pipeline by intent (above).
4. Auto-deliver winners to the vpt9 library (below); /tank copies ask-first.

## Tagging + the vpt9 media library (rules v2, verified live 2026-07-16)
The vpt9 control-plane library (`library_url` in config, currently
`http://192.168.0.214:8080`) stores ALL metadata **inside the files** as XMP
`dc:Subject` keywords. **Use the curated tools:**
- `comfy_library_collections()` — existing collections + counts + top loose
  tags. Always check first; REUSE collections.
- `comfy_library_upload(file, collection, tags, name)` — validates format,
  normalizes the collection name, sends `X-File-Name` + `X-Media-Tags` (the
  server embeds the XMP itself — no exiftool needed). Returns the media id.
- `comfy_library_delete(media_ids, confirm=True)` — one confirmed call
  reverses a whole batch.

Rules the tools enforce (and you must respect when naming):
1. **Collections** — `collection:` prefix + Title Case **1-2 word** name
   (e.g. `collection:Stained Glass`) → FOLDERS in the library UI. Every file
   needs ≥1 collection.
2. **Loose tags** — 2–5 plain descriptors ("loop", "calm", "gold").
   Demo-set convention: `collection:Vibe Library` + `collection:<Style>` +
   loose `[mood, color(s), motion, loop]`.
- Formats: **only mp4 (H.264 yuv420p), gif, jpg** — never PNG or WebM.
  comfy_master_still makes the jpg; comfy_loop_video makes the mp4.
- Display names descriptive, never `output_003`.
- Uploads are reversible → batch uploads may run WITHOUT asking (print a
  manifest of files/collection/tags first, report media ids after); deletes
  stay confirm-gated.

Manual fallback (no MCP): `exiftool -XMP-dc:Subject="collection:Fire" ...`
then `curl -X POST .../api/media -H "X-File-Name: name.gif" --data-binary
@file` (busybox wget corrupts uploads), or skip exiftool with
`-H "X-Media-Tags: collection:Fire, warm, loop"`.

Sources: [HeavyM video-mapping loops](https://www.heavym.net/video-mapping-loops/),
[Chameleon Interactive content tips](https://chameleon-interactive.com/2024/10/31/how-projection-mapping-and-led-screens-handle-content-tips-for-creating-eye-catching-visuals/),
[crazyartist VJ formats/FPS](https://crazyartist.net/en/fps-resolution-and-formats-everything-you-need-to-know-about-vj-loops/),
[Video Mapping Store — seamless looping](https://videomapping.store/vj/seamless-looping/),
[AI projection-mapping workflow (Medium)](https://medium.com/@_ifnull/projection-mapping-with-ai-my-end-to-end-workflow-19781ddd4fcf),
[GIF format limits](https://en.wikipedia.org/wiki/GIF#Animation_formats).
