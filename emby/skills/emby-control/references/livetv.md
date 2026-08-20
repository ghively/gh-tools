# Live TV / IPTV — setup and operation (live-verified on media-host, 4.7.x)

Live TV is Emby's largest API domain (66 operations). On media-host it is
**ready but unconfigured**: the M3U TV Tuner, XmlTV and Emby Guide Data plugins
are installed, Emby Premiere is active (DVR licensed), and the full setup write
path was **proven live and reversibly** (tuner add → Live TV enabled → tuner
delete → state restored) on 2026-07-15.

## Mental model

Live TV = **tuner source(s)** (where streams come from) + **guide provider(s)**
(EPG data) + a guide refresh. The moment at least one tuner exists,
`/LiveTv/Info` flips `IsEnabled: true` and clients show the Live TV section.

Supported on this server (from `/LiveTv/TunerHosts/Types` and
`/LiveTv/ListingProviders/Available`):

- Tuners: **`m3u`** (IPTV playlist URL or file path) and **`hdhomerun`**.
- Guide providers: **`xmltv`** (XMLTV file/URL — the usual IPTV pairing) and
  **`embygn`** (Emby Guide Data — Premiere service for US/CA broadcast lineups).

## IPTV setup flow (the common case)

1. `emby_livetv_status()` — confirm starting state.
2. Add the tuner: `emby_livetv_tuner("add", tuner_type="m3u",
   url="<playlist url>", tuner_count=<provider's connection limit>,
   user_agent=<if provider requires>, confirm=true)`.
   - **GOTCHA (verified live): Emby fetches and validates the playlist AT ADD
     TIME.** An unreachable URL fails with HTTP 500 "Connection ... timed out"
     and NO tuner is created. Have the playlist reachable before adding.
   - `tuner_count` matters for IPTV: providers limit concurrent connections;
     0 means unlimited and Emby will happily over-subscribe.
3. Add guide data: `emby_livetv_guide_provider("add", provider_type="xmltv",
   path="<xmltv url or file>", confirm=true)` (gzipped .xml.gz URLs are fine).
4. Pull the guide: find "Refresh Guide" in `emby_scheduled_tasks()` and
   `emby_run_task(id, confirm=true)`. Channels import asynchronously — they do
   NOT appear at tuner-add time; expect them after this task runs.
5. Verify: `emby_livetv_status()` → ChannelCount > 0, GuideRange populated;
   `emby_livetv_channels()` shows the lineup.
6. Grant access: each user's policy has `EnableLiveTvAccess` (and
   `EnableLiveTvManagement` for admins) — `emby_update_user_policy`.

## Channel & guide management

- `emby_livetv_channels(include_disabled=true)` — management view;
  enable/disable or reorder via `emby_call`:
  `POST /LiveTv/Manage/Channels/{Id}/Disabled` body `{"Disabled": true}`,
  `POST /LiveTv/Manage/Channels/{Id}/SortIndex` body `{"SortIndex": n}`.
- Map guide channels to tuner channels when names mismatch:
  `GET /LiveTv/ChannelMappingOptions?ProviderId=` then
  `POST /LiveTv/ChannelMappings` (find via `emby_list_endpoints("ChannelMapping")`).
- Guide window: `emby_livetv_guide(hours=..., search=...)`; recommendations at
  `GET /LiveTv/Programs/Recommended`.

## DVR (Premiere — active on this server)

- `emby_livetv_dvr("record", program_id=..., confirm=true)` — one airing;
  `series=true` for a series pass. Implementation: reads
  `/LiveTv/Timers/Defaults?ProgramId=` and POSTs it to `/LiveTv/Timers`
  (or `/LiveTv/SeriesTimers`).
- `emby_livetv_dvr("timers")` / `("recordings")` / `("cancel", timer_id=...,
  series=..., confirm=true)`.
- Recording storage: `GET /LiveTv/Recordings/Folders`; default path config in
  the `livetv` named store (`emby_get_config("livetv")`) — set a recording path
  with space before heavy DVR use. Recorded shows can auto-organize into
  libraries.

## Verified behaviors (from the reversible live proof, 2026-07-15)

| Step | Result |
|---|---|
| `POST /LiveTv/TunerHosts` (m3u, reachable playlist) | 200, returns tuner with generated `Id` |
| `POST /LiveTv/TunerHosts` (unreachable URL) | 500 "Connection timed out", tuner NOT created |
| Live TV state after add | `IsEnabled: true` immediately |
| Channels after add | 0 until "Refresh Guide" task runs (async import) |
| `DELETE /LiveTv/TunerHosts?Id=` | 200, tuner gone, `IsEnabled` back to `false` |

## Troubleshooting

- Playlist rejected at add: URL unreachable from the SERVER (not your PC) — the
  Emby host must fetch it; test with
  `emby_call("GET", "/Environment/DirectoryContents", ...)` mindset: it's the
  server's network position that counts.
- Channels missing after setup: run "Refresh Guide"; check
  `emby_logs("embyserver.txt")` for M3U parse or XMLTV errors.
- Stream plays in VLC but not Emby: try setting `user_agent` on the tuner
  (some IPTV providers filter default agents); check ffmpeg transcode logs.
- Guide names ≠ channel names: use ChannelMappings (above).
- A user can't see Live TV: their policy lacks `EnableLiveTvAccess`.
- Live TV management APIs require the caller's policy `EnableLiveTvManagement`
  (the plugin's admin API key has it).
