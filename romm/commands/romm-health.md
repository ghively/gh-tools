---
description: Full health check of the RomM server (status, library stats, tasks, activity, logs)
argument-hint: (optional) an area to focus on, e.g. "matching" or "scans"
---

# RomM server health check

Produce a concise health report for the RomM server using the `romm` MCP tools.
If `$ARGUMENTS` names a focus area, weight the report toward it, but always cover
the basics. This is **read-only** — make no changes.

1. **Identity & config** — `romm_status` (version, enabled metadata sources,
   filesystem platform dirs, scheduled-task config, whether scan triggering is
   available). Flag: no metadata sources enabled, empty
   `filesystem_platform_dirs` when the library should have content, config file
   not writable.
2. **Library stats** — `romm_stats(include_platform_stats=True)`. Report
   platform/ROM/save/state counts and total size.
3. **Library quality** — `romm_roms(matched=False, limit=1)` for the unmatched
   count, `romm_roms(missing=True, limit=1)` for files missing from disk,
   `romm_roms(duplicate=True, limit=1)` for duplicates (read the `total` field
   of each).
4. **Tasks** — `romm_tasks()`. Report which scheduled tasks/watcher are enabled
   and anything currently running.
5. **Logs** — `romm_logs(limit=100)`. Call out ERROR/WARNING lines, failed
   metadata fetches, and scan failures.
6. **Users & access (if focus is users/security)** — `romm_users()` for stale or
   disabled accounts; `romm_api_keys(action="list_all")` for keys that should be
   rotated.

## Output

Lead with an overall verdict: **Healthy / Needs attention / Critical**. Then a
short bulleted summary grouped by the sections above, with anything abnormal at
the top. Suggest (but do not perform) remediation steps for each finding.
