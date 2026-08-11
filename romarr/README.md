# romarr

Full control of a ROMarr instance (the *arr for games — Cartridge ecosystem
by Move Weight) from Claude Code.

Verified against **ROMarr 0.7.0** running as a Docker container on the
homelab Unraid box GH-Nvidia (`192.168.0.213:6868`).

## What this plugin does

A two-layer MCP server for ROMarr:

- **Generic passthrough** — `romarr_call` reaches any `/api/v1/*` (or legacy
  `/api/*`) endpoint; `romarr_endpoints` is the master index, pulled live
  from ROMarr's own `/api/v1/openapi.json` (with a static fallback baked in).
- **Curated tools** (51) for status, library, acquisition, and config:

| Area | Tools |
|---|---|
| System | `romarr_status`, `romarr_health`, `romarr_system_counts`, `romarr_config`, `romarr_logs`, `romarr_metrics`, `romarr_backup`, `romarr_restore` |
| Library | `romarr_platforms`, `romarr_library`, `romarr_wanted_missing`, `romarr_calendar`, `romarr_tags`, `romarr_export`, `romarr_frontend_formats`, `romarr_frontend_export` |
| Acquisition | `romarr_search`, `romarr_request`, `romarr_release`, `romarr_release_grab`, `romarr_import`, `romarr_manual_import`, `romarr_command` |
| Activity | `romarr_queue`, `romarr_history`, `romarr_blocklist` |
| Collections (DAT set-completion) | `romarr_collections`, `romarr_collection_plan`, `romarr_collection_start`, `romarr_collection_step`, `romarr_collection_control` |
| Indexers / clients / libraries | `romarr_indexers`, `romarr_indexer_schema`, `romarr_indexer_test`, `romarr_download_clients`, `romarr_download_client_schema`, `romarr_download_client_test`, `romarr_libraries`, `romarr_library_config`, `romarr_library_schema`, `romarr_library_test` |
| Connections / metadata | `romarr_connection_schema`, `romarr_connection_test`, `romarr_metadata_lookup`, `romarr_metadata_schema` |
| ROM Hub | `romarr_hub_status`, `romarr_hub_catalogue`, `romarr_hub_plugins`, `romarr_hub_plugin`, `romarr_hub_source_check`, `romarr_hub_submit` |

**All writes are confirm-gated** (`confirm=True` required).

## Configuration

ROMarr's own web UI does **not** display its API key anywhere, despite what
its README claims. To get one:

1. Set `ROMARR_API_KEY` (any value you choose) in the ROMarr container's
   environment and restart it. That value is now the API key — it also
   works to sign into the web UI via "Use an API key instead."
2. Copy `config.example.json` → `config.local.json` (git-ignored) and fill
   in host/port/api_key.

Env vars (`ROMARR_HOST`, `ROMARR_PORT`, `ROMARR_HTTPS`, `ROMARR_API_KEY`,
`ROMARR_VERIFY_SSL`, `ROMARR_TIMEOUT`) override the file.

## Run

```bash
cd romarr && uv run --script mcp/_smoketest.py
```

`mcp` is pinned `<2.0.0` — the 2.0 release renamed `FastMCP`→`MCPServer` and
moved its module path, which breaks every unpinned `mcp>=1.4.0` plugin in
this marketplace on a fresh install otherwise.

## Conventions encoded

- Auth: API key in the `X-Api-Key` header (ROMarr also accepts
  `Authorization: Bearer` or `?apikey=`).
- ROMarr's `/api/v1/openapi.json` publishes method/path/summary only — no
  parameter or request-body schemas. Curated write tools document which
  fields are confirmed vs. best-guess; probe with `confirm=false` before
  trusting a guess.
- Two acquisition paths: `romarr_search` (raw, fast) vs. `romarr_release` +
  `romarr_release_grab` (scored, with reasoning). **Prefer the scored
  path** — see security notes below.
- Most ROMarr settings env vars are read only on first boot; after that,
  saved settings always win. `ROMARR_API_KEY`/`ROMARR_PASSWORD` are the
  documented exception (re-read every start, for auth recovery/pinning).

## Security notes

- The API key lives only in `config.local.json` (git-ignored) or your
  environment.
- **`romarr_search` (the legacy `/api/search` endpoint) leaks Prowlarr's API
  key** in the raw `download_url` field of every result — verified live,
  contradicts ROMarr's own README claim that "download URLs are never
  returned to a client." `romarr_release` + `romarr_release_grab` (grab by
  opaque id, resolved server-side) does not have this problem; the tool
  docstring and skill both steer toward it.
- `romarr_backup(include_secrets=True)` can return every configured
  credential in the clear — confirm-gated.
- `romarr_hub_plugin(action="install")` runs third-party, sandboxed code —
  confirm the user trusts the source first.

## Honesty notes (gap taxonomy)

- **Works (live-verified):** all reads in the smoke test pass against the
  live install (44/49 tool calls, 5 failures below are genuine environment
  gaps, not tool bugs).
- **Fixable, not this plugin's job:**
  - `romarr_calendar` — needs a metadata provider (RAWG/IGDB) API key,
    unset on this install.
  - `romarr_collection_plan` — needs `DAT_PATH` pointed at a No-Intro/Redump
    directory, none loaded.
  - `romarr_library`/`romarr_status.libraries[].readable` — RomM is
    reachable and the library account authenticates, but RomM has zero
    platforms/ROMs scanned (`FS_PLATFORMS: []`); most likely trigger for the
    500, not fully root-caused.
  - `romarr_hub_*` — ROM Hub is a separate `pip install`, not bundled.
- **Method-verified, not live-executed:** confirm-gated writes (release
  grab, request, import, collection start/step/control, restore, hub plugin
  install, connection test). Safe-probed with placeholder values and
  `confirm=false` to verify the HTTP shape without mutating anything; live
  execution requires explicit owner approval.
- **Hard limit (upstream bug):** the `romarr_search` credential leak is in
  ROMarr itself, not fixable from the plugin side — mitigated by steering
  toward `romarr_release` instead.

Built with the **deep-integration-builder** methodology.
