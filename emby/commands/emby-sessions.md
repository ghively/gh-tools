---
description: Show who's watching what on Emby right now, with transcode analysis
argument-hint: (optional) a user or device to focus on
---

# Emby: now playing

Report current viewing activity using the `emby` MCP tools. Read-only.

1. `emby_sessions(active_only=true)` — for each active session report: user,
   device/app, item (with series/episode context), position vs. runtime,
   paused state, and **PlayMethod**.
2. For every transcoding session, explain each `TranscodeReasons` entry in plain
   language (see the emby-control skill's optimization reference) and whether
   hardware acceleration is active.
3. If `$ARGUMENTS` names a user/device, filter to it and go deeper: pull
   `emby_playback_info(item_id)` for the playing item and explain what would be
   needed for it to direct-play.
4. Also show idle connected sessions (`emby_sessions()` without filter) as a
   one-line count by app.

Output a compact table of active streams first, then the transcode analysis.
