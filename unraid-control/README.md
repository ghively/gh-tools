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
  - **99 curated tools** (106 total with the generic passthrough and SSH
    layers) across system health, the array & disks & parity,
    Docker (including live per-container stats over WebSocket), VMs, shares,
    notifications, UPS, network, users/API keys, settings, plugins (both
    classic `.plg` and API-level), and RClone/flash backups.
  - **A separate, opt-in SSH layer** for the things Unraid's GraphQL API
    cannot do at all (it can operate existing containers/VMs but not create
    them, and has no container-env mutation):
    - **Env editing** (`unraid_docker_env_get`, `unraid_docker_env_set`):
      `docker inspect` → `stop`+`rm`+`run` with the same config plus your
      changes, best-effort syncing the Unraid XML template.
    - **Deployment layer** — deploy apps, containers, compose stacks, and VMs
      the native Unraid way:
      - `unraid_docker_deploy` / `unraid_docker_redeploy` / `unraid_template_get`
        — writes a dockerMan template + runs with Unraid's managed labels, so
        the container shows up and is editable in the Docker tab.
      - `unraid_ca_search` / `unraid_ca_deploy` — search the Community
        Applications catalog (~4000 apps) and deploy one by its template.
      - `unraid_compose_deploy` / `unraid_compose_down` / `unraid_compose_list`
        — multi-container stacks (auto-installs the Compose Manager plugin on
        first use).
      - `unraid_vm_isos` / `unraid_vm_create` / `unraid_vm_delete` — create a
        VM (vdisk + OVMF/q35 libvirt domain + `virsh define`) so it appears in
        the VM Manager; Linux + Windows.
    - **Files** — `unraid_fs_list` / `unraid_fs_read` (reads), plus
      `unraid_fs_write` / `unraid_fs_mkdir` / `unraid_fs_move` /
      `unraid_fs_copy` / `unraid_fs_delete` (writes). System paths are
      hard-refused; recursive delete is double-gated.
    - **Shares** — `unraid_share_create` (writes the share `.cfg` + directory
      and applies it live via `emcmd`) and `unraid_share_delete` (data removal
      double-gated).
    - All deploy/create/write/delete tools are confirm-gated (vdisk/share-data
      deletion is double-gated); the whole layer stays disabled until you
      configure SSH credentials. `unraid_vm_*` refuse to touch protected VMs
      (e.g. `GH-Dev`).
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
2. **SSH credentials (optional)** — needed for the env-editing and deployment
   layers (`unraid_docker_env_*`, `unraid_docker_deploy`, `unraid_ca_deploy`,
   `unraid_compose_*`, `unraid_vm_create`/`delete`). Add `ssh_user` +
   (`ssh_password` or `ssh_key_path`) to `config.local.json` (`ssh_host`
   defaults to `host`, `ssh_port` defaults to 22). A dedicated key is
   recommended over a password. Each has an env-var override too
   (`UNRAID_SSH_HOST`, `UNRAID_SSH_PORT`, `UNRAID_SSH_USER`,
   `UNRAID_SSH_PASSWORD`, `UNRAID_SSH_KEY_PATH`). Leave them unset to
   disable this layer entirely — every other tool works without it.
   `unraid_ssh_test` verifies connectivity without changing anything.
3. **Runtime.** The MCP server launches via [`uv`](https://docs.astral.sh/uv/)
   (`uv run --script`), which auto-provisions its dependencies (`mcp`,
   `httpx`, `websockets`, `paramiko`) in a cached environment — no manual
   `pip install` needed. `uv` must be on PATH. `mcp` is pinned `<2.0.0` — the 2.0 release
   renamed `FastMCP`→`MCPServer` and moved its module path, which would break
   this (and every other unpinned `mcp>=1.4.0` plugin in this marketplace) on
   a fresh install otherwise.
4. **Load the plugin** in Claude Code (`/plugin marketplace add <this repo>`
   → `/plugin install unraid-control@gh-tools`), then run `/reload-plugins`
   or restart. Ask Claude to "check the Unraid server" or run
   `/unraid-health`.
5. **Smoke test (optional).** `cd unraid-control && uv run --script
   mcp/_smoketest.py` calls every curated read-only tool against your live
   server and prints each result's shape (no writes, no confirm-gated tools;
   the SSH layer is probed only if configured). Without a
   `config.local.json` it validates the offline schema tools and exits
   cleanly.

## Security notes

- The API key lives only in `config.local.json` (git-ignored) or your
  environment — never your root/webGUI password.
- HTTPS wasn't reachable on this box (port 443 closed) — plain HTTP only,
  LAN-only by design. If your server has HTTPS enabled, set `"https": true`.
- Every disruptive/destructive tool (array start/stop, disk add/remove/
  unmount, container stop/restart/pause/remove/update, VM stop/pause/
  force-stop/reboot/reset, API key create/delete, SSH/UPS/temperature/system-
  time settings, plugin install, RClone remote create/delete, flash backup,
  `unraid_docker_env_set`) requires `confirm=True`. The skill instructs
  Claude to confirm with you first regardless of the gate.
- SSH credentials, if configured, are a SEPARATE and more powerful trust
  boundary than the API key — root shell access. `unraid_docker_env_get`
  masks any env var whose name looks like a secret (PASS/SECRET/TOKEN/KEY/
  CRED) unless you explicitly pass `reveal_secrets=True`.

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
