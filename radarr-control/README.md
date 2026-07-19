# radarr-control

Full control of a Radarr movie manager (v3+ REST API) from Claude Code / opencode.

Verified against **Radarr 6.3.0.10514** on the homelab NAS (`192.168.0.133:8310`).

## What this plugin does

A two-layer MCP server for Radarr:

- **Generic passthrough** — `radarr_call` reaches any `/api/v3/*` endpoint;
  `radarr_list_endpoints` is the hand-enumerated master index (Radarr does
  not publish OpenAPI).
- **Curated tools** (~22) for status, library, activity, commands, and config:

| Area | Tools |
|---|---|
| System | `radarr_status`, `radarr_logs`, `radarr_system_tasks`, `radarr_system_backups` |
| Library | `radarr_list_movies`, `radarr_get_movie`, `radarr_lookup_movies`, `radarr_add_movie`, `radarr_update_movie`, `radarr_delete_movie`, `radarr_movie_files`, `radarr_collections` |
| Activity | `radarr_calendar`, `radarr_queue`, `radarr_history`, `radarr_wanted_missing`, `radarr_wanted_cutoff`, `radarr_blocklist` |
| Commands | `radarr_command`, `radarr_command_status`, `radarr_search_movie`, `radarr_refresh_movie` |
| Config | `radarr_quality_profiles`, `radarr_root_folders`, `radarr_tags`, `radarr_languages`, `radarr_notifications`, `radarr_download_clients`, `radarr_indexers`, `radarr_import_lists`, `radarr_custom_formats` |

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
- **Hard limits:** Radarr publishes no OpenAPI — the endpoint catalog is
  hand-enumerated from live probes (2026-07-19). A new Radarr major version
  could add endpoints not in the catalog; `radarr_call` still reaches them
  via the generic path.

Built with the **deep-integration-builder** methodology.
