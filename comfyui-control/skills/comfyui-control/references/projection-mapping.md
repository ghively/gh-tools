# Projection-mapping content (research-backed, 2026-07)

Guidance for batch-generating stills and GIF/video loops to feed a projection
rig (Gene's: vpt9 control-panel, 1080p projector, gh-nvidia renders).

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
  resampling artifacts. Generate at an SDXL 16:9-ish bucket (**1344×768**),
  then 4x-upscale and downscale/crop to 1920×1080, or let the mapping
  software scale the 4x master.
- Loops: VJ standard is **10–60s seamless**; 30fps video, or 12–18fps GIF.
- Prefer mp4/h264 for the player when possible; GIFs when the tool/workflow
  wants them (vpt9 accepts both).

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

## Batch workflow (the /comfy-projection command automates this)
1. `comfy_batch(prompt, count=4-8, width=1344, height=768)` — seed variations.
2. Review; `comfy_upscale` winners (→ 5376×3072 master, downscale to 1080p).
3. For loops: `comfy_txt2video(768×512 or 704×448, 97-121f)` per theme, then
   `comfy_to_gif(mp4, fps=15, width=960)` (crossfade loop).
4. Drop results where the mapping rig picks them up (e.g. /tank/projection-mapping).

## Tagging + the vpt9 media library (verified live 2026-07-16)
The vpt9 control-plane library (`http://192.168.0.214:8080/api/media`) stores
tags **inside the files** as XMP `dc:Subject` — embed keywords BEFORE upload
and the server reads them automatically (verified round-trip):
```bash
exiftool -overwrite_original -XMP-dc:Subject=neon -XMP-dc:Subject=loop file.gif
curl -X POST http://192.168.0.214:8080/api/media \
     -H "X-File-Name: neon-loop.gif" --data-binary @file.gif
```
(python: `subprocess.run(["exiftool","-overwrite_original",*[f"-XMP-dc:Subject={t}" for t in tags],path])`)
- Alternative: skip exiftool and pass `-H "X-Media-Tags: neon, loop"` — the
  server writes them into the file for you. DELETE `/api/media/{id}` removes.
- Tag convention used for the demo set: `<style>, <subject>, loop, demo`.
- **The library rejects PNG** — convert stills to jpg before upload
  (`ffmpeg -i in.png -q:v 2 out.jpg`); webm tags stay index-only. Embed into
  BOTH the gif and mp4 on disk so the tank copies stay portable.

Sources: [HeavyM video-mapping loops](https://www.heavym.net/video-mapping-loops/),
[Chameleon Interactive content tips](https://chameleon-interactive.com/2024/10/31/how-projection-mapping-and-led-screens-handle-content-tips-for-creating-eye-catching-visuals/),
[crazyartist VJ formats/FPS](https://crazyartist.net/en/fps-resolution-and-formats-everything-you-need-to-know-about-vj-loops/),
[Video Mapping Store — seamless looping](https://videomapping.store/vj/seamless-looping/),
[AI projection-mapping workflow (Medium)](https://medium.com/@_ifnull/projection-mapping-with-ai-my-end-to-end-workflow-19781ddd4fcf),
[GIF format limits](https://en.wikipedia.org/wiki/GIF#Animation_formats).
