# Common tasks — verified `synology_call` recipes

Copy-paste recipes for jobs that have **no curated tool**. Every call below was run
successfully against this box (DS1817+, DSM 7.3.1) unless explicitly marked. Use the
curated `synology_*` tools when one exists; drop to these for everything else.

Call shape: `synology_call(api=..., method=..., version=<optional>, params={...})`.

## Sessions & who's connected
- Active connections/sessions: `SYNO.Core.CurrentConnection` · `list`
- Kick a session: `SYNO.Core.CurrentConnection` · `kick` · `params={"targets":[<pid>]}` *(disruptive)*

## Network
- Global network config (gateway, DNS): `SYNO.Core.Network` · `get`
- Interfaces (eth/bond) + IPs: `SYNO.Core.Network.Interface` · `list`
- Change DNS/gateway: `SYNO.Core.Network` · `set` · `params={"dns_primary":"1.1.1.1", ...}` *(verify after; can drop connectivity)*
- Wake-on-LAN list: `SYNO.Core.Network.WOL` · `get_wol`
- VPN client/server config lives under `SYNO.Core.Network.VPN.*` (OpenVPN/L2TP/PPTP).

## Security
- Firewall on/off + active profile: `SYNO.Core.Security.Firewall` · `get`
- Firewall profiles: `SYNO.Core.Security.Firewall.Profile` · `list`
- Toggle firewall: `SYNO.Core.Security.Firewall` · `set` · `params={"enable_firewall":true,"profile_name":"..."}` *(can lock you out — confirm first)*
- Auto-block config: `SYNO.Core.Security.AutoBlock` · `get`; block list: `SYNO.Core.Security.AutoBlock.Rules` · `list`
- Security scan status: `SYNO.Core.SecurityScan.Status` · `system_get`
- Security Advisor settings: `SYNO.SecurityAdvisor.Conf` · `get`
- DoS protection: `SYNO.Core.Security.DoS` · `get`

## Certificates
- List certificates: `SYNO.Core.Certificate.CRT` · `list`
- Let's Encrypt account: `SYNO.Core.Certificate.LetsEncrypt.Account` · `get`

## SSH / Terminal
- SSH/telnet state + port: `SYNO.Core.Terminal` · `get`  (fields: `enable_ssh`, `ssh_port`, …)
- Enable/disable SSH: `SYNO.Core.Terminal` · `set` · `params={"enable_ssh":true,"ssh_port":22}` *(confirm; opens remote shell)*

## DSM updates
- Current update status: `SYNO.Core.Upgrade` · `status`
- Check for a new DSM: `SYNO.Core.Upgrade.Server` · `check`  (returns `update` info)
- Auto-update settings: `SYNO.Core.Upgrade.Setting` · `get`

## Storage extras (beyond `synology_storage`)
- Per-share snapshots: `SYNO.Core.Share.Snapshot` · `list` · `params={"name":"<ShareName>"}`
- Share details/permissions: `SYNO.Core.Share.Permission` · `list` · `params={"name":"<ShareName>"}`
- S.M.A.R.T. / disk health is included in `synology_storage`'s `disks[]`.

## External devices
- UPS status/settings: `SYNO.Core.ExternalDevice.UPS` · `get`
- USB storage/printers: filter `synology_list_apis("ExternalDevice")`.

## Logs
- System log (with info/warn/error counts): `SYNO.Core.SyslogClient.Log` · `list` · `params={"limit":50}`
- Log Center entries: `SYNO.LogCenter.Log` · `list` · `params={"limit":50}`
- Connection log: `SYNO.Core.SyslogClient.Log` with a log-type filter.

## Notifications
- Email notification config: `SYNO.Core.Notification.Mail.Conf` · `get`
- Push (mobile) config: `SYNO.Core.Notification.Push.Conf` · `get`
- Send a test/push: explore `SYNO.Core.Notification.Push.*` and `SYNO.DSM.PushNotification`.

## DDNS / QuickConnect
- External IP / DDNS: `SYNO.Core.DDNS.ExtIP` · `list`
- QuickConnect service permissions: `SYNO.Core.QuickConnect.Permission` · `get`

## Packages (beyond `synology_packages_list`)
- Full package info: `SYNO.Core.Package` · `get` · `params={"id":"<PackageId>"}`
- Start/stop a package: `SYNO.Core.Package` supports lifecycle methods; if `start`/
  `stop` return 103, use the package's own control API (probe with
  `synology_list_apis("Package")`). Package **status** (running/stopped) comes from
  `synology_packages_list` (`additional=["status"]`).

## Backups — covered (curated tools + recipes)
Method/param shapes were reverse-engineered from the DSM web UI's own traffic.
Note the **version**: these list methods live at **v1**, not the API's max version
(that's why guessing at max version returned 103).
- Hyper Backup tasks: `synology_backup_hyper_tasks` →
  `SYNO.Backup.Task` · `list` · v1 · `params={"node":"module_root","additional":["last_bkp_time","last_bkp_result","get_source"]}`
  (task list is in the `task_list` field).
- Active Backup devices/tasks: `synology_backup_active_devices` →
  `SYNO.ActiveBackup.Device` · `list` · v1 · `params={"load_result":true}` (optional
  `filter={"backup_type":2}` for PC/Mac). Fields include per-device last backup result.
- Active Backup activity log: `synology_backup_active_logs` →
  `SYNO.ActiveBackup.Log` · `list_log` · v1 · `params={"offset":0,"limit":50,"filter":{}}`.
- ActiveBackup server info: `SYNO.ActiveBackup.AEM` · `get_info` · v1.
- To trigger a backup run: capture the exact method the same way (open the app,
  intercept XHR); backup runs are writes — confirm with the user first.

## Sensitive settings need password-confirm elevation
Some write operations (create/modify/delete **shared folders**, set **share
permissions**, change **network** config) return **error 403** even for an admin.
DSM gates these behind a password re-confirmation: call
`SYNO.Core.User.PasswordConfirm` · `auth` · `params={"password": "..."}` to get a
`SynoConfirmPWToken`, then include that token in the sensitive `set`/`create`/`delete`
call. (The MCP client can implement this automatically once enabled.)

## Known gaps on this box (honest list)
- **VMM `SYNO.Virtualization.*`** — permission-denied (401/402/403). Full API control
  needs a **VMM Pro license**, which is not being purchased → treat VMM as **unavailable**.
- **Snapshots** — readable (`SYNO.Core.Share.Snapshot list`) but **create/delete are not**
  exposed here (needs the Snapshot Replication package / different API).
- **Firewall individual rules** — read/write via `SYNO.Core.Security.Firewall.Rules`
  `load`/`save` (needs the right `profile` id param), not `list`/`get`/`set`. Firewall
  on/off + profiles work.
- **Task Scheduler** — `get`/`create` exist but the `list` method is elusive; partial.
- **Send a notification** — notification *config* is readable; a one-off send method
  isn't wired.
- **Container Manager `SYNO.Docker.*`** — only while the package runs (start it first).

When a recipe isn't here: `synology_list_apis("<keyword>")` → pick the API →
`synology_call(..., method="get"|"list")` to learn its shape → then act.
