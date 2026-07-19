# CE vs EE gating + the security reality on a Free/CE instance

GitLab ships a **single codebase**. "CE" = an unlicensed **Free** tier; the same
binary run with a Premium/Ultimate **license key** unlocks EE routes. Without a
license, EE endpoints **403 / return empty / feature-off** even though the routes
exist in the code and may even appear in GraphQL introspection. This file is the
authoritative map of what actually works on this instance and the honest triage
flow when a call doesn't.

Verified against docs.gitlab.com tier badges for GitLab ~19.x and live-probed
against `git.hively.dev` (19.0.0, `enterprise: false`).

## How to tell which tier you're on (diagnostic flow)

Run these in order the moment a call behaves unexpectedly:

1. **`gitlab_status()`** → `metadata.enterprise` is the authoritative flag.
   `false` here = plain CE / Free, no license applied.
2. **`GET /api/v4/license`** → on CE this **404s** ("404 Not Found"). On a
   licensed instance it returns the license blob (`plan`, `seats`, `expires_at`).
   A 404 here *confirms* unlicensed; do not interpret it as "endpoint missing".
3. **`GET /api/v4/version`** → `enterprise` boolean echoes the same flag.
4. **`admin_settings(action="get")`** → many EE-gated settings appear in the
   payload as keys but are inert/no-op without a license (e.g.
   `require_admin_approval_after_signup`, `abuse_notification_namespaces`).

If `enterprise: false`, **every 403/404/empty in the tables below is expected** —
it is the license, not your token, not a bug.

## The three causes of a failed call (triage decision tree)

When a call 403s, 404s, or returns empty/null, distinguish:

| Symptom | Likely cause | Test |
|---|---|---|
| `401 Unauthorized` | bad/expired token, wrong header | `gitlab_status()` — if it works, the token is fine |
| `403 Forbidden` on an instance admin endpoint | token user is not admin, or not in admin mode | `gitlab_status()` → `is_admin`; some admin writes need admin-mode toggle |
| `403 Forbidden` on a normal endpoint | insufficient role on the target resource | `members(..., action="get")` on the project/group |
| `404 Not Found` on a documented EE endpoint | **EE-gated, no license** (most common on CE) | check the table below; confirm `enterprise: false` |
| `404 Not Found` on a CE endpoint | resource genuinely doesn't exist, or wrong ID-vs-IID | re-read `references/conventions.md` (ID vs IID, URL-encoded paths) |
| Returns `null` (GraphQL) or `[]` (REST) | unauthorized *field*, or EE resolver, or genuinely empty | see `references/graphql.md` — never infer "absent" from null |
| `422 Unprocessable` / `400 Bad Request` | wrong params, missing required field, or CE-restricted param | read `errors[]`; compare to docs |

**The skill's rule:** when reporting a failed capability, name the cause
explicitly — *"EE-only, returns 404 on this CE instance"* — not *"the API is
broken."*

## What genuinely works on Free/CE (build against these confidently)

Organized by domain. Each is live-verified on this instance unless marked.

**Projects & repository**
- Projects: full CRUD, archive/unarchive, fork, transfer, star, import/export,
  housekeeping, storage-move, snapshot.
- Repository: tree, files (CRUD via `write_files` multi-action), raw blob,
  archive, compare, commits incl. multi-action, blame, contributors, languages,
  changelog, merge-base.
- Branches, tags, **protected branches & tags** (granular user/group/role rules —
  **minus code-owner approval**, which is Premium).
- **Remote mirrors** (pull + push) — Free.
- Repository files API requires `ref` on reads — captured in conventions.

**Merge requests & issues**
- MRs: create/update/merge/rebase, **basic approve/unapprove/reset**, discussions
  & threads, blocks (merge blocks), time tracking, draft notes. *Multi-rule
  approval rules and merge trains are Premium.*
- Issues: full lifecycle, links (blocks/blocked-by/is-related-to), notes,
  time tracking, move, clone, due dates, confidential flag, assignees (single on
  CE — multiple assignees is Premium).
- Issue **boards** + lists (label/milestone/assignee/iteration lists — iteration
  lists need Premium iterations), **labels**, **milestones** (project + group).
- **Award emoji** on issues, MRs, notes — Free.

**CI/CD (the deepest Free-tier surface)**
- Pipelines, jobs, **artifacts** (keep/delete/download), triggers, schedules,
  **variables** (project, group, instance instance-scope via admin), **feature
  flags** (CE config-DB-backed — not the Premium operations interface),
  environments & deployments, **resource groups** (concurrency control), 
  **secure files** (CI-secret storage separate from variables).
- **Runners**: full management — instance/group/project type, the new
  `POST /user/runners` flow (v16), tags, locked flag, paused, usage queries.
  See `references/runners-deep.md`.
- **CI lint** (`/projects/:id/ci/lint`) validates `.gitlab-ci.yml` against the
  project's context. Always call before committing CI.
- **CI Catalog** (reusable pipeline components, `include: component:`) — Free.
- **Pipeline triggers tokens** (webhook-style fire-a-pipeline) — Free.

**Releases & packages**
- Releases + asset links — Free.
- Package registry (npm/pypi/maven/conda/composer/conan/debian/generic/nuget/
  rubygems/helm/terraform-modules) — Free.
- **Container registry** + tag protection rules + cleanup policies — Free
  (needs the registry service enabled on the instance; it is here).

**Access, identity, tokens**
- Users: full lifecycle (create/update/block/deactivate/ban/approve/reject/
  delete, hard-delete), SSH + GPG keys, custom attributes, impersonation tokens.
- **Personal, project, AND group access tokens** — all Free now (used to be EE).
- **Members**, invitations, access requests, SSH keys.
- **Deploy keys** (project-scoped read[/write]) and **deploy tokens**
  (project/group/instance-scoped pull credentials).

**Surface & integration**
- **Project webhooks** (push/MR/issue/pipeline/wiki/tag/release/deployment/
  subgroup-events). *Group-level webhooks are Premium.*
- **System hooks** (instance event surface) — Free.
- **Integrations / services** (Slack, Jira, Discord, Mattermost, Packagist,
  prometheus, etc.) — Free.
- **Pages** + custom domains + auto-SSL — Free.
- **Snippets** (personal + project), **wikis** (project — *group wikis are EE*).
- **Badges** (project + group), rendered markdown (`/markdown`), avatar lookup.
- **Search** (projects/issues/MRs/milestones/users/snippets; per-project also
  blobs/commits/notes/wiki_blobs). Global code search needs Elasticsearch and is
  not configured here — per-project code search works without it.

**Admin / instance**
- Application settings (`/application/settings`) — full read; many writes work.
- Broadcast messages, instance feature flags (`/features`), plan limits,
  appearance, topics, **sidekiq metrics** + queue admin, namespaces,
  statistics, system hooks, applications (OAuth).
- **Direct-transfer imports** (`/bulk_imports`) — enabled 2026-07-15, live.
- **Terraform state + module registry** — Free.
- **ML Model Registry + MLflow experiment tracking** — Free (CE). See
  `references/ai-and-model-registry.md`.

## EE-gated — will 403 / 404 / return empty on plain CE

Mark these as **unavailable** and fail gracefully. Do not retry, do not report as
a bug. Organized by the tier that unlocks them.

### Premium-tier gated

| Feature | Endpoint family |
|---|---|
| **Epics** (+ epic issues, links, boards) | `/groups/:id/epics/*`, `epicBoard*` |
| **Iterations** + iteration cadences | `/projects\|groups/:id/iterations`, `/cadences` |
| **Merge trains** | `/projects/:id/merge_trains/*` |
| **Multi-rule MR approval rules** | `/projects/:id/approval_rules`, MR/group variants |
| **Code-owner approval** on protected branch | `code_owner_approval_required` |
| Multiple issue assignees, issue `weight`, issue `epic_id` | issue attrs |
| **Group-level webhooks** | `/groups/:id/hooks` (project webhooks ARE Free) |
| Group LDAP links / sync, group push rules | `/groups/:id/ldap_group_links`, `/push_rule` |
| **Deployment approvals, protected environments** | `/projects/:id/protected_environments` |
| External status checks, `only_allow_merge_if_all_status_checks_passed` | `/external_status_checks`, project attr |
| **Service Desk** custom email addresses | (service desk itself works if email configured) |
| On-call schedules, escalation policies | GraphQL `oncall*`, `escalationPolicy*` |
| **Audit Events API** (instance/group/project/streaming) | `/audit_events`, `/groups\|projects/:id/audit_events` (streaming: Ultimate) |
| **Subgroup MR approvals** | group `merge_request_approval_settings` |

### Ultimate-tier gated

| Feature | Endpoint family |
|---|---|
| **Custom member roles** | `/member_roles`, `member_role_id` |
| **Vulnerabilities / findings / security dashboards / exports** | `/vulnerabilities`, `/projects/:id/vulnerabilities`, GraphQL `vulnerabilities`, `instanceSecurityDashboard` |
| **Dependency list / SBOM / CycloneDX export** | `/projects/:id/dependencies`, `dependency_list_export` |
| Security & compliance policies, security dashboards | `/security_policies`, GraphQL resolvers |
| Container scanning persistence in DB | (the job runs Free; findings DB is Ultimate) |
| DAST, fuzzing, API fuzzing results in UI | (`dast*` GraphQL mutations) |
| Group activity analytics, MR analytics widgets | GraphQL analytics resolvers |
| Geo replication sites/nodes | `/geo_sites`, `/geo_nodes` |
| Group billable members, member-approval workflow | `/groups/:id/billable_members` |

### Cross-tier trap: GitLab Duo / AI

Every `ai*`, `duo*`, `aiCatalog*` GraphQL field, every Duo REST endpoint, code
suggestions, Duo Chat, Duo Workflow — **all Enterprise-only**. GraphQL
introspection LISTS them on CE (the schema is shipped), but the runtime **rejects
every field** with `Field '...' doesn't exist on type 'Mutation'`/`Query'`. This
is the single most-reported false bug. Documented in
`references/ai-and-model-registry.md`.

## Degraded on Free — works but limited (know the ceiling)

These are NOT fully EE-gated, but a key capability is missing — explain the
ceiling rather than claim full coverage:

| Feature | Free reality | Premium adds |
|---|---|---|
| MR approvals | single required-approvals rule, reset-on-push | multiple named rules per MR, required code-owner |
| Push rules | project has `push_rules` but most fields (commit regex, max fs, reject unsigned) need Premium | full commit/branch/file push rules |
| Branch protection | role/user/group allow-lists | code-owner approval, required status checks |
| Issue assignees | one | multiple |
| Service Desk | works if incoming email configured | custom address per project |
| Security scanning jobs (SAST/Secret-Detection) | **run and produce artifacts** | findings hit MR widget + vulnerability DB |
| Container Scanning | runs (Free) | findings persisted to DB (Ultimate) |
| Dependency proxy | images + packages (works on `gregory` group) | — |
| Work items | work item types & basic CRUD | custom work item types, rollup widgets |

## The security-scanning reality on CE (the key recipe)

This is the single most important CE security pattern. On Free you can **run**
SAST and Secret Detection in a pipeline — the analyzer jobs execute, the
analyzers are the same ones Premium/Ultimate use, and each produces a structured
(SARIF or JSON) **artifact**. What you **lose** is the post-processing: findings
never reach the MR widget, vulnerability DB, or dashboards (those are
Ultimate-only). So:

**On CE, the integration itself must parse the artifact.** The recipe:

1. `.gitlab-ci.yml` includes the templates:
   ```yaml
   include:
     - template: Security/SAST.gitlab-ci.yml
     - template: Security/Secret-Detection.gitlab-ci.yml
   ```
2. Pipeline runs `sast` + `secret_detection` jobs → each uploads a `gl-sast-
   sast-report.json` / `gl-secret-detection-report.json` **artifact**.
3. The control integration downloads it: `jobs(project, pipeline_id=N)` → find
   the job → fetch the artifact file via the Jobs Artifacts API.
4. Parse the SARIF-like JSON (`results[].ruleId`, `results[].level`,
   `results[].locations[]`) and surface findings yourself (issue, MR comment,
   external ticket).

**Dependency Scanning and DAST are NOT available to run on Free at all** —
including `include:`-ing the template. The job either won't start or will exit
with a license error. Container Scanning **runs** Free but, like SAST, findings
don't persist without Ultimate.

**Push-side defenses on Free:** `pre-receive` secret detection
(`setPreReceiveSecretDetection` mutation / `pre_receive_secret_detection`
project setting) — verify on the target instance; it's been moving between tiers.

## Access levels (used everywhere: `access_level`, `*_access_level`)

```
0  NO_ACCESS       (none)
5  MINIMAL_ACCESS  (minimal — trigger via webhook, see repo)
10 GUEST           (read, issues)
15 PLANNER         (Ultimate-only role — reads issues, no repo on Free effectively)
20 REPORTER        (read + pull, issues, merge request comment)
25 SECURITY_MANAGER (Ultimate-only)
30 DEVELOPER       (push, create branches/tags/MRs, run pipelines)
40 MAINTAINER      (force-push to protected if allowed, manage runners, project settings, MR merge)
50 OWNER           (transfer/delete project, manage members)
```

Use the numeric value in API params (`access_level: 30`). `5/15/25` are inert on
CE without a license for the corresponding role tier — passing `15` on Free
behaves like `10` Guest.

## Honest reporting rules

1. Never present an EE-gated capability as "covered" on a CE instance — say
   *"EE-only (Premium/Ultimate), returns 404 here"* and propose the Free-tier
   workaround if one exists.
2. When a workflow *needs* an EE feature (e.g. `/gl-audit` wants audit events),
   say so explicitly in the report — *"audit-events API is Premium; cannot list
   historical admin actions from the API on this CE instance."*
3. When a feature is *degraded* (Free works but limited), state the ceiling —
   *"basic approvals work, but multi-rule per-MR approval rules are Premium."*
4. Don't conflate token-scope failures with license failures — test with
   `gitlab_status()` first.
5. The api-map.md lists EE-only resources per scope — cross-check before
   declaring a 404 a bug.
