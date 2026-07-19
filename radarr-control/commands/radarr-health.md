---
description: Take a snapshot of the Radarr movie manager (health + library + queue) and surface anything that needs attention.
allowed-tools: mcp__radarr__radarr_status, mcp__radarr__radarr_wanted_missing, mcp__radarr__radarr_queue, mcp__radarr__radarr_wanted_cutoff, mcp__radarr__radarr_blocklist, mcp__radarr__radarr_logs, mcp__radarr__radarr_system_tasks
---

Take a health snapshot of Radarr. Run these tools, then summarize:

1. `mcp__radarr__radarr_status` — identity, version, library counts, queue summary, health warnings, disks.
2. `mcp__radarr__radarr_wanted_missing` (page 1, page_size 5) — top of the missing list.
3. `mcp__radarr__radarr_wanted_cutoff` (page 1, page_size 5) — top upgradeable.
4. `mcp__radarr__radarr_queue` — anything actively downloading.
5. `mcp__radarr__radarr_blocklist` (page 1, page_size 5) — recently rejected releases.
6. `mcp__radarr__radarr_logs` (level="warn", page 1, page_size 5) — recent warnings/errors.
7. `mcp__radarr__radarr_system_tasks` — scheduler state.

Report:

- **Server:** version + library counts (monitored / with-file / missing).
- **Health warnings/errors:** list each with the message.
- **Queue:** per slot (movie, quality, status, timeleft).
- **Missing & cutoff:** count + the first few titles (don't dump the full list).
- **Blocklist:** recent failures with reasons.
- **Logs:** the top warnings/errors with timestamps.
- **Anything needing attention** at the top: failed imports, full disks, missing
  health-met conditions, etc.

Do NOT trigger any write commands (no refresh/search/scan). This is read-only.
