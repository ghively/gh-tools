---
description: Take a snapshot of SABnzbd (status + queue + recent history + warnings) and surface anything needing attention.
allowed-tools: mcp__sabnzbd__sabnzbd_status, mcp__sabnzbd__sabnzbd_queue, mcp__sabnzbd__sabnzbd_history, mcp__sabnzbd__sabnzbd_warnings, mcp__sabnzbd__sabnzbd_server_stats
---

Take a health snapshot of SABnzbd. Run these tools, then summarize:

1. `mcp__sabnzbd__sabnzbd_status` — version, paused state, speed, queue summary, diskspace, recent warnings.
2. `mcp__sabnzbd__sabnzbd_queue` — active download slots.
3. `mcp__sabnzbd__sabnzbd_history` (limit 10) — recent completed/failed.
4. `mcp__sabnzbd__sabnzbd_warnings` — recent warnings array.
5. `mcp__sabnzbd__sabnzbd_server_stats` — bytes downloaded per server.

Report:

- **Server:** version + paused/speed state + diskspace.
- **Queue:** per slot (filename, category, status, mb done/total, timeleft).
- **History:** per slot (name, status [Completed/Failed], category, fail_message if any).
- **Warnings:** the recent warnings list.
- **Server stats:** per-server bytes downloaded.
- **Anything needing attention** at the top: failed jobs that might need retry,
  disk space low, warnings about repair failures, etc.

Do NOT call pause/resume/addurl/delete/restart/shutdown. This is read-only.
