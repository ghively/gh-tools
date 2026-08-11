#!/usr/bin/env python3
"""Boot every MCP server, run the MCP handshake, list tools, validate schemas.

No credentials needed: uses config.example.json so servers have a base URL,
but never calls any tool that hits the network.
"""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_VAR = {
    "radarr-control": "RADARR_CONFIG", "sonarr-control": "SONARR_CONFIG",
    "sabnzbd-control": "SABNZBD_CONFIG", "tdarr-control": "TDARR_CONFIG",
    "searxng-control": "SEARXNG_CONFIG", "comfyui-control": "COMFYUI_CONFIG",
    "opencode-control": "OPENCODE_CONFIG", "romm": "ROMM_CONFIG",
    "romarr": "ROMARR_CONFIG", "emby": "EMBY_CONFIG", "gitlab": "GITLAB_CONFIG",
    "unifi": "UNIFI_CONFIG", "synology-nas": "SYNOLOGY_CONFIG",
    "unraid-control": "UNRAID_CONFIG",
}

def rpc(msg): return (json.dumps(msg) + "\n").encode()

results = []
for plugin, envvar in ENV_VAR.items():
    server = next((ROOT / plugin / "mcp").glob("*server*.py"), None) or ROOT / plugin / "mcp" / "server.py"
    env = dict(os.environ)
    env[envvar] = str(ROOT / plugin / "config.example.json")
    env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env["PATH"]
    try:
        p = subprocess.Popen(
            ["uv", "run", "--script", str(server)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, cwd=ROOT / plugin,
        )
        p.stdin.write(rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                       "clientInfo": {"name": "handshake-test", "version": "0"}}}))
        p.stdin.write(rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        p.stdin.write(rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        p.stdin.flush()
        tools, ok, err = None, False, ""
        deadline = time.time() + 45
        while time.time() < deadline:
            line = p.stdout.readline()
            if not line:
                break
            try:
                m = json.loads(line)
            except Exception:
                err = f"NON-JSON ON STDOUT: {line[:120]!r}"
                break
            if m.get("id") == 2:
                tools = m.get("result", {}).get("tools", [])
                ok = True
                break
        p.kill()
        if ok:
            bad = [t["name"] for t in tools
                   if not isinstance(t.get("inputSchema"), dict) or "properties" not in t.get("inputSchema", {})]
            note = f" schema-warn:{bad[:3]}" if bad else ""
            results.append((plugin, f"OK  {len(tools)} tools{note}"))
        else:
            stderr_tail = p.stderr.read().decode(errors="replace").strip().splitlines()[-2:]
            results.append((plugin, f"FAIL {err or 'no tools/list reply'} | stderr: {' / '.join(stderr_tail)}"))
    except Exception as e:
        results.append((plugin, f"FAIL {e}"))

width = max(len(r[0]) for r in results)
for name, res in results:
    print(f"{name:<{width}}  {res}")
fails = [r for r in results if r[1].startswith("FAIL")]
print(f"\n{len(results) - len(fails)}/{len(results)} servers pass MCP handshake + tools/list")
sys.exit(1 if fails else 0)
