# Instance administration & self-hosting — API surface and hard limits

Everything relative to `/api/v4` unless marked. Admin actions need an admin token; newer GitLab
also requires **Admin Mode** active (a re-auth state; a PAT with the `admin_mode` scope, or an
admin session). Verified against docs.gitlab.com for GitLab ~19.x.

## Instance admin (all CE unless noted)

- **Application settings**: `GET/PUT /application/settings` — the big config object: signup
  (`signup_enabled`, `require_admin_approval_after_user_signup`, `email_confirmation_setting`),
  visibility (`default_project_visibility`, `restricted_visibility_levels`), rate limits
  (`throttle_authenticated_api_*`, `raw_blob_request_limit`, `issues_create_limit`), CI defaults
  (`default_ci_config_path`, `shared_runners_enabled`, `ci_max_includes`), registry cleanup,
  SSRF controls (`allow_local_requests_from_web_hooks_and_services`, `dns_rebinding_protection_enabled`).
- **Identity/health reads**: `GET /version` (`{version, revision, enterprise}`), `GET /metadata`,
  `GET /application/statistics` (counts; ≥10k are approximated), `GET /application/plan_limits`,
  `GET /application/appearance`.
- **Health probes** (root, not `/api/v4`; IP-allowlisted, no token): `/-/health`, `/-/readiness`,
  `/-/liveness`. Prometheus metrics at `/-/metrics` (IP-allowlist auth, text format — a distinct
  auth class from PAT/OAuth).
- **License** (EE): `GET/POST/DELETE /license`, `/licenses`.
- **Sidekiq**: `DELETE /admin/sidekiq/queues/:queue_name` (delete jobs by metadata). No REST for
  live queue depth — that's Prometheus / the `/admin/sidekiq` UI only.
- **Repository storage moves** (CE, admin): `GET/POST /project_repository_storage_moves`,
  `/projects/:id/repository_storage_moves` (+ snippet/group variants). **Housekeeping**:
  `POST /projects/:id/housekeeping` (`task=prune|eager`).
- **Service ping**: `GET /usage_data/service_ping` (scope `read_service_ping`; returns last cached).

## Users & tokens (CE)

- Users: `GET/POST/PUT/DELETE /users[/:id]`, `GET /user` (self). State (admin, POST):
  `/users/:id/{block,unblock,deactivate,activate,ban,unban,approve,reject}`. Keys:
  `/users/:id/{keys,gpg_keys}` (admin) vs `/user/{keys,gpg_keys}` (self). Emails similarly.
  Impersonation tokens: `/users/:id/impersonation_tokens` (admin; must not be disabled instance-wide).
- Personal access tokens: `GET /personal_access_tokens[?user_id=]` (admin sees all),
  `/personal_access_tokens/self`, `POST .../:id/rotate`, `DELETE .../:id`,
  `POST /users/:user_id/personal_access_tokens` (admin creates for a user). Scopes: `api`,
  `read_api`, `read_repository`, `write_repository`, `read/write_registry`, `create_runner`,
  `manage_runner`, `ai_features`, `k8s_proxy`, `self_rotate`, + personal-only `read_user`,
  `admin_mode`, `read_service_ping`, `sudo`.
- **Project/Group access tokens** (Free now): `GET/POST/DELETE /projects\|groups/:id/access_tokens`
  + `/rotate`. Bot service accounts; `access_level` capped at the creator's role.

## Groups (CE core; several sub-features EE)

`GET/POST/PUT/DELETE /groups[/:id]`, `/subgroups`, `/descendant_groups`, `/projects`,
`POST /groups/:id/transfer`, `POST/DELETE /groups/:id/share[/:group_id]`, members + `/members/all`,
`GET/POST/PUT/DELETE /groups/:id/variables` (`environment_scope` is EE). **EE-only**: group
webhooks (`/hooks`), LDAP links, push rules, epics, iterations, billable members.

## System hooks — the best CE event surface

`GET/POST/PUT/DELETE /hooks[/:id]`, test via `POST /hooks/:id`. Admin-only, **no license gate**.
Events: `push_events`, `tag_push_events`, `merge_requests_events`, `repository_update_events`;
`token` + `enable_ssl_verification`. This is the instance-wide automation plumbing on CE (the
audit-events API is EE — on CE you get the generic activity `/events` feed, not a tamper-evident log).

## Hard limits — NO API on any tier (SSH/CLI only)

These are **out of API scope entirely** — the integration can only reach them via an SSH/exec
fallback, and should say so plainly rather than pretend:

1. **Backup / restore** — `gitlab-backup create|restore`, `gitlab-ctl backup-etc`. No API, not even status.
2. **`gitlab-ctl`** — reconfigure/restart/status/tail. No API equivalent.
3. **`gitlab-rails console` / `runner`** — full ActiveRecord access; strict superset of the API, never network-callable.
4. **Direct PostgreSQL / Redis administration** — infra-level (`gitlab.rb`, `psql`, `redis-cli`).
5. **Background migrations status/control** — Admin UI + `gitlab-rake gitlab:background_migrations:*` / Rails console only; no REST/GraphQL.

If the user wants these driven, it's an SSH job on `gh-git`/`git.hively.dev`, gated and confirmed —
not something the MCP REST layer can do. Name it as a hard limit.

## Admin mode (newer GitLab security feature)

Some admin endpoints additionally require **admin mode** active — a re-auth state that proves the
admin is intentionally doing admin work (not just having the role). On CE this is a softer
concept than on EE, but some calls may still gate behind `admin_mode` scope on the token. If a
call that should work returns 403 with an admin-mode hint, the token needs the `admin_mode`
scope AND the admin must have toggled admin mode on (UI: top-right → Admin Mode toggle; or
`POST /user/admin_mode`/`/user/disable_admin_mode` with a token that has `admin_mode` scope).
**Not commonly required on CE** — most admin endpoints work with a plain `api`-scoped admin PAT.

## User lifecycle — the state machine

Users move through states; each transition has different reversibility + access implications:

```
        ┌─ awaiting → approve ─→ active
        │                       │
        (signup)                ├─→ deactivate (reversible via activate)
                                ├─→ block     (reversible via unblock)
                                ├─→ ban       (reversible via unban)
                                └─→ delete (IRREVERSIBLE; use hard_delete to wipe contributions
                                            or soft-delete to reassign to Ghost User)
```

| State | Can sign in? | Can receive emails? | API token works? | Reversible? |
|---|---|---|---|---|
| `active` | yes | yes | yes | n/a |
| `awaiting` (confirmation pending) | no | yes | no | approve / reject |
| `deactivated` | no | no (until reactivated) | no | activate |
| `blocked` | no | no | no | unblock |
| `banned` | no | no | no | unban |
| `deleted` | — | — | — | NEVER (hard_delete wipes; soft reassigns to Ghost) |

**For offboarding** (`/gl-user-offboard`): prefer **deactivate** (leave of absence, reversible)
or **block** (immediate cut, reversible) over **delete** (permanent). Only `delete` with
`hard_delete=true` if contributions must be wiped; otherwise contributions reassign to the
Ghost User and history is preserved.

## Broadcast messages (instance-wide banner)

`admin_ops(area="broadcast_messages", action="list"|"create"|"update"|"delete")` — banner shown
at the top of every page. Fields: `message` (GFM), `starts_at`, `ends_at`, `broadcast_type`
(`banner` | `notification`), `target_path` (optional — show only on a path regex), `dismissible`.
Use for: maintenance windows, policy changes, security advisories.

## Instance feature flags

`admin_ops(area="features", action="list"|"set"|"delete")` — GitLab's internal feature gates
(NOT the project-level `feature_flags` tool which is user-facing feature flags). These toggle
GitLab's own behavior — `feature_flag_name`, `state: true|false|percentage`. **Can destabilize
the instance** — confirm twice before flipping. Examples: `search_rate_limit`, `ci_live_trace`,
`new_issue_dropdown`.

## Topics (instance-wide project tagging)

`admin_ops(area="topics", action="list"|"create"|"update"|"delete")` — projects can be tagged
with topics for discovery (`/explore/projects?topic=docker`). Fields: `name`, `title`,
`description`, `avatar` (uploaded separately). Use for org-level taxonomy ("team:payments",
"criticality:high", "lifecycle:active").

## OAuth applications

`admin_ops(area="applications", action="list"|"create"|"update"|"delete")` — register OAuth
apps that can authenticate users via GitLab (SSO for other services, bot integrations).
Fields: `name`, `redirect_uri`, `scopes` (`api`, `read_user`, `openid`, `profile`, `email`,
etc.), `confidential`. Returns `application_id` + `secret` (relay immediately).

## Two-factor enforcement

Per-group: `require_two_factor_authentication: true` on the group (enforces 2FA for members).
Instance-wide: `admin_settings(action="update", params={require_two_factor_authentication: true,
two_factor_grace_period: 48}, confirm=true)` — grace period (hours) before enforced. **On CE**,
enforcement is a soft block (user sees a "you must enable 2FA" screen); strong enforcement
needs Premium. Pair with `two_factor_authentication`-enabled users list (`users(action="list",
params={two_factor: false})`).

## Email configuration (instance-wide)

Service Desk, notifications, and signup-confirmation depend on the instance's email config (SMTP
in `gitlab.rb`). **No API to set this** — it's in the SSH-only surface. Verify delivery:
`admin_ops(area="features")` for any mail-related feature flags, or send a test by creating a
broadcast message and watching the logs.

## The SSH handoff pattern (when the API genuinely can't)

For every "I need to: backup / restore / reconfigure / repair Rails / query the DB directly"
request, the integration should:

1. **Name the limit clearly**: *"This needs `gitlab-ctl reconfigure` on gh-git — no API exists."*
2. **Hand off to the `ansible` agent** for this host: it can run the SSH command in a
   zero-drift, gated way (edit Ansible source → converge).
3. **Verify after**: many SSH actions have an API-visible effect — `gitlab_status()` for
   service health, `admin_ops(area="sidekiq")` for queue recovery, `pipelines` for CI recovery.

Do NOT pretend to do it via the API; do NOT hang trying endpoints that 404.
