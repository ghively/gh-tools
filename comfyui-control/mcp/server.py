#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0", "httpx>=0.27", "websockets>=12"]
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
           "compose_service": "comfyui"}
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
    dest = _outdir() / o["filename"].replace("/", "_")
    r = CLIENT.get("/view", params={"filename": o["filename"],
                                    "subfolder": o.get("subfolder", ""),
                                    "type": o.get("type", "output")})
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
                  tiled_vae: bool = False, wait_timeout: int = 240) -> str:
    """Text-to-image. checkpoint defaults to the first installed image model;
    SD3-family gets TripleCLIPLoader automatically. loras: comma list of
    'name.safetensors:strength'. Returns local file paths + per-node timings."""
    checkpoint = _default_checkpoint(checkpoint)
    g = G.txt2img(checkpoint, prompt, negative, width, height, _seed(seed),
                  steps, cfg, sampler, scheduler, loras, tiled_vae)
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
                  steps, cfg, "euler", "normal", loras)
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


def _to_gif(video_path: str, fps: int = 12, width: int = 480,
            loop: str = "crossfade", fade: float = 0.8) -> str:
    """High-quality mp4 -> GIF via ffmpeg two-pass palette.
    loop modes: 'crossfade' (DEFAULT — forward-only playback, the tail blends
    into the head so it wraps invisibly; output shortens by `fade` seconds),
    'palindrome' (forward-then-reverse boomerang), 'none' (plain cut)."""
    src = Path(video_path)
    gif = src.with_suffix(".gif")
    vf = f"fps={fps},scale={width}:-1:flags=lanczos"
    palette = (f"split[s0][s1];[s0]palettegen=stats_mode=diff[p];"
               f"[s1][p]paletteuse=dither=bayer:bayer_scale=4")
    if loop == "crossfade":
        d = _duration(src)
        if d <= 2 * fade + 0.2:
            fade = max(0.2, d / 4)
        chain = (f"[0:v]trim=start={fade},setpts=PTS-STARTPTS[main];"
                 f"[0:v]trim=duration={fade},setpts=PTS-STARTPTS[head];"
                 f"[main][head]xfade=transition=fade:duration={fade}:"
                 f"offset={d - 2 * fade},{vf},{palette}")
    elif loop == "palindrome":
        chain = (f"[0:v]{vf},split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1,"
                 f"{palette}")
    else:
        chain = f"[0:v]{vf},{palette}"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src),
         "-filter_complex", chain, str(gif)],
        check=True, capture_output=True, timeout=600)
    return str(gif)


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
    cps = CLIENT.get("/models/checkpoints").json()
    ltx = [c for c in cps if "ltx" in c.lower()]
    if not ltx:
        return ("no LTX-Video checkpoint installed. Fix: comfy_model_download("
                "hf_repo='Lightricks/LTX-Video', hf_file='ltx-video-2b-v0.9.5.safetensors', "
                "folder='checkpoints') (~6GB)")
    t5s = [t for t in CLIENT.get("/models/text_encoders").json() if "t5" in t.lower()]
    if not t5s:
        return "no T5 text encoder in text_encoders/ — LTXV needs t5xxl"
    if (frames - 1) % 8:
        frames = 8 * round((frames - 1) / 8) + 1
    g = G.ltxv_txt2video(ltx[0], t5s[0], prompt, negative, width, height,
                         frames, fps, _seed(seed), steps, cfg)
    out = _execute(g, wait_timeout)
    if gif:
        try:
            res = json.loads(out)
            vids = [f for f in res.get("outputs", []) if f.endswith((".mp4", ".webm"))]
            res["gifs"] = [_to_gif(v) for v in vids]
            return json.dumps(res, indent=1)
        except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
            return out + f"\n(gif conversion failed: {e})"
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
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(1 << 22):
                f.write(chunk)
                done += len(chunk)
                if done % (1 << 29) < (1 << 22):
                    print(f"[dl] {filename}: {done/1e9:.1f}/{total/1e9:.1f}GB",
                          file=sys.stderr)
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
            g.setdefault(nid, {}).setdefault("inputs", {}).update(ins)
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
    """Read-only smoke test (plus HF search network read)."""
    latest_png = next(iter(sorted(_outdir().glob("*.png"), reverse=True)), None)
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
