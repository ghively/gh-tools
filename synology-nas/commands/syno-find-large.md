---
description: Find the largest files/folders on the Synology NAS to reclaim space
argument-hint: (optional) a folder path to scan, e.g. "/video" (defaults to scanning shares)
---

# Find large files on the Synology NAS

Help the user reclaim space using the `synology` MCP tools. Read-only unless the user
explicitly asks to delete something.

1. Determine where to look. If `$ARGUMENTS` is a path, scan there. Otherwise list
   shares with `synology_fs_shares` and ask which to scan (or scan the largest).
2. Browse with `synology_fs_list(folder_path=..., limit=...)`, sorting by size where
   possible. Recurse into the biggest subfolders to find what's consuming space.
   For name-based hunts (e.g. "*.iso", "*.mkv") use `synology_fs_search`.
3. Present the top offenders as a ranked list with human-readable sizes and full paths.
4. If the user wants to delete, confirm the exact paths, then use
   `synology_fs_delete(paths=[...], confirm=True)`. Deletion is permanent — never
   delete without an explicit, specific go-ahead.

Note that files removed via the API bypass the Recycle Bin. Suggest moving to a
"to-delete" folder first if the user is unsure.
