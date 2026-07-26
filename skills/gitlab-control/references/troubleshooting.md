# Troubleshooting — diagnosing failures across the GitLab API surface

The honest map of "this failed, why?" GitLab's API returns a small set of status
codes that each have 2-4 distinct causes. This file collapses them into a
decision tree with the test to run for each. Read alongside
`references/conventions.md` and `references/ce-vs-ee-and-security.md`.

## The 30-second triage order

1. **Auth alive?** `gitlab_status()` → if it returns user/version data, the
   token, base URL, and TLS are all fine. If it 401s, the token is bad/expired
   or the header isn't `PRIVATE-TOKEN: <token>`.
2. **Admin needed?** `gitlab_status().is_admin` → `false` means instance-admin
   endpoints (`/admin/...`, `/users/:id/block`, `/application/settings`, ...)
   will 403.
3. **Role on the resource?** `members(scope_type, scope_id, action="get",
   user_id=N)` — confirm the caller's access_level is high enough for the action
   (write = 30+, settings/merge = 40+, owner-only = 50).
4. **EE-gated?** `metadata.enterprise: false` from `gitlab_status()` → consult
   `references/ce-vs-ee-and-security.md` before declaring a 404 a bug.
5. **Wrong ID flavor?** Most "I can't find it" issues are **IID vs ID**
   confusion — see below.

## HTTP status decision tree

### 401 Unauthorized
- **Token invalid/expired.** Test: `gitlab_status()`. Fix: rotate via
  `user_tokens(action="rotate")` (relay the new secret immediately) or create a
  new PAT.
- **Wrong auth header.** GitLab expects `PRIVATE-TOKEN: <PAT>` (or
  `Authorization: Bearer <oauth-or-job-token>` for OAuth/JWT). The MCP server
  handles this for you; only relevant for raw `gitlab_rest`.
- **Token lacks the scope.** A `read_api`-only token can't mutate. List scopes
  via `gitlab_status().token.scopes`. `api` scope covers everything; for finer
  scoping use project/group access tokens.

### 403 Forbidden
- **Not an admin.** `gitlab_status().is_admin: false`. Instance-admin endpoints
  need an admin user. Some admin endpoints additionally need **admin mode**
  active (EE-only toggle — not on CE).
- **Insufficient role on the target.** `members(action="get")` → check
  `access_level`. Writers need 30+, settings/merge need 40+, transfer/delete
  need 50.
- **Action not permitted at current role even if listed.** E.g. a Reporter
  (20) can read members but not add them. Cross-reference the action against
  the access-level table in `ce-vs-ee-and-security.md`.
- **EE-gated mutation on CE.** Some mutations 403 instead of 404 (esp. via
  GraphQL `errors[]`). Confirm via `enterprise: false`.

### 404 Not Found
- **EE-only on this CE instance** (most common false-bug). Cross-reference
  `references/ce-vs-ee-and-security.md`. Examples: `/license`, `/audit_events`,
  `/groups/:id/epics`, `/projects/:id/approval_rules`, `/vulnerabilities`,
  `/groups/:id/hooks`, `/projects/:id/protected_environments`.
- **Wrong path encoding.** The project/group argument must be **URL-encoded
  full path** when it contains slashes: `gregory/sub group/proj` → `gregory/
  sub%20group/proj`. The curated tools encode for you; `gitlab_rest` does not.
- **ID vs IID confusion.** See section below.
- **Resource genuinely gone.** Deleted project, pruned tag, merged-away branch.
  For projects: `list_projects(archived=null)` plus admin can see
  pending-delete state.
- **Ref required but missing.** The repository-files endpoint
  (`/projects/:id/repository/files/:path`) **requires `?ref=`** — without it,
  400 or 404. The `read_file` tool adds it; raw `gitlab_rest` users must add it.
- **Feature not enabled on instance.** Container Registry 404s if the registry
  service isn't configured; Pages 404s if disabled in admin settings; Service
  Desk 404s without incoming-email config. `gitlab_status()` +
  `admin_settings(action="get")` reveal most of these.

### 400 Bad Request
- **Missing required parameter.** Read `errors[]` — GitLab usually names the
  missing field.
- **Wrong enum value.** E.g. `state: "open"` vs `"opened"`, `scope` typos,
  `access_level: 35` (only standard values allowed).
- **Constraint violation.** E.g. protected-branch create with
  `allowed_to_push` containing a user who isn't a member.
- **CE-restricted parameter.** Some params exist on the request shape but are
  Premium/Ultimate (e.g. `code_owner_approval_required`, `only_allow_merge_if_
  all_status_checks_passed`). They 400 on CE.

### 422 Unprocessable Entity
- **Validation failure on otherwise-well-formed input.** Duplicate name where
  uniqueness required, invalid cron expression, date in the past, email
  format, etc. Read `errors[]`.
- **State transition illegal.** E.g. merging an MR that's not mergeable
  (conflicts/unresolved threads), closing an already-closed issue. Re-fetch
  state first.

### 409 Conflict
- **Concurrent modification.** Optimistic-locking on some resources. Re-fetch
  and retry.
- **Resource in transition.** E.g. pipeline already running when you cancel,
  project export already in progress.

### 429 Too Many Requests
- **Rate limit hit.** GitLab enforces user/IP/UI/api rate limits configurable
  in admin settings. Honor `Retry-After`. The MCP server doesn't auto-retry —
  back off and re-call. To raise: `admin_settings(action="update", params={
  "rate_limit": ...}, confirm=true)` (instance-wide — confirm twice).
- Not authenticated rate limit: 500/hour default on unauthenticated.

### 5xx
- **Server-side failure.** Rare. Sidekiq overload, DB connection exhaustion,
  Gitaly timeout on huge repos. Retry with backoff; if persistent, it's a
  real instance problem (check `gitlab_status()`, sidekiq metrics via
  `admin_ops(area="sidekiq")`).

## IID vs ID — the single most common confusion

- **`id`** = numeric, unique across the instance, never reused. E.g.
  `project.id = 24`. Used in URL paths (`/projects/24`).
- **`iid`** = scoped-to-parent, per-project (issues/MRs/milestones) or
  per-group (epics, group milestones). E.g. issue #42 in project A and issue
  #42 in project B are different objects with the same `iid`.
- **URL paths use the parent `id` + child `iid`**: `/projects/:project_id/
  merge_requests/:merge_request_iid`. The curated tools take the **human-facing
  pair** (`project="ns/name"`, `iid=42`) and resolve internally — use them.
- When using `gitlab_rest` raw, you must resolve the project id first
  (`GET /projects/<urlencoded%2Fpath>` → `.id`).

## Pagination — "I only got 20 results"

- Default page size is 20 across most REST endpoints; max 100. Pass
  `per_page=100` and follow the `Link: rel="next"` header, or use the curated
  tools' `paginate=true` (auto-follows up to `max_pages`).
- `X-Total: <int>` header gives the full count (may be hidden if
  `X-Total`-disabled for performance on huge collections — fall back to
  walking `Link`).
- **Keyset pagination** is more stable on large datasets and what GitLab
  recommends for >10k-item walks: `?pagination=keyset&per_page=100&order_by=id&
  sort=asc` then follow `Link: rel="next"`.
- GraphQL list fields are cursor-paginated (`first`/`after` + `pageInfo`) — see
  `references/graphql.md`.

## Quirks & traps (verified on this instance)

- **Delayed project deletion.** When `delayed_project_deletion` is enabled
  (admin setting), `manage_project(action="delete")` does NOT remove the
  project immediately — it renames it to `deleted-<path>-<timestamp>` and
  parks it. To purge now: `manage_project(action="delete", project="deleted-
  <origpath>-<ts>", params={...}, confirm=true)` or use the
  `permanently_remove` flag where supported. Verify baseline with
  `list_projects(archived=null)` before/after destructive tests.
- **Repository files `ref` required.** `GET /projects/:id/repository/files/:path`
  without `?ref=` returns 400. `read_file` adds it; raw REST users must.
- **Per-project code search works without Elasticsearch; global doesn't.**
  `search_gitlab(scope="blobs", project="...")` works. `scope="blobs"` without
  a project returns 400 on instances without Elasticsearch (this one).
- **Group webhooks 404** on CE — they're Premium. Project webhooks work.
- **Group wikis 404** on CE — Premium. Project wikis work.
- **Bulk import needs `bulk_import_enabled`** in admin settings — verified on
  here 2026-07-15.
- **ML model registry is Free** but uses a slightly different MLflow-compatible
  REST surface (`/api/v4/projects/:id/ml`) alongside the standard REST. See
  `references/ai-and-model-registry.md`.
- **CI lint dry-run.** `ci_lint(content=..., dry_run=true)` validates without
  marking processed; `dry_run=false` is the default and what you want for a
  one-shot check.
- **Webhook SSL verification.** If a webhook target has a self-signed or
  internal cert, the delivery fails unless `enable_ssl_verification: false`
  (flag this in audits — it's a security trade-off). For internal services on
  the tailnet, prefer `allow_local_requests_from_web_hooks` (admin setting).
- **Pipeline create with variables.** `pipelines(action="create", ref="...",
  variables=[{key, value}, ...])` — variables are scoped to that pipeline only
  (not persisted). For persistent variables use `ci_variables`.

## CI/CD-specific failures

- **`jobs(action="log")` returns 0 bytes.** Either the job hasn't started
  (still pending) or the trace was erased (`jobs(action="erase")` was called or
  retention expired). Check `jobs(action="get")` → `status`, `started_at`,
  `erased_at`.
- **Pipeline "created" but never "running".** No runner picked it up — check
  `runners` for matching tags, `run_untagged`, `active`, `contactedAt`. The
  classic cause: job has `tags: [docker]` but no runner with the `docker` tag.
- **Artifacts "not found".** Artifacts expire (default 30 days, configurable
  per job with `artifacts:expire_in`). `jobs(action="artifacts_keep",
  job_id=N)` to pin. Deleted artifacts can't be recovered.
- **`ci_lint valid:false`.** Read `errors[]` and `warnings[]`. Common: wrong
  indent, `rules:` with conflicting `if`/`changes`, `needs:` referencing a job
  that doesn't exist, deprecated `only/except` mixed with `rules`.

## GraphQL-specific failures

- **`null` result.** Three indistinguishable causes — see `references/graphql.md`.
  Pair with a REST call before concluding "not found."
- **`Field 'X' doesn't exist on type 'Y'`.** You used an EE-only field on CE
  (`epic`, `iteration`, `vulnerability`, `duoSettings`, ...), OR the field was
  renamed/removed in this version. Run `__type(name: "Y")` to confirm.
- **`Query complexity exceeds X`.** Trim fields or reduce `first:`. Auth limit
  is 250.
- **Mutation returns `{ errors: [...] }`.** Read the messages — they're
  specific. Empty `errors` array = success.

## MCP server-specific failures

- **"uv run --script" slow on first call.** The MCP server self-provisions its
  deps via `uv`. The first call after a restart downloads/caches them;
  subsequent calls are fast. If it hangs >30s consistently, check network to
  PyPI.
- **`--selftest` partial failure.** Run with `gitlab_rest GET /-/selftest` or
  the server's CLI flag. It probes every read domain; a 404 in the EE-gated
  column is **expected** and not a failure.
- **Tool returns `{"error": "..."}`.** The MCP server caught an exception,
  usually a transport/parse issue. The error message is the Python exception
  text — read it literally.

## Webhook delivery failures (when a webhook won't fire)

- **SSL verification fails** at the target. Set `enable_ssl_verification: false`
  (audit-flag this) or fix the target's cert chain.
- **Target unreachable.** Local RFC1918 targets need
  `allow_local_requests_from_web_hooks_and_services` (admin setting) —
  `gitlab_status()` + `admin_settings(action="get")` to verify.
- **Secret token mismatch.** `X-Gitlab-Token` header must equal the configured
  `token`. Use `webhooks(action="test", params={trigger: "push_events"})` to
  fire a test event and inspect the response.

## When to give up gracefully

Some jobs are **not possible via the API on any tier** — the SSH/CLI-only hard
limits: backup/restore (`gitlab-backup`), `gitlab-ctl` service control, Rails
console, direct DB/Redis access, background-migration management. Documented in
`references/admin-and-self-hosting.md`. If a user asks for one of these, say so
clearly and propose the SSH path (the gh-Nvidia `ansible` agent can drive that
for this host), don't burn calls probing the API.

## Honest-reporting checklist (for every workflow)

When a workflow step fails, the report row should read:

| Step | Expected | Got | Cause | Fix |
|---|---|---|---|---|
| List audit events | 200 + events | 404 | EE-only (Premium) | N/A on CE — note in report |
| Get member role | 200 + role | 403 | caller not admin | run as admin user |

Not just *"failed."* The cause column is the value-add.
