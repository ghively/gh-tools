#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.4.0,<2.0.0",
#   "httpx>=0.27",
#   "websockets>=12",
# ]
# ///
"""Smoke test the comfyui MCP server against the live system.

Imports server.py, then calls each curated read-only tool and prints the
result shape. Does NOT call any confirm-gated write tool and submits no
generation jobs. Exits 0 with a notice when no config.local.json exists
(nothing to test against). Run with:
    cd comfyui-control && uv run --script mcp/_smoketest.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_config = _here.parent / "config.local.json"
if not os.environ.get("COMFYUI_CONFIG"):
    if not _config.exists():
        print(f"SKIP: no {_config} and COMFYUI_CONFIG unset — nothing to smoke-test.")
        sys.exit(0)
    os.environ["COMFYUI_CONFIG"] = str(_config)

# Import the server module (it's a uv-script; we need to import it as a module)
sys.path.insert(0, str(_here))
import importlib.util
spec = importlib.util.spec_from_file_location("server", _here / "server.py")
server = importlib.util.module_from_spec(spec)
# __name__ != "__main__" inside exec_module, so mcp.run() is not invoked
spec.loader.exec_module(server)


def show(name: str, result) -> bool:
    print(f"\n=== {name} ===")
    text = str(result)
    if len(text) > 800:
        text = text[:800] + f"\n  ... ({len(text)} total chars)"
    print(text)
    return True


tools = [
    ("comfy_status",                server.comfy_status),
    ("comfy_discover (video)",      lambda: server.comfy_discover("video")),
    ("comfy_models (folders)",      lambda: server.comfy_models()),
    ("comfy_models (checkpoints)",  lambda: server.comfy_models("checkpoints", detailed=True)),
    ("comfy_nodes (ltxv)",          lambda: server.comfy_nodes("ltxv")),
    ("comfy_queue",                 server.comfy_queue),
    ("comfy_history",               lambda: server.comfy_history(max_items=3)),
    ("comfy_logs",                  lambda: server.comfy_logs(tail_chars=300)),
    ("comfy_output_files",          lambda: server.comfy_output_files()),
    ("comfy_call (GET /features)",  lambda: server.comfy_call("GET", "/features")),
    # confirm-gates must refuse without touching the host
    ("gate: comfy_interrupt",       lambda: server.comfy_interrupt()),
    ("gate: comfy_cancel",          lambda: server.comfy_cancel(["x"])),
    ("gate: comfy_free",            lambda: server.comfy_free()),
    ("gate: comfy_model_delete",    lambda: server.comfy_model_delete("loras", "x")),
    ("gate: comfy_library_delete",  lambda: server.comfy_library_delete(["x"])),
    ("gate: comfy_install_node",    lambda: server.comfy_install_node("https://x/y")),
    # offline graph builders (no network)
    ("graph: txt2img+lora+hires",   lambda: f"{len(server.G.txt2img('sd_xl_base_1.0.safetensors', 't', '', 1024, 1024, 1, 20, 5.0, 'euler', 'normal', 'a.safetensors:0.8', False, 1.5))} nodes"),
    ("graph: ltxv_img2video loop",  lambda: f"{len(server.G.ltxv_img2video('ltx.safetensors', 't5.safetensors', 'i.png', 't', 'n', 768, 512, 97, 24, 1, 25, 3.0, loop=True))} nodes"),
]

ok = 0
fail = 0
for name, fn in tools:
    try:
        result = fn()
        if show(name, result):
            ok += 1
        else:
            fail += 1
    except Exception as e:
        print(f"\n=== {name} ===\n  EXCEPTION: {e}")
        fail += 1

print(f"\n{'=' * 40}\n{ok} OK, {fail} FAIL")
sys.exit(0 if fail == 0 else 1)
