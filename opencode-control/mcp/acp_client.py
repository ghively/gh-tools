"""Minimal Agent Client Protocol (ACP v1) client for driving `opencode acp`.

ACP is JSON-RPC 2.0 over stdio, newline-delimited (NDJSON). This client spawns
`opencode acp`, runs the initialize handshake (protocolVersion 1), opens a
session, sends a prompt, services the agent's callbacks (permission requests and
fs read/write), collects the streamed `session/update` notifications, and returns
a structured transcript.

Verified against the ACP v1 schema and opencode 1.18.3's acp implementation:
  * framing: newline-delimited JSON, no embedded newlines, UTF-8
  * initialize -> session/new {cwd, mcpServers:[]} -> session/prompt {sessionId, prompt:[blocks]}
  * agent->client requests: session/request_permission, fs/read_text_file, fs/write_text_file
  * agent->client notifications: session/update (agent_message_chunk, agent_thought_chunk,
    tool_call, tool_call_update, plan, available_commands_update, usage_update, ...)
  * opencode offers permission options: once / always / reject; approving an edit
    triggers fs/write_text_file back to us — so we MUST implement it for edits to land.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional


class ACPError(Exception):
    pass


class ACPSession:
    def __init__(self, opencode_bin: str = "opencode", cwd: str = "",
                 permission: str = "reject", log=None):
        self.bin = opencode_bin
        self.cwd = str(Path(cwd or os.path.expanduser("~")).resolve())
        # permission policy: "reject" (read-only), "allow" (allow_once), "always"
        self.permission = permission
        self._log = log or (lambda *a: None)
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        # transcript captured from session/update notifications
        self.updates: list[dict] = []
        self.text_chunks: list[str] = []
        self.thought_chunks: list[str] = []
        self.tool_calls: dict[str, dict] = {}
        self.plan: list = []
        self.commands: list = []
        self.usage: Optional[dict] = None
        self.permissions_seen: list[dict] = []
        self.files_written: list[str] = []
        self.agent_info: Optional[dict] = None
        self.session_id: Optional[str] = None

    # ---- transport -------------------------------------------------
    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            self.bin, "acp", "--cwd", self.cwd,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _send(self, obj: dict):
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        self.proc.stdin.write(line.encode())
        await self.proc.stdin.drain()

    async def _request(self, method: str, params: dict, timeout: float = 300) -> Any:
        self._id += 1
        rid = self._id
        fut = asyncio.get_event_loop().create_future()
        self._pending[rid] = fut
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(rid, None)

    async def _notify(self, method: str, params: dict):
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _reply(self, rid, result=None, error=None):
        msg = {"jsonrpc": "2.0", "id": rid}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result if result is not None else {}
        await self._send(msg)

    async def _read_loop(self):
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            await self._dispatch(msg)
        # process ended: fail any pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ACPError("opencode acp process exited"))

    async def _dispatch(self, msg: dict):
        # response to one of our requests
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.get(msg["id"])
            if fut and not fut.done():
                if "error" in msg:
                    fut.set_exception(ACPError(json.dumps(msg["error"])))
                else:
                    fut.set_result(msg["result"])
            return
        method = msg.get("method")
        # agent -> client request (needs a reply)
        if method and "id" in msg:
            await self._handle_request(msg["id"], method, msg.get("params") or {})
            return
        # notification
        if method:
            await self._handle_notification(method, msg.get("params") or {})

    # ---- agent->client handlers -----------------------------------
    async def _handle_request(self, rid, method: str, params: dict):
        if method == "session/request_permission":
            self.permissions_seen.append(params)
            opts = {o.get("kind"): o.get("optionId") for o in params.get("options", [])}
            if self.permission == "always":
                pick = opts.get("allow_always") or opts.get("allow_once")
            elif self.permission == "allow":
                pick = opts.get("allow_once") or opts.get("allow_always")
            else:  # reject (read-only)
                pick = None
            if pick:
                await self._reply(rid, {"outcome": {"outcome": "selected", "optionId": pick}})
            else:
                # reject_once, else cancelled
                rej = opts.get("reject_once")
                if rej:
                    await self._reply(rid, {"outcome": {"outcome": "selected", "optionId": rej}})
                else:
                    await self._reply(rid, {"outcome": {"outcome": "cancelled"}})
            return
        if method == "fs/read_text_file":
            try:
                p = Path(params["path"])
                text = p.read_text()
                line = params.get("line")
                limit = params.get("limit")
                if line is not None or limit is not None:
                    lines = text.splitlines()
                    start = (line - 1) if line else 0
                    end = start + limit if limit else len(lines)
                    text = "\n".join(lines[start:end])
                await self._reply(rid, {"content": text})
            except Exception as e:  # noqa: BLE001
                await self._reply(rid, error={"code": -32000, "message": str(e)})
            return
        if method == "fs/write_text_file":
            # only lands because a permission was already approved above
            try:
                p = Path(params["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(params.get("content", ""))
                self.files_written.append(str(p))
                await self._reply(rid, {})
            except Exception as e:  # noqa: BLE001
                await self._reply(rid, error={"code": -32000, "message": str(e)})
            return
        # unknown request -> method not found
        await self._reply(rid, error={"code": -32601, "message": f"method not found: {method}"})

    async def _handle_notification(self, method: str, params: dict):
        if method != "session/update":
            return
        upd = params.get("update") or {}
        kind = upd.get("sessionUpdate")
        self.updates.append(upd)
        if kind == "agent_message_chunk":
            self.text_chunks.append(_content_text(upd.get("content")))
        elif kind == "agent_thought_chunk":
            self.thought_chunks.append(_content_text(upd.get("content")))
        elif kind in ("tool_call", "tool_call_update"):
            tid = upd.get("toolCallId") or f"t{len(self.tool_calls)}"
            cur = self.tool_calls.get(tid, {})
            cur.update({k: v for k, v in upd.items() if v is not None})
            self.tool_calls[tid] = cur
        elif kind == "plan":
            self.plan = upd.get("entries", [])
        elif kind == "available_commands_update":
            self.commands = upd.get("availableCommands", upd.get("commands", []))
        elif kind == "usage_update":
            self.usage = upd

    # ---- high-level flow ------------------------------------------
    async def initialize(self):
        res = await self._request("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": True, "writeTextFile": True},
                "terminal": False,
            },
            "clientInfo": {"name": "opencode-control-mcp", "version": "0.1.0"},
        }, timeout=30)
        self.agent_info = res.get("agentInfo")
        return res

    async def new_session(self, mcp_servers: Optional[list] = None) -> str:
        res = await self._request("session/new", {
            "cwd": self.cwd, "mcpServers": mcp_servers or [],
        }, timeout=60)
        self.session_id = res.get("sessionId")
        return self.session_id

    async def set_mode(self, mode: str):
        try:
            await self._request("session/set_mode",
                                {"sessionId": self.session_id, "modeId": mode}, timeout=20)
        except Exception:  # noqa: BLE001
            pass

    async def prompt(self, text: str, files: Optional[list] = None,
                     timeout: float = 300) -> dict:
        blocks: list = [{"type": "text", "text": text}]
        for f in (files or []):
            blocks.append({"type": "resource_link", "uri": f"file://{Path(f).resolve()}",
                           "name": Path(f).name})
        res = await self._request("session/prompt", {
            "sessionId": self.session_id, "prompt": blocks,
        }, timeout=timeout)
        return res

    async def cancel(self):
        if self.session_id:
            await self._notify("session/cancel", {"sessionId": self.session_id})

    async def close(self):
        try:
            if self.proc and self.proc.returncode is None:
                self.proc.terminate()
                try:
                    await asyncio.wait_for(self.proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        if self._reader_task:
            self._reader_task.cancel()

    def transcript(self) -> dict:
        return {
            "session_id": self.session_id,
            "agent": self.agent_info,
            "reply_text": "".join(self.text_chunks).strip(),
            "reasoning": "".join(self.thought_chunks).strip() or None,
            "tool_calls": [
                {"title": t.get("title"), "kind": t.get("kind"),
                 "status": t.get("status")} for t in self.tool_calls.values()
            ],
            "plan": self.plan or None,
            "commands_available": [c.get("name") for c in self.commands] or None,
            "permissions_requested": len(self.permissions_seen),
            "files_written": self.files_written or None,
            "usage": self.usage,
        }


def _content_text(content: Any) -> str:
    if isinstance(content, dict):
        if content.get("type") == "text":
            return content.get("text", "")
        return f"[{content.get('type')}]"
    if isinstance(content, str):
        return content
    return ""


async def run_prompt(prompt: str, *, opencode_bin: str = "opencode", cwd: str = "",
                     files: Optional[list] = None, mode: str = "",
                     permission: str = "reject", timeout: float = 300,
                     mcp_servers: Optional[list] = None) -> dict:
    """One-shot: spawn opencode acp, run a single prompt, return the transcript
    plus the final stopReason."""
    sess = ACPSession(opencode_bin=opencode_bin, cwd=cwd, permission=permission)
    try:
        await sess.start()
        init = await sess.initialize()
        await sess.new_session(mcp_servers=mcp_servers)
        if mode:
            await sess.set_mode(mode)
        result = await sess.prompt(prompt, files=files, timeout=timeout)
        out = sess.transcript()
        out["stop_reason"] = result.get("stopReason")
        out["init"] = {"protocolVersion": init.get("protocolVersion"),
                       "authMethods": [m.get("id") for m in init.get("authMethods", [])]}
        return out
    finally:
        await sess.close()
