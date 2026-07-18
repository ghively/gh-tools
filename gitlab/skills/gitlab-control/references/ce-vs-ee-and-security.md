# CE vs EE gating + the security reality on a Free/CE instance

GitLab CE and EE ship the **same codebase** — "CE" = an unlicensed **Free** tier. Premium/
Ultimate endpoints' routes exist in the code but **403 / return empty / feature-off** without
a license. (A self-hosted instance *can* apply a license key to unlock these without switching
packages — worth confirming whether `git.hively.dev` has any license via `GET /api/v4/license`,
which is itself EE-gated, or the `enterprise` flag in `GET /api/v4/version`.) Verified against
docs.gitlab.com tier badges for GitLab ~19.x.

## What genuinely works on Free/CE (build against these confidently)

Projects (CRUD/archive/fork/transfer/star/import-export/housekeeping), repository (tree/files/
blobs/raw/archive/compare/commits incl. multi-action, branches, tags), **protected branches/
tags** (minus code-owner approval), merge requests (create/update/merge/rebase, **basic
approve/unapprove/reset**, discussions, blocks, time tracking), issues (full lifecycle, links,
notes, time tracking, move/clone), boards, labels, milestones, members/invitations/access-
requests, **personal + project + group access tokens** (all Free now), users + full lifecycle
(block/deactivate/ban/approve), SSH/GPG keys, **CI/CD** (pipelines, jobs, artifacts, triggers,
schedules, variables, **feature flags**, environments/deployments — minus approvals), runners,
CI lint, releases + links, packages + container registry (+ cleanup), wikis, snippets, deploy
keys/tokens, webhooks, **system hooks**, integrations, application settings, repository storage
moves, housekeeping, search, todos/events, GraphQL (schema/queries that aren't EE-resolver-gated).

## EE-gated — will 403 / return empty on plain CE (mark as unavailable, fail gracefully)

| Feature | Endpoint family | Tier |
|---|---|---|
| **Epics** | `/groups/:id/epics/*` | Premium+ |
| **Iterations** | `/projects\|groups/:id/iterations`, cadences | Premium+ |
| **Merge trains** | `/projects/:id/merge_trains/*` | Premium+ |
| **Multi-rule MR approval rules** | `/projects/:id/approval_rules`, MR/group `approval_rules` | Premium+ |
| **Code-owner approval** on protected branch | `code_owner_approval_required` | Premium+ |
| **Custom member roles** | `/member_roles`, `member_role_id` | Ultimate |
| Multiple issue assignees, issue `weight`, `epic_id` | issue attrs | Premium+ |
| `only_allow_merge_if_all_status_checks_passed`, external status checks | project attr, `/external_status_checks` | Ultimate |
| **Audit Events API** (instance/group/project) | `/audit_events`, `/groups\|projects/:id/audit_events` | Premium+ (streaming: Ultimate) |
| **Vulnerabilities / findings / exports** | `/vulnerabilities`, `/projects/:id/vulnerabilities`, GraphQL `vulnerabilities` | Ultimate |
| **Dependency list / SBOM / CycloneDX** | `/projects/:id/dependencies`, dependency_list_export | Ultimate |
| Security dashboard, security/compliance policies | GraphQL + `/security_policies` | Ultimate |
| **Group webhooks** | `/groups/:id/hooks` | Premium+ (project webhooks ARE Free) |
| Group LDAP links (sync), group push rules | `/groups/:id/ldap_group_links`, `/push_rule` | Premium+ |
| Deployment approvals, protected environments | `/projects/:id/protected_environments` | Premium+ |
| Geo Sites/Nodes, group billable members, member-approval workflow | `/geo_sites`, `/billable_members` | Premium+ |

## The security-scanning nuance (important for CE)

On CE you **can run** SAST and Secret Detection in a pipeline (`include: template:
Security/SAST.gitlab-ci.yml` / `Security/Secret-Detection.gitlab-ci.yml`) — the jobs run free
and produce a SARIF/JSON **artifact**, retrievable via the ordinary Jobs/Artifacts REST API.
But the findings **never surface in the MR widget, vulnerability report, or dashboard** on
Free — those are Ultimate. **So on CE, a control integration must download and parse the raw
job artifact itself** to get structured findings. **Dependency Scanning and DAST aren't
available at all on Free** — not even to run. This is the single most useful CE security recipe:
run the scan template → `jobs` artifacts → parse the SARIF.

## Access levels (used everywhere: `access_level`, `*_access_level`)

`0` none · `5` minimal · `10` guest · `15` planner · `20` reporter · `25` security-manager ·
`30` developer · `40` maintainer · `50` owner.

## Honest reporting rule

When a call 403s or returns empty, distinguish **"your token lacks the scope/role"** from
**"this feature needs a Premium/Ultimate license"** from **"disabled for this project/instance."**
Never present an EE-gated capability as "covered" on a CE instance — mark it EE and move on.
