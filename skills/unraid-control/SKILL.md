---
name: unraid-control
description: >-
  Control and administer an Unraid server (Unraid OS 7.x) end-to-end via the
  unraid MCP server. Use this whenever the user wants to inspect, configure,
  or operate their Unraid server — including "GH-Nvidia" — for ANY of: system
  health/CPU/RAM/temperature, the array & disks & parity checks, Docker
  containers (list/logs/stats/start/stop/update), virtual machines, shares,
  notifications, UPS monitoring, network interfaces, users & API keys,
  plugins (both classic .plg and API-level), RClone/flash backups, system
  settings, or anything else exposed by Unraid's GraphQL API. Trigger this
  skill even when the user just names their server or asks to "check the
  NAS", "restart a container", "is the array healthy", "what's using CPU", or
  "back up the flash drive" — do not answer from memory; drive the live
  server through the tools.
metadata:
  hermes:
    tags: [unraid, nas, docker, vm, array, graphql, mcp, homelab]
    category: infrastructure
    requires_tools: [unraid_status]
    config:
      - {key: unraid.host, prompt: Unraid server host/IP, default: 192.168.0.213}
required_environment_variables:
  - name: UNRAID_API_KEY
    prompt: Unraid API key (Settings -> Management Access -> API Keys, role ADMIN)
    required_for: authenticating every unraid_* call (x-api-key header)
version: 0.1.0
author: poomonkey405
---

# Unraid control

This skill drives a real Unraid server through the **`unraid` MCP server**
(tools are named `mcp__unraid__*`, shown to you as `unraid_*`). The target
box and auth are already wired up — your job is to pick the right tool/field
and interpret results.

## Mental model

Unraid exposes one **GraphQL API** at `/graphql` — very different from a
REST-CGI NAS API: there's no per-endpoint versioning or session/CSRF dance,
just an `x-api-key` header on every request. Fields are typed and
self-documenting once you have the schema (bundled offline —
`references/schema.graphql` — because this server has live introspection
disabled by default).

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for the common jobs. Prefer
   these when one fits (table below).
2. **Generic passthrough** — `unraid_graphql` runs ANY query/mutation,
   including fields with no curated wrapper. `unraid_schema_search` /
   `unraid_schema_type` find the exact field/argument names first.
   `unraid_subscribe_once` reaches the handful of fields that exist ONLY as
   a `Subscription` (over WebSocket) with no plain-query equivalent.

**Golden rule:** if a curated tool exists, use it — several curated tools
work around real server-side bugs (see below) that a naive `unraid_graphql`
call would hit. If not, discover the field with `unraid_schema_search`, then
call it with `unraid_graphql`. Never guess a server fact — read it live.

**GraphQL lets you batch reads for free** — one query can pull several
resources in one round-trip:
```graphql
{ array { state } docker { containers { id state } } notifications { overview { unread { total } } } }
```
Prefer that over several separate tool calls when you need multiple reads.

## Start here

For almost any request, call **`unraid_status`** first. It confirms the
server is reachable, the API key is valid, and returns hostname, Unraid/API
versions, array state, and container/notification counts in one shot. If it
fails, the problem is connectivity/auth (see Troubleshooting), not the task.

## Curated tools (use these first)

| Area | Tools |
|------|-------|
| Identity / discovery | `unraid_status`, `unraid_graphql`, `unraid_schema_search`, `unraid_schema_type`, `unraid_subscribe_once` |
| System | `unraid_info`, `unraid_vars`, `unraid_metrics`, `unraid_registration`, `unraid_config_status`, `unraid_system_time`/`_update` |
| Logs | `unraid_logs_list`, `unraid_log_read` |
| Notifications | `unraid_notifications`, `_create`, `_archive`, `_unread`, `_delete`, `_archive_all`, `_delete_archived` |
| Array & disks | `unraid_array`, `_array_set_state` (start/stop), `unraid_disks`, `_assignable_disks`, `_disk`, `_array_disk_add`/`_remove`/`_mount`/`_unmount`/`_clear_stats`, `unraid_parity_history`, `unraid_parity_check` |
| Docker | `unraid_docker_containers`, `_container`, `_logs`, `_stats` (live, via WebSocket), `_networks`, `_start`/`_stop`/`_restart`/`_pause`/`_unpause`/`_remove`/`_update`/`_update_all`/`_autostart_set` |
| Docker env vars (SSH-backed, separate from the GraphQL layer above) | `unraid_ssh_test` (check connectivity first), `unraid_docker_env_get` (read, masks secret-looking values), `unraid_docker_env_set` (write, confirm-gated — stops/recreates the container) |
| VMs | `unraid_vms`, `_vm_start`/`_stop`/`_pause`/`_resume`/`_force_stop`/`_reboot`/`_reset` |
| Shares | `unraid_shares` |
| Users / API keys | `unraid_me`, `unraid_api_keys`, `_api_key_roles_catalog`, `_api_key_create`, `_api_key_delete`, `_api_key_role` |
| Network | `unraid_network_interfaces` |
| UPS | `unraid_ups`, `unraid_ups_config`/`_set_config` |
| Settings | `unraid_settings` (+ `_update` generic escape hatch), `_ssh_settings_update`, `_temperature_config_update`, `_theme_set`, `_locale_set` |
| Plugins | `unraid_plugins`, `unraid_installed_unraid_plugins`, `_plugin_api_add`/`_remove`, `_plugin_install` (.plg URL), `_plugin_install_language`, `_plugin_install_operation`(s) |
| RClone / backup | `unraid_rclone_settings`, `_rclone_remote_create`/`_delete`, `unraid_flash_backup_initiate` |

`references/api-map.md` has the full domain breakdown plus the honest
Works/Fixable/Hard-limit gap audit — read it when you need to know whether
something is actually possible on this server (e.g. VMs and UPS are Hard
Limits here — see below). `references/common-tasks.md` has copy-paste
`unraid_graphql` recipes for non-curated jobs (server rename, OIDC, Docker
folder organization, onboarding). `references/conventions.md` documents the
auth model, error codes, and every server-side quirk/bug discovered while
building this — **read it before assuming a raw `unraid_graphql` failure is
your mistake**; several non-null schema fields crash on null data for
specific devices on this box, and that's documented there.

## Known Hard Limits on this server — don't imply otherwise

- **VMs are disabled** (VM Manager off in Settings) — `unraid_vms` returns
  `available: false`. Any `unraid_vm_*` call will fail identically. If the
  user wants VMs, that's a one-time webGUI setting only they should flip.
- **No UPS is connected** — `unraid_ups` returns `connected: false`.
- **Unraid Connect isn't installed** — remote-access/cloud fields
  (`connect`, `cloud`, `remoteAccess`) don't exist in the live schema at all.
- **Registration is TRIAL**, not a purchased license.

Report these plainly if relevant to what the user asked — don't paper over
them or suggest a fix through this plugin (they're webGUI/account decisions).

## Safety — treat the server as production

This box runs real services (Docker containers serving media/downloads,
array storage with real data). Be deliberate:

- **Reads are free.** Inspect freely to answer questions.
- **Confirm before writing or disrupting.** Every curated tool that
  stops/removes/reboots/resets something, changes the array/disk layout,
  changes SSH/UPS/temperature-monitoring/system-time config, writes settings,
  installs a plugin, or creates/deletes an API key requires `confirm=True` —
  that gate is a backstop, not a substitute for actually asking the user
  first when the action is non-trivial.
- **`unraid_array_set_state("STOP")` is the single most disruptive action
  available** — it unmounts every array disk, taking down every
  array-backed share, Docker container, and VM at once. Only run it with
  explicit, specific user intent.
- **Prefer reversible steps** and read back after a change (e.g. re-list
  after a mutation) to verify it took effect. Report what actually happened,
  including failures — don't claim success you didn't observe.

## Interpreting results

- Sizes/capacities are usually **bytes** (some as strings for large values,
  e.g. `array.capacity.kilobytes` is actually kilobytes despite the name —
  check units per-field) — convert for humans.
- Array/disk `status`: `DISK_OK` is healthy; `DISK_NP`/`DISK_INVALID`/
  `DISK_DSBL`/anything with `_NP_`/`_DSBL` needs attention.
- `smartStatus`: `OK` is healthy; anything else (including `UNKNOWN` for
  some USB/NVMe devices — not itself alarming) merits a mention.
- Docker `state`: `RUNNING`/`PAUSED`/`EXITED`.
- VM `state`: `RUNNING`/`PAUSED`/`SHUTOFF`/`CRASHED` (CRASHED needs
  attention).
- Notification `importance`: `ALERT` > `WARNING` > `INFO` — surface unread
  `ALERT`s prominently in any status/health summary.

## Troubleshooting

- **`unraid_status` fails / connection refused:** the server may be off or
  unreachable, or `config.local.json` (host/api_key) is wrong. Confirm the
  host is pingable and port 80 (or the configured port) is open.
- **`UNAUTHENTICATED`:** the API key is missing/invalid/revoked — check it
  still exists via the webGUI or `unraid_api_keys` (if you have another
  working key).
- **`FORBIDDEN`:** the key's role doesn't cover this field — `unraid_me`
  shows current roles/permissions; needs `ADMIN` for most writes.
- **`GRAPHQL_VALIDATION_FAILED` on a custom query:** wrong field/argument
  name — check `unraid_schema_type` for the exact shape before retrying.
- **`INTERNAL_SERVER_ERROR` with "Cannot return null for non-nullable
  field":** likely one of the documented null-crash quirks (see
  `conventions.md`) — drop that field from your selection rather than
  assuming you misnamed something.
