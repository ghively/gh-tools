# Radarr API map

Verified live on Radarr 6.3.0.10514 (2026-07-19). Hand-enumerated — Radarr
publishes no OpenAPI document.

## 1Password

- Vault: `Gregory`
- Item: `Radarr API Key (GH-Storage)` (id `urdunwlckr2lq6kyuzwpp2hilq`)
- Fields: `credential` (API key), `serverurl` (e.g. `http://192.168.0.133:8310`)
- Read with: `op item get urdunwlckr2lq6kyuzwpp2hilq --vault Gregory --field credential --reveal`

## Auth

`X-Api-Key: <32-char hex>` header on every request. Created under
Settings > General > Security > API Key. Acts with full admin. 401 = bad key.

## Conventions

- All paths under `/api/v3/`.
- List endpoints take `page` (1-based), `pageSize`. Cap typically 200.
- POST/PUT expect the FULL object — write tools here GET-merge-POST/PUT.
- POST `/api/v3/command` with `{"name": "<CommandName>", ...}` is async.
  Returns a job object; poll `/api/v3/command/{id}`.
- 404 = resource doesn't exist (or no record for that id).
- 400 = exists but missing required query param.

## Live-verified endpoints

Catalog (also exposed via `radarr_list_endpoints`):

### System
- `GET /api/v3/system/status` — identity, version, OS, paths
- `GET /api/v3/system/task` (+ `/{id}`) — scheduled tasks
- `GET /api/v3/system/backup` — DB backups
- `GET /api/v3/log` — paged log (level filter)
- `GET /api/v3/health` — health checks
- `GET /api/v3/queue/status` — queue summary
- `GET /api/v3/diskspace` — disk free
- `GET /api/v3/qualityDefinition` — quality size matrix

### Library
- `GET /api/v3/movie` (+ `/{id}`) — all movies / one
- `GET /api/v3/movie/lookup?term=` — TMDB search
- `GET /api/v3/movie/lookup/tmdb?tmdbId=` — TMDB lookup
- `GET /api/v3/movie/lookup/imdb?imdbId=` — IMDB lookup
- `POST /api/v3/movie` — add (full object)
- `PUT /api/v3/movie` (bulk) / `PUT /api/v3/movie/{id}`
- `DELETE /api/v3/movie/{id}?deleteFiles=&addImportExclusion=`
- `GET /api/v3/movieFile?movieId=` (+ `/{id}`)
- `DELETE /api/v3/movieFile/{id}`
- `GET /api/v3/collection` (+ `PUT /{id}`)
- `GET /api/v3/extraFile`
- `GET /api/v3/alternativeRelease`
- `GET /api/v3/importlist`

### Activity
- `GET /api/v3/wanted/missing` — monitored, no file
- `GET /api/v3/wanted/cutoff` — has file but below cutoff
- `GET /api/v3/calendar?start=&end=`
- `GET /api/v3/queue` (+ `/details`) — `includeUnknown`, `includeCompleted`
- `GET /api/v3/history` (+ `/movie`) — `movieId`, `eventType`
- `GET /api/v3/blocklist`
- `GET /api/v3/release` (and `POST` to push a release)
- `GET /api/v3/manualimport?folder=`

### Commands
- `POST /api/v3/command` — `{"name": "...", "movieIds": [...]}`
- `GET /api/v3/command` / `GET /api/v3/command/{id}` / `DELETE /api/v3/command/{id}`

Command names (verified live by GET /api/v3/command schema presence):
`RefreshMovie`, `MoviesSearch`, `MissingMoviesSearch`, `DownloadedMoviesScan`,
`RenameFiles`, `RenameMovie`, `Backup`, `ApplicationUpdate`,
`RefreshMonitoredDownloads`.

### Config
- `GET /api/v3/qualityProfile`
- `GET /api/v3/language`
- `GET /api/v3/rootfolder`
- `GET /api/v3/tag` (also POST/PUT/DELETE for tag CRUD)
- `GET /api/v3/customFormat`
- `GET /api/v3/customFilter`
- `GET /api/v3/notification` (+ `/schema` — note the singular path typo)
- `GET /api/v3/downloadclient` (+ `/schema`)
- `GET /api/v3/indexer` (+ `/schema`)
- `GET /api/v3/metadata`
- `GET /api/v3/autoTagging`
- `GET /api/v3/config` — main config doc (movie/ui/indexers/downloadclient)

## Quirks worth knowing

- `notifications/schema` returns 404; the right path is `notification/schema`.
- `/movie` endpoint ignores `page`/`pageSize` query — pagination is done
  client-side in the curated tool.
- `/api/v3/movie?tmdbId=X` returns the matching library movie if it exists,
  useful for "is this already added?" checks before add.
- POST `/command` accepts `movieIds` (lowercase 'I' in 'Ids' — Radarr uses
  both `movieIds` and `movieId` depending on command; the curated tool sends
  the canonical `movieIds`).

## Beyond this map

This file lists the originally hand-verified core. Since then:

- Provider/config CRUD (notifications, download clients, indexers, import
  lists, metadata, quality/custom-format/delay/release profiles, root
  folders, remote path mappings, auto-tagging, custom filters, exclusions)
  is curated via `radarr_crud` (+ `radarr_provider_test` /
  `radarr_provider_action`).
- Bulk movie edit/delete via `PUT`/`DELETE /api/v3/movie/editor`
  (`radarr_movies_bulk_edit` / `radarr_movies_bulk_delete`).
- Interactive release search + grab via `GET`/`POST /api/v3/release`
  (`radarr_releases` / `radarr_grab_release`).
- The authoritative, always-current index is the live route table:
  `radarr_list_endpoints` (backed by `GET /api/v3/system/routes`).

Anything else is reachable via `radarr_call`.
