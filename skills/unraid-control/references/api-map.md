# Unraid GraphQL API map & gap audit

Full schema SDL: `references/schema.graphql` (3,713 lines, pulled from
github.com/unraid/api tag `v4.35.1` — the exact tag matching this server's
`unraid_api_version`). Search it with `unraid_schema_search` /
`unraid_schema_type` rather than reading the raw file. This document is the
categorized summary plus the honest "what actually works" audit.

## Domain → curated tools

| Domain | Curated tools |
|---|---|
| Identity / discovery | `unraid_status`, `unraid_graphql`, `unraid_schema_search`, `unraid_schema_type`, `unraid_subscribe_once` |
| System / hardware | `unraid_info`, `unraid_vars`, `unraid_metrics`, `unraid_registration`, `unraid_config_status`, `unraid_system_time`(+`_update`) |
| Logs | `unraid_logs_list`, `unraid_log_read` |
| Notifications | `unraid_notifications`, `_create`, `_archive`, `_unread`, `_delete`, `_archive_all`, `_delete_archived` |
| Array & disks | `unraid_array`, `_set_state`, `unraid_disks`, `_assignable_disks`, `_disk`, `_array_disk_add`/`_remove`/`_mount`/`_unmount`/`_clear_stats`, `unraid_parity_history`, `unraid_parity_check` |
| Docker | `unraid_docker_containers`, `_container`, `_logs`, `_stats`, `_networks`, `_start`/`_stop`/`_restart`/`_pause`/`_unpause`/`_remove`/`_update`/`_update_all`/`_autostart_set` |
| VMs | `unraid_vms`, `_vm_start`/`_stop`/`_pause`/`_resume`/`_force_stop`/`_reboot`/`_reset` |
| Shares | `unraid_shares` |
| Users / API keys | `unraid_me`, `unraid_api_keys`, `_api_key_roles_catalog`, `_api_key_create`, `_api_key_delete`, `_api_key_role` |
| Network | `unraid_network_interfaces` |
| UPS | `unraid_ups`, `unraid_ups_config`(+`_set_config`) |
| Settings | `unraid_settings`(+`_update` generic), `unraid_ssh_settings_update`, `unraid_temperature_config_update`, `unraid_theme_set`, `unraid_locale_set` |
| Plugins | `unraid_plugins`, `unraid_installed_unraid_plugins`, `_plugin_api_add`/`_remove`, `_plugin_install`, `_plugin_install_language`, `_plugin_install_operation`(s) |
| RClone / backup | `unraid_rclone_settings`, `_rclone_remote_create`/`_delete`, `unraid_flash_backup_initiate` |

Anything not in this table is reachable through `unraid_graphql` — find the
field with `unraid_schema_search`.

## Gap audit — Works / Fixable / Hard-limit

Following the standard three-bucket taxonomy. "Live-executed" = actually run
against GH-Nvidia during the build; "shape-verified" = arguments/fields
checked byte-for-byte against the authoritative schema SDL but not executed
(true of every `confirm=True`-gated write, since writes are never
self-tested — see Safety in SKILL.md).

### Works (live-verified reads, all curated tools return real data)
System (`info`/`vars`/`metrics`/`registration`/`config`/`systemTime`), logs,
notifications (read + create, with the id-bug workaround), array + all disk
types, Docker (containers/detail/logs/networks + **live per-container stats
via WebSocket subscription**), shares, `me`/`apiKeys`/roles catalog, network
interfaces, UPS config (read), settings (unified JSON form), installed
plugins (both kinds), RClone remotes, schema search/type against the bundled
offline SDL, generic `unraid_graphql` passthrough, generic
`unraid_subscribe_once` WebSocket passthrough.

### Fixable → closed during this build
- `createNotification`'s broken return id → worked around client-side (see
  `conventions.md`).
- No plain-query docker stats (subscription-only, no per-container arg) →
  built a WebSocket subscribe-and-filter helper.
- No `restart` mutation at this API version → composed from `stop`+`start`.
- Several non-null schema fields null-crash on specific devices
  (`Disk.bytesPerSector`, `RCloneBackupSettings.drives`, `InfoPci/Gpu.type`)
  → those fields dropped from curated queries (documented in
  `conventions.md` so custom `unraid_graphql` calls can avoid the same trap).
- `vars.sysCacheSlots` NaN crash (no cache pool) → dropped from the query.
- `parityHistory` errors instead of empty list when never run → caught and
  normalized to `[]`.
- **No GraphQL mutation exists to edit a container's environment
  variables at all** — confirmed against the schema (`DockerMutations` only
  has `start`/`stop`/`pause`/`unpause`/`removeContainer`/`updateContainer`/
  `updateContainers`/`updateAllContainers`/`updateAutostartConfiguration`;
  editing env vars is template-file territory,
  `/boot/config/plugins/dockerMan/templates-user/*.xml`, entirely outside
  the API). Closed with a separate, narrowly-scoped SSH layer
  (`unraid_ssh_test`, `unraid_docker_env_get`, `unraid_docker_env_set`) that
  does `docker inspect` → `stop`+`rm`+`run` with the same config plus the
  requested env changes, and best-effort syncs the matching XML template so
  the Unraid UI's Edit screen stays accurate. Requires separate SSH
  credentials in config (`ssh_host`/`ssh_user` + `ssh_password` or
  `ssh_key_path`) — unset by default, so this layer is opt-in.

### Hard limits — named plainly, not worked around
- **Unraid Connect / cloud features are entirely unavailable**: `connect`,
  `cloud`, `remoteAccess`, and `network { accessUrls }` are absent from the
  live schema (not even a permission error — the fields don't exist),
  because the **Unraid Connect plugin isn't installed** on this server
  (`unraid_plugins` → `[]`). Installing it is a user decision (adds a cloud
  dependency); if done, re-run `unraid_schema_search("connect")` — those
  fields should appear. `servers` (the local-only server list, not Connect's
  remote-access layer) works fine without it.
- **VM Manager is disabled** — `unraid_vms` reports `available: false`. No
  VMs are configured/enabled on this box (libvirt/KVM off in Settings). All
  `unraid_vm_*` mutations will fail the same way until VMs are enabled in the
  webGUI — that's a one-time settings change only the user should make.
- **No UPS is connected** — `unraid_ups` reports `connected: false`
  (apcupsd has nothing to report). `unraid_ups_config` still reads the
  (currently inert) configuration.
- **Registration is TRIAL** — `unraid_registration` shows `type: "TRIAL"`,
  i.e. this server isn't running under a purchased Unraid license key. Not
  something the API can fix; surfacing it here because it's the kind of
  thing worth knowing (some features — Connect, multi-array beyond the trial
  disk-count cap — are license-gated upstream of anything this plugin
  controls).
- **Live GraphQL introspection is permanently off by design** on this
  server (a production-safety default, not a bug) — worked around via the
  bundled offline schema, not something to "fix" by flipping a setting.

### Reachable only via generic passthrough (not curated — lower-traffic / setup-only)
- **OnboardingMutations** (`completeOnboarding`, `resetOnboarding`, etc.) —
  fresh-install wizard state, not relevant to an already-configured server.
- **Docker organizer/folder mutations** (`createDockerFolder`,
  `setDockerFolderChildren`, `moveDockerEntriesToFolder`, etc.) — the
  webGUI's drag-and-drop container-grouping UI state; cosmetic organization,
  not container control.
- **OIDC provider configuration** — `oidcProviders`/`oidcConfiguration` are
  readable; there's no dedicated mutation in this schema version (managed via
  the generic `unraid_settings_update` JSON writer instead, same as most
  settings-form fields that lack a typed mutation).
- **`updateServerIdentity`** (rename the server / set model) — simple enough
  to not need a wrapper: `unraid_graphql('mutation($n:String!){
  updateServerIdentity(name:$n){name} }', {"n":"..."})`.
- **`syncDockerTemplatePaths` / `resetDockerTemplateMappings` /
  `refreshDockerDigests`** — maintenance utilities for the Docker template
  cache; rarely needed, reach them directly if you do.
