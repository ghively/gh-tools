# Full enumerated API surface — ComfyUI 0.26.0

Source-enumerated from the deployed tree (`server.py`, `api_server/`), verified
live 2026-07-15. 46 HTTP routes + websocket. Every route is reachable via
`comfy_call`; ✦ marks ones with a curated tool.

## System & discovery
| Route | Notes |
|---|---|
| GET /system_stats ✦ | versions, RAM, per-device VRAM |
| GET /features | feature flags, max_upload_size (100MB) |
| GET /extensions | frontend extension JS list |
| GET /embeddings | embedding names (empty here) |
| GET /i18n | translation bundles (large) |
| GET /workflow_templates | custom-node template workflows |
| GET /global_subgraphs, /global_subgraphs/{id} | subgraph library |
| GET /node_replacements | migration suggestions |

## Nodes & models
| Route | Notes |
|---|---|
| GET /object_info ✦ (via comfy_nodes) | ALL node classes, 1.4MB |
| GET /object_info/{class} ✦ | one class schema |
| GET /models ✦, /models/{folder} ✦ | 21 folders; checkpoints has 2 files |
| GET /experiment/models(+/{folder}, +preview) | adds size/metadata previews |
| GET /view_metadata/{folder}?filename= | safetensors header JSON |

## Execution & queue
| Route | Notes |
|---|---|
| POST /prompt ✦ (txt2img/generate) | submit graph |
| GET /prompt | `{exec_info: {queue_remaining}}` |
| GET /queue ✦ | running/pending arrays |
| POST /queue ✦ (comfy_cancel) | `{clear}` / `{delete:[ids]}` |
| POST /interrupt ✦ | stop current execution |
| POST /free ✦ | unload models / free VRAM |
| GET /history ✦, /history/{id} ✦ | finished prompts + outputs |
| POST /history | `{clear}` / `{delete:[ids]}` |
| GET /api/jobs, /api/jobs/{id} | newer job list API (status/limit filters) |
| POST /api/jobs/cancel, /api/jobs/{id}/cancel | job cancellation |
| WS /ws | progress events (poll history instead) |

## Files & user data
| Route | Notes |
|---|---|
| GET /view?filename&subfolder&type ✦ | download output/input/temp file |
| POST /upload/image ✦, /upload/mask | multipart into input/ |
| GET /internal/files/{output,input,temp} ✦ | list files |
| GET /internal/folder_paths | every model folder → container paths |
| GET /internal/logs, /internal/logs/raw ✦ | server log |
| GET/POST/DELETE /userdata/{file}, +/move/{dest} | saved workflows etc. |
| GET /userdata?dir=, /v2/userdata?path= | listings |
| GET/POST /users | single-user mode here |
| GET/POST /settings, /settings/{id} | frontend settings store |

## Installed extras (2026-07-15)
- Custom nodes: **ComfyUI-GGUF** (UnetLoaderGGUF, CLIPLoaderGGUF — quantized
  loaders), **rgthree-comfy** (QoL pack, installed via comfy_install_node),
  **websocket_image_save**. 828 node classes total. Node packs add classes,
  not HTTP routes.
- Checkpoints: `sd3.5_medium`, `sd_xl_base_1.0`, `ltx-video-2b-v0.9.5`.
  LoRAs: 15 SDXL (12 style + 3 icon — see projection-styles.md). Upscaler:
  `4x-UltraSharpV2`. Encoders: clip_g / clip_l / t5xxl_fp8. Host store:
  `/mnt/NVME/ai-models/comfyui/models`
  (comfy_model_download writes here; new files visible without restart —
  only COMBO dropdown caches may lag).

## vpt9 media-library service (separate host service, `library_url` :8080)
Not part of ComfyUI — the projection rig's media library. Curated tools:
`comfy_library_collections` / `comfy_library_upload` / `comfy_library_delete`.
| Route | Notes |
|---|---|
| GET /state | full library state; media[].tags[] carries `collection:` + loose XMP keywords |
| POST /api/media | body = raw file bytes; headers `X-File-Name` (display name) + `X-Media-Tags` (server embeds XMP dc:Subject itself) |
| DELETE /api/media/{id} | remove one media item (confirm-gated in the tool) |
Formats: mp4 (h264 yuv420p) / gif / jpg only. POST response shape is
version-dependent — the upload tool parses the id defensively (falls back to
a /state diff).
