---
description: Take a snapshot of the Sonarr TV-series manager (health + library + queue + today's calendar) and surface anything that needs attention.
allowed-tools: mcp__sonarr__sonarr_status, mcp__sonarr__sonarr_wanted_missing, mcp__sonarr__sonarr_queue, mcp__sonarr__sonarr_wanted_cutoff, mcp__sonarr__sonarr_blocklist, mcp__sonarr__sonarr_logs, mcp__sonarr__sonarr_system_tasks, mcp__sonarr__sonarr_calendar
---

Take a health snapshot of Sonarr. Run these tools, then summarize:

1. `mcp__sonarr__sonarr_status` — identity, version, library counts, queue summary, health warnings, disks.
2. `mcp__sonarr__sonarr_calendar` — episodes airing in the next 7 days.
3. `mcp__sonarr__sonarr_wanted_missing` (page 1, page_size 5) — top of the missing list (per-episode).
4. `mcp__sonarr__sonarr_wanted_cutoff` (page 1, page_size 5) — top upgradeable.
5. `mcp__sonarr__sonarr_queue` — anything actively downloading.
6. `mcp__sonarr__sonarr_blocklist` (page 1, page_size 5) — recently rejected releases.
7. `mcp__sonarr__sonarr_logs` (level="warn", page 1, page_size 5) — recent warnings/errors.
8. `mcp__sonarr__sonarr_system_tasks` — scheduler state.

Report:

- **Server:** version + library counts (total / monitored series).
- **Upcoming episodes:** next 7 days (series, SxxEyy, air date).
- **Health warnings/errors:** list each with the message.
- **Queue:** per slot (series, episode, quality, status, timeleft).
- **Missing & cutoff:** counts + the first few titles.
- **Blocklist:** recent failures with reasons.
- **Logs:** the top warnings/errors with timestamps.
- **Anything needing attention** at the top.

Do NOT trigger any write commands. This is read-only.
