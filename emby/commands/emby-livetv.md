---
description: Emby Live TV — status, IPTV setup, guide browsing, DVR scheduling
argument-hint: e.g. "status", "setup <m3u-url> [xmltv-url]", "guide", "record <show>"
---

# Emby Live TV

Drive Live TV using the `emby` MCP tools (see the emby-control skill's
livetv reference for verified behaviors). Writes are confirm-gated.

Parse `$ARGUMENTS`:

- **"status" / no args** → `emby_livetv_status()`. Report enabled state,
  tuners, guide providers, channel/recording/timer counts. If unconfigured,
  explain what's needed (tuner + guide + refresh) and that this server
  supports `m3u` + `hdhomerun` tuners and `xmltv` + `embygn` guides.
- **"setup ..."** → guided IPTV setup:
  1. Ask for / extract the M3U playlist URL, the provider's connection limit,
     and the XMLTV guide URL if given.
  2. `emby_livetv_tuner("add", ...)` — preview → confirm. Remember: Emby
     validates the playlist URL at add time; if it 500s with a timeout, the
     URL is unreachable from the server.
  3. `emby_livetv_guide_provider("add", provider_type="xmltv", path=...)` —
     preview → confirm.
  4. Find "Refresh Guide" in `emby_scheduled_tasks()`, run it (confirm),
     wait for completion, then verify `emby_livetv_status()` shows channels.
  5. Check each user's `EnableLiveTvAccess` policy; offer to enable.
- **"guide" / "what's on"** → `emby_livetv_guide(hours=6)`; group by channel,
  highlight movies/sports/news flags.
- **"record X"** → `emby_livetv_guide(search=X)` to find the program, show
  airings, then `emby_livetv_dvr("record", program_id, series=?, confirm=true)`
  after approval. Confirm whether they want one airing or the series.
- **"recordings" / "timers"** → `emby_livetv_dvr("recordings"|"timers")`.
- **"remove tuner/provider"** → list first, preview the exact target, then
  delete with confirm.
