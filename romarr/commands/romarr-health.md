---
description: Take a snapshot of ROMarr (dependency health + library + queue + wanted + recent activity) and surface anything that needs attention.
allowed-tools: mcp__romarr__romarr_status, mcp__romarr__romarr_system_counts, mcp__romarr__romarr_wanted_missing, mcp__romarr__romarr_queue, mcp__romarr__romarr_history, mcp__romarr__romarr_blocklist, mcp__romarr__romarr_logs
---

Take a health snapshot of ROMarr. Run these tools, then summarize:

1. `mcp__romarr__romarr_status` — dependency health (Prowlarr, each library
   backend with its `readable`/`detail`), platform count, queue size.
2. `mcp__romarr__romarr_system_counts` — library/queue sizes.
3. `mcp__romarr__romarr_wanted_missing` — requested but not yet found.
4. `mcp__romarr__romarr_queue` — anything actively downloading.
5. `mcp__romarr__romarr_history` — most recent activity (imports, grabs, failures).
6. `mcp__romarr__romarr_blocklist` — recently rejected releases with reasons.
7. `mcp__romarr__romarr_logs` — recent log lines, scan for warnings/errors.

Report:

- **Server:** version, platform count.
- **Dependencies:** Prowlarr and each library backend — reachable? readable?
  If any `readable: false`, quote the `detail` field verbatim.
- **Queue:** what's actively downloading.
- **Wanted:** count + the first few titles.
- **Recent activity:** last few history entries.
- **Blocklist:** recent failures with reasons, if any.
- **Log warnings/errors** with timestamps, if any.
- **Anything needing attention** at the top of the report, not buried.

Do NOT trigger any write commands. This is read-only.
