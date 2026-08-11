#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0,<2.0.0", "httpx>=0.27", "websockets>=12"]
# ///
"""ComfyUI control MCP server v2.

Layers:
  * Generic passthrough (comfy_call / comfy_discover) — reaches every HTTP route.
  * Curated generation suite — txt2img (+LoRA), img2img, inpaint, upscale,
    batch, LTX-Video txt2video; websocket-driven progress with per-node timings.
  * Model management — search/download (HuggingFace, Civitai) straight into the
    host model store, delete (gated).
  * Workflow power tools — extract the graph embedded in any ComfyUI PNG,
    re-run/remix it, install custom nodes (gated; restarts the service).

Conventions (verified live against ComfyUI 0.26.0 @ gh-nvidia):
  * No auth. Plain JSON. /object_info is ~1.4 MB — always filtered server-side.
  * Disruptive actions are confirm-gated. Logs to stderr; stdout is MCP.
"""

import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
import comfy_graphs as G  # noqa: E402

# ---------------------------------------------------------------- config

def _load_config() -> dict:
    cfg = {"base_url": "http://127.0.0.1:8188", "timeout": 60,
           "output_dir": "~/comfy-outputs",
           "models_dir": "",          # host path of the models store (optional)
           "custom_nodes_dir": "",    # host path of custom_nodes (optional)
           "compose_file": "",        # compose file for service restarts (optional)
           "compose_service": "comfyui",
           "library_url": ""}         # vpt9 media-library base URL (optional)
    path = os.environ.get("COMFYUI_CONFIG")
    if path and Path(path).expanduser().exists():
        try:
            cfg.update(json.loads(Path(path).expanduser().read_text()))
        except Exception as e:  # noqa: BLE001
            print(f"[comfyui] bad config {path}: {e}", file=sys.stderr)
    if os.environ.get("COMFYUI_BASE_URL"):
        cfg["base_url"] = os.environ["COMFYUI_BASE_URL"]
    cfg["base_url"] = cfg["base_url"].rstrip("/")
    return cfg


CFG = _load_config()
CLIENT = httpx.Client(base_url=CFG["base_url"], timeout=CFG["timeout"])
MAX_INLINE = 60_000

mcp = FastMCP("comfyui")

_NODE_CACHE: dict = {"at": 0.0, "data": None}


def _object_info() -> dict:
    if _NODE_CACHE["data"] is None or time.time() - _NODE_CACHE["at"] > 300:
        _NODE_CACHE["data"] = CLIENT.get("/object_info").json()
        _NODE_CACHE["at"] = time.time()
    return _NODE_CACHE["data"]


def _clip(payload) -> str:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=1)
    if len(text) > MAX_INLINE:
        return text[:MAX_INLINE] + f"\n…[truncated, {len(text)} chars total — narrow the query]"
    return text


def _outdir() -> Path:
    p = Path(CFG["output_dir"]).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- generic layer

ROUTES = [
    ("GET", "/system_stats", "versions, RAM/VRAM, devices"),
    ("GET", "/features", "server feature flags"),
    ("GET", "/extensions", "frontend extension JS files"),
    ("GET", "/embeddings", "embedding names"),
    ("GET", "/object_info", "ALL node classes (1.4MB — use comfy_nodes instead)"),
    ("GET", "/object_info/{node_class}", "one node class definition"),
    ("GET", "/models", "model folder names"),
    ("GET", "/models/{folder}", "files in a model folder"),
    ("GET", "/experiment/models", "model folders w/ metadata"),
    ("GET", "/experiment/models/{folder}", "files w/ metadata"),
    ("GET", "/view_metadata/{folder_name}?filename=", "safetensors header metadata"),
    ("GET", "/prompt", "queue depth {exec_info.queue_remaining}"),
    ("POST", "/prompt", "submit workflow graph {prompt:{...}, client_id}"),
    ("GET", "/queue", "running + pending queue items"),
    ("POST", "/queue", "{clear:true} or {delete:[prompt_ids]}"),
    ("POST", "/interrupt", "stop current execution"),
    ("POST", "/free", "{unload_models:bool, free_memory:bool}"),
    ("GET", "/history", "all finished prompts (use ?max_items=N)"),
    ("GET", "/history/{prompt_id}", "one prompt's status+outputs"),
    ("POST", "/history", "{clear:true} or {delete:[ids]}"),
    ("GET", "/api/jobs", "job list (newer job API; ?status=&limit=)"),
    ("GET", "/api/jobs/{job_id}", "one job"),
    ("POST", "/api/jobs/{job_id}/cancel", "cancel a job"),
    ("POST", "/api/jobs/cancel", "cancel jobs in bulk"),
    ("GET", "/view?filename=&subfolder=&type=", "download an image/file"),
    ("POST", "/upload/image", "multipart upload to input/"),
    ("POST", "/upload/mask", "multipart mask upload"),
    ("GET", "/userdata?dir=", "user data files"),
    ("GET", "/v2/userdata?path=", "user data files v2"),
    ("GET", "/userdata/{file}", "read a userdata file (workflows live here)"),
    ("POST", "/userdata/{file}", "write a userdata file"),
    ("DELETE", "/userdata/{file}", "delete a userdata file"),
    ("POST", "/userdata/{file}/move/{dest}", "move/rename"),
    ("GET", "/users", "user config (single-user here)"),
    ("POST", "/users", "create user"),
    ("GET", "/settings", "frontend settings"),
    ("POST", "/settings/{id}", "set a setting"),
    ("GET", "/workflow_templates", "custom-node template workflows"),
    ("GET", "/global_subgraphs", "global subgraph library"),
    ("GET", "/i18n", "translations"),
    ("GET", "/node_replacements", "node replacement suggestions"),
    ("GET", "/internal/logs", "structured log entries"),
    ("GET", "/internal/logs/raw", "raw terminal log + size"),
    ("GET", "/internal/folder_paths", "every model/config folder -> host paths"),
    ("GET", "/internal/files/{directory_type}", "list files (output|input|temp)"),
    ("WS", "/ws", "realtime progress events (used internally by generation tools)"),
]


@mcp.tool()
def comfy_discover(search: str = "") -> str:
    """List every ComfyUI HTTP route this server can reach (the full enumerated
    surface). Optional case-insensitive substring filter over path+note."""
    s = search.lower()
    rows = [f"{m:6} {p}  — {n}" for m, p, n in ROUTES
            if s in p.lower() or s in n.lower()]
    return "\n".join(rows) or "no route matches"


@mcp.tool()
def comfy_call(method: str, path: str, query: dict | None = None,
               body: dict | None = None) -> str:
    """Generic passthrough: call ANY ComfyUI HTTP endpoint (see comfy_discover).
    method GET/POST/DELETE; path like '/history'; query -> URL params;
    body -> JSON body for POST. Escape hatch for everything not curated."""
    r = CLIENT.request(method.upper(), path, params=query, json=body)
    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        payload = r.text
    return f"HTTP {r.status_code}\n{_clip(payload)}"


# ---------------------------------------------------------------- curated: reads

@mcp.tool()
def comfy_status() -> str:
    """Health snapshot: version, device, VRAM/RAM, queue depth, running job."""
    s = CLIENT.get("/system_stats").json()
    q = CLIENT.get("/queue").json()
    dev = s["devices"][0] if s.get("devices") else {}
    gib = 1024 ** 3
    return json.dumps({
        "comfyui": s["system"]["comfyui_version"],
        "device": dev.get("name"),
        "vram_free_gib": round(dev.get("vram_free", 0) / gib, 2),
        "vram_total_gib": round(dev.get("vram_total", 0) / gib, 2),
        "ram_free_gib": round(s["system"]["ram_free"] / gib, 2),
        "queue_running": [i[1] for i in q.get("queue_running", [])],
        "queue_pending": len(q.get("queue_pending", [])),
    }, indent=1)


@mcp.tool()
def comfy_models(folder: str = "", detailed: bool = False) -> str:
    """List model folders, or files inside one (e.g. 'checkpoints', 'loras',
    'vae', 'upscale_models', 'text_encoders'). detailed=True adds size/mtime."""
    if not folder:
        return json.dumps(CLIENT.get("/models").json())
    path = f"/experiment/models/{folder}" if detailed else f"/models/{folder}"
    r = CLIENT.get(path)
    return _clip(r.json() if r.status_code == 200 else f"HTTP {r.status_code}: {r.text}")


@mcp.tool()
def comfy_nodes(search: str = "", node_class: str = "", limit: int = 40) -> str:
    """Search installed node classes (object_info, filtered server-side).
    search: substring over class name/display name/category.
    node_class: exact class -> full input/output definition."""
    if node_class:
        r = CLIENT.get(f"/object_info/{node_class}")
        return _clip(r.json() if r.status_code == 200 else f"HTTP {r.status_code}")
    info = _object_info()
    s = search.lower()
    hits = []
    for name, d in info.items():
        hay = f"{name} {d.get('display_name','')} {d.get('category','')}".lower()
        if s in hay:
            hits.append(f"{name}  [{d.get('category','?')}]  {d.get('display_name','')}")
            if len(hits) >= limit:
                hits.append(f"…more — narrow the search ({len(info)} classes total)")
                break
    return "\n".join(hits) or f"no match in {len(info)} node classes"


@mcp.tool()
def comfy_queue() -> str:
    """Current queue: running item(s) and pending count with prompt ids."""
    q = CLIENT.get("/queue").json()
    out = {"running": [{"prompt_id": i[1]} for i in q.get("queue_running", [])],
           "pending": [{"prompt_id": i[1]} for i in q.get("queue_pending", [])]}
    return json.dumps(out, indent=1)


@mcp.tool()
def comfy_history(prompt_id: str = "", max_items: int = 8) -> str:
    """Finished prompts. Without prompt_id: recent summary (id, status, output
    files). With prompt_id: that prompt's full status + outputs."""
    if prompt_id:
        return _clip(CLIENT.get(f"/history/{prompt_id}").json())
    h = CLIENT.get("/history", params={"max_items": max_items}).json()
    rows = []
    for pid, entry in h.items():
        status = entry.get("status", {})
        rows.append({"prompt_id": pid,
                     "completed": status.get("completed"),
                     "status": status.get("status_str"),
                     "outputs": [o["filename"] for o in _output_files(entry)]})
    return json.dumps(rows, indent=1)


@mcp.tool()
def comfy_logs(tail_chars: int = 4000) -> str:
    """Tail the ComfyUI server log (crashes, load errors, execution traces)."""
    r = CLIENT.get("/internal/logs/raw").json()
    text = "".join(e.get("m", "") for e in r.get("entries", [])) or str(r)
    return text[-tail_chars:]


@mcp.tool()
def comfy_output_files(directory: str = "output") -> str:
    """List files in ComfyUI's output/input/temp directory."""
    r = CLIENT.get(f"/internal/files/{directory}")
    return _clip(r.json() if r.status_code == 200 else f"HTTP {r.status_code}")


# ------------------------------------------------- execution engine (WS-first)

def _output_files(entry: dict) -> list[dict]:
    """Every downloadable artifact in a history entry (images, video, audio)."""
    found = []
    for node in entry.get("outputs", {}).values():
        for val in node.values():
            if isinstance(val, list):
                for o in val:
                    if isinstance(o, dict) and "filename" in o:
                        found.append(o)
    return found


def _download(o: dict) -> str:
    # subfolder/type go into the local name so same-basename artifacts from
    # different server locations don't overwrite each other.
    ftype = o.get("type", "output")
    parts = [p for p in (ftype if ftype != "output" else "",
                         o.get("subfolder", "").replace("/", "_"),
                         o["filename"].replace("/", "_")) if p]
    dest = _outdir() / "_".join(parts)
    r = CLIENT.get("/view", params={"filename": o["filename"],
                                    "subfolder": o.get("subfolder", ""),
                                    "type": ftype})
    if r.status_code != 200:
        raise RuntimeError(f"/view HTTP {r.status_code} for {o['filename']}")
    dest.write_bytes(r.content)
    return str(dest)


def _wait_poll(prompt_id: str, timeout: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = CLIENT.get(f"/history/{prompt_id}").json()
        if prompt_id in h:
            entry = h[prompt_id]
            st = entry.get("status", {})
            if st.get("completed") or st.get("status_str") == "error":
                return entry
        time.sleep(1.5)
    return {}


async def _run_ws(graph: dict, timeout: float) -> tuple[str, list, dict]:
    """Submit with a client_id and watch /ws: returns (prompt_id, per-node
    timeline, history entry). Falls back to polling upstream on WS failure."""
    import websockets
    client_id = f"mcp-{uuid.uuid4().hex[:8]}"
    ws_url = CFG["base_url"].replace("http", "ws", 1) + f"/ws?clientId={client_id}"
    timeline: list = []
    async with websockets.connect(ws_url, max_size=2 ** 25) as ws:
        r = CLIENT.post("/prompt", json={"prompt": graph, "client_id": client_id})
        if r.status_code != 200:
            raise RuntimeError(f"submit failed HTTP {r.status_code}: {r.text[:2000]}")
        pid = r.json()["prompt_id"]
        cur, cur_t0, t0 = None, 0.0, time.time()
        while time.time() - t0 < timeout:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
            except asyncio.TimeoutError:
                h = CLIENT.get(f"/history/{pid}").json()   # missed-event safety
                if pid in h and h[pid].get("status", {}).get("completed"):
                    break
                continue
            if isinstance(msg, (bytes, bytearray)):
                continue                                   # preview frame
            ev = json.loads(msg)
            t, d = ev.get("type"), ev.get("data", {})
            if d.get("prompt_id") not in (None, pid):
                continue
            if t == "executing":
                now = time.time()
                if cur is not None:
                    cls = graph.get(cur, {}).get("class_type", cur)
                    timeline.append(f"{cls}: {now - cur_t0:.1f}s")
                cur, cur_t0 = d.get("node"), now
                if d.get("node") is None:
                    break                                  # prompt finished
            elif t in ("execution_error", "execution_interrupted"):
                timeline.append(f"ERROR@{d.get('node_type')}: "
                                f"{d.get('exception_message', t)[:400]}")
                break
    entry = _wait_poll(pid, 15)
    return pid, timeline, entry


def _execute(graph: dict, timeout: float) -> str:
    """Run a graph with WS progress; fall back to polling. Download artifacts."""
    try:
        pid, timeline, entry = asyncio.run(_run_ws(graph, timeout))
    except RuntimeError as e:
        return str(e)
    except Exception as e:  # WS layer failed — degrade to plain polling
        print(f"[comfyui] ws failed ({e}); polling", file=sys.stderr)
        r = CLIENT.post("/prompt", json={"prompt": graph})
        if r.status_code != 200:
            return f"submit failed HTTP {r.status_code}: {_clip(r.text)}"
        pid, timeline = r.json()["prompt_id"], []
        entry = _wait_poll(pid, timeout)
    if not entry:
        return f"submitted prompt_id={pid}, still running after {timeout}s — comfy_history('{pid}')"
    st = entry.get("status", {})
    if st.get("status_str") == "error":
        detail = [t for t in timeline if t.startswith("ERROR")] or \
                 [m for m in st.get("messages", []) if m[0] == "execution_error"]
        return f"prompt_id={pid} FAILED: {_clip(detail)}"
    files = [_download(o) for o in _output_files(entry)]
    return json.dumps({"prompt_id": pid, "outputs": files,
                       "node_timings": timeline}, indent=1)


def _upload(path: str, overwrite: bool = True) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such file: {p}")
    r = CLIENT.post("/upload/image", files={"image": (p.name, p.read_bytes())},
                    data={"overwrite": str(overwrite).lower()})
    r.raise_for_status()
    j = r.json()
    return (j.get("subfolder", "") + "/" + j["name"]).lstrip("/")


def _resolve_image(image: str) -> str:
    """Accept a local path (uploads it) or a server-side input filename."""
    if Path(image).expanduser().exists():
        return _upload(image)
    return image


def _default_checkpoint(want: str = "") -> str:
    cps = CLIENT.get("/models/checkpoints").json()
    if want:
        return want
    non_video = [c for c in cps if "ltx" not in c.lower() and "video" not in c.lower()]
    if not non_video:
        raise RuntimeError("no image checkpoints installed")
    return non_video[0]


def _seed(seed: int) -> int:
    return seed if seed else int.from_bytes(os.urandom(4), "big")


# --------------------------------------------------------- generation suite

@mcp.tool()
def comfy_txt2img(prompt: str, negative: str = "", checkpoint: str = "",
                  width: int = 1024, height: int = 1024, steps: int = 20,
                  cfg: float = 5.0, seed: int = 0, sampler: str = "euler",
                  scheduler: str = "normal", loras: str = "",
                  tiled_vae: bool = False, hires_scale: float = 0,
                  wait_timeout: int = 240) -> str:
    """Text-to-image. checkpoint defaults to the first installed image model;
    SD3-family gets TripleCLIPLoader automatically. loras: comma list of
    'name.safetensors:strength'. hires_scale (1.5-2.0): latent-space hires-fix
    — upscale the latent, re-sample at denoise 0.25 with the same seed, decode
    tiled (forced regardless of tiled_vae); the projection mastering path.
    Returns local file paths + per-node timings."""
    checkpoint = _default_checkpoint(checkpoint)
    g = G.txt2img(checkpoint, prompt, negative, width, height, _seed(seed),
                  steps, cfg, sampler, scheduler, loras, tiled_vae,
                  hires_scale)
    return _execute(g, wait_timeout)


@mcp.tool()
def comfy_img2img(image: str, prompt: str, negative: str = "",
                  denoise: float = 0.6, checkpoint: str = "", steps: int = 20,
                  cfg: float = 5.0, seed: int = 0, sampler: str = "euler",
                  scheduler: str = "normal", loras: str = "",
                  wait_timeout: int = 240) -> str:
    """Image-to-image: restyle/vary an existing image. image = local path
    (auto-uploaded) or a filename already in ComfyUI's input dir. denoise:
    0.3 subtle -> 0.8 heavy change."""
    name = _resolve_image(image)
    checkpoint = _default_checkpoint(checkpoint)
    g = G.img2img(checkpoint, name, prompt, negative, denoise, _seed(seed),
                  steps, cfg, sampler, scheduler, loras)
    return _execute(g, wait_timeout)


@mcp.tool()
def comfy_inpaint(image: str, mask: str, prompt: str, negative: str = "",
                  checkpoint: str = "", steps: int = 24, cfg: float = 5.5,
                  seed: int = 0, grow_mask_by: int = 16,
                  wait_timeout: int = 240) -> str:
    """Inpaint: regenerate only the masked region. mask = an image whose
    white/bright (red-channel) areas mark what to replace; both args accept
    local paths or server-side input filenames."""
    img_name, mask_name = _resolve_image(image), _resolve_image(mask)
    checkpoint = _default_checkpoint(checkpoint)
    g = G.inpaint(checkpoint, img_name, mask_name, prompt, negative,
                  _seed(seed), steps, cfg, "euler", "normal", grow_mask_by)
    return _execute(g, wait_timeout)


@mcp.tool()
def comfy_upscale(image: str, model: str = "", wait_timeout: int = 180) -> str:
    """Upscale with an ESRGAN-class model from upscale_models/ (typically 4x).
    model defaults to the first installed; if none, download one first
    (comfy_model_search('4x upscale') -> comfy_model_download)."""
    ups = CLIENT.get("/models/upscale_models").json()
    if not ups:
        return "no upscale models installed — comfy_model_download one into 'upscale_models' first"
    model = model or ups[0]
    g = G.upscale(_resolve_image(image), model)
    return _execute(g, wait_timeout)


@mcp.tool()
def comfy_batch(prompt: str, count: int = 4, checkpoint: str = "",
                width: int = 1024, height: int = 1024, steps: int = 20,
                cfg: float = 5.0, negative: str = "", loras: str = "",
                wait_timeout: int = 900) -> str:
    """Generate `count` (max 8) variations of one prompt with fresh seeds —
    queued together, reported together with their seeds."""
    count = min(count, 8)
    checkpoint = _default_checkpoint(checkpoint)
    subs = []
    for _ in range(count):
        s = _seed(0)
        g = G.txt2img(checkpoint, prompt, negative, width, height, s,
                      steps, cfg, "euler", "normal", loras, False)
        r = CLIENT.post("/prompt", json={"prompt": g})
        if r.status_code != 200:
            return f"submit failed HTTP {r.status_code}: {_clip(r.text)}"
        subs.append({"prompt_id": r.json()["prompt_id"], "seed": s})
    results, t0 = [], time.time()
    for sub in subs:
        left = max(30.0, wait_timeout - (time.time() - t0))
        entry = _wait_poll(sub["prompt_id"], left)
        results.append({**sub,
                        "outputs": [_download(o) for o in _output_files(entry)]
                        if entry else "TIMEOUT"})
    return json.dumps(results, indent=1)


@mcp.tool()
def comfy_generate(workflow_json: str, wait_timeout: int = 240) -> str:
    """Submit a raw API-format workflow graph (node-id -> {class_type, inputs}).
    WS progress + artifact download included."""
    graph = json.loads(workflow_json)
    if "prompt" in graph and "class_type" not in next(iter(graph.values()), {}):
        graph = graph["prompt"]
    return _execute(graph, wait_timeout)


# --------------------------------------------------------------- video

def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True,
        check=True, timeout=60)
    return float(out.stdout.strip())


def _loop_prefix(src: Path, loop: str, fade: float) -> tuple[str, float]:
    """filter_complex prefix that always ends in a labeled [looped] pad, so
    gif and mp4 encoders can share the loop logic. Modes: 'crossfade'
    (forward-only seamless wrap — the tail blends into the head; output
    shortens by `fade` seconds), 'palindrome' (boomerang; fps/scale applies
    downstream of the split/reverse now — slightly more memory, same look),
    'none' (passthrough)."""
    if loop == "crossfade":
        d = _duration(src)
        if d <= 2 * fade + 0.2:
            fade = max(0.2, d / 4)
        return ((f"[0:v]trim=start={fade},setpts=PTS-STARTPTS[main];"
                 f"[0:v]trim=duration={fade},setpts=PTS-STARTPTS[head];"
                 f"[main][head]xfade=transition=fade:duration={fade}:"
                 f"offset={d - 2 * fade}[looped]"), fade)
    if loop == "palindrome":
        return ("[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1[looped]",
                fade)
    return "[0:v]null[looped]", fade


def _to_gif(video_path: str, fps: int = 12, width: int = 480,
            loop: str = "crossfade", fade: float = 0.8) -> str:
    """High-quality mp4 -> GIF via ffmpeg two-pass palette. loop modes: see
    _loop_prefix; 'crossfade' is the owner-preferred default."""
    src = Path(video_path)
    gif = src.with_suffix(".gif")
    prefix, fade = _loop_prefix(src, loop, fade)
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    palette = (f"split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
               f"[s1][p]paletteuse=dither=bayer:bayer_scale=4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter_complex", f"{prefix};[looped]{vf},{palette}", str(gif)],
        check=True, capture_output=True, timeout=600)
    return str(gif)


_MP4_ENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-preset", "slow", "-movflags", "+faststart", "-an"]


def _to_loop_mp4(video_path: str, fade: float = 0.8) -> str:
    """Crossfade-wrap a clip into a seamless forward-only loop, encoded as
    h264 yuv420p mp4 (the vpt9 library's required pixel format; ~40x smaller
    than the equivalent GIF)."""
    src = Path(video_path)
    out = src.with_name(src.stem + "_loop.mp4")
    prefix, _ = _loop_prefix(src, "crossfade", fade)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter_complex", prefix, "-map", "[looped]", *_MP4_ENC, str(out)],
        check=True, capture_output=True, timeout=600)
    return str(out)


def _src_fps(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True, timeout=60)
    num, _, den = out.stdout.strip().partition("/")
    return float(num) / float(den or 1)


def _interpolate_loop(video_path: str, target_fps: int) -> str:
    """Loop-aware motion interpolation (A B C -> A B C A -> interpolate ->
    trim the duplicate tail): run on an ALREADY-WRAPPED clip, whose end and
    start are consecutive-in-cycle frames, so the optical flow crosses a true
    seam. Interpolating before the wrap would smear the tail->head jump."""
    src = Path(video_path)
    d, fps_in = _duration(src), _src_fps(src)
    first = src.with_name(src.stem + "_f0.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src),
                    "-frames:v", "1", str(first)],
                   check=True, capture_output=True, timeout=120)
    dest = src.with_name(src.stem + f"_{target_fps}fps.mp4")
    chain = (f"[0:v][1:v]concat=n=2:v=1,"
             f"minterpolate=fps={target_fps}:mi_mode=mci,"
             f"trim=duration={d:.6f},setpts=PTS-STARTPTS")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(src),
             "-loop", "1", "-framerate", f"{fps_in:.6f}",
             "-t", f"{1 / fps_in:.6f}", "-i", str(first),
             "-filter_complex", chain, *_MP4_ENC, str(dest)],
            check=True, capture_output=True, timeout=1800)
    finally:
        first.unlink(missing_ok=True)
    return str(dest)


@mcp.tool()
def comfy_to_gif(video_path: str, fps: int = 12, width: int = 480,
                 loop: str = "crossfade", fade: float = 0.8) -> str:
    """Convert any local video file (e.g. a comfy_txt2video mp4) into an
    animated GIF (ffmpeg two-pass palette — sharp colors, sane size).
    loop='crossfade' (default) = forward-only seamless wrap (owner-preferred);
    'palindrome' = boomerang; 'none' = plain. fade = crossfade seconds."""
    try:
        return _to_gif(str(Path(video_path).expanduser()), fps, width, loop, fade)
    except subprocess.CalledProcessError as e:
        return f"ffmpeg failed: {e.stderr.decode()[-400:]}"


@mcp.tool()
def comfy_loop_video(video_path: str, fade: float = 0.8, format: str = "mp4",
                     fps: int = 15, gif_width: int = 960,
                     interpolate_fps: int = 0) -> str:
    """Turn any clip into a seamless forward-only loop. Crossfade wrap (tail
    blends into head; output shortens by `fade`s), encoded h264 yuv420p mp4 —
    vpt9-library-ready and ~40x smaller than GIF. format: mp4 | gif | both
    (gif is rendered FROM the wrapped mp4, no double-blend).
    interpolate_fps (optional, SLOW — optical flow): loop-aware cadence
    smoothing applied AFTER the wrap. Do NOT run this tool on clips that are
    already true cycles (comfy_img2video loop=True, comfy_animate_still) —
    re-crossfading a perfect cycle breaks it; use comfy_to_gif(loop='none')
    for those instead."""
    src = Path(video_path).expanduser()
    if not src.exists():
        return f"no such file: {src}"
    try:
        mp4 = _to_loop_mp4(str(src), fade)
        if interpolate_fps:
            mp4 = _interpolate_loop(mp4, interpolate_fps)
        res = {"mp4": mp4}
        if format in ("gif", "both"):
            res["gif"] = _to_gif(mp4, fps=fps, width=gif_width, loop="none")
    except subprocess.CalledProcessError as e:
        return f"ffmpeg failed: {e.stderr.decode()[-400:]}"
    return json.dumps(res, indent=1)


@mcp.tool()
def comfy_master_still(image: str, width: int = 1920, height: int = 1080,
                       upscale: bool = True, upscale_model: str = "",
                       wait_timeout: int = 300) -> str:
    """Finish a still for delivery: optional 4x model upscale, then an exact
    width x height master (scale-to-cover + center crop, lanczos) saved as
    jpg — the vpt9 library takes jpg, never png. Defaults to the 1080p
    projector raster; pass width=height for square texture-set faces. Keep
    the returned master_png as the lossless master; the jpg is the delivery
    proxy."""
    src = Path(image).expanduser()
    if not src.exists():
        return f"no such file: {src}"
    master = src
    if upscale:
        ups = CLIENT.get("/models/upscale_models").json()
        if not ups:
            return ("no upscale models installed — comfy_model_download one "
                    "into 'upscale_models' first, or pass upscale=False")
        g = G.upscale(_resolve_image(str(src)), upscale_model or ups[0])
        out = _execute(g, wait_timeout)
        try:
            pngs = [f for f in json.loads(out).get("outputs", [])
                    if f.endswith(".png")]
        except json.JSONDecodeError:
            return out
        if not pngs:
            return out
        master = Path(pngs[0])
    jpg = _outdir() / f"{master.stem}_{width}x{height}.jpg"
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase:"
          f"flags=lanczos,crop={width}:{height}")
    try:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(master),
                        "-vf", vf, "-frames:v", "1", "-q:v", "2", str(jpg)],
                       check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        return f"ffmpeg failed: {e.stderr.decode()[-400:]}"
    return json.dumps({"master_png": str(master), "jpg": str(jpg)}, indent=1)


# --------------------------------------------------- parametric still motion

_MOTIONS = ("zoom_in", "zoom_out", "tunnel", "rotate", "rotate_ccw",
            "drift", "pulse", "kaleido")


def _motion_chain(motion: str, w: int, h: int, duration: float, fps: int,
                  intensity: float, fade: float) -> tuple[str, int, bool]:
    """Pure builder for comfy_animate_still ffmpeg graphs. Returns
    (filter_complex, total_frames, needs_crossfade_wrap).

    Loop math: every motion except 'tunnel' drives its parameter around a
    CLOSED CYCLE sampled at phase n/N over [0,T) — frame N would equal frame
    0 exactly, so we render exactly N frames and playback wraps perfectly in
    position AND velocity (the Electric Sheep principle: rotate the
    parameters 360 degrees and the shape must return to its start). 'tunnel'
    is a perpetual exponential zoom (constant d/dt ln z, so seam velocity
    matches) rendered T+fade long then crossfade-wrapped — the blend
    double-exposes the image at a scale ratio, so tunnel needs SELF-SIMILAR
    sources (mandala/fractal/radial); generic imagery ghosts."""
    N = max(2, round(duration * fps))
    fmt = "format=yuv420p"
    cover = (f"scale={w}:{h}:force_original_aspect_ratio=increase:"
             f"flags=lanczos,crop={w}:{h}")
    D = math.ceil(math.hypot(w, h))  # covering square: no corner exposure
    cover_sq = (f"scale={D}:{D}:force_original_aspect_ratio=increase:"
                f"flags=lanczos,crop={D}:{D}")
    # 2x2 mirror tile: edge-continuous and periodic with period (2w, 2h)
    mirror = (f"{cover},split=4[a][b][c][d];[b]hflip[bf];[a][bf]hstack[top];"
              f"[c]vflip[cf];[d]hflip,vflip[df];[cf][df]hstack[bot];"
              f"[top][bot]vstack[mt]")
    if motion in ("rotate", "rotate_ccw"):
        k = max(1, round(intensity))       # integer revolutions = exact cycle
        sign = "-" if motion == "rotate_ccw" else ""
        return (f"{cover_sq},rotate={sign}2*PI*{k}*n/{N}:ow={w}:oh={h},{fmt}",
                N, False)
    if motion in ("zoom_in", "zoom_out"):
        # closed-cycle log-zoom: z = exp(A*(1∓cos(2πn/N))/2) is C∞-periodic —
        # frame N ≡ frame 0 in position and velocity, no crossfade needed.
        # cos is periodic, so zoompan's 0- vs 1-based `on` only phase-shifts.
        amp = math.log(1 + 0.6 * intensity)
        ph = "1-cos" if motion == "zoom_in" else "1+cos"
        z = f"exp({amp:.6f}*({ph}(2*PI*on/{N}))/2)"
        return (f"scale={4 * w}:-2:flags=lanczos,"  # supersample: xy jitter
                f"zoompan=z='{z}':d={N}:x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},{fmt}", N, False)
    if motion == "tunnel":
        M = N + round(fade * fps)
        k = math.log(1 + 1.2 * intensity) / (duration + fade)
        z = f"exp({k:.6f}*on/{fps})"       # z clamped to [1,10] by ffmpeg
        return (f"scale={4 * w}:-2:flags=lanczos,"
                f"zoompan=z='{z}':d={M}:x='iw/2-(iw/zoom/2)':"
                f"y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},{fmt}", M, True)
    if motion == "drift":
        # translate the mirror tile by exactly c periods over N frames:
        # offset(N) ≡ offset(0) ⇒ exact cycle. 4x4 canvas keeps the crop
        # window inside for any offset < one period.
        c = max(1, round(intensity))
        pw, ph2 = 2 * w, 2 * h
        return (f"{mirror};[mt]split=4[t1][t2][t3][t4];[t1][t2]hstack[tt];"
                f"[t3][t4]hstack[bb];[tt][bb]vstack[big];"
                f"[big]crop={w}:{h}:x='mod(round(n*{c * pw}/{N}),{pw})':"
                f"y='mod(round(n*{c * ph2}/{N}),{ph2})',{fmt}", N, False)
    if motion == "pulse":
        # integer sinusoid cycles: value AND velocity continuous at the wrap
        amp = min(0.10 * intensity, 0.45)
        c = max(1, round(2 * intensity))
        s = f"sin(2*PI*{c}*n/{N})"
        return (f"{cover},eq=brightness='{amp:.3f}*{s}':"
                f"saturation='1+{amp:.3f}*{s}':eval=frame,{fmt}", N, False)
    if motion == "kaleido":
        # mirror symmetry (seamless internal edges) + integer revolutions
        k = max(1, round(intensity))
        return (f"{mirror};[mt]{cover_sq}[sq];"
                f"[sq]rotate=2*PI*{k}*n/{N}:ow={w}:oh={h},{fmt}", N, False)
    raise ValueError(f"unknown motion '{motion}' — one of: {', '.join(_MOTIONS)}")


@mcp.tool()
def comfy_animate_still(image: str, motion: str = "zoom_in",
                        duration: float = 8.0, fps: int = 30,
                        width: int = 1920, height: int = 1080,
                        intensity: float = 1.0, fade: float = 0.8,
                        format: str = "mp4") -> str:
    """Animate a still into a seamlessly LOOPING clip with parametric ffmpeg
    motion — no GPU, loops are mathematically exact (closed parameter
    cycles). Motions: zoom_in/zoom_out (breathing log-zoom), rotate /
    rotate_ccw (full revolutions), drift (mirror-tile scroll), pulse
    (brightness/saturation breathe), kaleido (mirror symmetry + spin),
    tunnel (perpetual zoom, crossfade-wrapped — SELF-SIMILAR sources only:
    mandala/fractal/radial). intensity ~0.3 ambient .. 2.0 bold. format:
    mp4 | gif | both. Texture-set tip: animate every face with the same
    duration+fps and the faces loop phase-locked on the rig."""
    src = Path(image).expanduser()
    if not src.exists():
        return f"no such file: {src}"
    try:
        chain, total, needs_wrap = _motion_chain(
            motion, width, height, duration, fps, intensity, fade)
    except ValueError as e:
        return str(e)
    out = _outdir() / f"{src.stem}_{motion}.mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-loop", "1",
             "-framerate", str(fps), "-i", str(src),
             "-filter_complex", chain, "-frames:v", str(total),
             *_MP4_ENC, str(out)],
            check=True, capture_output=True, timeout=1800)
        mp4 = str(out)
        if needs_wrap:
            mp4 = _to_loop_mp4(mp4, fade)
        res = {"mp4": mp4, "loop": "crossfade-wrapped" if needs_wrap
               else "exact cycle"}
        if format in ("gif", "both"):
            res["gif"] = _to_gif(mp4, fps=min(fps, 15), width=960, loop="none")
    except subprocess.CalledProcessError as e:
        return f"ffmpeg failed: {e.stderr.decode()[-400:]}"
    return json.dumps(res, indent=1)


def _ltxv_models() -> tuple[str, str, str]:
    """(ltx_checkpoint, t5_encoder, error) — error is "" when both found."""
    cps = CLIENT.get("/models/checkpoints").json()
    ltx = [c for c in cps if "ltx" in c.lower()]
    if not ltx:
        return "", "", ("no LTX-Video checkpoint installed. Fix: comfy_model_download("
                        "hf_repo='Lightricks/LTX-Video', hf_file='ltx-video-2b-v0.9.5.safetensors', "
                        "folder='checkpoints') (~6GB)")
    t5s = [t for t in CLIENT.get("/models/text_encoders").json() if "t5" in t.lower()]
    if not t5s:
        return "", "", "no T5 text encoder in text_encoders/ — LTXV needs t5xxl"
    return ltx[0], t5s[0], ""


def _snap_frames(frames: int) -> int:
    """LTXV frame counts must be 8n+1."""
    return frames if (frames - 1) % 8 == 0 else 8 * round((frames - 1) / 8) + 1


def _attach_gifs(out: str, loop: str = "crossfade") -> str:
    """Add GIF renders of any mp4/webm outputs in an _execute result."""
    try:
        res = json.loads(out)
        vids = [f for f in res.get("outputs", []) if f.endswith((".mp4", ".webm"))]
        res["gifs"] = [_to_gif(v, loop=loop) for v in vids]
        return json.dumps(res, indent=1)
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        return out + f"\n(gif conversion failed: {e})"


@mcp.tool()
def comfy_txt2video(prompt: str, negative: str = "low quality, blurry, distorted",
                    width: int = 768, height: int = 512, frames: int = 97,
                    fps: int = 24, steps: int = 25, cfg: float = 3.0,
                    seed: int = 0, gif: bool = False,
                    wait_timeout: int = 900) -> str:
    """Text-to-video via LTX-Video (needs an 'ltx' checkpoint in checkpoints/
    and t5xxl in text_encoders/ — comfy_model_download can fetch them).
    frames must be 8n+1 (97 ≈ 4s @ 24fps). LTXV wants LONG, detailed,
    motion-rich prompts. Output: mp4 downloaded locally; gif=True also
    renders an animated GIF alongside it."""
    ltx, t5, err = _ltxv_models()
    if err:
        return err
    g = G.ltxv_txt2video(ltx, t5, prompt, negative, width, height,
                         _snap_frames(frames), fps, _seed(seed), steps, cfg)
    out = _execute(g, wait_timeout)
    return _attach_gifs(out) if gif else out


@mcp.tool()
def comfy_img2video(image: str, prompt: str,
                    negative: str = "low quality, blurry, distorted",
                    width: int = 768, height: int = 512, frames: int = 97,
                    fps: int = 24, steps: int = 25, cfg: float = 3.0,
                    seed: int = 0, strength: float = 0.9, loop: bool = True,
                    gif: bool = False, wait_timeout: int = 900) -> str:
    """Image-to-video via LTX-Video keyframe guides. image = local path
    (auto-uploaded) or a server-side input filename. The BEST style-control
    pipeline: render an SDXL still with your checkpoint+LoRA stack, then
    animate it here. loop=True pins the image as BOTH first and last frame —
    a true seamless cycle, no crossfade ghosting. Write a STEADY-STATE motion
    prompt (motion mid-cycle at start/end: "rotates continuously", "breathes
    gently" — never "begins to..."). strength 0.7-1.0: how hard the guides
    anchor (1.0 can over-anchor to near-static). frames must be 8n+1."""
    name = _resolve_image(image)
    ltx, t5, err = _ltxv_models()
    if err:
        return err
    g = G.ltxv_img2video(ltx, t5, name, prompt, negative, width, height,
                         _snap_frames(frames), fps, _seed(seed), steps, cfg,
                         strength, loop)
    out = _execute(g, wait_timeout)
    if gif:
        # a loop=True clip is already a perfect cycle — crossfading it again
        # would double-blend the seam
        return _attach_gifs(out, loop="none" if loop else "crossfade")
    return out


# --------------------------------------------------------- model management

def _models_dir() -> Path:
    if not CFG["models_dir"]:
        raise RuntimeError("models_dir not set in config.local.json")
    p = Path(CFG["models_dir"]).expanduser()
    if not p.is_dir():
        raise RuntimeError(f"models_dir missing on this host: {p}")
    return p


@mcp.tool()
def comfy_model_search(query: str, source: str = "huggingface",
                       civitai_type: str = "", limit: int = 8) -> str:
    """Search downloadable models. source: 'huggingface' or 'civitai'.
    civitai_type filters (Checkpoint, LORA, Upscaler, VAE, ...). Returns
    name/id + the info needed for comfy_model_download."""
    x = httpx.Client(timeout=30, follow_redirects=True)
    if source.startswith("h"):
        r = x.get("https://huggingface.co/api/models",
                  params={"search": query, "limit": limit})
        rows = [{"repo": m["id"], "downloads": m.get("downloads"),
                 "tags": [t for t in m.get("tags", [])[:5]]} for m in r.json()]
        return json.dumps(rows, indent=1) + \
            "\n(pick a file: comfy_call GET https not needed — use " \
            "comfy_model_download(hf_repo=..., hf_file=<file in repo>) ; " \
            "browse files at huggingface.co/<repo>/tree/main)"
    r = x.get("https://civitai.com/api/v1/models",
              params={"query": query, "limit": limit,
                      **({"types": civitai_type} if civitai_type else {})})
    rows = []
    for m in r.json().get("items", []):
        ver = (m.get("modelVersions") or [{}])[0]
        f = (ver.get("files") or [{}])[0]
        rows.append({"name": m["name"], "type": m.get("type"),
                     "trainedWords": ver.get("trainedWords", [])[:4],
                     "size_mb": round((f.get("sizeKB", 0)) / 1024),
                     "download_url": f.get("downloadUrl")})
    return json.dumps(rows, indent=1)


@mcp.tool()
def comfy_model_download(folder: str, url: str = "", hf_repo: str = "",
                         hf_file: str = "", filename: str = "") -> str:
    """Download a model into the live store (models_dir/<folder>/). Either a
    direct url (Civitai download_url etc.) or hf_repo + hf_file. Streams to
    disk, checks free space, then verifies ComfyUI can see the file."""
    if hf_repo and hf_file:
        url = f"https://huggingface.co/{hf_repo}/resolve/main/{hf_file}"
        filename = filename or Path(hf_file).name
    if not url:
        return "need url= or hf_repo=+hf_file="
    dest_dir = _models_dir() / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = filename or Path(httpx.URL(url).path).name or "model.safetensors"
    dest = dest_dir / filename
    headers = {}
    if "civitai.com" in url and CFG.get("civitai_token"):
        headers["Authorization"] = f"Bearer {CFG['civitai_token']}"
    x = httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                     headers=headers)
    with x.stream("GET", url) as r:
        if r.status_code == 401 and "civitai.com" in url:
            return ("HTTP 401 — this Civitai file requires an API token: add "
                    '"civitai_token": "<key from civitai.com/user/account>" '
                    "to config.local.json")
        if r.status_code != 200:
            return f"HTTP {r.status_code} from {url}"
        total = int(r.headers.get("content-length", 0))
        free = shutil.disk_usage(dest_dir).free
        if total and free - total < 10 * 1024 ** 3:
            return f"refused: {total/1e9:.1f}GB download would leave <10GB free"
        done, aborted = 0, False
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 22):
                f.write(chunk)
                done += len(chunk)
                if done % (1 << 29) < (1 << 22):
                    print(f"[dl] {filename}: {done/1e9:.1f}/{total/1e9:.1f}GB",
                          file=sys.stderr)
                    # chunked downloads (no Content-Length) bypass the
                    # pre-check — re-verify free space as we stream
                    if shutil.disk_usage(dest_dir).free < 10 * 1024 ** 3:
                        aborted = True
                        break
    if aborted:
        dest.unlink(missing_ok=True)
        return (f"aborted at {done/1e9:.1f}GB: free space fell below 10GB "
                "(partial file removed)")
    seen = filename in json.loads(CLIENT.get(f"/models/{folder}").text or "[]")
    return json.dumps({"saved": str(dest), "bytes": done,
                       "comfyui_sees_it": seen,
                       "note": None if seen else
                       "not visible yet — COMBO caches may need a service restart"},
                      indent=1)


@mcp.tool()
def comfy_model_delete(folder: str, filename: str, confirm: bool = False) -> str:
    """DESTRUCTIVE: delete a model file from models_dir/<folder>/.
    Requires confirm=True."""
    if not confirm:
        return "refused: pass confirm=True to delete a model file"
    p = _models_dir() / folder / filename
    if not p.is_file():
        return f"no such file: {p}"
    size = p.stat().st_size
    p.unlink()
    return f"deleted {p} ({size/1e9:.2f}GB)"


# --------------------------------------------------------- workflow power tools

@mcp.tool()
def comfy_png_workflow(png_path: str) -> str:
    """Extract the full API-format workflow graph embedded in any
    ComfyUI-generated PNG — every output carries its own recipe."""
    return _clip(G.png_workflow(str(Path(png_path).expanduser())))


@mcp.tool()
def comfy_rerun(png_path: str, seed: int = 0, prompt: str = "",
                overrides_json: str = "", wait_timeout: int = 300) -> str:
    """Re-run/remix the workflow inside a ComfyUI PNG. seed 0 -> fresh random
    on every sampler; prompt (if given) replaces the positive CLIPTextEncode
    text; overrides_json: {"<node_id>": {"<input>": value}} for surgical edits."""
    g = G.png_workflow(str(Path(png_path).expanduser()))
    for node in g.values():
        for k in ("seed", "noise_seed"):
            if k in node.get("inputs", {}):
                node["inputs"][k] = _seed(seed)
    if prompt:
        # positive = the CLIPTextEncode wired into a 'positive' input somewhere
        pos_ids = {v[0] for n in g.values() for k, v in n.get("inputs", {}).items()
                   if k == "positive" and isinstance(v, list)}
        # LTXVConditioning indirection: follow one more hop
        for pid_ in list(pos_ids):
            n = g.get(pid_, {})
            if n.get("class_type") != "CLIPTextEncode":
                for k, v in n.get("inputs", {}).items():
                    if k == "positive" and isinstance(v, list):
                        pos_ids.add(v[0])
        for pid_ in pos_ids:
            if g.get(pid_, {}).get("class_type") == "CLIPTextEncode":
                g[pid_]["inputs"]["text"] = prompt
    if overrides_json:
        for nid, ins in json.loads(overrides_json).items():
            if nid not in g:
                return (f"override error: no node '{nid}' in this workflow "
                        f"(node ids: {', '.join(sorted(g))})")
            g[nid].setdefault("inputs", {}).update(ins)
    return _execute(g, wait_timeout)


@mcp.tool()
def comfy_install_node(git_url: str, confirm: bool = False,
                       restart_timeout: int = 150) -> str:
    """DISRUPTIVE: clone a custom-node repo into custom_nodes/ and RESTART the
    ComfyUI service to load it. Requires confirm=True and host-side config
    (custom_nodes_dir + compose_file). Reports import success/failure honestly
    — packs with extra python deps need those baked into the image."""
    if not confirm:
        return "refused: pass confirm=True (this restarts ComfyUI)"
    if not (CFG["custom_nodes_dir"] and CFG["compose_file"]):
        return "custom_nodes_dir / compose_file not set in config.local.json"
    name = Path(git_url).stem
    dest = Path(CFG["custom_nodes_dir"]).expanduser() / name
    if dest.exists():
        return f"{dest} already exists"
    before = len(_object_info())
    r = subprocess.run(["git", "clone", "--depth", "1", git_url, str(dest)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode:
        return f"clone failed: {r.stderr[-500:]}"
    subprocess.run(["docker", "compose", "-f", CFG["compose_file"], "restart",
                    CFG["compose_service"]], capture_output=True, text=True,
                   timeout=restart_timeout)
    t0 = time.time()
    while time.time() - t0 < restart_timeout:
        try:
            CLIENT.get("/system_stats", timeout=3)
            break
        except Exception:  # noqa: BLE001
            time.sleep(3)
    _NODE_CACHE["data"] = None
    after = len(_object_info())
    log = comfy_logs(3000)
    fail = [ln for ln in log.splitlines() if "import" in ln.lower()
            and name.lower() in ln.lower() and "fail" in ln.lower()]
    return json.dumps({"installed": name, "node_classes_before": before,
                       "node_classes_after": after,
                       "import_errors": fail or None}, indent=1)


# --------------------------------------------------------- vpt9 media library

def _lib() -> httpx.Client:
    if not CFG.get("library_url"):
        raise RuntimeError("library_url not set in config.local.json")
    return httpx.Client(base_url=CFG["library_url"].rstrip("/"), timeout=120)


def _lib_collection(name: str) -> str:
    """Normalize to the library rule: Title Case, at most 2 words (strip any
    user-supplied 'collection:' prefix)."""
    if name.lower().startswith("collection:"):
        name = name.partition(":")[2]
    words = name.replace("_", " ").replace("-", " ").split()[:2]
    return " ".join(w.capitalize() for w in words) or "Untitled"


@mcp.tool()
def comfy_library_collections() -> str:
    """List the vpt9 media library's collections (folder-like groupings, from
    'collection:' tags) with item counts, plus the most-used loose tags.
    Read this before uploading so existing collections get reused."""
    try:
        lib = _lib()
    except RuntimeError as e:
        return str(e)
    state = lib.get("/state").json()
    media = state.get("media") or []
    colls: dict = {}
    loose: dict = {}
    for m in media if isinstance(media, list) else []:
        for t in (m.get("tags") or []) if isinstance(m, dict) else []:
            if not isinstance(t, str):
                continue
            if t.startswith("collection:"):
                key = t[len("collection:"):]
                colls[key] = colls.get(key, 0) + 1
            else:
                loose[t] = loose.get(t, 0) + 1
    top = dict(sorted(loose.items(), key=lambda kv: -kv[1])[:15])
    return json.dumps({"media_count": len(media), "collections": colls,
                       "loose_tags_top": top}, indent=1)


@mcp.tool()
def comfy_library_upload(file_path: str, collection: str, tags: str = "",
                         name: str = "") -> str:
    """Upload a file to the vpt9 media library. The server embeds the tags
    into the file itself (XMP dc:Subject) via the X-Media-Tags header — no
    exiftool needed. Formats: mp4 (h264 yuv420p), gif, jpg ONLY — PNGs must
    go through comfy_master_still first. collection: 1-2 words (Title-Cased
    automatically, becomes a folder in the library UI); tags: 2-5 loose
    descriptors ("loop, calm, gold"); name: display name (default: a
    descriptive form of the filename — never leave outputs called
    output_003). Reversible: comfy_library_delete removes by media id."""
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"no such file: {p}"
    suffix = ".jpg" if p.suffix.lower() == ".jpeg" else p.suffix.lower()
    if suffix not in (".mp4", ".gif", ".jpg"):
        return (f"unsupported format '{p.suffix}' — the library takes only "
                "mp4/gif/jpg. Stills: comfy_master_still converts to jpg; "
                "video: comfy_loop_video re-encodes to yuv420p mp4.")
    warnings = []
    if suffix == ".mp4":
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(p)],
                capture_output=True, text=True, check=True, timeout=60)
            pix = probe.stdout.strip()
            if pix and pix != "yuv420p":
                return (f"refused: {p.name} is {pix}; the library requires "
                        "yuv420p — re-encode with comfy_loop_video first")
        except (subprocess.CalledProcessError, FileNotFoundError):
            warnings.append("ffprobe unavailable — pix_fmt unverified")
    coll = _lib_collection(collection)
    loose = [t.strip() for t in tags.split(",") if t.strip()]
    if not 2 <= len(loose) <= 5:
        warnings.append(f"{len(loose)} loose tags (convention wants 2-5)")
    display = name or p.stem.replace("_", "-")
    if not display.lower().endswith(suffix):
        display += suffix
    try:
        lib = _lib()
    except RuntimeError as e:
        return str(e)
    r = lib.post("/api/media", content=p.read_bytes(),
                 headers={"X-File-Name": display,
                          "X-Media-Tags": ", ".join(
                              [f"collection:{coll}"] + loose)})
    if r.status_code >= 300:
        return f"HTTP {r.status_code}: {r.text[:400]}"
    media_id = None
    try:  # response shape undocumented — parse defensively
        j = r.json()
        media_id = (j.get("id") or j.get("media_id")
                    or (j.get("media") or {}).get("id"))
    except Exception:  # noqa: BLE001
        pass
    if media_id is None:
        try:  # fall back to a /state lookup by display name
            for m in _lib().get("/state").json().get("media", []):
                if isinstance(m, dict) and display in (
                        m.get("name"), m.get("file_name"), m.get("fileName")):
                    media_id = m.get("id")
        except Exception:  # noqa: BLE001
            pass
    return json.dumps({"uploaded": display, "collection": f"collection:{coll}",
                       "tags": loose, "media_id": media_id,
                       "warnings": warnings or None}, indent=1)


@mcp.tool()
def comfy_library_delete(media_ids: list[str] | None = None,
                         confirm: bool = False) -> str:
    """DESTRUCTIVE: delete media from the vpt9 library by id. Takes a LIST so
    one confirmed call can undo an entire batch upload. Requires
    confirm=True."""
    if not confirm:
        return "refused: pass confirm=True to delete library media"
    if not media_ids:
        return "no media_ids given"
    try:
        lib = _lib()
    except RuntimeError as e:
        return str(e)
    results = {}
    for mid in media_ids:
        r = lib.delete(f"/api/media/{mid}")
        results[str(mid)] = f"HTTP {r.status_code}"
    return json.dumps(results, indent=1)


# ------------------------------------------------------------ files & actions

@mcp.tool()
def comfy_upload_image(file_path: str, overwrite: bool = False) -> str:
    """Upload a local image into ComfyUI's input/ dir (for img2img/inpaint)."""
    try:
        return f"uploaded as: {_upload(file_path, overwrite)}"
    except FileNotFoundError as e:
        return str(e)


@mcp.tool()
def comfy_download_output(filename: str, subfolder: str = "",
                          file_type: str = "output") -> str:
    """Download one generated file from ComfyUI to the local output_dir."""
    return _download({"filename": filename, "subfolder": subfolder,
                      "type": file_type})


@mcp.tool()
def comfy_interrupt(confirm: bool = False) -> str:
    """DISRUPTIVE: stop the currently-executing prompt. Requires confirm=True."""
    if not confirm:
        return "refused: pass confirm=True to interrupt the running job"
    r = CLIENT.post("/interrupt")
    return f"HTTP {r.status_code} — interrupt sent"


@mcp.tool()
def comfy_cancel(prompt_ids: list[str] | None = None, clear_all: bool = False,
                 confirm: bool = False) -> str:
    """DISRUPTIVE: delete pending queue items (by id) or clear the whole queue.
    Requires confirm=True."""
    if not confirm:
        return "refused: pass confirm=True to cancel queue items"
    body = {"clear": True} if clear_all else {"delete": prompt_ids or []}
    r = CLIENT.post("/queue", json=body)
    return f"HTTP {r.status_code} — {json.dumps(body)}"


@mcp.tool()
def comfy_free(unload_models: bool = True, free_memory: bool = True,
               confirm: bool = False) -> str:
    """DISRUPTIVE: unload models / free VRAM (next run reloads from disk).
    NOTE: does NOT release the container's cgroup page cache — if generations
    OOM with free VRAM, restart the comfyui service instead."""
    if not confirm:
        return "refused: pass confirm=True to free model memory"
    r = CLIENT.post("/free", json={"unload_models": unload_models,
                                   "free_memory": free_memory})
    return f"HTTP {r.status_code} — free sent"


# ---------------------------------------------------------------- entrypoint

def _selftest() -> None:
    """Read-only smoke test (plus HF search network read). Off-LAN, checks
    that hit the ComfyUI host or the vpt9 library are expected to FAIL; the
    graph/motion/gate checks must always pass."""
    latest_png = next(iter(sorted(_outdir().glob("*.png"), reverse=True)), None)

    def check_i2v(loop: bool) -> str:
        g = G.ltxv_img2video("ltx.safetensors", "t5.safetensors", "img.png",
                             "t", "n", 768, 512, 97, 24, 1, 25, 3.0, loop=loop)
        g1, g2, smp, crop = "22", "23", "9", "24"
        last = g2 if loop else g1
        assert g[g1]["inputs"]["frame_idx"] == 0
        if loop:
            assert g[g2]["inputs"]["frame_idx"] == -1
            assert g[g2]["inputs"]["positive"] == [g1, 0]
            assert g[g2]["inputs"]["negative"] == [g1, 1]
            assert g[g2]["inputs"]["latent"] == [g1, 2]
        else:
            assert g2 not in g
        assert g["7"]["inputs"]["latent"] == [last, 2]
        assert g[smp]["inputs"]["positive"] == [last, 0]
        assert g[smp]["inputs"]["negative"] == [last, 1]
        assert g[smp]["inputs"]["latent_image"] == [last, 2]
        assert g[crop]["inputs"]["positive"] == [last, 0]
        assert g[crop]["inputs"]["negative"] == [last, 1]
        assert g[crop]["inputs"]["latent"] == [smp, 0]
        assert g["10"]["inputs"]["samples"] == [crop, 2]
        return f"edge wiring ok ({len(g)} nodes)"

    def check_hires() -> str:
        g = G.txt2img("sd_xl_base_1.0.safetensors", "t", "", 1024, 1024, 1,
                      20, 5.0, "euler", "normal", hires_scale=1.5)
        assert g["12"]["class_type"] == "LatentUpscaleBy"
        assert g["12"]["inputs"]["upscale_method"]
        assert g["12"]["inputs"]["scale_by"] == 1.5
        assert g["13"]["inputs"]["denoise"] == 0.25
        assert g["13"]["inputs"]["latent_image"] == ["12", 0]
        assert g["6"]["class_type"] == "VAEDecodeTiled"
        assert g["6"]["inputs"]["samples"] == ["13", 0]
        return "hires wiring ok"

    def check_motions() -> str:
        for m in _MOTIONS:
            chain, total, wrap = _motion_chain(m, 1920, 1080, 8.0, 30, 1.0, 0.8)
            assert "format=yuv420p" in chain
            assert wrap == (m == "tunnel")
            assert total == (264 if m == "tunnel" else 240)
        rot, _, _ = _motion_chain("rotate", 1920, 1080, 8.0, 30, 1.0, 0.8)
        assert "rotate=2*PI*1*n/240" in rot           # integer revolutions
        z, _, _ = _motion_chain("zoom_in", 1920, 1080, 8.0, 30, 1.0, 0.8)
        assert "zoompan=z='exp(" in z and "1-cos(2*PI*on/240)" in z
        d, _, _ = _motion_chain("drift", 1920, 1080, 8.0, 30, 1.0, 0.8)
        assert "mod(round(n*3840/240),3840)" in d     # integer periods
        p, _, _ = _motion_chain("pulse", 1920, 1080, 8.0, 30, 1.0, 0.8)
        assert "eval=frame" in p and "sin(2*PI*2*n/240)" in p
        try:
            _motion_chain("wiggle", 1920, 1080, 8.0, 30, 1.0, 0.8)
            raise AssertionError("unknown motion accepted")
        except ValueError:
            pass
        return f"{len(_MOTIONS)} motions ok"

    def check_lib_guard() -> str:
        saved = CFG.get("library_url")
        CFG["library_url"] = ""     # force the unset path regardless of config
        try:
            assert "library_url not set" in comfy_library_collections()
            return "guard ok"
        finally:
            CFG["library_url"] = saved

    def check_upload_validation() -> str:
        tmp = _outdir() / "selftest_reject.png"
        tmp.write_bytes(b"\x89PNG\r\n\x1a\n")
        try:                        # .png must be rejected before any network
            assert "unsupported format" in comfy_library_upload(
                str(tmp), "Test", "a, b")
            return "png rejected pre-network"
        finally:
            tmp.unlink(missing_ok=True)

    checks = [
        ("status", lambda: comfy_status()),
        ("models(folders)", lambda: comfy_models()),
        ("models(checkpoints,detailed)", lambda: comfy_models("checkpoints", True)[:200]),
        ("nodes(search=ltxv)", lambda: comfy_nodes("ltxv")[:200]),
        ("queue", lambda: comfy_queue()),
        ("history", lambda: comfy_history(max_items=3)[:300]),
        ("logs", lambda: comfy_logs(200)),
        ("output_files", lambda: comfy_output_files()[:200]),
        ("discover(video)", lambda: comfy_discover("video")),
        ("call(GET /features)", lambda: comfy_call("GET", "/features")[:150]),
        ("model_search(hf)", lambda: comfy_model_search("RealESRGAN", limit=3)[:300]),
        ("model_search(civitai)", lambda: comfy_model_search("upscale", "civitai", limit=2)[:300]),
        ("png_workflow", lambda: comfy_png_workflow(str(latest_png))[:200]
         if latest_png else "SKIP no png"),
        ("gate(interrupt)", lambda: comfy_interrupt()),
        ("gate(model_delete)", lambda: comfy_model_delete("loras", "x", False)),
        ("gate(install_node)", lambda: comfy_install_node("https://x/y")),
        ("graphs(txt2img+lora)", lambda: str(len(G.txt2img(
            "sd_xl_base_1.0.safetensors", "t", "", 1024, 1024, 1, 20, 5.0,
            "euler", "normal", "sdxl-simple-icons.safetensors:0.8")))),
        ("graphs(ltxv)", lambda: str(len(G.ltxv_txt2video(
            "ltx.safetensors", "t5.safetensors", "t", "n", 768, 512, 97, 24, 1, 25, 3.0)))),
        ("graphs(ltxv_i2v loop)", lambda: check_i2v(True)),
        ("graphs(ltxv_i2v noloop)", lambda: check_i2v(False)),
        ("graphs(txt2img hires)", lambda: check_hires()),
        ("motion(chains)", lambda: check_motions()),
        ("gate(library_delete)", lambda: comfy_library_delete(["x"], False)),
        ("library(config guard)", lambda: check_lib_guard()),
        ("library(upload validation)", lambda: check_upload_validation()),
    ]
    failed = 0
    for name, fn in checks:
        try:
            out = fn()
            print(f"OK   {name}: {str(out)[:110].replace(chr(10), ' ')}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        _selftest()
    mcp.run()
