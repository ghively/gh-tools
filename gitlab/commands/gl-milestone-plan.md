---
description: Create a release-cadence milestone set (e.g. monthly sprints) for a project or group
argument-hint: <project | group> [--count N] [--prefix "Sprint"] [--duration weeks]
---

Generate a sequence of milestones for a release cadence. Read `references/projects-repo-mrs-issues.md`.
Creates N milestones starting from the next sensible date, each spanning the configured duration.

1. **Parse args** (read-only defaults): count (default 6), prefix (default "Sprint"), duration
    (default 2 weeks). Decide scope: project or group.
2. **Check existing**: `milestones(scope_type, scope_id, action="list", state="active")` —
    identify the latest milestone's end date as the starting point; flag any title collisions
    with the planned sequence.
3. **Plan the sequence**: list of `{title: "<prefix> YYYY-MM-DD", start_date, due_date}`. Title
    format avoids collisions (date suffix). Present the plan as a table.
4. **Confirm-plan**: get explicit approval for the batch.
5. **Apply**: loop with `confirm=true`:
    `milestones(scope_type, scope_id, action="create", params={title, start_date, due_date,
    description: "..."}, confirm=true)`.
6. **Verify**: re-`list`. Report: created milestones with their web URLs, the cadence summary,
    and how to assign issues to them (`manage_issue(..., params={milestone_id}))` or via the UI).

Group milestones are shared across all projects in the group — prefer group scope for
cross-project planning. Project milestones are project-local. Iteration cadences (sprints
with auto-rollover) are Premium — this command is the CE approximation using dated milestones.
