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
