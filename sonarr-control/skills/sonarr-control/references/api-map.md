# Sonarr API map

Verified live on Sonarr 4.0.18.2978 (2026-07-19). Hand-enumerated — Sonarr
publishes no OpenAPI document. Sonarr's surface is parallel to Radarr's
with TV-specific resources (series/seasons/episodes) and language profiles.

## 1Password

- Vault: `Gregory`
- Item: `Sonarr API Key (GH-Storage)` (id `ravq52fc24jbotc2zgaeu4ynce`)
- Fields: `credential` (API key), `serverurl` (e.g. `http://192.168.0.133:8989`)
- Read with: `op item get ravq52fc24jbotc2zgaeu4ynce --vault Gregory --field credential --reveal`

## Auth

`X-Api-Key: <32-char hex>` header. Same model as Radarr.

## Conventions

- All paths under `/api/v3/`.
- POST/PUT expect FULL object — write tools here GET-merge-PUT.
- POST `/api/v3/command` with `{"name": "...", ...}` is async; poll `/command/{id}`.
- `/wanted/missing` and `/wanted/cutoff` return EPISODES (not series).
- `/calendar` returns EPISODES (one per airing, series embedded).

## Live-verified endpoints

(Catalog also exposed via `sonarr_list_endpoints`.)

### System
- `GET /api/v3/system/status`, `/system/task` (+ `/{id}`), `/system/backup`
- `GET /api/v3/log`, `/api/v3/health`, `/api/v3/queue/status`
- `GET /api/v3/diskspace`, `/api/v3/qualityDefinition`

### Library
- `GET /api/v3/series` (+ `/{id}`)
- `GET /api/v3/series/lookup?term=` — search by title OR `term=tvdb:<id>` (this is the canonical form on 4.x)
- `GET /api/v3/series/lookup/tvdb?tvdbId=` — **404s on Sonarr 4.x**; do NOT use (the `sonarr_add_series` tool uses the `term=tvdb:` form internally)
- `POST /api/v3/series` — add (full object incl. seasons, addOptions)
- `PUT /api/v3/series` (bulk) / `PUT /api/v3/series/{id}`
- `DELETE /api/v3/series/{id}?deleteFiles=&addImportExclusion=`
- `GET /api/v3/episode?seriesId=&seasonNumber=` (+ `/{id}`, `PUT /{id}`)
- `GET /api/v3/episodeFile?seriesId=` (+ `/{id}`, `DELETE /{id}`)
- `GET /api/v3/seasonPass` — monitoring map
- `GET /api/v3/extraFile`, `/api/v3/alternativeRelease`, `/api/v3/importlist`

### Activity
- `GET /api/v3/wanted/missing`, `/api/v3/wanted/cutoff` (EPISODE records)
- `GET /api/v3/calendar?start=&end=&includeUnmonitored=`
- `GET /api/v3/queue` (+ `/details`)
- `GET /api/v3/history` (+ `/history/series?seriesId=`)
- `GET /api/v3/blocklist`, `/api/v3/release`, `/api/v3/manualimport`

### Commands
- `POST /api/v3/command` — `{"name": "...", "seriesIds": [...], "episodeIds": [...], "seasonNumber": N}`
- `GET /api/v3/command` / `GET /{id}` / `DELETE /{id}`

Command names: `RefreshSeries`, `SeriesSearch`, `SeasonSearch`,
`EpisodeSearch`, `EpisodesSearch`, `MissingEpisodesSearch`,
`DownloadedEpisodesScan`, `RenameSeries`, `Backup`, `ApplicationUpdate`,
`RefreshMonitoredDownloads`, `RssSync`.

### Config
- `GET /api/v3/qualityProfile`
- `GET /api/v3/languageProfile` (Sonarr-specific; needed for `add_series`)
- `GET /api/v3/language`, `/api/v3/rootfolder`, `/api/v3/tag`
- `GET /api/v3/notification` (+ `/schema`)
- `GET /api/v3/downloadclient` (+ `/schema`)
- `GET /api/v3/indexer` (+ `/schema`)
- `GET /api/v3/metadata`, `/api/v3/autoTagging`, `/api/v3/config`

## Quirks

- `languageProfileId` is REQUIRED for new series — Radarr doesn't have it,
  Sonarr does. The `sonarr_add_series` tool accepts `language_profile_id`.
- For `SeasonSearch`, send both `seriesIds=[X]` and `seasonNumber=N`.
- Season monitoring lives on the series object's `seasons[]` array — toggle
  via `sonarr_toggle_season_monitored` (which does GET-modify-PUT).
- `/series?tvdbId=X` returns the matching library series if it exists.

## Not covered here (out of MVP scope)

- `POST`ing new notifications / download clients / indexers (use UI;
  reachable via `sonarr_call`).
- Quality / language profile CRUD (UI; `sonarr_call` reachable).

Reachable via `sonarr_call` if needed.
