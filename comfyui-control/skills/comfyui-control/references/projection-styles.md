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
| + the 3 icon LoRAs | flat icons | "icons" | 0.8–1.0 |

## Worth downloading when a job calls for it (Civitai, SDXL, triggers verified)
Neon Outline `ral-neotlns` · Glitch Style `ral-glydch` · Aether Glitch (VHS,
"vhs glitch") · Chrome Style `ral-chrome` · Iridescent SDXL · Synthwave-Style
`synthworld` · Dark Particles `ais-darkpartz` · Glowing & Light Particles ("glowing",
"light particles"; also covers SD3.5) · Dissolve `dissolve` · Smoke `dvr-smoke`
/ `Smoke_XL` · Line Art + Flat Colors (`lineart, flat colors`, w 1.0–2.0) and
Minimalist Vector Art (`ArsMJStyle`, w 1.2–1.5) for clean vector output.
NOTE: no tunnel/infinite-zoom LoRA exists — that's an animation-layer effect.

## Checkpoints ranked for this work (none installed yet — comfy_model_search)
1. **DreamShaper XL** — the abstract/surreal workhorse (corroborated twice).
2. **ZavyChromaXL** — punchy saturated neon-cinematic; ideal for this exact look.
3. **Juggernaut XL** — photoreal base; use for structural/facade content.
`sd_xl_base_1.0` (installed) works — finetunes mostly buy color punch + coherence.

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
- **Seamless loops, best → good**:
  1. *FLF2V*: image-to-video with the SAME still as first and last frame +
     cyclical motion prompt (explore `LTXVAddGuide`/`LTXVImgToVideo` via
     comfy_nodes — not yet live-tested here).
  2. *Palindrome*: `comfy_to_gif(mp4, palindrome=True)` — verified, works on
     anything, doubles length.
  3. Prompt-only ("seamless looping motion") — helps, doesn't guarantee.
- **Pipeline that beats txt2video for style control**: SDXL still (checkpoint
  + LoRA stack, 1216×832) → LTXV image-to-video → palindrome GIF/mp4.
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
