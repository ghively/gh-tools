# Tdarr API map

**SOURCE:** Built from the official Tdarr API docs at <https://tdarr.readme.io/reference>
(v2.25.01+). Frozen 2026-07-19. **NOT YET LIVE-VERIFIED** — Tdarr is not deployed
on this homelab; when it is, run `_smoketest.py` and update this file with any
discrepancies.

## 1Password

**Tdarr Server is currently unauthenticated.** If you later enable Tdarr
auth (set `auth=true` env on the server), generate an API key via the
web UI's Tools → API Keys page, store it in 1Password (vault: `Gregory`),
and reference it in `config.local.json` as `api_key` with
`api_key_header: "X-API-Key"`.

For automated deploys, the server takes a `seededApiKey` env var (must
start with `tapi_`, ≥14 chars). See `integrations.md`.

## Auth

Tdarr has **two modes**:

1. **Unauthenticated (default, `auth=false`)**: API wide-open on the LAN.
   Suitable for isolated home networks; same trust model as the *arr stack.
   Your current setup.
2. **Authenticated (`auth=true`)**: Tdarr Server prompts for username +
   password on first web-UI visit; generate API keys via Tools → API Keys.
   Nodes + this MCP plugin pass the key in the `X-API-Key` header (or
   whatever you configure via `api_key_header`). **Required when
   `enableUnmappedNodes=true`** — unmapped nodes expose library files over
   the API.

Always enable auth before exposing Tdarr outside the trusted LAN.

## Conventions

- Base path: `/api/v2/<endpoint>` (kebab-case names).
- Almost every endpoint is POST with body `{"data": {...}}` — the client wraps
  your params in `data` automatically.
- 4 endpoints are GET: `/status`, `/get-nodes`, `/download-plugins`, `/get-server-log`.
- No standard error-shape documented — assume HTTP status codes + JSON body.
- No live route introspection (no equivalent of *arr's `/system/routes`) — the
  static catalog here is the source of truth for the documented API.

## Documented endpoints (from official docs)

Catalog also exposed via `tdarr_list_endpoints`.

### System / status (mostly reads)
- `GET  /api/v2/status` — server status (liveness)
- `POST /api/v2/get-time-now` — current server time
- `POST /api/v2/get-res-stats` — server resource statistics (CPU, mem)
- `POST /api/v2/performance-stats` — performance / throughput stats
- `POST /api/v2/get-db-statuses` — status of all databases (libraries)
- `GET  /api/v2/get-server-log` — server log file (raw text)
- `POST /api/v2/get-node-log` — log file for a given node (`{nodeID}`)
- `POST /api/v2/get-filescanner-status` — file-scanner status for a db (`{dbName}`)

### Backups
- `POST /api/v2/get-backup-status`
- `POST /api/v2/get-backups`
- `POST /api/v2/create-backup` (W)
- `POST /api/v2/delete-backup` (W) — `{fileName}`
- `POST /api/v2/reset-backup-status` (W)

### Library / files
- `POST /api/v2/search-db` — `{string, lessThanGB, greaterThanGB}`
- `POST /api/v2/scan-files` (W) — `{scanConfig}` (exact shape TBD)
- `POST /api/v2/scan-individual-file` (W) — `{filePath, dbID?}`
- `POST /api/v2/delete-file` (W, IRREVERSIBLE) — `{filePath, dbID?}`
- `POST /api/v2/delete-unhealthy-files` (W) — `{table}`
- `POST /api/v2/create-sample` (W) — sample file
- `POST /api/v2/verify-folder-exists` — `{folderPath}`
- `POST /api/v2/get-subdirectories` — `{folderPath}`
- `POST /api/v2/remove-library-files` (W) — `{libraryID}` or `{arrayOfIDs}`
- `POST /api/v2/set-all-status` (W) — bulk-set status of all records in a table
- `POST /api/v2/kill-file-scanner` (W, doubly-gated) — `{dbName}`
- `POST /api/v2/delete-cache-file` (W) — delete a cache file

### DB CRUD (the powerful one)
- `POST /api/v2/cruddb` — full CRUD on 8 collections

```
mode: insert | getById | getAll | update | removeOne | removeAll
collection: FileJSONDB | LibrarySettingsJSONDB | StatisticsJSONDB | NodeJSONDB
          | SettingsGlobalJSONDB | StagedJSONDB | F2FOutputJSONDB | FlowsJSONDB
docID: required for insert/getById/update/removeOne (often the file path)
obj:    required for insert (full doc) and update (keys to change)
```

Reads (getById / getAll) are not confirm-gated. Every other mode IS.

### Nodes
- `GET  /api/v2/get-nodes` — list all
- `POST /api/v2/update-node` (W)
- `POST /api/v2/restart-node` (W) — `{nodeID}`
- `POST /api/v2/disconnect-node` (W, doubly-gated) — `{nodeID}`
- `POST /api/v2/alter-worker-limit` (W) — `{nodeID, workerType, limit}`
  (workerType enum TBD — likely cpu/gpu/transcode)
- `POST /api/v2/poll-worker-limits` — `{nodeID}`
- `POST /api/v2/cancel-worker-item` (W) — `{nodeID, workerType}`
- `POST /api/v2/kill-worker` (W, doubly-gated) — `{nodeID, workerType}`
- `POST /api/v2/client/{clientType}` — get client data by type

### Plugins
- `POST /api/v2/search-plugins` — `{string?}`
- `POST /api/v2/search-flow-plugins` — `{string?}`
- `POST /api/v2/search-flow-templates` — `{string?}`
- `GET  /api/v2/download-plugins` — plugin zip
- `POST /api/v2/sync-plugins` (W)
- `POST /api/v2/update-plugins` (W)
- `POST /api/v2/read-plugin` — `{id}`
- `POST /api/v2/read-plugin-text` — `{id}`
- `POST /api/v2/save-plugin-text` (W) — `{id, text}`
- `POST /api/v2/create-plugin` (W)
- `POST /api/v2/delete-plugin` (W) — `{id}`
- `POST /api/v2/verify-plugin` — `{id}`
- `POST /api/v2/copy-community-to-local` (W) — `{id}` (install)
- `POST /api/v2/run-help-command` — `{command, args?}` (ffmpeg/handbrake help)

### Library settings
- `POST /api/v2/toggle-folder-watch` (W) — `{libraryID}`
- `POST /api/v2/toggle-schedule` (W) — `{libraryID, type?}`
- `POST /api/v2/update-schedule-block` (W)
- `POST /api/v2/add-plugin-include` (W)
- `POST /api/v2/update-plugin-include` (W)
- `POST /api/v2/remove-plugin-include` (W)
- `POST /api/v2/add-video-codec-exclude` (W) — `{libraryID, videoCodec}`
- `POST /api/v2/update-video-codec-exclude` (W)
- `POST /api/v2/remove-video-codec-exclude` (W)
- `POST /api/v2/add-audio-codec-exclude` (W) — `{libraryID, audioCodec}`
- `POST /api/v2/update-audio-codec-exclude` (W)
- `POST /api/v2/remove-audio-codec-exclude` (W)

### Reports / jobs
- `POST /api/v2/list-footprintId-reports` — `{footprintId}`
- `POST /api/v2/read-job-file`
- `POST /api/v2/transcode-user-verdict` (W) — `{filePath, verdict}`
- `POST /api/v2/item-proc-end` (W, internal) — node signals item completion

## Quirks worth knowing (from docs + community)

- **No auth model**: Tdarr trusts the LAN. If exposed externally, front with
  nginx-basic-auth or Authentik and use the `api_key` config field.
- **`{"data": {...}}` wrapping**: easy to forget — every POST body is wrapped
  in `data`. The MCP client handles this for you.
- **`/cruddb` is genuinely dangerous**: `removeAll` on `FileJSONDB` wipes the
  file index. Always `getAll` first to confirm collection name; never `removeAll`
  as a test.
- **GPU worker type**: Tdarr supports GPU transcoding via NVENC (and others).
  The worker_type enum for `alter-worker-limit` likely includes `gpu` but is
  not explicitly documented — confirm on first live use.
- **Plugin IDs**: typically a name like `Migz1Remux` rather than a UUID. The
  search-plugins response shows the canonical IDs.

## Hard limits (presumed)

- **No live route introspection**: Tdarr doesn't expose a `/system/routes`
  equivalent. The static catalog in this file is the source of truth for the
  documented API; new endpoints in future Tdarr versions may not appear until
  this catalog is updated.
- **No WebSocket surface in this MCP**: the Tdarr web UI uses Socket.IO for
  live progress updates — out of scope here.

## Live-verification checklist (when Tdarr deploys)

Run in order; each pass closes one gap:

1. `tdarr_status()` — should return server status JSON.
2. `tdarr_full_status()` — composite snapshot.
3. `tdarr_nodes()` — empty until you connect a node.
4. `tdarr_db_statuses()` — should show library DBs after first library setup.
5. `tdarr_search_db(string=".mkv", limit=3)` — should return scanned files.
6. `tdarr_search_plugins(string="")` — should return community + local plugins.
7. **Reversible write proof**: `tdarr_create_backup(confirm=True)` →
   `tdarr_backups()` → `tdarr_delete_backup(file_name, confirm=True)`.
8. **Plugin install proof**: search → `tdarr_install_plugin(id, confirm=True)`
   → re-search to verify present → optionally delete.

After all pass, bump `plugin.json` version from `0.1.0-docverified` → `0.2.0`
and update README to drop the NOT-LIVE-VERIFIED warning.
