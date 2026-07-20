---
description: Take a snapshot of the Tdarr transcoding server (status + nodes + DB statuses + perf stats) and surface anything needing attention. Fails cleanly if Tdarr isn't deployed.
allowed-tools: mcp__tdarr__tdarr_full_status, mcp__tdarr__tdarr_search_db, mcp__tdarr__tdarr_backup_status, mcp__tdarr__tdarr_server_log
---

Take a health snapshot of Tdarr. Run these tools, then summarize:

1. `mcp__tdarr__tdarr_full_status` — composite of status + nodes + DB statuses + perf/res stats.
2. `mcp__tdarr__tdarr_backup_status` — last backup time + status.
3. `mcp__tdarr__tdarr_search_db` (string="") with limit=3 — sample of indexed files (or empty if no libraries yet).
4. `mcp__tdarr__tdarr_server_log` — tail of recent activity.

Report:

- **Server:** status, version (if exposed), uptime indicators.
- **Nodes:** count + per-node state (online/offline, worker counts).
- **Libraries (DB statuses):** per-library counts + health.
- **Performance:** throughput numbers, errors.
- **Backups:** last backup time + size; flag if stale (>7d).
- **Anything needing attention** at the top: offline nodes, failed transcodes,
  stale backups, scanner stalls, etc.

If the tools return connection errors, **report clearly that Tdarr is not
deployed yet** and surface the host/port from config — don't pretend to
diagnose. Do NOT trigger any write commands.
