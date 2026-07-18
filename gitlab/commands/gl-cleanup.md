---
description: Safely clean up a project — merged branches, expired artifacts, old pipelines, stale tokens
argument-hint: <project>
---

Tidy up **$ARGUMENTS**. This proposes destructive actions — enumerate first, show the user the
exact list, get approval, then act with `confirm=true`. Never bulk-delete without a reviewed list.

1. **Merged branches**: `branches(project, action="list")` — identify branches already merged into
   the default branch (protected branches are skipped automatically). Show the list; on approval
   `branches(project, action="delete_merged", confirm=true)`.
2. **Expired artifacts**: `get_project(project)` statistics for `job_artifacts_size`. Old artifacts
   can be dropped via `gitlab_rest("DELETE", "/projects/:id/artifacts", confirm=true)` (deletes
   artifacts for jobs older than the expiry) — confirm the user wants this.
3. **Old pipelines**: `pipelines(project, action="list", params={updated_before:<date>})` — list
   candidates; delete individually with `pipelines(project, action="delete", ..., confirm=true)`
   (this removes the pipeline + its jobs/logs — irreversible; confirm each batch).
4. **Stale CI tokens/schedules**: `pipeline_triggers(project, action="list")` and
   `pipeline_schedules(project, action="list")` — flag unused ones; delete with confirmation.
5. **Housekeeping**: `manage_project` / `gitlab_rest("POST", "/projects/:id/housekeeping",
   {"task":"prune"}, confirm=true)` to prune unreachable git objects and shrink the repo.

Report freed space (compare statistics before/after) and exactly what was removed.
