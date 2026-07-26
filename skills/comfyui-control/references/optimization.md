# Optimization on this deployment (RTX 3060 12GB, --lowvram, 24g cgroup)

## The deployment's shape
- Container runs `--lowvram`: weights offload aggressively to **system RAM**,
  so RAM (not VRAM) is the working ceiling — cgroup limit **24g**
  (gh-Nvidia compose, raised from 12g after verified OOMs on 2026-07-15).
- The GPU is **shared with Ollama** (8g cgroup, models evict after 10m idle).
  `comfy_status` → `vram_free_gib` before heavy runs; below ~2 GiB free,
  expect the load to thrash.

## Measured timings (live, 2026-07-15)
| Job | Time |
|---|---|
| SDXL 1024², 22–25 steps | ~16s sampling, +6s cold checkpoint load |
| SD3.5 1024², 20 steps | ~26s sampling, +8s TripleCLIP cold load, +13s/encode cold T5 |
| 4x upscale 1024→4096 (UltraSharpV2) | ~33s |
| LTX-Video 768×512×97f, 25 steps | ~53s sampling + ~23s T5 encodes + 4s VAE (fresh container; ~85s wall) |
| Warm re-run same checkpoint | skips all load time — batch same-model work together |

## Rules that pay
1. **Group work by model family.** Checkpoint swaps are the expensive path
   (load + RAM accumulation). comfy_batch > individual calls.
2. **Generate at native res, then upscale.** 1024² + 4x-UltraSharpV2 beats
   direct 2048² (which OOMs or distorts composition anyway).
3. **tiled_vae=True** on txt2img/img2img above ~1408² or when VRAM is tight —
   slower decode, immune to decode OOM.
4. **The OOM signature**: `torch.OutOfMemoryError: Allocation on device` while
   `nvidia-smi` shows an empty GPU = **container RAM pressure**, not VRAM
   (ComfyUI's RAM cache is cgroup-blind — it sizes itself from HOST free
   memory). Check `docker stats agent-lab-comfyui-1`; fix with
   `docker compose -f /srv/agent-lab/docker-compose.yml restart comfyui`.
   `comfy_free` releases VRAM but NOT the cgroup page cache.
5. **Video is the heaviest RAM job** (all frames decode at once). Keep
   768×512×97f as the ceiling; prefer fewer frames over lower steps.
6. Seeds are free; steps are not. Explore with steps=16–18, finalize at 25+.

## VRAM budget cheat-sheet (12 GiB card)
| Load | approx |
|---|---|
| SDXL base full | ~7 GiB |
| SD3.5-medium + 3 encoders | ~11 GiB peak (fits; nothing else resident) |
| LTX-Video 2B + T5 | ~8 GiB |
| Ollama qwen-9b resident | ~7 GiB — don't run image gen against it; wait for the 10m evict or `docker exec agent-lab-ollama-1 ollama stop <model>` |
