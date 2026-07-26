# Common multi-step tasks (recipes)

Worked sequences for jobs that take more than one call. All write steps follow
the confirm-gate protocol: preview → user approves → re-run with confirm=true.

## "Why is playback buffering / transcoding?"

1. `emby_sessions(active_only=true)` — find the session; read `NowPlaying.PlayMethod`
   and the `Transcoding` block (`Reasons`, `HardwareAccel`, `Bitrate`).
2. Map the reason to a fix (optimization.md §2): bitrate caps → raise limit or set
   app to Auto; `SubtitleCodecNotSupported` → PGS burn-in, switch to SRT;
   codec/container → check `emby_playback_info(item_id)` for what the file is.
3. If transcode initialization failed: `emby_logs()` → fetch newest
   `ffmpeg-transcode-*.txt` → look at decoder/encoder selection and the error tail.
4. Verify hw-accel is actually in use: encoder names ending `_vaapi`/`_qsv`/`_nvenc`
   in the ffmpeg log (4.7 has no hw flags in Sessions).

## "Fix this item's metadata / wrong match"

1. `emby_search(term)` → get the item id; `emby_item(id)` to see current state.
2. Small manual fix: `emby_update_item(id, patch)` (round-trip merge).
3. Wrong identification: `emby_call("GET", "/Items/RemoteSearch/...")` — find via
   `emby_list_endpoints("RemoteSearch")`; then `POST /Items/RemoteSearch/Apply/{id}`.
4. Re-pull from providers: `emby_refresh_item(id)`; add `replace_all_metadata=true`
   only if the user wants local edits overwritten.

## "New media isn't showing up"

1. `emby_libraries()` — check `RefreshStatus` and that the path is listed.
2. `emby_scheduled_tasks()` — is "Scan media library" running/failed?
3. `emby_scan_library(confirm=true)` after approval; re-check.
4. Still missing: `emby_logs("embyserver.txt")` during scan — permission errors
   (Linux: emby user needs read on `/mnt/Media/...`), naming-convention misses.
5. Check the file is visible server-side:
   `emby_call("GET", "/Environment/DirectoryContents", params='{"Path": "/mnt/Media/Movies"}')`.

## "Onboard a new user (kid-safe)"

1. `emby_create_user(name, confirm=true)`.
2. `emby_set_user_password(name, pw, confirm=true)`.
3. `emby_update_user_policy(name, patch, confirm=true)` — e.g.
   `{"MaxParentalRating": 7, "EnableContentDeletion": false, "EnableRemoteAccess": false,
     "EnableAllFolders": false, "EnabledFolders": ["<library ItemId>"]}`
   (library ids from `emby_libraries()`).
4. Verify: `emby_user(name)` → Policy reflects the changes.

## "Install and configure a plugin"

1. `emby_packages(search)` → exact `name`.
2. `emby_install_plugin(name, confirm=true)`.
3. `emby_activity(10)` — confirm "installed" entry; then
   `emby_restart_server(confirm=true)` (warn active viewers first — `emby_sessions`).
4. After restart: `emby_plugins()` shows it; `emby_plugin_config(plugin)` to read
   settings (auto-resolves the named store), `emby_plugin_config(plugin, patch,
   confirm=true)` to write.

## "Server health report"

1. `emby_status` — version, pending restart, sessions, item counts.
2. `emby_scheduled_tasks()` — any `LastRun.Status != "Completed"`.
3. `emby_activity(25)` — errors, failed logins.
4. `emby_sessions(active_only=true)` — transcode load.
5. `emby_logs()` — abnormal log sizes (multi-GB embyserver.txt = error loop).

## "Free up the server before maintenance"

1. `emby_sessions(active_only=true)` — who's watching.
2. `emby_send_message(session, "Server restarting in 5 min", confirm=true)` to each.
3. Wait, then `emby_restart_server(confirm=true)`.
4. Verify back up: `emby_status` (also `/System/Info/Public` needs no auth).

## "Curate a collection"

1. `emby_items(include_types="Movie", genres="Horror", limit=100)` → gather ids.
2. `emby_collection("create", name="Halloween", item_ids="id1,id2", confirm=true)`
   or `emby_collection("add", collection_id=..., item_ids=..., confirm=true)`.
3. Verify: `emby_collection("items", collection_id=...)`.

## "Enable Live TV" (currently dep-gated on gh-media)

M3U Tuner, XmlTV and Emby Guide Data plugins are already installed. Needs: a tuner
source (M3U playlist URL or HDHomeRun) + a guide source. Add via
`emby_list_endpoints(tag="LiveTvService")` → `POST /LiveTv/TunerHosts` and
`POST /LiveTv/ListingProviders` with the user's sources, then verify
`emby_call("GET", "/LiveTv/Info")` shows `IsEnabled: true`. Live TV management
requires the user's policy `EnableLiveTvManagement`.
