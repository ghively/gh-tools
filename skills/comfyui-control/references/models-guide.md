# Model guide — what runs on this box, what to download, how to drive each

Fit ratings are for THIS host: RTX 3060 **12GB VRAM**, 24g container RAM,
`--lowvram`. ✅ comfortable · ⚠️ fits with care (GGUF quant / offload / patience)
· ❌ don't bother. Download via `comfy_model_search` → `comfy_model_download`
(**.safetensors/.gguf only** — never pickle formats). Knowledge current to
early 2026 — search before downloading anything not listed.

## Image models

| Family | Fit | Notes |
|---|---|---|
| **SD1.5** | ✅ easy | 512×512 native, 2GB. Ancient but the biggest LoRA/finetune ecosystem (Civitai). Tag-style prompts, cfg 7, steps 25. CheckpointLoaderSimple, all-in-one. |
| **SDXL** (installed) | ✅ | 1024 buckets, tag-style + negatives, cfg 6–8. Fine-tunes (Juggernaut XL, RealVisXL, DreamShaper XL) usually beat base — same wiring, drop-in. Turbo/Lightning/Hyper variants: 4–8 steps, cfg 1–2, great for fast drafts. |
| **SD3.5-medium** (installed) | ✅ | Natural-language prompts, text rendering, cfg 4.5–5.5. Needs TripleCLIPLoader (auto-wired here). SD3.5-**large**: ❌ (needs ~18GB+ unquantized; GGUF Q4 ⚠️ borderline). |
| **FLUX.1-schnell / dev** | ⚠️ best-quality path for this card | 12B DiT. Full fp16 won't fit — use **GGUF Q4_K_S–Q6_K** (`city96/FLUX.1-dev-gguf` etc.) via `UnetLoaderGGUF` + DualCLIPLoader(clip_l + t5xxl fp8, type flux) + `ae.safetensors` VAE (**already in vae/**). schnell: 4 steps, cfg 1. dev: 20 steps, guidance 3.5 (FluxGuidance node, cfg 1). Superb prompt following + text. Expect ~1–2 min/image. |
| **Pixart Sigma / Lumina 2** | ✅ | Lightweight DiTs, natural-language prompts. Niche but cheap. Core loader support (CLIPLoader type pixart/lumina2). |
| **Qwen-Image / HiDream** | ⚠️/❌ | 20B-class; GGUF Q3/Q4 technically loads but slow + RAM-hungry — not worth it on 12GB. |
| **Upscalers** (UltraSharpV2 installed) | ✅ | ESRGAN-class, ~150MB. Others: 4xNomos8kDAT (photos), RealESRGAN family. All via comfy_upscale. |

## Video models

| Family | Fit | Notes |
|---|---|---|
| **LTX-Video 2B** (installed) | ✅ the workhorse | Fastest video model class; 768×512×97f in ~2–5 min. Long cinematic single-shot prompts, cfg 3, steps 25. Also img2video (`LTXVImgToVideo`). 13B-distilled: ⚠️ GGUF only. |
| **WAN 2.1/2.2 t2v-1.3B** | ✅ | Strong motion quality at 1.3B, 480p. Needs `umt5_xxl_fp8` encoder (~6GB, one-time) + wan VAE; wire UNETLoader/GGUF + CLIPLoader(type wan) + WanImageToVideo/t2v graph. Slower than LTXV, better physics. |
| **WAN 14B** | ⚠️ GGUF Q4 + patience | ~10 min/clip with offload. Only when quality demands it. |
| **HunyuanVideo (13B)** | ⚠️ GGUF Q4 borderline | High quality, very slow here; 544×960 ceiling. RAM pressure risk — restart service after. |
| **Mochi / CogVideoX** | ⚠️/❌ | Mochi GGUF is marginal; CogVideoX needs custom nodes. LTXV/WAN cover the need better. |
| **SVD (img2video)** | ✅ legacy | 25-frame image animation; superseded by LTXV img2video but tiny and reliable. |

## Loader wiring cheat-sheet
- **All-in-one checkpoint** (SD1.5/SDXL/SD3.5/LTXV): `CheckpointLoaderSimple`
  → model/clip/vae (SD3.5 clip is empty → TripleCLIPLoader; LTXV clip via
  CLIPLoader type ltxv).
- **Split diffusion model** (FLUX, WAN, Hunyuan): weights → `diffusion_models/`
  (safetensors → `UNETLoader`, gguf → `UnetLoaderGGUF`), encoders →
  `text_encoders/` + `CLIPLoader`/`DualCLIPLoader` with the right `type`,
  VAE → `vae/` + `VAELoader`.
- Folder must match or the COMBO won't list it: checkpoints/, diffusion_models/,
  text_encoders/, vae/, loras/, upscale_models/.

## Decision shortcuts
- Draft fast → SDXL (or a Lightning finetune). Best text/prompt-following →
  FLUX dev GGUF. Balanced default → SD3.5-medium. Icons → SDXL + installed
  icon LoRAs. Photoreal people → SDXL photoreal finetune from Civitai.
- Video default → LTXV 2B. Better motion, ok waiting → WAN 1.3B. GIF → any of
  these + `gif=True`/`comfy_to_gif`.
- Before any multi-GB download: check `comfy_models(folder, detailed=True)`
  isn't already holding it, quote the size, and prefer fp8/GGUF variants.
