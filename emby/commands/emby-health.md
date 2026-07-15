---
description: Full health check of the Emby server (status, tasks, activity, sessions, logs)
argument-hint: (optional) an area to focus on, e.g. "transcoding" or "library"
---

# Emby server health check

Produce a concise health report for the Emby server using the `emby` MCP tools.
If `$ARGUMENTS` names a focus area, weight the report toward it, but always cover
the basics. This is **read-only** — make no changes.

1. **Identity & load** — `emby_status` (version, pending restart/update, item
   counts, connected sessions, who's playing what and whether it transcodes).
2. **Scheduled tasks** — `emby_scheduled_tasks()`. Flag any task whose
   `LastRun.Status` is not `Completed` and anything unexpectedly `Running`.
3. **Recent activity** — `emby_activity(25)`. Call out errors, failed logins,
   and unusual severity entries.
4. **Sessions & transcoding** — `emby_sessions(active_only=true)`. For each
   transcode, report the `Reasons` and whether hardware acceleration is in play.
5. **Logs** — `emby_logs()`. Flag abnormally large log files (a multi-GB
   embyserver.txt usually means an error loop); if suspicious, pull the tail of
   `embyserver.txt` and summarize repeated errors.
6. **Libraries (if focus is library)** — `emby_libraries()` refresh status; item
   counts vs. expectations.

## Output

Lead with an overall verdict: **Healthy / Needs attention / Critical**. Then a
short bulleted summary grouped by the sections above, with anything abnormal at
the top. Suggest (but do not perform) remediation steps for each finding.
