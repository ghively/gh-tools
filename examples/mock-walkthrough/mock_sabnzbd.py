#!/usr/bin/env python3
"""A tiny fake SABnzbd /api for the no-credential walkthrough. Stdlib only.

Implements just enough of SABnzbd's mode-based API for the walkthrough:
version, fullstatus, queue, warnings, pause, resume. Every request is
appended to a JSON-lines log so the demo can prove what did (and did not)
reach the "server". Special behaviours, toggled by the demo over /_control:

* api key other than ``demo-key``  -> HTTP 401
* ``rate_limit`` armed              -> the next /api call returns HTTP 429
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

API_KEY = "demo-key"
STATE = {"paused": False, "rate_limit": False}
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "mock-requests.jsonl"
QUEUE = {
    "paused": False, "speed": "0 ", "speedlimit": "100", "speedlimit_abs": "",
    "diskspace1": "812.4", "diskspace2": "812.4", "diskspacetotal1": "931.5",
    "have_warnings": "0", "noofslots": 2, "status": "Idle", "timeleft": "0:00:00",
    "sizeleft": "0 B", "slots": [
        {"nzo_id": "SABnzbd_nzo_demo1", "filename": "example.linux.iso", "status": "Queued"},
        {"nzo_id": "SABnzbd_nzo_demo2", "filename": "example.dataset.tar", "status": "Queued"},
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep stdout clean
        pass

    def _send(self, code: int, body: dict | str) -> None:
        data = (json.dumps(body) if isinstance(body, dict) else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json" if isinstance(body, dict) else "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/_control":
            STATE.update({k: v == "1" for k, v in q.items() if k in STATE})
            return self._send(200, {"ok": True, **STATE})
        if u.path != "/api":
            return self._send(404, "not found")
        mode = q.get("mode", "")
        entry = {"mode": mode, "key_ok": q.get("apikey") == API_KEY}
        if STATE["rate_limit"]:
            STATE["rate_limit"] = False
            entry["status"] = 429
            self._log(entry)
            return self._send(429, "Too Many Requests")
        if not entry["key_ok"]:
            entry["status"] = 401
            self._log(entry)
            return self._send(401, "API Key Incorrect")
        entry["status"] = 200
        self._log(entry)
        if mode == "version":
            return self._send(200, {"version": "4.4.0-mock"})
        if mode == "fullstatus":
            return self._send(200, {"status": {"paused": STATE["paused"], "loadavg": "0.10"}})
        if mode == "queue":
            return self._send(200, {"queue": {**QUEUE, "paused": STATE["paused"]}})
        if mode == "warnings":
            return self._send(200, {"warnings": []})
        if mode in ("pause", "resume"):
            STATE["paused"] = mode == "pause"
            return self._send(200, {"status": True})
        return self._send(200, {"error": f"mode {mode} not implemented in mock"})

    def _log(self, entry: dict) -> None:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 18080
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
