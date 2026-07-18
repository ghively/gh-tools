# Workflows — multi-step playbooks

Each is a `/gl-*` slash command that orchestrates several tools into one reliable job. All follow
the same safety contract: **read-only gather → propose the exact changes → get the user's yes →
apply with `confirm=true` → verify → report.** Never bulk-mutate without a reviewed list.

## Available workflows

| Command | Purpose | Key tools / templates |
|---|---|---|
| `/gl-onboard <ns/name> [ci]` | Bootstrap a project to team standard | manage_project, protected, ci_lint, write_files + `templates/config` + `templates/ci` + `templates/project` |
| `/gl-ci-bootstrap <project> [stack]` | Add/replace CI with a bulletproof template | detect stack → `templates/ci/*` → ci_lint → write_files → pipelines |
| `/gl-audit [project\|instance]` | Security/protection/CI/hygiene audit (read-only) | get_project, protected, members, access_tokens, ci_variables, webhooks, admin_settings |
| `/gl-cleanup <project>` | Prune merged branches, artifacts, old pipelines, stale tokens | branches(delete_merged), pipelines(delete), housekeeping |
| `/gl-user-offboard <user>` | Audit access → block/deactivate → revoke tokens (admin) | users, user_tokens, access_tokens, members (reassign owner first) |
| `/gl-triage <project>` | Label/prioritize/assign open issues & MRs | list_issues, list_merge_requests, get_merge_request, manage_issue/mr |
| `/gl-release <project> <ver>` | Cut a release from merged MRs since last tag | commits, list_merge_requests, releases |
| `/gl-mr-review <project> !<iid>` | Deep MR review → drafted feedback | get_merge_request(include=all), read_file |
| `/gl-security-scan <project>` | Run SAST/Secret-Detection, parse the CE artifact | read_file, pipelines, jobs(artifacts) |
| `/gl-ci-debug <project> [pipeline]` | Diagnose a failing pipeline | pipelines, jobs(log), ci_lint |
| `/gl-model-registry <project>` | Inspect ML models / experiments (CE) | model_registry |
| `/gl-project <project>` | Project overview | get_project, repo_tree, list_merge_requests, pipelines |
| `/gl-health` | Instance health snapshot | gitlab_status |

## Orchestration patterns (compose your own)

- **Scaffold → protect → wire CI** (onboarding): create/update project → apply hardened settings
  → protect the default branch → lint+commit a CI template → write repo scaffolding, each step
  confirmed. The order matters: protect the branch *before* pushing CI so the CI commit itself
  goes through an MR if you want strict enforcement.
- **Detect → lint → commit → run** (any CI change): never commit `.gitlab-ci.yml` without
  `ci_lint(project, content=...)` returning `valid:true` first — the templates are pre-linted, but
  edits aren't.
- **Enumerate → confirm-list → batch-apply** (cleanup/triage/offboard): produce a reviewed list,
  get one approval for the batch, then loop with `confirm=true`. Report exactly what changed.
- **Reassign-before-remove** (offboarding): add a replacement Owner to sole-owned groups/projects
  *before* removing/blocking the user, or the resource is orphaned.
- **Read-only audit → remediation table** (audit): never fix during an audit; deliver a
  Works/At-Risk/Fix table with the exact call for each fix so the user chooses.

## Honesty in workflows

Workflows surface real findings (unprotected branches, expiring tokens, unmasked CI secrets, no
pipeline, EE-gated gaps). When a step hits an EE-gated feature on CE (audit-events, approval-rules,
protected-environments), say "EE-only, not available on this CE instance" rather than treating a
404 as an error. See `references/ce-vs-ee-and-security.md`.
