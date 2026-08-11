# radarr-control

Full control of a Radarr movie manager (v3+ REST API) from Claude Code / opencode.

Verified against **Radarr 6.3.0.10514** on the homelab NAS (`192.168.0.133:8310`).

## What this plugin does

A two-layer MCP server for Radarr:

- **Generic passthrough** — `radarr_call` reaches any `/api/v3/*` endpoint;
  `radarr_list_endpoints` searches the live route table (`/system/routes`,
  ~470 operations — Radarr publishes no OpenAPI) and falls back to a static
  catalog if the server is unreachable. Every operation is annotated
  curated-vs-generic-only.
- **Curated tools** (~65) for status, library, activity, commands, and config:

| Area | Tools |
|---|---|
| System | `radarr_status`, `radarr_logs`, `radarr_log_files`, `radarr_system_tasks`, `radarr_system_backups`, `radarr_system_routes`, `radarr_filesystem`, `radarr_system_restart` / `radarr_system_shutdown` (double-gated) |
| Library | `radarr_list_movies`, `radarr_get_movie`, `radarr_lookup_movies`, `radarr_add_movie`, `radarr_update_movie`, `radarr_delete_movie`, `radarr_movies_bulk_edit`, `radarr_movies_bulk_delete`, `radarr_movie_files`, `radarr_delete_movie_file`, `radarr_collections`, `radarr_rename_preview`, `radarr_manual_import`, `radarr_parse` |
| Activity | `radarr_calendar`, `radarr_calendar_ics`, `radarr_queue`, `radarr_queue_delete`, `radarr_queue_grab`, `radarr_queue_bulk_delete`, `radarr_history`, `radarr_history_since`, `radarr_wanted_missing`, `radarr_wanted_cutoff`, `radarr_blocklist`, `radarr_blocklist_delete`, `radarr_blocklist_bulk_delete`, `radarr_releases`, `radarr_grab_release` |
| Commands | `radarr_command`, `radarr_command_status`, `radarr_search_movie`, `radarr_refresh_movie` |
| Config | `radarr_quality_profiles`, `radarr_quality_definitions`, `radarr_root_folders`, `radarr_tags`, `radarr_tag_details`, `radarr_tag_create`, `radarr_tag_delete`, `radarr_languages`, `radarr_notifications`, `radarr_download_clients`, `radarr_indexers`, `radarr_import_lists`, `radarr_custom_formats`, `radarr_delay_profiles`, `radarr_release_profiles`, `radarr_remote_path_mappings`, `radarr_import_exclusions`, `radarr_auto_tagging`, `radarr_config_section`, `radarr_update_config_section`, `radarr_provider_test`, `radarr_provider_action`, `radarr_crud` (generic CRUD over 14 config resource types) |

**All writes are confirm-gated** (`confirm=True` required). DELETE of a movie
or POST /command only runs after explicit user approval.

## Configuration

1. Create an API key in Radarr under **Settings > General > Security > API Key**.
2. Store it in 1Password (vault: `Gregory`, item: `Radarr API Key (GH-Storage)`),
   with the URL in the `serverurl` field.
3. Copy `config.example.json` → `config.local.json` (git-ignored) and fill in.
   The `api_key` should normally be retrieved from 1Password, not hardcoded.

```bash
op item get '<item-id>' --vault Gregory --field credential --reveal
```

Env vars (`RADARR_HOST`, `RADARR_PORT`, `RADARR_HTTPS`, `RADARR_URL_BASE`,
`RADARR_API_KEY`, `RADARR_VERIFY_SSL`, `RADARR_TIMEOUT`) override the file.

## Run

The MCP server is launched by opencode/Claude Code from `.mcp.json` via
`uv run --script mcp/server.py` — it self-provisions `mcp` and `httpx`.

Standalone smoke test:

```bash
cd radarr-control && uv run --script mcp/_smoketest.py
```

## Conventions encoded

- Auth: API key in the `X-Api-Key` header.
- POST/PUT expects the FULL object — write tools GET-merge-PUT internally so
  you can pass just the keys to change.
- POST /command with `{"name": "<CommandName>", ...}` triggers async jobs;
  poll status at `radarr_command_status(id)`.

## Honesty notes (gap taxonomy)

- **Works (live-verified, GETs):** all reads in the smoke test pass against
  the live library.
- **Method-verified, not live-executed:** confirm-gated writes (add/update/
  delete movie, POST /command). The HTTP shape is correct; live execution
  requires explicit owner approval.
- **Hard limits:** Radarr publishes no OpenAPI — `radarr_list_endpoints`
  reads the live route table from `/api/v3/system/routes` at runtime, with a
  hand-enumerated static catalog (2026-07-19) as offline fallback. New
  endpoints in future Radarr versions are still reachable via `radarr_call`.

Built with the **deep-integration-builder** methodology.
