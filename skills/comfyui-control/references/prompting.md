# Per-model prompt engineering (this install)

Different model families want *different prompt languages*. Match the style to
the checkpoint or results suffer more than any sampler tweak can recover.

## SD3.5-medium (`sd3.5_medium.safetensors`) — default
- **Write natural language, full sentences.** The T5-XXL encoder parses grammar
  and spatial relations: "a red cube on top of a blue sphere, to the left of a
  green cone" actually works. Tag soup wastes this model.
- Long prompts are fine (T5 handles ~300+ words); front-load the subject.
- **Renders text well**: put desired text in double quotes — `a neon sign that
  says "OPEN LATE"`.
- Keep CFG **4.5–5.5**, steps 20–28. Negatives are weak at low CFG — prefer
  positive phrasing ("sharp focus" over negating "blurry"); keep the negative
  short or empty.
- Resolutions: 1024×1024, 1152×896, 1344×768 (and portrait swaps).

## SDXL base (`sd_xl_base_1.0.safetensors`)
- **Tag/phrase style**: `subject, medium, style, lighting, color, mood, quality
  boosters` — e.g. `portrait of an old fisherman, oil painting, dramatic rim
  lighting, muted palette, highly detailed`.
- Negatives genuinely matter: `worst quality, low quality, jpeg artifacts,
  deformed, watermark, text` is a solid default.
- CFG **6–8**, steps 25–30. Use SDXL's native buckets: 1024×1024, 1152×896,
  1216×832, 1344×768, 1536×640 (+ portrait swaps). Off-bucket sizes degrade.

## Installed LoRAs (all SDXL — do NOT stack onto SD3.5)
| File | Style | Trigger |
|---|---|---|
| `sdxl-simple-icons.safetensors` | minimal flat icons (verified live) | include "icon"/"icons" in prompt |
| `IconsRedmond.safetensors`, `IconsRedmondV2-Icons.safetensors` | app-icon style | "icons" (Redmond family trigger) |

Use `loras="file.safetensors:0.8"`; 0.8–1.0 strength for icon work, pair with
SDXL checkpoint + simple flat-design language. Check a Civitai LoRA's
`trainedWords` (comfy_model_search source=civitai) before use — triggers are
per-LoRA.

## LTX-Video (`ltx-video-2b-v0.9.5.safetensors`)
- **Write a shot description, not tags** — one flowing paragraph, present
  tense: subject → what it does → camera move → lighting/mood → detail level.
  Short prompts produce mush; aim for 3–6 sentences.
  > "A lone astronaut walks slowly across a red desert plain, dust swirling
  > around their boots. The camera tracks alongside at hip height. Golden-hour
  > light casts long shadows; heat haze shimmers on the horizon. Cinematic,
  > highly detailed, 35mm."
- Describe ONE continuous shot — scene cuts confuse it.
- CFG ~**3.0**, steps 25; negative: `low quality, worst quality, deformed,
  distorted, watermark`.
- Motion words matter: "slowly pans", "orbits", "handheld", "static shot".

## General
- Seed 0 = random; reuse a reported seed + same settings to iterate on one
  composition (change only the words you must).
- comfy_batch for 4–8 seed variations, then upscale the winner
  (comfy_upscale → 4x-UltraSharpV2).
- Every output PNG carries its full recipe — comfy_png_workflow /
  comfy_rerun(prompt=...) to remix any earlier result without rebuilding.
