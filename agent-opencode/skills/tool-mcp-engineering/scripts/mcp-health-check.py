#!/usr/bin/env python3
"""MCP stdio server health monitor.

Usage:
  python scripts/mcp-health-check.py path/to/mcp-servers.yaml

Expected config format, YAML or JSON:
  servers:
    example:
      command: node
      args: ["/absolute/path/to/dist/server.js"]
      cwd: "/optional/working/directory"
      env:
        API_BASE: "https://api.example.com"
      timeout: 30
      enabled: true

For each enabled server, this script launches the command over stdio, sends
initialize + notifications/initialized + tools/list, and prints a JSON result.
It exits 1 if any enabled server is broken.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "agent-foundry-mcp-health", "version": "1.0"},
    },
}
INITED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required for YAML config files; use JSON or install pyyaml") from exc
    return yaml.safe_load(text) or {}


def read_response(proc: subprocess.Popen[bytes], want_id: int, deadline: float) -> dict[str, Any] | None:
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 1.0))
        if not ready:
            continue
        line = proc.stdout.readline() if proc.stdout else b""
        if not line:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == want_id:
            return msg
    return None


def probe(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    cmd = [str(spec["command"]), *[str(arg) for arg in spec.get("args", [])]]
    env = {**os.environ, **{str(k): str(v) for k, v in (spec.get("env") or {}).items()}}
    timeout = min(float(spec.get("timeout", 30)), 60.0)
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=spec.get("cwd"),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
        )
    except FileNotFoundError as exc:
        return {"name": name, "status": "broken", "error_class": "FileNotFoundError", "error": str(exc), "tool_count": 0}

    deadline = time.monotonic() + timeout

    def send(msg: dict[str, Any]) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        proc.stdin.flush()

    try:
        send(INIT)
        init_resp = read_response(proc, 1, deadline)
        if not init_resp or init_resp.get("error"):
            err = (init_resp or {}).get("error", {}).get("message", "initialize timed out")
            return {"name": name, "status": "broken", "error_class": "InitializeFailed", "error": err, "tool_count": 0}
        send(INITED)
        send(TOOLS)
        tools_resp = read_response(proc, 2, deadline)
        if not tools_resp:
            return {"name": name, "status": "broken", "error_class": "ToolsListTimeout", "error": "tools/list timed out", "tool_count": 0}
        if tools_resp.get("error"):
            return {"name": name, "status": "broken", "error_class": "ToolsListError", "error": tools_resp["error"].get("message"), "tool_count": 0}
        tools = tools_resp.get("result", {}).get("tools", [])
        return {"name": name, "status": "up", "error_class": None, "error": None, "tool_count": len(tools)}
    except Exception as exc:
        return {"name": name, "status": "broken", "error_class": type(exc).__name__, "error": str(exc), "tool_count": 0}
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        probe.last_duration_ms = duration_ms  # type: ignore[attr-defined]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path, help="YAML/JSON file containing servers mapping")
    args = parser.parse_args()
    cfg = load_config(args.config)
    servers = cfg.get("servers") or cfg.get("mcpServers") or cfg.get("mcp_servers") or {}
    results = []
    for name in sorted(servers):
        spec = servers[name] or {}
        if spec.get("enabled") is False:
            continue
        result = probe(name, spec)
        result["duration_ms"] = getattr(probe, "last_duration_ms", None)
        results.append(result)
        print(json.dumps(result, sort_keys=True))
    return 1 if any(r["status"] != "up" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
