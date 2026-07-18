---
name: gitlab-control
description: >
  Drive a self-hosted GitLab CE instance through the gitlab MCP server — projects,
  repository files, branches, merge requests, issues, CI/CD pipelines, runners,
  users/admin, groups, search, releases, webhooks, packages, and the full REST +
  GraphQL surface via generic passthrough. Use whenever the user asks to inspect or
  manage anything on their GitLab server (git.hively.dev).
---

# Controlling GitLab CE

Built and live-verified against GitLab **19.0.0 CE** at `https://git.hively.dev`
with an **admin** token — instance administration works, not just project access.

## Layered approach — pick the right tool

1. **Curated tools first** (59): `list_projects`, `get_project`, `manage_project`,
   `repo_tree`, `read_file`, `write_files`, `repo_extras`, `branches`, `tags`, `commits`,
   `compare_refs`, `protected`, `list_merge_requests`, `get_merge_request`,
   `manage_merge_request`, `mr_discussions`, `list_issues`, `get_issue`, `manage_issue`,
   `labels`, `milestones`, `boards`, `pipelines`, `jobs`, `ci_variables`,
   `pipeline_schedules`, `pipeline_triggers`, `feature_flags`, `runners`, `ci_lint`,
   `environments`, `releases`, `deploy_credentials`, `pages`, `users`, `user_tokens`,
   `access_tokens`, `groups`, `members`, `membership_requests`, `badges`, `admin_settings`,
   `admin_ops`, `search_gitlab`, `webhooks`, `integrations`, `snippets`, `wikis`,
   `packages`, `container_registry`, `project_import_export`, `model_registry`,
   `ci_catalog`, `templates`, `todos_and_events`.
   Most take an `action` parameter — read the tool description. New in v0.3.0:
   `model_registry` (ML models + MLflow experiments — CE), `ci_catalog` (reusable CI
   components), `templates` (GitLab's built-in gitignore/license/dockerfile/CI templates).
   New in v0.2.0: `pages`
   (Pages + custom domains), `boards`, `feature_flags`, `pipeline_triggers`,
   `access_tokens` (project/group bot tokens), `membership_requests` (invitations +
   access requests), `protected` (granular protected branches/tags/environments),
   `badges`, `project_import_export`, `repo_extras` (contributors/languages/blame/changelog).
2. **`gitlab_rest`** for anything not curated — it reaches every REST endpoint.
   Find paths with `gitlab_api_search(keyword)` or `references/api-map.md`.
   Recipes for common non-curated jobs: `references/common-tasks.md`.
3. **`gitlab_graphql`** when REST is awkward (nested data in one call, work items,
   newer features). 160 root queries / 622 mutations on 19.0.

Start sessions (or debug auth issues) with `gitlab_status()`.

## References (read the relevant one before non-trivial work)

- `references/api-map.md` — the full enumerated REST surface (177 resource groups).
- `references/conventions.md` — auth (`PRIVATE-TOKEN`, scopes, admin mode, sudo),
  pagination (offset + keyset, `X-Total`/`Link` headers), ID vs IID, URL-encoded
  paths, rate limits, error vocabulary, discovery via `/help/api/api_resources`.
- `references/common-tasks.md` — verified call recipes for non-curated jobs.
- `references/cicd.md` — pipelines, jobs & artifacts, triggers/schedules, variables,
  runners (incl. the new `POST /user/runners` flow), environments/deployments,
  releases, feature flags, CI-lint, `CI_JOB_TOKEN` scope, and a `.gitlab-ci.yml` cheat-sheet.
- `references/projects-repo-mrs-issues.md` — projects/repo/files/commits (multi-action)/
  branches/tags/protected refs, merge requests (+ basic approvals, blocks, suggestions),
  issues/boards/labels/milestones, members/invitations/access-requests, packages/registry,
  deploy keys/tokens, webhooks, wikis/snippets/releases, and the shared notes/discussions model.
- `references/admin-and-self-hosting.md` — application settings, users + full lifecycle,
  personal/project/group access tokens, groups, **system hooks** (the CE event surface),
  and the **SSH/CLI-only hard limits** (backup/restore, `gitlab-ctl`, Rails console, DB/Redis,
  background migrations — no API on any tier).
- `references/ce-vs-ee-and-security.md` — the honest **CE-vs-EE gating map** (what 403s/returns
  empty without a license) and the CE security-scanning reality (run SAST/Secret-Detection
  templates → parse the raw job **artifact**, since findings never hit the MR widget on Free).
- `references/graphql.md` — the GraphQL endpoint, live **introspection** as the version-exact
  discovery path, when GraphQL beats REST (and vice versa), and the null-means-unauthorized gotcha.
- `references/templates.md` — the **bulletproof templates** catalog: `templates/ci/*.yml`
  (all live-linted `valid:true` on 19.0.0), project scaffolding, and config presets, with how
  to apply each. **Read before scaffolding or adding CI.**
- `references/workflows.md` — the `/gl-*` **workflow** playbooks and orchestration patterns
  (onboard, ci-bootstrap, audit, cleanup, user-offboard, triage, release, model-registry).
- `references/ai-and-model-registry.md` — the ML **Model Registry** + MLflow experiment tracking
  + CI Catalog (all CE), and the honest story that **GitLab Duo / AI is EE-gated and 404s here**.

## Templates & workflows

Bulletproof, ready-to-use assets live in `templates/`: CI pipelines (`templates/ci/*.yml`, each
validated against this instance's CI Lint API), project scaffolding (`templates/project/` — issue/
MR templates, CODEOWNERS, .editorconfig, CONTRIBUTING), and config presets (`templates/config/*.json`).
The `/gl-*` workflow commands orchestrate them into one job (e.g. `/gl-onboard` bootstraps a project
end-to-end). Always `ci_lint(project, content=...)` after editing a CI template before committing.
See `references/templates.md` and `references/workflows.md`.

## Safety rules (non-negotiable)

- Every write tool requires `confirm=true`. **Never set it without the user's
  explicit approval of that specific action in this conversation.** State what
  you're about to change; get a yes; then call.
- Destructive tier — `delete` on projects/groups/users/branches/tags, `merge`,
  `rebase`, token rotate/revoke, `admin_settings update`, instance `features set`
  — deserves an extra-careful confirmation naming the exact target.
- `user_tokens rotate/create` responses contain the only copy of the new secret —
  relay it to the user immediately.
- Instance feature flags (`admin_ops area=features`) toggle GitLab's internal
  feature gates — they can destabilize the instance. Confirm twice.

## CE hard limits (verified live — these 404 and are NOT bugs)

Epics, iterations, merge trains, approval rules, audit events, `/license`,
group-level webhooks, group wikis, protected environments, member roles,
LDAP/SAML group sync, vulnerabilities/dependency scanning APIs, Geo, and **all
GitLab Duo / AI features** (code suggestions, Duo chat/workflows — REST 404s and
GraphQL rejects every `ai*`/`duo*` field at runtime, even though introspection
lists them). On CE a 404 can mean "EE-only" as well as "not found" — check
`references/api-map.md` before declaring a bug. Full conventions and quirks:
`references/conventions.md`.

CE features that DO work here beyond the obvious (verified): secure files,
ML model registry, CI/CD catalog, work items, alert management, achievements,
group dependency proxy (enabled on `gregory`), terraform state/module registry,
service desk (needs incoming-email config), direct-transfer imports
(`bulk_import_enabled` turned on 2026-07-15 — `/bulk_imports` live).

## Instance facts (as of 2026-07-14)

115 projects, 9 groups (root: `gregory`, user ns `dadmonkey405`), 3 users
(1 active), signup disabled, KAS enabled, registry API reachable. Token:
`hermes-agent-20260625-v2` (admin, `api` scope, expires 2027-06-25).
