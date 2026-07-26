# Verified recipes for non-curated jobs

All via `comfy_call` unless noted. Verified against the live server 2026-07-15
(reads executed; writes verified to the level noted).

## Inspect a checkpoint's metadata (read, verified)
```
comfy_call("GET", "/view_metadata/checkpoints", query={"filename": "sd3.5_medium.safetensors"})
```
Returns the safetensors header (arch, dtype info).

## Model folders with file sizes (read, verified)
```
comfy_call("GET", "/experiment/models/checkpoints")
```

## Queue depth only (read, verified)
```
comfy_call("GET", "/prompt")   # {"exec_info": {"queue_remaining": N}}
```

## Saved workflows (userdata) (read verified; write shape from source)
```
comfy_call("GET", "/userdata", query={"dir": "workflows"})          # list
comfy_call("GET", "/userdata/workflows%2Fmy-flow.json")             # read one
comfy_call("POST", "/userdata/workflows%2Fnew.json", body={...})    # save (writes!)
```
Path separators inside {file} must be URL-encoded (`%2F`).

## Clear history (write — ask user first)
```
comfy_call("POST", "/history", body={"clear": true})
```

## img2img sketch
1. `comfy_upload_image(file_path="/path/pic.png")` → note returned name
2. Build graph: `LoadImage(image=<name>)` → `VAEEncode` → `KSampler(denoise≈0.6)`
   → `VAEDecode` → `SaveImage`; submit with `comfy_generate`.

## GGUF quantized models (ComfyUI-GGUF installed)
`comfy_nodes(search="gguf")` → `UnetLoaderGGUF(unet_name=...)` loads from the
`diffusion_models`/`unet` folders; combine with `CLIPLoaderGGUF` + normal VAE.
No GGUF files installed yet — drop them in `/mnt/NVME/ai-models/comfyui/models/unet`.

## Watch a long run
Poll `comfy_history(prompt_id)` (or `comfy_queue` for position). For token-level
progress you'd need the `/ws` websocket — not exposed; poll instead.
