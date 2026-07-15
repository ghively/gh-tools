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

1. **Curated tools first** (~35): `list_projects`, `get_project`, `manage_project`,
   `repo_tree`, `read_file`, `write_files`, `branches`, `tags`, `commits`,
   `compare_refs`, `list_merge_requests`, `get_merge_request`, `manage_merge_request`,
   `mr_discussions`, `list_issues`, `get_issue`, `manage_issue`, `labels`,
   `milestones`, `pipelines`, `jobs`, `ci_variables`, `pipeline_schedules`, `runners`,
   `ci_lint`, `users`, `user_tokens`, `groups`, `members`, `admin_settings`,
   `admin_ops`, `search_gitlab`, `releases`, `environments`, `deploy_credentials`,
   `webhooks`, `integrations`, `snippets`, `wikis`, `packages`, `container_registry`,
   `todos_and_events`. Most take an `action` parameter — read the tool description.
2. **`gitlab_rest`** for anything not curated — it reaches every REST endpoint.
   Find paths with `gitlab_api_search(keyword)` or `references/api-map.md`.
   Recipes for common non-curated jobs: `references/common-tasks.md`.
3. **`gitlab_graphql`** when REST is awkward (nested data in one call, work items,
   newer features). 160 root queries / 622 mutations on 19.0.

Start sessions (or debug auth issues) with `gitlab_status()`.

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
