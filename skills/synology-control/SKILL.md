---
name: synology-control
description: >-
  Control and administer a Synology DiskStation NAS (DSM 7.x) end-to-end via the
  synology MCP server. Use this whenever the user wants to inspect, configure, or
  operate their Synology / DSM / DiskStation / NAS — including "nas-host" and the
  DS1817+ — for ANY of: system health/CPU/RAM/temperature, storage & volumes &
  disks & SMART, shared folders & permissions, File Station browsing/upload/
  download/search, Download Station tasks, installed packages & services, users &
  groups, network/firewall/certificates/SSH, snapshots, Hyper Backup / Active
  Backup, Virtual Machine Manager, notifications, DSM updates, task scheduler, or
  anything else exposed by the DSM Web API. Trigger this skill even when the user
  just names their NAS or asks to "check the NAS", "restart a package", "see what's
  downloading", "free up space", or "is the array healthy" — do not answer from
  memory; drive the live box through the tools.
metadata:
  hermes:
    tags: [synology, dsm, nas, diskstation, storage, mcp, homelab]
    category: infrastructure
    requires_tools: [synology_status]
    config:
      - {key: synology.host, prompt: Synology DSM host/IP, default: 192.0.2.20}
      - {key: synology.username, prompt: Synology DSM admin username}
required_environment_variables:
  - name: SYNOLOGY_PASSWORD
    prompt: Synology DSM admin password
    required_for: authenticating synology_* calls (session id + CSRF token)
  - name: SYNOLOGY_OTP_CODE
    prompt: DSM 2-step verification OTP code (only if 2FA is enabled)
    required_for: completing 2FA login
    optional: true
version: 0.2.1
author: ghively
---

# Synology DSM control

This skill drives a real Synology NAS through the **`synology` MCP server** (tools
are named `mcp__synology__*`, shown to you as `synology_*`). The target box, auth,
and behavior are already wired up — your job is to pick the right tool/API and
interpret results.

## Mental model

The DSM Web API exposes **~870 APIs** named `SYNO.<Domain>.<Thing>` (e.g.
`SYNO.Core.System`, `SYNO.Core.Security.Firewall.Rules`). Each has methods
(`list`, `get`, `info`, `set`, `create`, `delete`, `start`, `stop`, …) and a
version. The server handles login, the session id, and the CSRF token for you.

Two layers of tools:

1. **Curated tools** — ergonomic one-shot calls for the common jobs. Prefer these
   when one fits (see the list below).
2. **Generic passthrough** — `synology_call` reaches *any* API, including things
   without a curated tool. This is how "control everything" actually works.
   `synology_list_apis` and `synology_describe_api` help you find the right name;
   `synology_batch` runs several calls in one round-trip.

**Golden rule:** if a curated tool exists, use it. If not, discover the API name
with `synology_list_apis`, then call it with `synology_call`. Never guess a NAS
fact — read it from the box.

## Start here

For almost any request, call **`synology_status`** first. It confirms the NAS is
reachable and returns model, DSM version, uptime, RAM and temperature in one shot.
If it fails, the problem is connectivity/auth (see Troubleshooting), not the task.

## Curated tools (use these first)

| Area | Tools |
|------|-------|
| Identity / health | `synology_status`, `synology_system_info`, `synology_utilization`, `synology_logs` |
| Storage | `synology_storage` (volumes, disks, SMART, pools), `synology_snapshots_list` |
| Files | `synology_fs_shares`, `synology_fs_list`, `synology_fs_search`, `synology_fs_download`, `synology_fs_upload`, `synology_fs_create_folder`, `synology_fs_rename`, `synology_fs_copy_move`, `synology_fs_delete` |
| Downloads | `synology_downloads_list`, `synology_download_add`, `synology_download_control` |
| Packages / apps | `synology_packages_list`, `synology_services_list`, `synology_package_control` (start/stop), `synology_package_available`, `synology_package_uninstall` |
| Containers (Docker) | `synology_containers_list`, `synology_container_inspect`/`_logs`/`_stats`, `synology_container_start`/`_stop`/`_restart`/`_delete`/`_create`, `synology_images_list`/`_image_pull`/`_image_remove`, `synology_projects_list`/`_project_inspect`/`_start`/`_stop`/`_create`/`_delete` |
| DSM updates | `synology_dsm_update_check`, `synology_dsm_update_apply` (reboots) |
| Users / groups | read: `synology_users_list`, `synology_groups_list`; write: `synology_user_create`/`_modify`/`_set_password`/`_delete`, `synology_group_create`/`_delete`/`_add_members` |
| Shares | read: `synology_shares_list`; write: `synology_share_create`/`_delete`/`_set_permissions` |
| Security / network | `synology_firewall_status`, `synology_firewall_rules`, `synology_firewall_set_enabled`, `synology_autoblock_list`, `synology_autoblock_manage` (add/remove, gated), `synology_network_set_dns`, `synology_scheduler_list` |
| Certificates / power | `synology_certificates_list`, `synology_ups_status` |
| Backups | `synology_backup_hyper_tasks`, `synology_backup_active_devices`, `synology_backup_active_logs` |
| Power | `synology_reboot`, `synology_shutdown` |
| Anything else | `synology_call`, `synology_batch`, `synology_list_apis`, `synology_describe_api` |

## Sensitive settings need elevation (shares, permissions, network)

Creating/deleting/modifying **shared folders**, setting **share permissions**, and
changing **network** config return **error 403** unless the request carries a
password-confirmation token. The curated tools for these (and `synology_call` with
`elevate=True`) handle it automatically — the client fetches a `SynoConfirmPWToken`
via `SYNO.Core.User.PasswordConfirm` and attaches it. If you hit a 403 on any other
sensitive write, retry the generic call with `elevate=True`.

## Deploying & managing apps and containers

- **Packages/apps:** `synology_packages_list` shows what's installed and running;
  `synology_package_control(package_id, action)` starts/stops them (stop needs
  `confirm=True`); `synology_package_available` lists the online Package Center
  catalog; `synology_package_uninstall` removes one.
- **Containers (Container Manager / Docker):** the `SYNO.Docker.*` APIs only work
  when the **ContainerManager package is running** — if container tools return
  error 102, start it with
  `synology_package_control(package_id="ContainerManager", action="start")`.
  Then: `synology_containers_list`, inspect/logs/stats, and
  start/stop/restart/delete. To deploy, `synology_image_pull` an image then
  `synology_container_create`, or — preferred for multi-container stacks — use
  `synology_project_create` with a docker-compose YAML string.
- **DSM OS updates:** `synology_dsm_update_check` to see if one is available;
  `synology_dsm_update_apply` installs and **reboots** (gated behind `confirm=True`
  — always check with the user first).

## Discovery-first workflow (for anything not curated)

Certificates (`synology_certificates_list`), UPS (`synology_ups_status`), auto-block
(`synology_autoblock_list` / `synology_autoblock_manage`) and firewall rules
(`synology_firewall_rules`) now have curated tools — prefer them. Other requests
(VPN, notifications, DDNS, general network config, triggering a Hyper Backup run)
have no curated tool. Do this:

1. **Find the API.** `synology_list_apis(filter="Firewall")` →
   `SYNO.Core.Security.Firewall.Rules`, etc. Filter by a domain keyword.
2. **Call it.** Start with a read method to learn the shape:
   `synology_call(api="SYNO.Core.Security.Firewall.Rules", method="get")`.
3. **Act.** Use `set`/`create`/`delete`/`start`/`stop` with the parameters you saw.

`references/api-map.md` is the full categorized list of every API on this box —
read it when you need to locate a capability. `references/common-tasks.md` has
copy-paste-ready `synology_call` recipes for the most-requested non-curated jobs
(firewall, certs, updates, snapshots, VMM, scheduler, network, notifications).
`references/conventions.md` documents the auth model, error codes, parameter
encoding, pagination, and box-specific quirks — consult it when a call misbehaves.

## Parameters

`synology_call`'s `params` is a plain object. Arrays and objects are JSON-encoded
for you, so pass them naturally:

```
synology_call(
  api="SYNO.Core.User", method="list", version=1,
  params={"type": "local", "additional": ["email", "description", "expired"]}
)
```

Omit `version` to use the API's max version. Pass it explicitly when a method only
exists at a specific version (some `list` methods differ by version — e.g. this
box's `SYNO.Core.Service` needs `method="get"` at v3, not `list`).

## Safety — treat the NAS as production

This box holds real data (tens of TB across two volumes). Be deliberate:

- **Reads are free.** Inspect freely to answer questions.
- **Confirm before writing or disrupting.** Before deleting files, changing
  permissions/firewall/network/shares, stopping services, or removing users,
  state what you're about to do and get a clear go-ahead — a locked-out firewall
  rule or a stopped SMB service can cut off access to the box itself.
- **Destructive curated tools are gated.** Every destructive or disruptive curated
  tool — `synology_reboot`/`_shutdown`, `synology_fs_delete`, download-task delete,
  container/image/project stop & delete, package stop & uninstall,
  `synology_dsm_update_apply`, share/user/group writes, the firewall toggle, and
  `synology_autoblock_manage` (block/allow-list add/remove) — requires `confirm=True`.
  That gate is a backstop, not a substitute for asking.
- **Prefer reversible steps** and read-back after a change (e.g. re-list after a
  `set`) to verify it took effect. Report what actually happened, including
  failures — don't claim success you didn't observe.

## Interpreting results

- Sizes are **bytes** (strings for large values) unless noted — convert for humans.
- Volume `status`: `normal` is healthy; `attention`/`degraded`/`crashed` need
  attention — surface these prominently.
- Disk/SMART `status` likewise; report temperatures.
- DSM error codes are mapped to messages: `102` = API not registered here, `103` =
  wrong method, `104` = wrong version, `105`/`117` = permission, `119` = session/CSRF
  (the server auto-retries this once). See `references/conventions.md` for the table.

## Troubleshooting

- **`synology_status` fails / connection refused:** the NAS may be off or
  unreachable, or `config.local.json` (host/port/credentials) is wrong. Confirm the
  host is pingable and DSM is on the configured port (5001 https / 5000 http).
- **Auth errors (400/403):** wrong password, or 2-factor is on and no `otp_code` is
  set. 2FA codes expire in ~30s, so they suit a one-off, not a long-lived server.
- **`102 API does not exist`:** the API isn't registered for this session. Try
  `synology_describe_api` to probe it; some package APIs aren't exposed via the
  standard Web API on this DSM (noted in the api-map).
