# sabnzbd-control

Full control of a SABnzbd usenet downloader (v4+/5+ HTTP API) from Claude Code / opencode.

Verified against **SABnzbd 5.x** on the homelab NAS (`192.0.2.20:8080`).

## What this plugin does

A two-layer MCP server for SABnzbd:

- **Generic passthrough** — `sabnzbd_call` reaches any `/api?mode=...` endpoint;
  `sabnzbd_list_modes` is the hand-enumerated master index (SABnzbd has no
  OpenAPI; the catalog is built from the official API wiki + live probes).
- **Curated tools** (25) covering the common jobs:

| Area | Tools |
|---|---|
| Status / read | `sabnzbd_status`, `sabnzbd_version`, `sabnzbd_queue`, `sabnzbd_history`, `sabnzbd_server_stats`, `sabnzbd_warnings`, `sabnzbd_get_config`, `sabnzbd_categories`, `sabnzbd_scripts` |
| Queue control | `sabnzbd_pause`, `sabnzbd_resume`, `sabnzbd_pause_job`, `sabnzbd_resume_job`, `sabnzbd_speed_limit` |
| Job management | `sabnzbd_add_url`, `sabnzbd_add_local_file`, `sabnzbd_delete_jobs`, `sabnzbd_retry_job`, `sabnzbd_queue_change_category`, `sabnzbd_queue_change_priority`, `sabnzbd_history_clear` |
| Config / notifications | `sabnzbd_set_config`, `sabnzbd_test_email` |
| Dangerous (double-gated) | `sabnzbd_restart`, `sabnzbd_shutdown` |

**Confirm-gating is layered:**

- All writes (`confirm=True`).
- `sabnzbd_restart` and `sabnzbd_shutdown` are DOUBLY gated — they need both
  `confirm=true` AND a typed `acknowledge="restart"` / `"shutdown"` token.
  This is intentional: SABnzbd honors these modes literally. During initial
  development, a probe of `mode=shutdown` actually shut the server down (no
  auto-restart). That mistake is now structurally prevented.

## Configuration

1. Get the API key from SABnzbd **Config > General > API Key**.
2. Store it in 1Password (vault: `Homelab`, item: `SABnzbd API Key`).
3. Copy `config.example.json` → `config.local.json` (git-ignored).

```bash
op item get '<item-id>' --vault Homelab --field credential --reveal
```

Env vars (`SABNZBD_HOST`, `SABNZBD_PORT`, `SABNZBD_HTTPS`, `SABNZBD_URL_BASE`,
`SABNZBD_API_KEY`, `SABNZBD_VERIFY_SSL`, `SABNZBD_TIMEOUT`) override the file.

## Run

```bash
cd sabnzbd-control && uv run --script mcp/_smoketest.py
```

## Conventions encoded

- Auth: API key as the `apikey` query param (`output=json` is always attached).
- Modes that change state accept their inputs as query params
  (`pause?value=60`, `addurl?name=<url>`, `delete?value=<nzo_id>`).
- Server returns `{"error": "..."}` on most failures (HTTP 200, error in body)
  — the client surfaces this as a raised exception.
- Wraps the "queue delete" / "history delete" subtlety: SABnzbd deletes via
  `mode=queue&name=delete&value=<ids>` (the catalog notes this).

## Honesty notes (gap taxonomy)

- **Works (live-verified, GETs):** all reads in the smoke test pass against
  the live server (status, queue empty, history, server stats, full config).
- **Method-verified, not live-executed:** confirm-gated writes (pause, resume,
  addurl, delete, retry, set_config, per-job pause/resume, category/priority
  changes, history clear, addlocalfile) — the HTTP shape matches the
  documented API; the decline path is verified; live execution requires
  explicit owner approval.
- **Not implemented:** `addfile` (multipart NZB upload) — the generic
  `sabnzbd_call` mode can still reach it for users who can supply the body.
- **Hard limits:** SABnzbd honors `mode=shutdown` literally with no
  auto-restart; recovery requires DSM/Container Manager intervention.

Built with the **deep-integration-builder** methodology.
