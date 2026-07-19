---
name: radarr-control
description: >-
  Control and administer a Radarr movie manager instance via the radarr MCP
  server. Use this whenever the user wants to inspect, configure, operate,
  or troubleshoot their Radarr — including ANY of: server status & health,
  listing / searching / adding / updating / deleting movies, looking up new
  movies from TMDB, movie collections, movie files, wanted missing/cutoff,
  upcoming releases (calendar), active download queue, history, blocklist,
  quality profiles, root folders, languages, tags, custom formats,
  notifications, download clients, indexers, import lists, application logs,
  system tasks, system backups, OR triggering commands (RefreshMovie,
  MoviesSearch, DownloadedMoviesScan, Backup, etc.). Trigger this skill
  whenever the user says "Radarr", "check my movies", "what's missing",
  "search for X", "add the movie Y", or "why isn't Z downloading" — do not
  answer from memory; drive the live Radarr server through the tools.
---

# Radarr control

This skill drives a real Radarr movie manager through the **`radarr` MCP
server** (tools are named `mcp__radarr__*`, shown to you as `radarr_*`).
The target server, auth, and behavior are already wired up — your job is to
pick the right tool/endpoint and interpret results. Verified against
**Radarr 6.3.0.10514** on the homelab NAS (`192.168.0.133:8310`,
"GH-Storage"). Auth = `X-Api-Key` header (admin API key in 1Password
"Gregory" vault).

## Mental model

Radarr is one REST surface under `/api/v3/<resource>` (~50 endpoints). Key
conventions the tools encode:

- All writes need the FULL object: POST/PUT to `/movie/{id}` ignores omitted
  fields or resets them. The write tools here GET-merge-PUT internally; use
  `radarr_update_movie(patch='{"monitored": false}')`, never hand-POST a
  partial object through `radarr_call`.
- Commands (`RefreshMovie`, `MoviesSearch`, etc.) are ASYNC — POST /command
  returns a job object you can poll with `radarr_command_status(id)`.
- All writes are **confirm-gated** in code: pass `confirm=true` only after
  the user explicitly approved the action. State this clearly before passing
  it. (DELETE /movie removes from library only; pass `delete_files=true` to
  also delete the media file from disk — irreversible.)

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for common jobs. Prefer these.
2. **Generic passthrough** — `radarr_call` reaches *any* /api/v3 endpoint;
   `radarr_list_endpoints` searches the hand-enumerated catalog (Radarr
   publishes no OpenAPI).

**Golden rule:** if a curated tool exists, use it. Otherwise find the
endpoint with `radarr_list_endpoints`, then call it with `radarr_call`.
Never guess a library/server fact — read it from the server.

## Start here

For almost any request, call **`radarr_status`** first: identity, version,
library counts (monitored / with-file / monitored-missing), queue summary,
health warnings, and disk usage.

## Tool map

| Job | Tool |
|---|---|
| Health snapshot | `radarr_status` |
| Browse library | `radarr_list_movies(monitored=, has_file=, page=, page_size=)` |
| One movie (with files) | `radarr_get_movie(movie_id)` |
| Files attached to a movie | `radarr_movie_files(movie_id)` |
| Search for new movies | `radarr_lookup_movies(term="dune part two")` |
| Add a movie (write) | `radarr_add_movie(tmdb_id, quality_profile_id, root_folder_path, ...)` |
| Edit a movie (write) | `radarr_update_movie(movie_id, patch='{"monitored": false}')` |
| Delete a movie (write) | `radarr_delete_movie(movie_id, delete_files=, confirm=)` |
| Collections | `radarr_collections(monitored_only=)` |
| What's missing | `radarr_wanted_missing()` (monitored, no file) |
| What's upgradeable | `radarr_wanted_cutoff()` |
| Upcoming releases | `radarr_calendar(start=, end=)` |
| Active downloads | `radarr_queue()` |
| Recent activity | `radarr_history(movie_id=, event_type=)` |
| Auto-rejected releases | `radarr_blocklist()` |
| Logs | `radarr_logs(level="warn")` |
| Scheduled tasks | `radarr_system_tasks()` |
| DB backups | `radarr_system_backups()` |

## Commands (trigger async jobs)

`radarr_command(name=, movie_ids=, confirm=)` and conveniences:

- `RefreshMovie` — re-scan disk + refresh metadata for one or all movies.
- `MoviesSearch` — search indexers for monitored missing movies.
- `MissingMoviesSearch` — search for ALL monitored missing movies (heavy).
- `DownloadedMoviesScan` — scan drone factory / completed downloads.
- `RefreshMonitoredDownloads` — sync with download clients (harmless, idempotent).
- `RenameMovie` — rename files using the configured renaming schema.
- `Backup` — create an immediate DB backup.
- `ApplicationUpdate` — check for + install an app update (admin only).

Common pattern: search a missing movie by id, then poll for completion:
`radarr_search_movie(movie_id)` → `radarr_command_status(id)`.

## Configuration tools (read-only)

- `radarr_quality_profiles()` — needed before `add_movie`.
- `radarr_root_folders()` — needed before `add_movie` (use the `path` exactly).
- `radarr_languages()`, `radarr_tags()`, `radarr_custom_formats()`.
- `radarr_download_clients()`, `radarr_indexers()`, `radarr_import_lists()`.
- `radarr_notifications()`.

## Adding a movie — workflow

```
radarr_lookup_movies(term="dune part two")
  → get the tmdb_id
radarr_quality_profiles()  → get the profile id (e.g. HD-1080p)
radarr_root_folders()      → get the exact path (e.g. /volume2/Media/Movies)
radarr_add_movie(
    tmdb_id=..., quality_profile_id=..., root_folder_path="...",
    monitored=True, minimum_availability="released",
    search_for_movie=False, confirm=True
)
```

State to the user before passing `confirm=True`:
- Which movie you're adding and from where (TMDB id).
- Which root folder and quality profile.
- Whether you'll trigger an immediate search.

## Generic passthrough

If a curated tool doesn't exist:

1. `radarr_list_endpoints(search="quality")` → find the right path.
2. `radarr_call(method="GET", path="/api/v3/qualityDefinition")`.

WRITES via `radarr_call` are NOT confirm-gated — only use this for reads,
or after explicit owner approval for writes.

## Safety

- **Confirm-gate every write.** State the change to the user, pass
  `confirm=true` only after approval.
- DELETE /movie with `delete_files=true` deletes the media file from disk —
  irreversible. Default to `delete_files=false` and let the user opt in.
- POST /command triggers ACTIVE WORK (searches, scans). Even "harmless"
  commands like `RefreshMonitoredDownloads` make live calls to download
  clients — say what you'll do first.
- Never run a "test" write against the live library without explicit owner
  approval. Reversible proofs (add a throwaway, then delete it) are good;
  destructive proofs are not.

## Honesty

- **Live-verified (reads):** all GETs in the smoke test pass against the
  live library (Dune, TRON Legacy, etc.).
- **Method-verified (writes):** the HTTP shape is correct; live execution
  awaits explicit owner approval.
- **Hard limits:** no OpenAPI; catalog hand-enumerated as of 2026-07-19.

See `references/api-map.md` for the full endpoint list.
