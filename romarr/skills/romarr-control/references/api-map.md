# ROMarr API map

Full endpoint catalog as published live by ROMarr 0.7.0's own
`/api/v1/openapi.json` (53 operations), with the curated tool that wraps
each one. `romarr_endpoints` returns this same data live (and stays
accurate across ROMarr version upgrades); this file is a static snapshot
for quick reference.

Not wrapped by a curated tool = reach it via `romarr_call(method, path, ...)`.

| Method | Path | Summary | Curated tool |
|---|---|---|---|
| GET | `/` | The web UI | — (not an API op) |
| GET | `/api/health` | Liveness; full dependency report with a key | `romarr_health` |
| POST | `/api/import` | Import a finished download | `romarr_import` |
| GET | `/api/platforms` | Every platform, media, extensions, play route | `romarr_platforms` |
| GET | `/api/queue` | Active downloads (legacy path) | — (use `romarr_queue`, the v1 route) |
| POST | `/api/request` | Request a game | `romarr_request` |
| GET | `/api/search` | Search every configured indexer | `romarr_search` (leaks Prowlarr key — see SKILL.md) |
| GET | `/api/v1/backup` | Restorable snapshot; `?secrets=1` unmasks credentials | `romarr_backup` |
| GET | `/api/v1/blocklist` | Releases that will never be taken again | `romarr_blocklist` |
| GET | `/api/v1/calendar` | Games released recently or due soon | `romarr_calendar` |
| GET | `/api/v1/collection` | Set-acquisition batches + available DATs | `romarr_collections` |
| POST | `/api/v1/collection/control` | pause/resume/retry/cancel a batch | `romarr_collection_control` |
| GET | `/api/v1/collection/plan` | Compare a DAT against the library | `romarr_collection_plan` |
| POST | `/api/v1/collection/start` | Queue every missing title from a plan | `romarr_collection_start` |
| POST | `/api/v1/collection/step` | Request the next slice of a batch | `romarr_collection_step` |
| POST | `/api/v1/command` | Run a task: search, import or refresh | `romarr_command` |
| GET | `/api/v1/config` | Settings, credentials masked | `romarr_config` |
| GET | `/api/v1/connection/schema` | The eight notification providers | `romarr_connection_schema` |
| POST | `/api/v1/connection/test` | Send a test notification to every connection | `romarr_connection_test` |
| GET | `/api/v1/downloadclient` | Configured download clients | `romarr_download_clients` |
| GET | `/api/v1/downloadclient/schema` | The five client types and their fields | `romarr_download_client_schema` |
| POST | `/api/v1/downloadclient/test` | Test one client's connection | `romarr_download_client_test` |
| GET | `/api/v1/export` | Library/wanted/blocklist as JSON or CSV | `romarr_export` |
| GET | `/api/v1/frontend/export` | LaunchBox XML, ES-DE gamelist.xml, or Playnite JSON | `romarr_frontend_export` |
| GET | `/api/v1/frontend/formats` | Available frontend export formats | `romarr_frontend_formats` |
| GET | `/api/v1/game` | The library | `romarr_library` |
| GET | `/api/v1/history` | What ROMarr has done | `romarr_history` |
| GET | `/api/v1/hub/catalogue` | Search the ROM Hub plugin catalogue | `romarr_hub_catalogue` |
| POST | `/api/v1/hub/plugin` | Install/enable/disable/uninstall a plugin | `romarr_hub_plugin` |
| GET | `/api/v1/hub/plugins` | The plugin catalogue, unfiltered | `romarr_hub_plugins` |
| POST | `/api/v1/hub/source/check` | Whether a repo URL may be installed from | `romarr_hub_source_check` |
| GET | `/api/v1/hub/status` | Whether ROM Hub is installed and reachable | `romarr_hub_status` |
| POST | `/api/v1/hub/submit` | Validate a catalogue submission, return a link (does not post it) | `romarr_hub_submit` |
| GET | `/api/v1/indexer` | Configured indexers, keys masked | `romarr_indexers` |
| GET | `/api/v1/indexer/schema` | The nine indexer types and their fields | `romarr_indexer_schema` |
| POST | `/api/v1/indexer/test` | Test one indexer's connection | `romarr_indexer_test` |
| GET | `/api/v1/library` | Configured library servers | `romarr_libraries` |
| GET | `/api/v1/library/config` | One library's stored configuration | `romarr_library_config` |
| GET | `/api/v1/library/schema` | Library backend types and their fields | `romarr_library_schema` |
| POST | `/api/v1/library/test` | Test one library server | `romarr_library_test` |
| GET | `/api/v1/log` | Recent log lines | `romarr_logs` |
| POST | `/api/v1/login` | Exchange an API key/password for a session cookie | — (session auth; this client uses the API-key header instead) |
| GET | `/api/v1/manualimport` | Scan a directory for files ROMarr could adopt | `romarr_manual_import` |
| GET | `/api/v1/metadata/lookup` | Identify a file (matched_by: dat/filename) | `romarr_metadata_lookup` |
| GET | `/api/v1/metadata/schema` | Metadata providers and their fields | `romarr_metadata_schema` |
| GET | `/api/v1/openapi.json` | This document | — (used internally by `romarr_endpoints`) |
| GET | `/api/v1/queue` | Active downloads | `romarr_queue` |
| GET | `/api/v1/release` | Interactive search: scored candidates + reasoning | `romarr_release` |
| POST | `/api/v1/release/grab` | Grab a specific release by id | `romarr_release_grab` |
| POST | `/api/v1/restore` | Restore a backup | `romarr_restore` |
| POST | `/api/v1/setup` | First-run claim: set the admin password | — (first-run only; irrelevant once claimed) |
| GET | `/api/v1/system/counts` | Library and queue sizes | `romarr_system_counts` |
| GET | `/api/v1/system/status` | Health of every dependency + play-route counts | `romarr_status` |
| GET | `/api/v1/tag` | Tags, by library item | `romarr_tags` |
| GET | `/api/v1/wanted/missing` | Games wanted but not yet found | `romarr_wanted_missing` |
| POST | `/api/v1/webhook` | Inbound game request from a front-end | — (inbound-only; not an admin op) |
| POST | `/api/v1/webhook/ggrequestz` | Inbound request, GG Requestz shape | — (inbound-only; not an admin op) |
| GET | `/login` | The sign-in screen | — (browser UI only) |
| GET | `/metrics` | Prometheus exposition | `romarr_metrics` |

53 total operations. 44 wrapped by a curated tool or directly equivalent
(e.g. `/api/queue` legacy → use `romarr_queue`'s v1 route); the remainder
are session/first-run/inbound-only routes with no legitimate reason for
this client to call them, or the doc endpoint itself.
