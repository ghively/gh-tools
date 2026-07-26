# Projection/VJ style arsenal — models, LoRAs, prompt recipes (researched 2026-07)

The community verdict: **no purpose-built "VJ checkpoint" exists** — the look is
assembled from an artistic checkpoint + style LoRA + the black-background
keyword cluster. **SDXL is the workhorse** for this: FLUX renders "too smooth
and polished" for stylized/glitch aesthetics and has a thinner LoRA ecosystem;
SD3.5 has no community champion for abstract work. (Corroborated:
[SDXL vs FLUX](https://stable-diffusion-art.com/sdxl-vs-flux/),
[3-way comparison](https://willitrunai.com/blog/flux-vs-sdxl-vs-sd35-comparison).)

## Installed style LoRAs (all SDXL — pair with sd_xl_base or a finetune below)

| File (in loras/) | Style | Trigger | Strength |
|---|---|---|---|
| `ral-frctlgmtry-sdxl` | fractal geometry | `ral-frctlgmtry` | 0.8–1.0 |
| `neon-night-sdxl` | neon city/objects glow | `Neon Night page` | 0.7–1.0 |
| `wireframe-hologram-sdxl` | wireframe/holographic | `noc-wfhlgr` | 0.75–1.2 |
| `sacred-geometry-sdxl` | mandala/sacred geometry | `sacred geometry` | 0.8–1.0 |
| `psychedelic-noir-sdxl` | dark psychedelic | (none needed) | 0.6–0.9 |
| `particles-style-sdxl` | glowing particles | `ais-particlez` | 0.8–1.0 |
| `dissolve-style-sdxl` | particle disintegration | `ral-dissolve` | 0.8–1.0 |
| `liquid-water-flow-sdxl` | flowing water/fluid | `watce` | 0.7–1.0 |
| `art-nouveau-sdxl` | art nouveau ornament | `ArsMJStyle, Art Nouveau` | 0.8–1.0 |
| `stained-glass-sdxl` | stained glass | `Stained Glass Portrait` | 0.8–1.0 |
| `ink-wash-sdxl` | sumi-e ink wash | `ink-style, ink_wash_painting` | 0.7–1.0 |
| `baroque-fantasy-sdxl` | baroque gold fantasy | `Baroque Fantasy Realism` | 0.7–1.0 |
| + the 3 icon LoRAs | flat icons | "icons" | 0.8–1.0 |

## Worth downloading when a job calls for it (Civitai, SDXL, triggers verified)
Neon Outline `ral-neotlns` · Glitch Style `ral-glydch` · Aether Glitch (VHS,
"vhs glitch") · Chrome Style `ral-chrome` · Iridescent SDXL · Synthwave-Style
`synthworld` · Dark Particles `ais-darkpartz` · Glowing & Light Particles ("glowing",
"light particles"; also covers SD3.5) · Dissolve `dissolve` · Smoke `dvr-smoke`
/ `Smoke_XL` · Line Art + Flat Colors (`lineart, flat colors`, w 1.0–2.0) and
Minimalist Vector Art (`ArsMJStyle`, w 1.2–1.5) for clean vector output.
From the owner's texture research (texture-research.md has the comparison
table): add-detail-xl (detail dial, ± weights) · Controllable Vector Art XL
(`vector` + control terms) · Papercut SDXL (`papercut`) · Stylized
Silhouette XL · Negative XL (negative-strength).
NOTE: no tunnel/infinite-zoom LoRA exists — use
`comfy_animate_still(motion="tunnel")` on a self-similar still instead.

## Checkpoints ranked for this work (none installed yet — comfy_model_search)
1. **DreamShaper XL** — the abstract/surreal workhorse (corroborated twice).
2. **ZavyChromaXL** — punchy saturated neon-cinematic; ideal for this exact look.
3. **Juggernaut XL** — photoreal base; use for structural/facade content.
`sd_xl_base_1.0` (installed) works — finetunes mostly buy color punch + coherence.

## Style families beyond neon/scifi (prompt recipes — all on the black-bg cluster)
The bright-on-black physics is style-agnostic: swap neon for gold, fire, ink,
or glass and it projects just as well. Verified/no-LoRA-needed recipes (SDXL
renders these natively; SD3.5 takes the same ideas as sentences):

| Family | Prompt core (+ keyword bible) | LoRA when installed |
|---|---|---|
| Ornamental gold | `ornate golden baroque filigree ornament, glowing gold on black, intricate scrollwork` | Baroque Fantasy Realism / Gold Filigree `dskgold_filigree` |
| Fire & embers | `swirling flames and rising embers, orange and gold fire on black background` | (none needed — native) |
| Ink & sumi-e | `black ink wash blooming in water, white background inverted OR glowing white ink on black` | Ink wash `ink-style, ink_wash_painting` |
| Water/fluid | `flowing liquid ribbons, caustic light patterns, deep blue and cyan on black` | Liquid Water Flow `watce` |
| Stained glass | `stained glass window panel, glowing jewel tones, black leading` — projection makes it LITERALLY glow | Stained Glass `Stained Glass` |
| Botanical | `time-lapse blooming flowers, bioluminescent petals, glowing vines on black` | (native; vines/growth read great on facades) |
| Art nouveau | `art nouveau ornament, flowing organic curves, gold and emerald on black` | Art Nouveau `ArsMJStyle, Art Nouveau` |
| Dissolve/decay | `figure dissolving into glowing particles` — transition loops | Dissolve `ral-dissolve` (26k dl — the community favorite) |
| Aurora/atmosphere | `aurora borealis ribbons, ethereal light curtains, green and violet on black` | (native) |
| Kaleidoscope | `symmetrical kaleidoscope pattern, radial symmetry` + sacred-geometry LoRA | `sacred geometry` (installed) |
| Fractal flame | `luminous twisting elastic filaments, wispy glowing smoke tendrils, self-similar curling ribbons of light, soft glow falloff, no clipped highlights, structural color gradients on pure black` — the Electric Sheep look (texture-research.md appendix); motions: rotate/drift/tunnel | `ral-frctlgmtry` (installed) |

## Organic textures & mood/scene-setting (2026-07-16)
The bright-on-black physics extends to organic matter — these families SET
SCENES AND MOODS rather than punch (cross-ref texture-research.md's photoreal
pipeline for lit-surface material plates: stone, plaster, bark, moss,
oxidized metal — DPM++ 2M, add-detail-xl low weight, "texture plate, no
focal object", low-denoise refinement):

| Family | Prompt core (+ keyword bible) | Motion (steady-state) | LoRA |
|---|---|---|---|
| Smoke & incense | `curling incense smoke, soft volumetric wisps on black` | billows and curls in place | dvr-smoke/Smoke_XL (download) |
| Cloud / nebula | `deep space nebula, billowing cloud banks, volumetric light` | drifts in a constant current | (native; pair with drift motion) |
| Water caustics | `underwater caustic light patterns, god rays, rippling refractions` | ripples in a continuous cycle | `watce` (installed) |
| Bioluminescent flora | `glowing mushrooms and vines, bioluminescent forest floor` | pulses gently in rhythm | (native) |
| Mycelium / network | `branching mycelium network, glowing filament web spreading held steady` | light travels along the threads | `ais-particlez` (installed) |
| Jellyfish / deep sea | `translucent jellyfish drifting, trailing luminous tendrils` | drifts and undulates in place | (native) |
| Silk / fabric | `flowing silk ribbons suspended, soft sheen` | undulates in a constant wave | (native) |
| Murmuration | `starling murmuration, thousands of particles flowing as one form` | circulates in a closed orbit | `ais-particlez` |
| Growth held steady | `frost crystals / vines / coral, fully grown, glinting` | light sweeps across the structure | (native — never prompt "growing": progressive verbs break loops) |

**Mood doctrine**: ambient scene loops are the opposite energy pole from peak
VJ hits — slow motion rates, `comfy_animate_still` intensity 0.3–0.6, longer
durations (20–60s), drift/pulse over zoom/rotate. Palette psychology: warm
ember = intimate; deep blue/teal = calm/underwater; violet+green aurora =
otherworldly; gold filigree = sacred/ornate; desaturate toward jewel tones
for calm, saturate for energy. Program a set as an **energy ladder** —
ambient wash → breathing accent → pulse → peak — so the rig can build a show
arc, not play disconnected clips.

**Motion rule for loops (learned the hard way 2026-07-16): STEADY-STATE ONLY.**
Progressive verbs (unfold, grow, bloom, disperse, disintegrate, reveal) make
the end frame structurally different from the start — no crossfade can hide
it. Phrase motion as a held cycle: "rotates in place", "breathes gently",
"circulates in a constant current", "light travels along the curves in a
continuous cycle", "continuously sheds sparks while the form holds steady".
Per family: gold *light travels along scrollwork*; fire *flickers in constant
rhythm*; ink *billows and curls in place*; water *circulates steadily*; glass
*light sweeps across panes*; dissolve *sheds particles while the form holds*.
Always static camera + one cyclical motion.

**Color rule (owner feedback): vary palettes per clip, never per style.** A
fixed style palette (cyan+magenta everywhere) reads as monotone purple across
a set. Assign each clip its own palette from the full wheel — including
unexpected ones (blue flame, emerald fire, ruby-and-gold filigree) — and say
"vivid saturated" explicitly; LTXV desaturates timid color language.

## The keyword bible (black-background/high-contrast cluster)
Load-bearing positives: **`black background`** (belt-and-suspenders:
`fully black background, background hex 000000`) · **`OLED wallpaper` /
`amoled`** · `neon` · `glowing` · `geometric` · `bioluminescent` · `UV
blacklight` — plus the LoRA's trigger token. One glowing subject, centered.
Negatives: `white background, grey background, bright background, gradient
background, washed out, low contrast, text, watermark, photo, film grain`.
For vector-clean output, don't fight the model — use a line-art/vector LoRA
with `vector art, flat design, clean lines, minimalist`.

## Video-loop recipes (12GB card)
- **LTXV prompting rules** (corroborated across the official guide + 3 others):
  camera instruction in the FIRST sentence ("slow continuous push in" /
  "STATIC SHOT // NO CAMERA MOVEMENT" to kill drift); motion described
  literally + chronologically ("the ribbons rotate clockwise, slowly
  accelerating" — never "gracefully/hypnotically"); ≤200 words; ~1 action per
  2–3s; 768×512 is its sweet spot.
- **Seamless loops — OWNER PREFERENCE (2026-07-16): forward-only, never
  boomerang.** Best → good:
  1. *FLF true cycle* (IMPLEMENTED): `comfy_img2video(image, prompt,
     loop=True)` pins the still as BOTH first and last frame via LTXV
     keyframe guides — a real cycle, no fade ghosting. Steady-state motion
     prompt required (motion mid-cycle at start/end, never "begins to...").
  2. *Parametric* (IMPLEMENTED): `comfy_animate_still` — mathematically
     exact loops from any still, no GPU (see motion table below).
  3. *Crossfade* (the default for arbitrary clips): `comfy_loop_video(mp4)`
     → seamless yuv420p mp4 (+gif on request); `comfy_to_gif(mp4)` for
     GIF-only. Tail blends into head; output shortens by the fade.
     `interpolate_fps=` adds loop-aware cadence smoothing (slow).
  4. Prompt-only ("seamless looping motion") — helps, doesn't guarantee.
  Palindrome (`loop="palindrome"`) exists but the owner dislikes the
  forward-backward look — don't use it unless asked. NEVER re-crossfade a
  true cycle (img2video loop=True / animate_still): use
  comfy_to_gif(loop="none") on those.
- **Pipeline that beats txt2video for style control** (IMPLEMENTED): SDXL
  still (checkpoint + LoRA stack, 1216×832) → `comfy_img2video(loop=True)`
  → seamless mp4.
- **Parametric motion ↔ style family map** (`comfy_animate_still`; all loops
  exact-cycle except tunnel):

| Motion | Best content | Notes |
|---|---|---|
| tunnel | sacred-geometry / mandala / fractal flame | closes the "no tunnel LoRA" gap — crossfade-wrapped, SELF-SIMILAR sources only (generic images ghost) |
| drift | nebula, clouds, water, smoke, texture fields | mirror-tile scroll — also makes any texture seamless-tiling |
| rotate / rotate_ccw | radial/kaleidoscopic compositions, mandalas | integer revolutions |
| kaleido | anything — instant symmetry | mirror tile + spin |
| zoom_in / zoom_out | centered glowing subjects | breathing log-zoom, closed cycle |
| pulse | neon, fire, bioluminescence | brightness/saturation breathe — the ambient workhorse |

  Steady-state FLF prompt lines that work: "the pattern breathes and returns
  to its original arrangement", "light completes one full circuit along the
  curves", "filaments swirl in one continuous cycle".
- File-size reality (measured): 4s loop = **1.2MB mp4 vs 46MB GIF** at 960px.
  GIF only when the workflow needs it; mp4 (h264) otherwise.
- Real-time AI VJ (TouchDesigner + StreamDiffusion) wants a 3090/4090 —
  on the 3060, pre-rendered loops are the right call (corroborated).

## Structure-aware / facade content (advanced)
Practitioner workflow ([Medium](https://medium.com/@_ifnull/projection-mapping-with-ai-my-end-to-end-workflow-19781ddd4fcf)):
photo from the projector's position + high-contrast B/W alignment image →
ControlNet-style conditioning (strength ~0.95 alignment / ~0.8 content) →
mask early → export at exact projector res. Outdoor/lit facades invert the
palette rule: go high-key bright, dark art disappears.

Key sources: [Apatero SDXL roundup](https://apatero.com/blog/best-sdxl-models-checkpoints-2025) ·
[Civitai style-LoRA pages](https://civitai.com/models/269592) (triggers verified per page) ·
[LTX prompt guide](https://ltx.io/blog/ltx-2-3-prompt-guide) ·
[stablediffusionweb prompt DB](https://stablediffusionweb.com/prompts/black-oled-background) ·
[AnimateDiff closed_loop docs](https://github.com/continue-revolution/sd-webui-animatediff/blob/master/docs/how-to-use.md).
