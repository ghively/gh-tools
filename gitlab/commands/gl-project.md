---
description: Deep-dive one GitLab project — activity, branches, MRs, CI, protections
argument-hint: <project path or id>
---

Deep-dive the GitLab project **$ARGUMENTS** (read-only) using the gitlab MCP tools:

1. `get_project` — description, visibility, default branch, sizes, enabled features.
2. `branches(action="list")` + `branches(action="protected_list")` — stale branches
   (no commits in 90+ days) and whether the default branch is protected.
3. `list_merge_requests(project=...)` — open MRs, note drafts and stale ones.
4. `pipelines(action="list", limit=10)` — recent pipeline health; if the latest
   failed, pull the failing job log via `jobs(action="list_pipeline")` +
   `jobs(action="log")`.
5. `commits(action="list", limit=10)` — recent activity and authors.
6. `webhooks(scope_type="project")`, `ci_variables(scope_type="project")` (names
   only — do not print values), `members(action="list_all")` — configuration surface.
7. `list_issues(project=...)` — open issue count and oldest.

Report: a compact status summary, then findings ordered by importance (broken CI,
unprotected default branch, stale MRs/branches, risky hooks). Read-only.
