---
name: romarr-control
description: >-
  Control and administer a ROMarr instance (the *arr for games — Cartridge
  ecosystem by Move Weight) via the romarr MCP server. Use this whenever the
  user wants to inspect, configure, operate, or troubleshoot their ROMarr —
  including ANY of: server status/health, the game library, wanted/missing
  titles, upcoming calendar, active download queue, history, blocklist,
  requesting a game, interactive search & scored release grabbing, DAT-based
  (No-Intro/Redump) collection set-completion batches, indexers, download
  clients (qBittorrent/SABnzbd/NZBGet), library backends (RomM, Gaseous,
  Retrom, or a plain folder), notification connections, metadata lookup,
  frontend exports (LaunchBox/ES-DE/Playnite), backup/restore, or the ROM Hub
  plugin catalogue. Trigger this skill whenever the user says "ROMarr", "my
  ROM requests", "what games are missing", "grab this ROM", "request
  <game>", or names the Cartridge/Move Weight stack — do not answer from
  memory; drive the live ROMarr server through the tools.
metadata:
  hermes:
    tags: [romarr, roms, retro-gaming, emulation, game-library, servarr, mcp, homelab, cartridge]
    category: media
    requires_tools: [romarr_status]
    config:
      - {key: romarr.host, prompt: ROMarr host/IP, default: 192.0.2.10}
      - {key: romarr.port, prompt: ROMarr port, default: 6868}
required_environment_variables:
  - name: ROMARR_API_KEY
    prompt: ROMarr API key
    required_for: authenticating romarr_* calls to the /api/v1 REST surface
version: 0.1.0
author: ghively
---

# ROMarr control

This skill drives a real ROMarr instance through the **`romarr` MCP server**
(tools shown as `romarr_*`). Verified against **ROMarr 0.x** running as a
Docker container ("ROMarr") on the homelab Unraid box Unraid-Host
(`192.0.2.10:6868`), part of the **Cartridge** stack (Prowlarr for
indexing, SABnzbd for usenet, RomM as the library backend).

## Mental model

ROMarr is one REST surface, mostly under `/api/v1/<resource>` with a handful
of legacy routes at `/api/<resource>` (health, import, platforms, queue,
request, search). ~59 operations total. Key conventions:

- Auth: `X-Api-Key` header on every request except `/`, `/api/health` and
  `/api/v1/login`. **ROMarr's own UI does not display its API key anywhere**
  (despite the project README claiming it does) — the only way to get one is
  to set `ROMARR_API_KEY` in the container's environment and restart; see
  "Known quirks" below.
- Two layers: curated tools (prefer), generic passthrough
  (`romarr_call` / `romarr_endpoints` — ROMarr *does* publish a live
  OpenAPI 3.1 doc at `/api/v1/openapi.json`, but it only lists
  method/path/summary, no parameter or body schemas, so treat every
  parameter name as best-effort until confirmed).
- All writes are **confirm-gated**: pass `confirm=true` only after the user
  explicitly approved. Read-only "test a connection" tools
  (`romarr_indexer_test`, `romarr_download_client_test`,
  `romarr_library_test`) are NOT confirm-gated — they verify reachability
  without persisting anything.
- Two acquisition paths exist side by side: the quick path
  (`romarr_search` → raw indexer hits) and the scored path
  (`romarr_release` → `romarr_release_grab`, with reasoning per candidate).
  **Prefer the scored path** — see the security note below on why.

**Golden rule:** if a curated tool exists, use it. Otherwise find the
endpoint with `romarr_endpoints` then call it with `romarr_call`. Never
guess a write's body shape without probing first (call with obviously
placeholder values and `confirm=false` — the confirm-gate means nothing
mutates, and ROMarr's error responses are usually specific enough to reveal
what's missing).

## Start here

Call **`romarr_status`** first (or `romarr_health`, same shape, different
route): dependency health for Prowlarr, the library backend(s), platform
count, queue size.

## Tool map

| Job | Tool |
|---|---|
| Health snapshot | `romarr_status()` / `romarr_health()` |
| Library/queue/download-client identity counts | `romarr_system_counts()` |
| Full settings (masked) | `romarr_config()` |
| Browse the library | `romarr_library(params=)` |
| What's missing | `romarr_wanted_missing()` |
| Recently released / due soon | `romarr_calendar()` — needs a metadata provider with an API key configured, see quirks |
| Every platform + how it plays here | `romarr_platforms()` |
| Quick indexer search (raw) | `romarr_search(game=, platform=)` — **leaks Prowlarr's API key, see security note** |
| Scored interactive search | `romarr_release(game=, platform=)` |
| Grab a scored release (write) | `romarr_release_grab(release_id=, confirm=)` |
| Request a game end-to-end (write) | `romarr_request(title=, platform=, confirm=)` |
| Run a background task (write) | `romarr_command(name=, confirm=, extra=)` — accepted names for `name` are unconfirmed beyond the summary ("search, import or refresh"); probe first |
| Active downloads | `romarr_queue()` |
| Activity log | `romarr_history(params=)` |
| Blocked releases | `romarr_blocklist()` |
| DAT set-completion batches | `romarr_collections()` |
| Plan a DAT vs. library | `romarr_collection_plan(params=)` — needs a DAT loaded, see quirks |
| Start/step/control a batch (write) | `romarr_collection_start/step/control(..., confirm=)` |
| Indexers | `romarr_indexers()` / `romarr_indexer_schema()` / `romarr_indexer_test(config)` |
| Download clients | `romarr_download_clients()` / `romarr_download_client_schema()` / `romarr_download_client_test(config)` |
| Library backends (RomM/Gaseous/Retrom/folder) | `romarr_libraries()` / `romarr_library_config(library_id=)` / `romarr_library_schema()` / `romarr_library_test(config)` |
| Notification connections | `romarr_connection_schema()` / `romarr_connection_test(confirm=)` — sends a REAL notification |
| Metadata providers/lookup | `romarr_metadata_schema()` / `romarr_metadata_lookup(params=)` |
| Frontend exports (LaunchBox/ES-DE/Playnite) | `romarr_frontend_formats()` / `romarr_frontend_export(fmt=)` |
| Library/wanted/blocklist export (JSON/CSV) | `romarr_export(kind=, fmt=)` |
| Logs / metrics | `romarr_logs()` / `romarr_metrics()` |
| Backup / restore | `romarr_backup(include_secrets=, confirm=)` / `romarr_restore(backup=, confirm=)` |
| ROM Hub plugin catalogue | `romarr_hub_status()` / `romarr_hub_catalogue()` / `romarr_hub_plugins()` / `romarr_hub_plugin(plugin_id=, action=, confirm=)` |
| Manual import scan | `romarr_manual_import(directory=)` |
| Import a finished download (write) | `romarr_import(payload=, confirm=)` — body shape unverified, probe first |
| Escape hatch | `romarr_call(method, path, params=, body=, confirm=)`, `romarr_endpoints(search=)` |

## Known quirks (verified live, 2026-08-07/08, ROMarr 0.x)

- **No API key in the UI.** The project README says "the API key is
  generated on first run and shown under Settings > General" — the actual
  shipped UI's General page has no such field, only Prowlarr/qBittorrent/
  RomM connection URLs ("Credentials live in the environment file, not
  here"). The only way to pin/recover a key is `ROMARR_API_KEY` in the
  container's environment + restart (this also signs into the web UI via
  "Use an API key instead").
- **Most settings env vars are first-boot-only; auth vars are the
  exception.** The Unraid template warns that ROMarr reads its general
  config env vars ONCE, on first start — after that saved settings always
  win, and editing the template does nothing. `ROMARR_API_KEY` and
  `ROMARR_PASSWORD` are explicitly re-read on every start (they're the
  auth-recovery/pinning mechanism), so pinning a key on an already-claimed
  install works via a container restart.
- **`romarr_search` leaks a credential.** The legacy `/api/search` endpoint
  returns a raw `download_url` (for `best` and every item under
  `top`/`indexers`) that embeds Prowlarr's API key in the clear
  (`...?apikey=<key>&link=...`) — contradicting the README's claim that
  "download URLs are never returned to a client." `romarr_release` +
  `romarr_release_grab` (grab by opaque id, resolved server-side) does not
  have this problem. Prefer that path, and never forward `romarr_search`'s
  raw output anywhere untrusted.
- **`error` can appear as a normal, non-error field.** Some ROMarr
  responses (e.g. `GET /api/v1/indexer`) legitimately include an
  `"error": null` key as part of successful data — don't treat the mere
  presence of an `error` key as failure; check its truthiness.
- **No per-operation parameter schemas.** `/api/v1/openapi.json` publishes
  only method/path/summary/response-codes, not request bodies or query
  params. Every "exact param name unverified" note in the tool docstrings
  reflects this — verify live before assuming.
- **`romarr_calendar` needs a metadata provider configured** (RAWG or IGDB
  with an API key under Settings > Metadata) — without one it errors "no
  metadata provider with an API key is configured" rather than returning
  an empty list.
- **`romarr_collection_plan` needs a DAT loaded** (No-Intro/Redump, under
  Settings or `DAT_PATH`) — without one it errors "no DAT loaded" rather
  than returning an empty comparison.
- **ROM Hub is a separate install.** `romarr_hub_plugins`/`romarr_hub_catalogue`
  error "No module named 'rom_hub'" unless the host has run
  `pip install "rom-hub @ git+https://github.com/BlizzHacker/rom-hub@master"`
  inside the ROMarr container/image — it is not bundled by default.
- **RomM library reads intermittently 500** on this install
  (`romarr_library`/`romarr_status.libraries[].readable=false`,
  `"HTTP 500 from the library server."`). RomM itself is reachable and the
  configured library account authenticates fine (`/api/platforms` → 200),
  but RomM has zero platforms/ROMs scanned yet (`FS_PLATFORMS: []`) — most
  likely trigger, not fully root-caused. Scan at least one platform in RomM
  and re-check `romarr_status`.

## Safety

- Confirm every write with the user before passing `confirm=true` — this
  applies to `romarr_call` on non-GET methods too.
- `romarr_backup(include_secrets=True)` and `romarr_restore` are the two
  highest-blast-radius tools: the former can exfiltrate every configured
  credential, the latter overwrites live configuration. Treat both as
  requiring explicit, specific user approval, not a blanket "yes go ahead."
- `romarr_hub_plugin(action="install")` runs third-party, sandboxed-by-host
  code — confirm the user trusts the specific plugin first.
- `romarr_connection_test` pings every configured external notification
  service for real — don't call it just to "check if it works" without
  telling the user it'll fire a real message.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every call 401s | No `ROMARR_API_KEY` configured, or wrong value | Set `ROMARR_API_KEY` in the ROMarr container's environment and restart; use that value in `config.local.json` |
| `romarr_library` / status shows `readable: false` | Library backend (e.g. RomM) errored | Check `romarr_status` for the `detail` field; for RomM specifically, confirm at least one platform is scanned |
| `romarr_calendar` errors "no metadata provider" | No RAWG/IGDB key set | Add one under Settings > Metadata, or accept the gap |
| `romarr_collection_plan` errors "no DAT loaded" | No No-Intro/Redump DAT configured | Point `DAT_PATH` at a DAT directory, or add one under Settings |
| Hub tools error "No module named 'rom_hub'" | ROM Hub not installed | `pip install "rom-hub @ git+https://github.com/BlizzHacker/rom-hub@master"` on the host/image |
| A write tool's body guess is rejected | ROMarr's OpenAPI has no param schemas | Call with `confirm=false` and read the error detail — it usually names the missing/wrong field; fall back to `romarr_call` once you know the right shape |
