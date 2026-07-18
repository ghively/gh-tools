---
description: Audit a project (or the instance) for security posture, protection, CI health, and hygiene
argument-hint: [project | "instance"]
---

Audit **$ARGUMENTS** and report findings ranked by severity. Read-only — make NO changes;
propose fixes at the end. Read `references/ce-vs-ee-and-security.md` and `references/admin-and-self-hosting.md`.

**If a project:**
1. Settings: `get_project(project)` — visibility, `only_allow_merge_if_pipeline_succeeds`,
   `remove_source_branch_after_merge`, squash, default branch.
2. Branch protection: `protected(project, kind="branches", action="list")` and `..."tags"` —
   flag: default branch unprotected, `allow_force_push:true`, developers allowed to push to main.
3. Membership: `members(project, action="list_all")` — flag over-privileged direct members
   (Owner/Maintainer sprawl), external users, stale invites (`membership_requests(...,kind="invitations")`).
4. Tokens: `access_tokens(scope_type="project", scope_id=project, action="list")` — flag tokens
   near/after expiry or with broad scopes.
5. CI: `read_file(project, ".gitlab-ci.yml")` — is there a pipeline? Are SAST/Secret-Detection
   templates included (see `references/ce-vs-ee-and-security.md`)? `ci_variables(...)` — flag
   unmasked/unprotected secrets. `pipeline_schedules(...)`, `pipeline_triggers(...)` — stale tokens.
6. Webhooks: `webhooks(scope_type="project", scope_id=project, action="list")` — flag
   `enable_ssl_verification:false` or missing secret token.
7. Hygiene: `branches(project, action="list")` — count stale/merged branches; recent `pipelines(...)`
   failures; artifact bloat (`get_project(project)` statistics).

**If "instance"** (admin): `gitlab_status()`, `admin_settings(action="get")` (signup, visibility,
rate limits, SSRF/`allow_local_requests_from_web_hooks`), `users(action="list")` (admins, blocked,
external), `user_tokens(action="list")` (expiring PATs), `runners(action="list")` (stale/offline),
`admin_ops(area="system_hooks")`. Note EE-gated gaps (no audit-events API on CE) honestly.

Deliver: a Works/At-Risk/Fix table with the exact remediation call for each finding (don't run them).
