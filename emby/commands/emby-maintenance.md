---
description: Guided Emby maintenance — scan library, run tasks, restart, with viewer-safe sequencing
argument-hint: (optional) "scan" | "restart" | task name
---

# Emby maintenance

Run a maintenance action safely using the `emby` MCP tools. Every write is
confirm-gated: preview first, get my explicit approval, then execute.

1. **Check impact first** — `emby_sessions(active_only=true)`. If anyone is
   actively watching, tell me who before proposing anything disruptive, and
   offer to `emby_send_message` them a heads-up.
2. Interpret `$ARGUMENTS`:
   - "scan" → `emby_scan_library` (preview → confirm). Track progress via
     `emby_scheduled_tasks()` and report when the scan completes.
   - "restart" → `emby_restart_server` (preview → confirm). After confirming,
     poll `emby_status` until the server is back and report downtime.
   - A task name → find it in `emby_scheduled_tasks()`, show its last result,
     then `emby_run_task(id, confirm=true)` after approval and report the outcome.
   - No arguments → show the maintenance menu: scheduled tasks with last-run
     status, pending restart flag, and log sizes; recommend what's worth running.
3. Afterwards verify: re-read the relevant state (task result, server version/
   uptime) and summarize what changed.
