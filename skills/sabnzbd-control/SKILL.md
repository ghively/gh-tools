---
name: sabnzbd-control
description: >-
  Control and administer a SABnzbd usenet downloader via the sabnzbd MCP
  server. Use this whenever the user wants to inspect, configure, operate,
  or troubleshoot SABnzbd — including ANY of: server status / version /
  current speed / pause state, the active download queue (with per-slot
  detail), completed and failed history, per-server byte totals, recent
  warnings, full configuration, OR queue control (pause, resume, speed
  limit), job management (add by URL, delete, retry), config updates,
  restart, and shutdown. Trigger this skill whenever the user says
  "SABnzbd", "my usenet downloader", "what's downloading", "pause the
  queue", "resume downloads", "add this NZB", or "why did this download
  fail" — do not answer from memory; drive the live SABnzbd server through
  the tools.
metadata:
  hermes:
    tags: [sabnzbd, usenet, nzb, downloader, mcp, homelab, media]
    category: media
    requires_tools: [sabnzbd_status]
    config:
      - {key: sabnzbd.host, prompt: SABnzbd host/IP, default: 192.0.2.20}
      - {key: sabnzbd.port, prompt: SABnzbd port, default: 8080}
required_environment_variables:
  - name: SABNZBD_API_KEY
    prompt: SABnzbd API key (Config > General > API Key)
    required_for: authenticating sabnzbd_* mode-based API calls
version: 0.3.0
author: ghively
---

# SABnzbd control

This skill drives a real SABnzbd usenet downloader through the **`sabnzbd`
MCP server** (tools shown as `sabnzbd_*`). Verified against **SABnzbd
5.x** on the homelab NAS (`192.0.2.20:8080`, "NAS-Host"). Auth =
`apikey` query parameter (admin API key in 1Password "Homelab" vault,
item `SABnzbd API Key`).

## Mental model

SABnzbd is one mode-based HTTP API at `/api?mode=<name>&output=json&apikey=`.
There is NO REST/OpenAPI surface; the catalog is hand-enumerated from the
official SABnzbd API wiki + live probes.

Key conventions:

- All writes are **confirm-gated** (`confirm=True`).
- `restart` and `shutdown` are DOUBLY gated — they need both `confirm=true`
  AND a typed `acknowledge="restart"` / `"shutdown"` token. SABnzbd honors
  these modes literally; `shutdown` takes the server offline until manually
  restarted (no auto-restart). DO NOT call these without explicit owner
  approval and a recovery plan.
- SABnzbd returns `{"error": "..."}` for most failures with HTTP 200 — the
  client surfaces this as a raised exception.

Two layers: curated tools (prefer), generic passthrough
(`sabnzbd_call` / `sabnzbd_list_modes`).

**Golden rule:** if a curated tool exists, use it. Otherwise find the mode
with `sabnzbd_list_modes` then call it with `sabnzbd_call`.

## Start here

Call **`sabnzbd_status`** first: version, paused state, current speed,
speed limit, queue summary, disk space, recent warnings. This is the cheapest
non-trivial health check.

## Tool map

| Job | Tool |
|---|---|
| Health snapshot | `sabnzbd_status` |
| Just the version | `sabnzbd_version()` (cheapest liveness check) |
| Active queue | `sabnzbd_queue(limit=, search=)` |
| Completed / failed | `sabnzbd_history(limit=, search=)` |
| Per-server bytes | `sabnzbd_server_stats()` |
| Warnings | `sabnzbd_warnings()` |
| Read config | `sabnzbd_get_config(section=, keyword=)` |
| List categories | `sabnzbd_categories()` |
| List post-proc scripts | `sabnzbd_scripts()` |
| Pause queue (write) | `sabnzbd_pause(minutes=, confirm=)` |
| Resume queue (write) | `sabnzbd_resume(confirm=)` |
| Pause ONE job (write) | `sabnzbd_pause_job(nzo_id=, confirm=)` |
| Resume ONE job (write) | `sabnzbd_resume_job(nzo_id=, confirm=)` |
| Set speed limit (write) | `sabnzbd_speed_limit(value=, confirm=)` |
| Add NZB by URL (write) | `sabnzbd_add_url(url=, pp=, category=, priority=, confirm=)` |
| Add server-side NZB file (write) | `sabnzbd_add_local_file(path=, pp=, category=, priority=, confirm=)` |
| Delete jobs (write) | `sabnzbd_delete_jobs(nzo_ids=, delete_files=, from_history=, confirm=)` |
| Retry a failed job (write) | `sabnzbd_retry_job(nzo_id=, confirm=)` |
| Change a job's category (write) | `sabnzbd_queue_change_category(nzo_id=, category=, confirm=)` |
| Change a job's priority (write) | `sabnzbd_queue_change_priority(nzo_id=, priority=, confirm=)` |
| Clear history (write) | `sabnzbd_history_clear(failed_only=, confirm=)` |
| Update config (write) | `sabnzbd_set_config(section=, keyword=, value=, confirm=)` |
| Test email notification (write) | `sabnzbd_test_email(email_address=, confirm=)` |
| Restart (DANGER) | `sabnzbd_restart(confirm=, acknowledge="restart")` |
| Shutdown (DANGER) | `sabnzbd_shutdown(confirm=, acknowledge="shutdown")` |

## A note on safety (read this)

SABnzbd's `mode=shutdown` is honored literally and the process does NOT
auto-restart (depending on how the container/process is supervised). During
initial development of this integration, a probe of `mode=shutdown` shut
the server down and required a manual restart via DSM Container Manager.
That is why these tools are doubly gated — never pass the `acknowledge`
token without explicit owner approval AND a recovery plan in hand.

For everything else, the standard confirm gate applies: state what will
change, pass `confirm=true` only after the user says yes.

## Reading state — common patterns

- "What's downloading?" → `sabnzbd_queue()` → look at `slots[]`.
- "What finished recently?" → `sabnzbd_history()` → `slots[]` with
  `status="Completed"` or `status="Failed"`.
- "Anything wrong?" → `sabnzbd_warnings()` and check the queue's
  `status` field per slot.
- "How much have I downloaded?" → `sabnzbd_server_stats()` (total/month/week/day
  per server).
- "What's my current config?" → `sabnzbd_get_config()` (large) or
  `sabnzbd_get_config(section="servers")`.

## Writes — common patterns

- "Pause for 30 min" → `sabnzbd_pause(minutes=30, confirm=true)`.
- "Pause until I say" → `sabnzbd_pause(confirm=true)`.
- "Cap speed at 5 MB/s" → `sabnzbd_speed_limit(value=5120, confirm=true)`
  (value is in KB/s — 5 MB/s × 1024).
- "Add this NZB" → `sabnzbd_add_url(url="...", confirm=true)` (use a real
  URL the user provided; never invent one).
- "Clear that stuck download" → get the `nzo_id` from `sabnzbd_queue` or
  `sabnzbd_history`, then `sabnzbd_delete_jobs(nzo_ids=[...], confirm=true)`
  (pass `from_history=true` if the job already moved to history — queue and
  history are separate delete endpoints).
- "Hold just this one download" → `sabnzbd_pause_job(nzo_id=..., confirm=true)`;
  undo with `sabnzbd_resume_job`.
- "Move it to the TV category" → `sabnzbd_categories()` to check the name,
  then `sabnzbd_queue_change_category(nzo_id=..., category=..., confirm=true)`.

## Generic passthrough

If a curated tool doesn't exist:

1. `sabnzbd_list_modes(search="config")` → find the mode.
2. `sabnzbd_call(mode="get_config", params='{"section":"misc"}')`.

WRITES via `sabnzbd_call` are NOT confirm-gated — only use this for reads
or after explicit owner approval.

## Honesty

- **Live-verified (reads):** all GETs in the smoke test pass against the
  live server (status, queue, history, server_stats, get_config all
  returned real data).
- **Method-verified (writes):** the HTTP shape is correct; the decline
  path is verified (every confirm-gated tool correctly returns
  `confirmation_required: true` without `confirm=true`). The newer tools
  (`sabnzbd_pause_job`, `sabnzbd_resume_job`, `sabnzbd_history_clear`,
  `sabnzbd_queue_change_category`, `sabnzbd_queue_change_priority`,
  `sabnzbd_add_local_file`) follow the documented API shape but have not
  been executed against a live server.
- **Not implemented:** `addfile` (multipart NZB upload). The generic
  `sabnzbd_call` can reach it, but the file body has to come from elsewhere.
- **Hard limits:** `mode=shutdown` is honored literally; no auto-restart.

See `references/api-map.md` for the full mode catalog.
