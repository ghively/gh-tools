# romm — RomM control plugin for Claude Code

Full control of a [RomM](https://romm.app) ROM-library server from Claude
Code. Verified against **RomM 5.x**.

## What's inside

- **MCP server** (`mcp/romm_server.py`, self-provisioning via
  `uv run --script`) with two layers:
  - a **generic passthrough** — `romm_call` / `romm_endpoints` /
    `romm_schema` — reaching every one of the server's ~189 REST operations,
    discovered live from its own OpenAPI document;
  - **~70 curated tools**: status & stats, platforms, ROM search & metadata
    editing & matching, ROM manuals/soundtracks/patches, screenshots,
    collections (manual/smart/virtual, incl. smart-collection edits), users &
    fine-grained permission groups & invite links & API keys, saves/states,
    BIOS firmware, background tasks, config exclusions & platform bindings,
    device management & pairing approval, save/state sync sessions, netplay
    rooms, play activity & sessions, game music, client feeds
    (Tinfoil/webRcade/PKGi), gamelist.xml & Pegasus exports, chunked ROM
    upload and streaming download — plus `romm_scan`/`romm_scan_status`,
    which trigger and poll library scans over **Socket.IO** (the one job
    RomM does not expose over REST) without blocking a single call for the
    whole scan.
- **Control skill** (`skills/romm-control`) teaching Claude RomM's
  conventions: auth model, error vocabulary, library folder structure,
  scan types, matching workflow, and safety rules.
- **Workflow commands**: `/romm-health`, `/romm-library`, `/romm-scan`,
  `/romm-match`, `/romm-collections`, `/romm-users`, `/romm-setup`.
- **Smoke test** (`mcp/_smoketest.py`, also a `uv run --script` file):
  exercises every read tool against your configured server and calls every
  write tool *without* `confirm` to prove the confirmation gate holds — no
  mutations. Run it after setup to verify the config end to end.

## Setup

1. Copy `config.example.json` → `config.local.json` (git-ignored) and fill
   in your server address and an API key from the RomM UI (Settings → API
   Keys).
2. Optional: add `username`/`password` to enable `romm_scan` — RomM
   authenticates its scan socket with a session cookie that an API key
   cannot mint. Everything else works with the key alone.
3. Install the plugin from this marketplace; the MCP server self-provisions
   its Python environment on first launch (needs `uv`).

## Safety model

Every destructive or disruptive tool requires `confirm=True`, which Claude
sets only after asking you. Deleting ROMs/firmware can optionally remove
files from disk — those calls spell that out in the confirmation. Read
tools never mutate anything.

## Honest coverage notes

What's genuinely covered vs. what's a deliberate boundary, not a gap:

- **Scan trigger** needs the optional username/password (Socket.IO session
  auth) — a RomM design decision, not a plugin gap. `romm_scan` handles the
  session login internally; there is intentionally no standalone login tool.
- **Admin actions** on device pairing (`romm_device_auth`), sync sessions
  (`romm_sync`), and netplay room listing (`romm_netplay_rooms`) are curated.
  What's still passthrough-only is the *other* half of each — the steps the
  pairing device/emulator client itself performs (device-auth init/token,
  sync negotiate/complete, the live netplay Socket.IO session) — these are
  protocol steps a client library runs, not things an admin invokes.
- **Auth self-service** (openid login, forgot/reset-password) is out of
  scope by design — it's a session/email flow for end users, not an admin
  API surface, and admins can already set a user's password directly via
  `romm_user_update`.
- **Screenshots, ROM manuals, and soundtracks** are curated
  (`romm_screenshot`, `romm_rom_manuals`, `romm_rom_soundtracks`). Save/state
  file uploads (as opposed to save/state metadata, which is curated) remain
  passthrough-only via `romm_call` with `file_path` — a narrower gap than
  before, not eliminated.
- Browser-side **EmulatorJS play** is a UI feature, not an API — nothing to
  cover here.
- Two things were found and fixed while building this, not just documented:
  `romm_scan`'s single blocking call (now `romm_scan`/`romm_scan_status`
  start-and-poll, so a long scan reports progress instead of going silent),
  and `romm_roms()`'s default sort (`order_by="name"` silently returns an
  empty library when unfiltered on RomM 5.x — the default is now
  `created_at`, which doesn't trigger the bug).
