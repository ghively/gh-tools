---
description: Configure branch + tag protection and the CE-available merge-gate policy for a project
argument-hint: <project> [preset: standard | strict | permissive]
---

Establish the branch/tag protection and merge-gate posture for **$ARGUMENTS**. Read
`references/projects-repo-mrs-issues.md` and `references/ce-vs-ee-and-security.md`. CE has
**basic** approval (single required-approvals rule, reset-on-push) — multi-rule approval rules
and code-owner-required approval are Premium; flag them honestly rather than trying to set them.

1. **Read current state (read-only)**: `protected(project, kind="branches", action="list")` and
   `protected(project, kind="tags", action="list")`; `get_project(project)` for merge-related
   settings (`only_allow_merge_if_pipeline_succeeds`, `remove_source_branch_after_merge`,
   `squash_option`, `merge_method`, `resolve_outdated_diff_discussions`). Identify the default
   branch (`get_project(...).default_branch`).
2. **Pick preset** (or take user overrides):
   - **standard** (default): default branch — maintainers merge, no direct push, no force-push;
     `*-stable` tags — maintainers create. `templates/config/protected-branch-standard.json`.
   - **strict**: default + release branches (`release/*`) — maintainers merge, code reviewed
     via CODEOWNERS convention (not enforced on CE — note it); all tags — maintainers only.
   - **permissive**: default branch — developers push (force-push off), maintainers merge; tags
     — developers can create.
3. **Apply protection** (per preset, replacing existing rules): for each rule,
   `protected(project, kind="branches"|"tags", action="create", params={
   name: <pattern>, allowed_to_push: [{access_level: 0}], allowed_to_merge: [{access_level:
   40}], allow_force_push: false, ...}, confirm=true)`. Delete prior conflicting rules first
   (`protected(..., action="delete", name=..., confirm=true)`) so the new set is authoritative.
4. **Merge-gate settings**: `manage_project(action="update", project=..., params={
   only_allow_merge_if_pipeline_succeeds: true, remove_source_branch_after_merge: true,
   squash_option: "always"|"default_on"|"default_off", merge_method: "merge"|"rebase_merge"|
   "ff", resolve_outdated_diff_discussions: true, ...}, confirm=true)`.
5. **Approvals (CE-basic)**: `gitlab_rest("POST", "/projects/:id/approvals", params={
   approvals_required: N, reset_approvals_on_push: true, disable_overriding_approvers_per_merge_request:
   false}, confirm=true)`. **Do NOT attempt** `/approval_rules` (multi-rule) or
   `code_owner_approval_required` — both Premium, both 400/404 on CE. Note these as gaps.
6. **CODEOWNERS** (convention, not enforced on CE): `write_files(project, [{action:"create"|
   "update", file_path:"CODEOWNERS", content:<from templates/project/CODEOWNERS, tailored>}],
   confirm=true)`. Explain that CE can't enforce it; it's documentation + reviewer hint.
7. **Verify**: re-list protected refs and project settings; confirm each took. Report the final
   posture in a table (branch/tag pattern → who can push/create/merge) plus the CE-vs-Premium
   gap row (multi-rule approval + code-owner enforcement = Premium).
