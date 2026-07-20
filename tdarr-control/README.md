# tdarr-control

Control of a **Tdarr** distributed transcoding server (v2 API) from Claude Code / opencode.

## ⚠️ STATUS: DOC-VERIFIED — NOT YET LIVE-VERIFIED

This plugin was built from the official Tdarr API documentation at
<https://tdarr.readme.io/reference> (v2.25.01+, frozen 2026-07-19). **Tdarr is
not deployed on this homelab yet**, so every call shape, parameter name, and
response structure is taken from the docs and has NOT been exercised against a
running instance.

When Tdarr is deployed (likely on `gh-nvidia:8265`), run:

```bash
cd tdarr-control && uv run --script mcp/_smoketest.py
```

Every passing tool closes one doc-verified → live-verified gap. Write tools
need a separate reversible proof — see `mcp/_writeproof.py` template (TBD).

## What this plugin does

Two-layer MCP server for Tdarr:

- **Generic passthrough** — `tdarr_call` reaches any documented `/api/v2/*`
  endpoint; `tdarr_list_endpoints` is the static catalog (built from the
  official API docs). 67 endpoints across system, library, plugins, nodes,
  backups, /cruddb, settings, and reports.
- **Curated tools** (~30) for the common jobs:

| Area | Tools |
|---|---|
| Status | `tdarr_status`, `tdarr_full_status`, `tdarr_nodes`, `tdarr_db_statuses`, `tdarr_performance_stats`, `tdarr_res_stats`, `tdarr_server_log`, `tdarr_node_log` |
| Library | `tdarr_search_db`, `tdarr_scan_files`, `tdarr_scan_individual_file`, `tdarr_filescanner_status`, `tdarr_verify_folder_exists`, `tdarr_get_subdirectories`, `tdarr_delete_file`, `tdarr_delete_unhealthy_files`, `tdarr_kill_file_scanner` |
| Plugins | `tdarr_search_plugins`, `tdarr_search_flow_plugins`, `tdarr_search_flow_templates`, `tdarr_read_plugin`, `tdarr_install_plugin`, `tdarr_delete_plugin`, `tdarr_sync_plugins`, `tdarr_update_plugins`, `tdarr_verify_plugin` |
| Nodes | `tdarr_nodes`, `tdarr_restart_node`, `tdarr_disconnect_node`, `tdarr_alter_worker_limit`, `tdarr_poll_worker_limits`, `tdarr_cancel_worker_item`, `tdarr_kill_worker` |
| Backups | `tdarr_backup_status`, `tdarr_backups`, `tdarr_create_backup`, `tdarr_delete_backup` |
| DB (the powerful one) | `tdarr_db` (full CRUD on 8 collections), `tdarr_collections` |
| Library settings | `tdarr_toggle_folder_watch`, `tdarr_toggle_schedule`, `tdarr_add_video_codec_exclude`, `tdarr_add_audio_codec_exclude`, `tdarr_run_help_command` |
| Reports | `tdarr_list_footprint_reports`, `tdarr_transcode_user_verdict` |

**All writes confirm-gated.** Disruptive ops (`kill_worker`, `disconnect_node`,
`kill_file_scanner`) and the `/cruddb` write modes are **doubly gated** —
`confirm=true` AND a typed `acknowledge="<token>"`.

## Configuration

1. **Deploy Tdarr.** Typical Docker on `gh-nvidia`:
   ```bash
   docker run -d --name tdarr -p 8265:8265 -p 8266:8266 \
     -e PUID=1000 -e PGID=1000 \
     -e NVIDIA_VISIBLE_DEVICES=all \
     -v /tank/media:/media \
     -v tdarr_server:/app/server \
     -v tdarr_configs:/app/configs \
     -v tdarr_logs:/app/logs \
     ghcr.io/haveagitgat/tdarr:latest
   ```
   (When you actually deploy, formalize this as an Ansible playbook under
   `~/gh-Nvidia/playbooks/projects/`.)
2. **Copy** `config.example.json` → `config.local.json` (git-ignored) and fill
   in `host`/`port` (Tdarr does not require an API key — the API trusts the LAN).
3. Optional: if you front Tdarr with an auth proxy, set `api_key` +
   `api_key_header` in `config.local.json`.

Env vars (`TDARR_HOST`, `TDARR_PORT`, `TDARR_HTTPS`, `TDARR_URL_BASE`,
`TDARR_API_KEY`, `TDARR_API_KEY_HEADER`, `TDARR_VERIFY_SSL`, `TDARR_TIMEOUT`)
override the file.

## Conventions encoded (per the docs)

- Base path `/api/v2/<endpoint>`. Endpoint names are kebab-case.
- Almost all endpoints are POST with body `{"data": {...}}`. The client wraps
  your params in `data` automatically — pass just the inner object.
- 4 endpoints are GET: `/status`, `/get-nodes`, `/download-plugins`,
  `/get-server-log`.
- **No auth** by default; Tdarr trusts the LAN like the *arr stack.
- `/cruddb` is the powerful generic DB endpoint — full CRUD on 8 collections.
  Reads (getById / getAll) are not gated; all writes are confirm-gated.

## Honest gap taxonomy

- **DOC-VERIFIED (not live-verified):** all 47 tools. Built from the v2.25.01+
  official API docs.
- **Likely gap candidates (param shapes that need live confirmation):**
  - `scan_files(scan_config)` — exact `scanConfig` shape undocumented.
  - `alter_worker_limit(worker_type)` — `workerType` enum values (likely
    `cpu`/`gpu`/`transcode`).
  - `toggle_schedule(type)` — exact type values.
  - `transcode_user_verdict(verdict)` — exact verdict strings.
  - `tdarr_db(obj)` — `obj` shape varies per collection; always `getAll` first.
- **Not implemented (out of MVP scope):** WebSocket live updates (the Tdarr web
  UI uses Socket.IO — out of scope for MCP), `download-plugins` binary download,
  `client/{clientType}` (internal node↔server).

## First-deployment checklist

When Tdarr is deployed, in order:

1. Run `_smoketest.py` — fix any param-shape mismatches the live API rejects.
2. Hit `/system-status` style endpoints to verify the response shapes match
   what the curated tools assume (they're permissive — pass-through — so this
   should mostly Just Work).
3. Reversible write proof: `tdarr_create_backup(confirm=True)` →
   `tdarr_backups()` to verify → `tdarr_delete_backup(file_name, confirm=True)`
   to clean up.
4. Plugin install proof: `tdarr_search_plugins(string="Migz")` → pick a
   community plugin → `tdarr_install_plugin(plugin_id, confirm=True)` → verify
   via re-search → optionally `tdarr_delete_plugin(...)` to roll back.
5. Bump `plugin.json` version from `0.1.0-docverified` to `0.2.0` once
   live-verified.

Built with the **deep-integration-builder** methodology.
