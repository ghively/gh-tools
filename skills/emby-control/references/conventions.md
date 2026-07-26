# Emby API conventions (proven live against 4.7.14.0)

## Connection & auth

- Base URL: `http://<host>:8096` (HTTPS on 8920 only if enabled — on gh-media
  it is NOT; the server speaks plain HTTP on the LAN).
- Every request needs the API key: header `X-Emby-Token: <key>` (query param
  `?api_key=` also works). Keys are minted in Dashboard → Advanced → API Keys
  and act with **server admin** privilege.
- Paths work with or without the `/emby` prefix (`/System/Info` ≡
  `/emby/System/Info`).
- `GET /System/Info/Public` needs NO auth — use it as a reachability probe.

## Error vocabulary

| Status | Meaning (observed) |
|---|---|
| 200 / 204 | OK (204 = empty body, common on writes) |
| 206 | Partial content (image/media delivery with Range) |
| 400 | Missing/invalid required parameter (message names it) |
| 401 | Missing or invalid API key |
| 404 | Route exists but entity not found; also "Unable to find the specified file" |
| 500 + "Object reference not set..." | Emby's catch-all for a NONEXISTENT entity id, a missing dependency, or an unimplemented legacy route — do NOT read it as a server crash. Retry with a verified id before concluding anything. |

## Shapes & units

- List queries return `{"Items": [...], "TotalRecordCount": n}`; page with
  `StartIndex`/`Limit`.
- **Ticks**: all durations/positions. 1 s = 10,000,000 ticks.
  `RunTimeTicks`, `PositionTicks`, `StartPositionTicks`.
- Dates are ISO-8601 UTC.
- Item ids are opaque strings ("59912"); user/plugin ids are GUID-ish hex.

## Round-trip writes (the #1 gotcha)

`POST /System/Configuration[/key]`, `POST /Items/{id}`,
`POST /Users/{id}/Policy`, `POST /Plugins/.../Configuration` all replace the
WHOLE object. Posting `{"EnableUPnP": false}` alone would reset every other
setting to defaults. Always GET → merge → POST (curated tools do this).

## User scoping

- `/Items?...&UserId=x` adds per-user data (Played, resume, favorites) to
  results; `/Users/{id}/Items/{itemId}` is the user-view item detail.
- Watched flag: `POST|DELETE /Users/{uid}/PlayedItems/{itemId}`.
- Favorite: `POST|DELETE /Users/{uid}/FavoriteItems/{itemId}`.

## Plugin configuration (4.x reality)

Legacy `GET/POST /Plugins/{id}/Configuration` returns **500 for all 18
plugins** on this server — modern Emby plugins don't implement it. The real
mechanism is **named configuration stores**:

- `GET /web/ConfigurationPages` lists dashboard pages with `PluginId`.
- Store key ≈ page name minus `js`/`settings` suffix:
  `opensubtitles`, `webhooks`, `cinemamode`, `fanart`, `musicbrainz`, `xmltv`,
  `dlnasettings→dlna`.
- Read/write via `GET/POST /System/Configuration/{key}` (full-object rule
  applies). Core stores that always exist: `encoding`, `livetv`,
  `notifications`, `subtitles`.

## Useful direct URLs

- Item artwork: `GET /Items/{id}/Images/Primary` (also `Backdrop`, `Logo`;
  supports `MaxWidth`, `Quality` params).
- Log file: `GET /System/Logs/Log?Name=embyserver.txt` (list: `/System/Logs`).
- Live OpenAPI catalog: `GET /openapi.json` (~484 ops — emby_list_endpoints
  serves a searchable index of it).

## Verified facts about gh-media (2026-07)

- Emby Server 4.7.14.0, Linux, `ProgramDataPath /var/lib/emby`,
  transcode temp `/var/emby-transcode-temp` (check `emby_get_config("encoding")`).
- **Emby Premiere active** (`/Plugins/SecurityInfo` → IsMBSupporter true) —
  Sync/downloads, cinema intros etc. are license-eligible.
- Users: `dadmonkey405` (admin), `Home`. Libraries: Movies (`/mnt/Media/Movies`),
  TV shows (`/mnt/Media/TV`), Collections. ~513 movies, 262 series,
  24k episodes, 61 collections.
- Live TV: disabled (no tuner/guide configured; M3U Tuner + XmlTV + Emby
  Guide Data plugins are installed and ready).
- Emby Connect: not linked (Connect endpoints 404).
- 18 plugins installed; catalog exposes 133 packages.
