# DSM Web API conventions & quirks (this box)

Verified against gh-storage / DS1817+, DSM 7.3.1-86003. The `synology` MCP server
implements all of this for you; this is background for interpreting behavior and
crafting `synology_call` requests.

## Auth model (handled by the server)

- Login: `SYNO.API.Auth` v7, `method=login`, `format=sid`, `enable_syno_token=yes`
  → returns a `sid` (session id) and a `synotoken` (CSRF token).
- Every subsequent call sends `_sid=<sid>` **and** the header `X-SYNO-TOKEN: <synotoken>`.
  Omitting the token yields **error 119** on Core APIs. The server always sends both.
- Sessions can drop (errors 106/107/119). The server transparently re-logs-in once
  and retries the call.
- 2-factor: if the account has OTP enabled, set `otp_code` in config/env. Codes
  expire in ~30 s, so 2FA is impractical for a long-running server — prefer a
  dedicated non-2FA service account, or an app/scoped credential.

## Endpoints

- Base: `https://<host>:5001/webapi/` (HTTPS self-signed on LAN → cert verify off).
- Almost every API lives at `entry.cgi`. The exact path per API comes from
  `SYNO.API.Info` discovery; the server resolves it automatically.
- File download uses `SYNO.FileStation.Download` (raw bytes, GET); upload uses
  `SYNO.FileStation.Upload` (multipart POST). The server wraps both.

## Parameter encoding

- Scalars pass as-is. **Arrays/objects must be JSON-encoded** — the server does this,
  so pass native lists/objects in `params`:
  `params={"additional": ["email","description"], "type": "local"}`.
- Booleans serialize to `true`/`false`.
- Pagination: many `list` methods accept `offset` and `limit` (default limits vary;
  pass an explicit `limit` for big collections). Results usually include `total`.
- `additional=[...]` requests extra fields, but **only valid keys** are accepted —
  an invalid key (or a native field like `version`) triggers **error 120
  "condition"**. When unsure, call without `additional` first to see native fields.

## Version selection

- Omit `version` and the server uses the API's `maxVersion`. That is usually right,
  but some methods only exist at a specific version. Known example on this box:
  `SYNO.Core.Service` lists via `method="get"` at **v3**, not `list`.

## Batching

- `synology_batch` / `SYNO.Entry.Request` runs many calls in one HTTP round-trip
  (`mode="sequential"` or `"parallel"`). Result is `{"has_fail":bool,"result":[...]}`
  with one entry per sub-call, in order. Great for dashboards/health checks.

## Error codes

| Code | Meaning |
|------|---------|
| 100 | Unknown error |
| 101 | Missing/invalid api·method·version parameter |
| 102 | **API not registered** for this session/DSM (try `synology_describe_api`) |
| 103 | **Method does not exist** on that API (try `list`/`get`, or another name) |
| 104 | Version not supported for this functionality |
| 105 / 117 | Insufficient permission / needs manager rights |
| 106 / 107 | Session timeout / duplicate-login interruption (auto-retried) |
| 119 | SID/CSRF token error (auto-retried) |
| 120 | Invalid parameter (often a bad `additional` key — see above) |
| 400–410 | Auth errors: 400 wrong account/pw, 403 need 2FA code, 407 blocked IP |

## Box-specific quirks discovered

- **Container Manager (Docker):** the `SYNO.Docker.*` APIs are **only registered while
  the ContainerManager package is running**. If they return error 102, start the
  package: `synology_package_control(package_id="ContainerManager", action="start")`.
  Confirmed working method names on this box: `SYNO.Docker.Container` ·
  `list`/`get`/`get_log`/`start`/`stop`/`restart`/`delete`/`create` (list needs
  `limit`+`offset`); `SYNO.Docker.Container.Resource` · `get` (stats);
  `SYNO.Docker.Image` · `list`/`pull_start`/`delete`; `SYNO.Docker.Project` (compose) ·
  `list`/`get`/`create`/`start`/`stop`/`delete`; `SYNO.Docker.Network` · `list`.
- **Virtual Machine Manager:** the `SYNO.Virtualization.*` APIs return permission
  errors (401/402/403) even for an administrator; full API control requires a VMM
  **Pro license**, which is not being purchased. Treat VMM as **unavailable** via
  this plugin.
- **Sensitive settings elevation:** create/modify/delete of shares, share
  permissions, and network config return **403** until the request carries a
  password-confirmation token. Get it from `SYNO.Core.User.PasswordConfirm` · `auth`
  (`{"password": ...}`) → `SynoConfirmPWToken`, then pass that token on the write.
  This is a normal DSM protection, not a hard block — the server automates it
  (`synology_call(..., elevate=True)`; curated write tools do it themselves).
- **Security Advisor report** (`SYNO.SecurityAdvisor.Report`) needs manager rights
  (117); its config (`SYNO.SecurityAdvisor.Conf get`) and the security scan status
  (`SYNO.Core.SecurityScan.Status system_get`) are readable.
- **`admin` and `poomonkey405`** are both in the `administrators` group.
- One volume (`volume_2`, btrfs) currently reports status **`attention`** — worth
  surfacing in any health check.
