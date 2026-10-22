# Mock walkthrough — no account, no credentials

Runs the real `sabnzbd-control` MCP server (unchanged) against a 100-line fake SABnzbd API
on localhost, over MCP stdio, and checks the behaviours that matter when an agent is given
control of a live system.

```bash
python3 examples/mock-walkthrough/run_demo.py      # needs uv; nothing else
```

| Step | What is checked |
|---|---|
| 1 | MCP `initialize` + `tools/list`; every tool publishes an input schema |
| 2 | Safe read: `sabnzbd_status` returns version and queue state |
| 3 | `sabnzbd_pause` without `confirm` returns `confirmation_required` **and the mock's request log shows no pause call was sent** |
| 4 | Wrong API key: server reports `401 Unauthorized` as a structured error |
| 5 | HTTP 429 from the API: structured error, server keeps running |
| 6 | `sabnzbd_pause(confirm=true)` pauses; `sabnzbd_resume(confirm=true)` restores |

The mock (`mock_sabnzbd.py`) logs every request it receives, so step 3 is proven from the
server side, not from the tool's own claim. Expected output ends with `6/6 steps passed` and a
table of the requests that reached the API.

CI runs this walkthrough and `scripts/mcp_handshake_test.py` (all 14 servers) on every push.
Live verification against real systems is separate and is not claimed by these checks.
