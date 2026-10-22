#!/usr/bin/env python3
"""No-credential walkthrough: drive the real sabnzbd-control MCP server against a mock.

Steps (each prints PASS/FAIL; exit code is non-zero if any step fails):

1. MCP handshake: initialize + tools/list, every tool has an input schema.
2. Safe read: sabnzbd_status returns version and queue state from the mock.
3. Denied write: sabnzbd_pause without confirm returns confirmation_required
   and the mock log proves no pause request was sent.
4. Bad credential: a server started with the wrong API key reports 401 cleanly.
5. Rate limit: a 429 from the API surfaces as a structured error, not a crash.
6. Approved write: sabnzbd_pause(confirm=true) pauses the mock queue; resume restores it.

Requires: uv (the server is a PEP 723 script). No network beyond localhost after
uv has fetched the server's two dependencies.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SERVER = ROOT / "sabnzbd-control" / "mcp" / "server.py"
results: list[tuple[str, bool, str]] = []


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class McpClient:
    def __init__(self, port: int, api_key: str):
        env = dict(os.environ)
        env.update({
            "SABNZBD_CONFIG": str(ROOT / "sabnzbd-control" / "config.example.json"),
            "SABNZBD_HOST": "127.0.0.1", "SABNZBD_PORT": str(port),
            "SABNZBD_API_KEY": api_key, "SABNZBD_TIMEOUT": "5",
        })
        self.p = subprocess.Popen(["uv", "run", "--quiet", "--script", str(SERVER)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True)
        self.n = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method,
                                       "params": params or {}}) + "\n")
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("server exited")
            msg = json.loads(line)
            if msg.get("id") == self.n:
                return msg

    def notify(self, method: str) -> None:
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.p.stdin.flush()

    def start(self) -> dict:
        r = self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                        "clientInfo": {"name": "mock-walkthrough", "version": "1"}})
        self.notify("notifications/initialized")
        return r

    def tool(self, name: str, **args) -> dict:
        r = self.request("tools/call", {"name": name, "arguments": args})
        res = r.get("result", {})
        if res.get("structuredContent") is not None:
            sc = res["structuredContent"]
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
        text = "".join(c.get("text", "") for c in res.get("content", []))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_text": text}

    def close(self) -> None:
        self.p.kill()


def step(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def modes(log: Path) -> list[str]:
    return [json.loads(x)["mode"] for x in log.read_text().splitlines()] if log.exists() else []


def control(port: int, **kw) -> None:
    q = "&".join(f"{k}={v}" for k, v in kw.items())
    urllib.request.urlopen(f"http://127.0.0.1:{port}/_control?{q}", timeout=5).read()


def main() -> int:
    port = free_port()
    log = Path(tempfile.mkdtemp()) / "mock-requests.jsonl"
    mock = subprocess.Popen([sys.executable, str(HERE / "mock_sabnzbd.py"), str(port), str(log)])
    for _ in range(50):
        try:
            control(port)
            break
        except OSError:
            time.sleep(0.1)
    c = McpClient(port, "demo-key")
    try:
        init = c.start()
        tools = c.request("tools/list")["result"]["tools"]
        bad = [t["name"] for t in tools if "properties" not in t.get("inputSchema", {})]
        step("1. MCP handshake + tools/list", bool(tools) and not bad,
             f"server={init['result']['serverInfo']['name']}, {len(tools)} tools, all with input schemas")

        st = c.tool("sabnzbd_status")
        step("2. Safe read (sabnzbd_status)", st.get("version") == "4.4.0-mock" and st.get("noofslots") == 2,
             f"version={st.get('version')} paused={st.get('paused')} slots={st.get('noofslots')}")

        before = modes(log).count("pause")
        denied = c.tool("sabnzbd_pause")
        sent = modes(log).count("pause") - before
        step("3. Write without confirm is refused, nothing sent", denied.get("confirmation_required") is True and sent == 0,
             f"confirmation_required={denied.get('confirmation_required')}, pause requests reaching API={sent}")

        control(port, rate_limit=1)
        rl = c.tool("sabnzbd_version")
        step("5. HTTP 429 surfaces as a structured error", "error" in rl and "429" in rl["error"],
             rl.get("error", "")[:70])

        ok = c.tool("sabnzbd_pause", confirm=True)
        paused = c.tool("sabnzbd_status").get("paused")
        c.tool("sabnzbd_resume", confirm=True)
        resumed = c.tool("sabnzbd_status").get("paused")
        step("6. Approved write pauses, resume restores", paused is True and resumed is False,
             f"pause→paused={paused}, resume→paused={resumed}, call={json.dumps(ok)[:40]}")
    finally:
        c.close()

    bad_c = McpClient(port, "wrong-key")
    try:
        bad_c.start()
        r = bad_c.tool("sabnzbd_version")
        step("4. Wrong API key reports 401 cleanly", "error" in r and "401" in r["error"], r.get("error", "")[:70])
    finally:
        bad_c.close()
        mock.terminate()

    results.sort(key=lambda r: int(r[0].split(".")[0]))
    print("\nRequests that reached the mock API (mode, key_ok, status):")
    for x in log.read_text().splitlines():
        e = json.loads(x)
        print(f"  {e['mode']:<11} key_ok={e['key_ok']!s:<5} {e['status']}")
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
