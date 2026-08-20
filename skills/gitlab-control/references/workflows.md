# Workflows — multi-step playbooks for every `/gl-*` command

Every `/gl-*` slash command orchestrates several tools into one reliable job. They all share
the **same safety contract**: *read-only gather → propose the exact changes → get the user's
yes → apply with `confirm=true` → verify → report.* Never bulk-mutate without a reviewed list.

This file is the playbook index — for each command: the goal, the canonical step sequence,
the templates/references it leans on, and the failure modes to watch for. Read the command
file itself (`.opencode/command/gl-*.md`) for the literal prompt; read this for the *why*.

## Command roster (33)

| Group | Commands |
|---|---|
| **Read-only** | `/gl-health`, `/gl-audit`, `/gl-project`, `/gl-mr-review`, `/gl-triage`, `/gl-model-registry`, `/gl-time-report`, `/gl-storage-audit`, `/gl-search` |
| **Setup & bootstrap** | `/gl-onboard`, `/gl-group-setup`, `/gl-ci-bootstrap`, `/gl-branch-strategy`, `/gl-pages-deploy`, `/gl-boards-setup`, `/gl-milestone-plan`, `/gl-mirror-setup`, `/gl-cluster-agent`, `/gl-wiki-seed` |
| **Operate** | `/gl-release`, `/gl-variables-sync`, `/gl-secure-files`, `/gl-runner-manage`, `/gl-member-sync`, `/gl-label-sync`, `/gl-apply-suggestions` |
| **Diagnose** | `/gl-ci-debug`, `/gl-security-scan` |
| **Lifecycle / cleanup** | `/gl-cleanup`, `/gl-user-offboard`, `/gl-token-rotate`, `/gl-backup`, `/gl-bulk-import` |

## Cross-cutting orchestration patterns (compose your own)

- **Scaffold → protect → wire CI** (onboarding): create/update project → apply hardened
  settings → protect the default branch → lint+commit a CI template → write repo scaffolding,
  each step confirmed. **Order matters**: protect the branch *before* pushing CI so the CI
  commit itself goes through an MR if you want strict enforcement.
- **Detect → lint → commit → run** (any CI change): never commit `.gitlab-ci.yml` without
  `ci_lint(project, content=...)` returning `valid:true` first. Templates are pre-linted, but
  edits aren't.
- **Enumerate → confirm-list → batch-apply** (cleanup/triage/offboard/rotate/runner-manage):
  produce a reviewed list, get ONE approval for the batch, then loop with `confirm=true`.
  Report exactly what changed.
- **Reassign-before-remove** (offboarding): add a replacement Owner to sole-owned groups/
  projects *before* removing/blocking the user, or the resource is orphaned.
- **Read-only audit → remediation table** (audit/security-scan/mr-review): never fix during an
  audit; deliver a Works/At-Risk/Fix table with the exact call for each fix so the user chooses.
- **Async-poll** (backup/bulk-import/export): start → poll status until terminal → download/
  verify. Never assume success on the start response.
- **Reassign-secret-on-rotate** (token-rotate/runner-manage): rotated secrets exist exactly
  once in the response — relay immediately to the user and recommend the org secret store.

## Per-command playbooks

### `/gl-health` — instance health snapshot
1. `gitlab_status()` → version, enterprise flag, current user, token info, statistics.
2. `admin_settings(action="get")` if admin → signup, rate limits, import sources, features.
3. `admin_ops(area="sidekiq", action="queue_metrics")` → queue depth / latency.
4. `runners(action="list", scope="instance")` → fleet count, any never-contacted.
5. **Report**: a one-screen health card (version, users, projects, sidekiq, runners, license
   tier, any anomalies). Read-only.

### `/gl-project <project>` — project overview
1. `get_project(project)` → settings + statistics.
2. `repo_tree(project, path="", recursive=false)` → top-level layout.
3. `list_merge_requests(project, state="opened", limit=10)` + `list_issues(project, limit=10)`.
4. `pipelines(project, action="latest")` + recent `pipelines(project, action="list", limit=5)`.
5. **Report**: overview card + open work + recent CI signal. Read-only.

### `/gl-audit [project | instance]` — security/hygiene audit (read-only)
1. Project path: settings, branch/tag protection, members, access tokens, CI config + variables,
   webhooks, hygiene (stale branches, failed pipelines, artifact bloat). Instance path: admin
   settings, users (admins/external/blocked), PATs, runners, system hooks.
2. **Report**: Works/At-Risk/Fix table with the exact remediation call per finding — never
   auto-apply. Flag EE-gated gaps (audit-events, approval-rules) honestly.

### `/gl-onboard <ns/name> [ci]` — bootstrap a project to team standard
1. Create/update project → 2. hardened settings (`templates/config/project-settings-hardened.json`)
   → 3. protect default branch (`templates/config/protected-branch-standard.json`) → 4. lint+commit
   CI (`templates/ci/<stack>.yml`) → 5. write scaffolding (`templates/project/*`) → 6. badges →
   7. verify. Each step its own approval.

### `/gl-group-setup <path>` — bootstrap a group
1. Plan structure → 2. `groups(create)` → 3. settings/policies (2FA, branch protection defaults,
   project/subgroup creation levels) → 4. members (≥2 owners) → 5. labels → 6. recurse for
   subgroups → 7. verify. See the command file for the full policy payload.

### `/gl-ci-bootstrap <project> [stack]` — add/replace CI
1. Detect stack (read `repo_tree` + look at `package.json`/`go.mod`/`pyproject.toml`/`Dockerfile`).
2. Pick `templates/ci/<stack>.yml`. 3. `ci_lint(project, content=...)` — must be `valid:true`.
4. `write_files` to commit. 5. `pipelines(action="create", ref=<branch>)` to run + watch.

### `/gl-branch-strategy <project> [preset]` — protection + merge gate
1. Read current state → 2. pick preset (standard/strict/permissive) → 3. delete conflicting
   rules + create new → 4. merge-gate settings (`only_allow_merge_if_pipeline_succeeds` etc.) →
   5. CE-basic approvals (`/approvals` endpoint) → 6. CODEOWNERS convention (note: not enforced
   on CE) → 7. verify. Premium gaps (multi-rule approval, code-owner enforcement) flagged.

### `/gl-pages-deploy <project> [domain]` — Pages + domain + SSL
1. Inspect → 2. enable Pages (`pages_access_level`) → 3. domain create (auto-SSL or cert+key)
   → 4. DNS verification record → 5. force-HTTPS → 6. verify deploy. Driven by a Pages CI job
   (see `templates/ci/pages-static.yml`).

### `/gl-boards-setup <project|group> [--lists ...]` — issue boards
1. Pre-flight (labels/milestones exist?) → 2. plan lists in column order → 3. `boards(create)`
   → 4. `list_create` per column → 5. reorder → 6. verify. Iteration lists = Premium.

### `/gl-release <project> <ver>` — cut a release
1. `tags(action="list")` for the last tag → 2. `compare_refs(project, from_ref=<last-tag>,
   to_ref=<default-branch>)` for the diff → 3. `list_merge_requests(project, state="merged",
   since=<last-tag>)` for the changelog → 4. draft notes → 5. `releases(action="create",
   params={tag_name, ref, name, description, assets:{links:[...]}}, confirm=true)` → 6. verify.

### `/gl-variables-sync <json> --targets` — baseline CI variables
1. Parse spec → 2. enumerate targets → 3. diff per target → 4. confirm-plan matrix → 5. apply
   creates/updates/deletes → 6. verify. Handle masked-value rules; trust create response for
   masked values (can't read back).

### `/gl-secure-files <project> <op>` — file credentials
1. `get_project` → 2. list/add/remove via `gitlab_rest("/projects/:id/secure_files")` (multipart
   add → shell or UI) → 3. verify. Pair with `/gl-audit` for expiry tracking.

### `/gl-runner-manage [scope]` — fleet inventory + health
1. Inventory (REST + GraphQL for health signals) → 2. classify each → 3. tag-gap analysis →
   4. propose actions → 5. confirm-list → 6. apply (pause/resume/delete/reset-token) → 7. verify.
   Relay any reset auth tokens immediately.

### `/gl-ci-debug <project> [pipeline]` — diagnose a failing pipeline
1. `pipelines(action="get"|"list", status="failed")` → 2. `jobs(action="list_pipeline",
   pipeline_id=N, scope=["failed"])` → 3. `jobs(action="log", job_id=N)` for the failing job →
   4. `ci_lint(project, content=read_file(project, ".gitlab-ci.yml"))` if config drift suspected
   → 5. **Report**: root cause + the exact fix (config edit, runner tag fix, secret rotation,
   image pull issue).

### `/gl-security-scan <project>` — SAST/Secret-Detection on CE
1. Confirm `.gitlab-ci.yml` includes `Security/SAST.gitlab-ci.yml` and
   `Security/Secret-Detection.gitlab-ci.yml` (offer to add via `/gl-ci-bootstrap`). 2. Run a
   pipeline. 3. `jobs(action="list_pipeline")` for `sast`/`secret_detection` jobs →
   `jobs(action="artifacts")` or raw artifact fetch for the SARIF/JSON. 4. Parse findings
   yourself (no MR widget on Free). 5. **Report**: findings table with rule, severity, file,
   line — plus the proposed remediation per finding.

### `/gl-triage <project>` — label/prioritize/assign
1. `list_issues(project, state="opened")` + `list_merge_requests(project, state="opened")` →
   2. classify by age, labels, assignee, priority heuristic → 3. propose label/assignee/
   milestone changes → 4. confirm-list → 5. apply (`manage_issue`, `manage_merge_request`)
   → 6. verify.

### `/gl-mr-review <project> !<iid>` — deep MR review
1. `get_merge_request(project, iid=N, include="all")` — metadata, diffs, commits, discussions,
   pipelines. 2. `read_file` for context on touched files. 3. Read diffs; assess correctness,
   test coverage, security, style. 4. Draft structured feedback: summary, blocking issues,
   suggestions, nits. 5. Either post as an MR comment (`mr_discussions(action="add")`, confirm)
   or relay to the user for review.

### `/gl-model-registry <project>` — inspect ML models/experiments
1. `model_registry(project, action="models")` → registered models. 2. `model_registry(action=
   "experiments")` → experiments. 3. `model_registry(action="packages")` → artifact packages.
   4. Optional MLflow passthrough: `model_registry(action="mlflow", mlflow_path="runs/search",
   params={...})`. 5. **Report**: model versions, latest experiments, candidate runs. Read-only.

### `/gl-cleanup <project>` — prune merged branches, artifacts, old pipelines, stale tokens
1. Enumerate (merged branches, expired artifacts, old pipelines, stale triggers/schedules) →
   2. confirm-list → 3. batch-delete with `confirm=true` → 4. `manage_project`/housekeeping
   (`prune`) → 5. report freed space. Never bulk without review.

### `/gl-member-sync <spec> --targets` — baseline membership across projects/groups
1. Parse spec → 2. enumerate targets → 3. diff per target (list_all) → 4. confirm-plan matrix
   (block if Owner count drops below 2) → 5. apply → 6. verify.

### `/gl-label-sync <spec> --targets` — baseline label taxonomy
1. Parse spec → 2. enumerate targets → 3. diff per target → 4. confirm-plan → 5. apply →
   6. verify. Non-destructive to issues.

### `/gl-apply-suggestions <project> <mr_iid>` — batch-apply MR review suggestions
1. `get_merge_request(include="discussions")` → 2. collect suggestion IDs → 3. classify
   (applicable/stale/applied) → 4. confirm-plan → 5. apply (single or batch_apply) →
   6. verify commits + pipeline re-run.

### `/gl-time-report <scope>` — time tracking aggregate
1. GraphQL deep read (issues + MRs + timeStats + assignees + milestone) → 2. aggregate per
   assignee/milestone/state/type → 3. flag overruns + unestimated → 4. report tables. Read-only.

### `/gl-storage-audit <scope>` — storage consumption + cleanup targets
1. Enumerate projects → 2. get_project(statistics=true) per project → 3. rank + classify
   dominant component → 4. propose cleanup per top-N → 5. report ranked table + totals.

### `/gl-search <term> [--scope] [--project] [--group]` — structured instance-wide search
1. Determine scope(s) → 2. fan out search_gitlab calls → 3. enrich code hits → 4. dedup by
   web_url → 5. report grouped by scope, ranked. Code search needs `--project` on CE (no ES).

### `/gl-milestone-plan <scope> [--count N]` — release-cadence milestones
1. Parse args → 2. check existing milestones → 3. plan sequence (dated titles) →
   4. confirm-plan → 5. create loop → 6. verify. The CE iteration-cadence approximation.

### `/gl-mirror-setup <project> <mode> <url>` — pull/push remote mirrors
1. Inspect current mirrors → 2. validate remote URL (creds embedded or SSH) → 3. build params
   (redact URL on display) → 4. confirm-plan → 5. create → 6. trigger initial sync → 7. verify.

### `/gl-cluster-agent <project> <name>` — Kubernetes agent bootstrap
1. Pre-flight (list existing) → 2. create agent → 3. create auth token (RELAY IMMEDIATELY) →
   4. generate helm install snippet (KAS address from gitlab_status) → 5. seed config.yaml →
   6. verify after user installs agentk.

### `/gl-wiki-seed <project> [--pages ...]` — structured wiki page set
1. Inspect existing → 2. plan page set (Home, Architecture, Runbook, Decisions) →
   3. generate content → 4. confirm-plan → 5. create loop → 6. verify + report URLs.

### `/gl-user-offboard <user>` — audit → block/deactivate → revoke tokens
1. Identify + audit (memberships, tokens, keys, owned resources) → 2. decide mode with user
   (deactivate/block/ban/delete) → 3. revoke tokens/keys → 4. **reassign ownership** of sole-
   owned resources BEFORE removing → 5. execute → 6. verify. Prefer reversible modes.

### `/gl-token-rotate [scope] [--dry-run]` — expiring token sweep
1. Enumerate PATs + project/group tokens + deploy tokens + trigger tokens → 2. classify
   (ExpiringSoon/Expired/LongLived/NeverUsed/Healthy) → 3. propose rotate/revoke per token →
   4. confirm-list → 5. apply, **relaying each new secret immediately** → 6. verify. Default
   dry-run.

### `/gl-backup <project|group>` — verified-restorable export
1. Pre-flight (baseline counts; flag CI secrets in the tarball) → 2. `export_start` → 3. poll
   `export_status` → 4. `export_download` → 5. verify structure + (full) import-and-diff →
   6. report what was/wasn't captured. Treat the tarball as a credential.

### `/gl-bulk-import <src-url> <src-token> <entities>` — direct-transfer
1. Pre-flight (`bulk_import_enabled`, paths, destination collisions) → 2. build entities payload
   → 3. confirm-plan → 4. POST `/bulk_imports` → 5. poll top-level + per-entity status → 6. retry
   failed entities → 7. verify per project (diff) → 8. report. Re-create secrets/runners/hooks
   separately (see `references/migrations-imports.md`).

## Honesty in workflows

Workflows surface real findings — unprotected branches, expiring tokens, unmasked CI secrets,
no pipeline, EE-gated gaps, stale runners, failed exports. When a step hits an EE-gated feature
on CE (audit-events, approval-rules, protected-environments, epic boards, iteration boards,
DAST), say **"EE-only, not available on this CE instance"** rather than treating the 404 as an
error. See `references/ce-vs-ee-and-security.md`.

When a workflow depends on the SSH/CLI-only surface (backup-restore, `gitlab-ctl`, Rails
console, runner-binary install on unraid-host), hand off to the `ansible` agent for the host-side
work — don't burn API calls probing the impossible.

## Composing workflows (chained jobs)

- **New team onboarding**: `/gl-group-setup` → `/gl-onboard` per project → `/gl-branch-strategy`
  → `/gl-ci-bootstrap` → `/gl-boards-setup`.
- **Disaster recovery rehearsal**: `/gl-backup` (a real project) → restore to a throwaway
  namespace → diff → `/gl-cleanup` the throwaway.
- **Instance migration**: `/gl-bulk-import` from source → per-project verify → `/gl-variables-sync`
  to re-establish secrets → `/gl-runner-manage` to register new runners → `/gl-webhook`-style
  re-creation (use `webhooks` tool directly).
- **Quarterly hygiene**: `/gl-audit instance` → `/gl-token-rotate` → `/gl-runner-manage` →
  `/gl-cleanup` per stale project.

Each composition is just sequential `/gl-*` invocations — the safety contract applies at every
step.
