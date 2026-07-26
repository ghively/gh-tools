# ComfyUI call conventions (verified live, v0.26.0)

- **No auth.** Plain HTTP JSON on the trusted LAN. Anyone on the LAN can do
  anything — treat writes with care; there is no undo service-side.
- **Content types:** JSON in/out everywhere except `/upload/*` (multipart form,
  field `image`, optional `subfolder`, `overwrite=true|false`) and `/view`
  (binary response).
- **Submit contract:** `POST /prompt` body `{"prompt": <graph>, "client_id":
  <optional>}`. Success → `{"prompt_id", "number", "node_errors"}`. Invalid
  graph → HTTP 400 with `{"error", "node_errors"}` naming the bad node/input.
- **Graph format:** API format — `{"<node_id>": {"class_type": str, "inputs":
  {...}}}`. Connections are `["<source_node_id>", <output_index>]`. The UI's
  saved `.json` workflow (nodes/links arrays) is NOT accepted here; export
  "API format" from the UI or build directly.
- **Completion model:** no blocking call. Poll `GET /history/{prompt_id}` until
  `status.completed` true or `status.status_str == "error"`. Realtime progress
  exists only on the `/ws` websocket (protocol: JSON events `status`,
  `executing`, `progress`) — the MCP server polls instead.
- **Caching:** identical graphs re-run instantly (node outputs cached);
  vary `seed` to force re-execution.
- **`/api/*` prefix:** every route also exists under `/api/` (e.g.
  `/api/queue`) — same handlers; plus the newer jobs API only lives there
  (`/api/jobs`).
- **Error vocabulary:** 400 invalid prompt/params, 404 missing entity/file,
  405 wrong method, 500 internal (check `comfy_logs`).
- **Big payloads:** `/object_info` ≈ 1.4 MB, `/i18n` large, `/history` grows
  unbounded (`?max_items=` caps it).
- **Quirk:** `/models/{folder}` 404s for unknown folder names — folder list
  comes from `GET /models`. File paths inside the container are `/app/...`;
  host-side, models live at `/mnt/NVME/ai-models/comfyui/models` (bind mount),
  outputs at `~/projects/ComfyUI/output`.
