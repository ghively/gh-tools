# unraid-control

Full, authenticated control of an Unraid server over its official GraphQL
API, from Claude Code. Built and tested against **GH-Nvidia**, running
**Unraid OS 7.3.2** / **unraid-api 4.35.1**.

## What's inside

- **MCP server** (`mcp/unraid_server.py`) — authenticates with a single
  `x-api-key` header (no session/CSRF dance) and exposes:
  - **Generic passthrough** (`unraid_graphql`) reaching the **entire GraphQL
    schema** — Query, Mutation, and (via a WebSocket helper,
    `unraid_subscribe_once`) Subscription. Live introspection is disabled by
    default on Unraid, so the schema is shipped offline
    (`skills/unraid-control/references/schema.graphql`, pulled from
    github.com/unraid/api at the exact tag matching this server's API
    version) and searchable via `unraid_schema_search`/`unraid_schema_type`.
  - **84 curated tools** across system health, the array & disks & parity,
    Docker (including live per-container stats over WebSocket), VMs, shares,
    notifications, UPS, network, users/API keys, settings, plugins (both
    classic `.plg` and API-level), and RClone/flash backups.
- **Skill** (`skills/unraid-control/`) — teaches Claude how to drive the
  server, with a categorized **API map + honest gap audit**
  (Works/Fixable/Hard-limit), verified **task recipes**, and an
  **auth/conventions** reference documenting every server-side quirk found
  while building this (including a couple of genuine Unraid API bugs worked
  around client-side — see below).
- **Commands** (`commands/`) — `/unraid-health`, `/unraid-docker`,
  `/unraid-storage`, `/unraid-notifications`.

## Setup

1. **Credentials.** In the Unraid webGUI: Settings → Management Access → API
   Keys → create a key (role `ADMIN` for full control). Copy
   `config.example.json` → `config.local.json` and fill in your host and the
   key. `config.local.json` is git-ignored so the key is never committed. Any
   field can instead be set via environment variables (`UNRAID_HOST`,
   `UNRAID_PORT`, `UNRAID_HTTPS`, `UNRAID_API_KEY`, `UNRAID_VERIFY_SSL`,
   `UNRAID_TIMEOUT`), which override the file.
2. **Runtime.** The MCP server launches via [`uv`](https://docs.astral.sh/uv/)
   (`uv run --script`), which auto-provisions its dependencies (`mcp`,
   `httpx`, `websockets`) in a cached environment — no manual `pip install`
   needed. `uv` must be on PATH. `mcp` is pinned `<2.0.0` — the 2.0 release
   renamed `FastMCP`→`MCPServer` and moved its module path, which would break
   this (and every other unpinned `mcp>=1.4.0` plugin in this marketplace) on
   a fresh install otherwise.
3. **Load the plugin** in Claude Code (`/plugin marketplace add <this repo>`
   → `/plugin install unraid-control@gh-tools`), then run `/reload-plugins`
   or restart. Ask Claude to "check the Unraid server" or run
   `/unraid-health`.

## Security notes

- The API key lives only in `config.local.json` (git-ignored) or your
  environment — never your root/webGUI password.
- HTTPS wasn't reachable on this box (port 443 closed) — plain HTTP only,
  LAN-only by design. If your server has HTTPS enabled, set `"https": true`.
- Every disruptive/destructive tool (array start/stop, disk add/remove/
  unmount, container stop/restart/pause/remove/update, VM stop/pause/
  force-stop/reboot/reset, API key create/delete, SSH/UPS/temperature/system-
  time settings, plugin install, RClone remote create/delete, flash backup)
  requires `confirm=True`. The skill instructs Claude to confirm with you
  first regardless of the gate.

## Coverage notes (this server)

- **VMs are disabled** (VM Manager off) and **no UPS is connected** — both
  report a graceful `available`/`connected: false` rather than an error.
- **Unraid Connect isn't installed**, so remote-access/cloud GraphQL fields
  don't exist on this server at all (not a permission issue — they're
  absent from the live schema).
- **Two genuine Unraid API bugs were found and worked around**:
  `createNotification`'s returned id doesn't match the real notification
  file (client re-resolves the real id); several schema fields declared
  non-null return null for specific devices and crash the whole query
  (those fields are omitted from curated queries).

See `skills/unraid-control/references/` for the full API map, gap audit, and
conventions.
