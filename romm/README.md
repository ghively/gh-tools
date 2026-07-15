# romm — RomM control plugin for Claude Code

Full control of a [RomM](https://romm.app) ROM-library server from Claude
Code. Verified against **RomM 5.0.0**.

## What's inside

- **MCP server** (`mcp/romm_server.py`, self-provisioning via
  `uv run --script`) with two layers:
  - a **generic passthrough** — `romm_call` / `romm_endpoints` /
    `romm_schema` — reaching every one of the server's ~189 REST operations,
    discovered live from its own OpenAPI document;
  - **~50 curated tools**: status & stats, platforms, ROM search & metadata
    editing & matching, collections (manual/smart/virtual), users &
    permissions & invite links & API keys, saves/states, BIOS firmware,
    background tasks, config exclusions & platform bindings, play activity &
    sessions, game music, client feeds (Tinfoil/webRcade/PKGi), gamelist.xml
    & Pegasus exports, chunked ROM upload and streaming download — plus
    `romm_scan`, which triggers library scans over **Socket.IO** (the one
    job RomM does not expose over REST).
- **Control skill** (`skills/romm-control`) teaching Claude RomM's
  conventions: auth model, error vocabulary, library folder structure,
  scan types, matching workflow, and safety rules.
- **Workflow commands**: `/romm-health`, `/romm-library`, `/romm-scan`,
  `/romm-match`, `/romm-collections`, `/romm-users`, `/romm-setup`.

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

- **Scan trigger** needs the optional username/password (Socket.IO session
  auth) — a RomM design decision, not a plugin gap.
- Interactive **netplay/sync/device-auth handshakes** are Socket.IO
  client flows aimed at emulator frontends; the REST sides are reachable via
  `romm_call`, but driving a netplay session isn't a CLI job.
- Browser-side **EmulatorJS play** is a UI feature, not an API.
- Asset **uploads** (saves/states/screenshots per-emulator) exist via
  `romm_call` with `file_path`; curated upload tools cover ROMs and
  firmware.
