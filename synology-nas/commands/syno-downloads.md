---
description: View and manage Synology Download Station tasks
argument-hint: (optional) a URL/magnet to add, or "pause all" / "resume all" / "clean completed"
---

# Synology Download Station

Use the `synology` MCP tools to manage downloads.

1. Always start by listing current tasks with `synology_downloads_list` and show a
   readable table: title, status, size, % complete, and down/up speed. Decode common
   Download Station status values (e.g. downloading, seeding, finished, error, paused).

2. Then act on `$ARGUMENTS` if present:
   - A URL, `magnet:`, or `ftp://` link → add it with `synology_download_add(uri=...)`,
     then re-list to confirm it was queued.
   - "pause all" / "resume all" → collect the relevant task ids and call
     `synology_download_control(task_ids=[...], action="pause"|"resume")`.
   - "clean completed" / "remove <name>" → identify the matching task ids and,
     **after confirming with the user**, call
     `synology_download_control(task_ids=[...], action="delete", confirm=True)`.

Deleting tasks removes them from Download Station — confirm before deleting. Adding,
pausing, and resuming are low-risk. Report the resulting task list after any change.
