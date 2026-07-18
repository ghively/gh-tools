---
description: Triage open issues and MRs for a project — label, prioritize, assign, flag stale
argument-hint: <project>
---

Triage the open work in **$ARGUMENTS**. Read-only analysis first; propose a batch of changes, get
approval, then apply with `confirm=true`.

1. **Gather**: `list_issues(project, params={state:"opened"})` and
   `list_merge_requests(project, params={state:"opened"})`. For each, note age (created/updated),
   labels, assignee, and linked MR/issue.
2. **Assess** each item:
   - Missing labels → propose type (`~bug`/`~feature`) + priority.
   - Unassigned → suggest an assignee from `members(project, action="list")`.
   - Stale (no update in N days) → flag for a ping or close.
   - MRs: `get_merge_request(project, iid, include="all")` — draft status, CI red, unresolved
     threads, no approval → flag the blocker.
3. **Propose a batch table**: item → suggested labels/assignee/action. Get the user's yes.
4. **Apply** with confirmation: `manage_issue(..., action="update", params={labels, assignee_ids},
   confirm=true)` / `manage_merge_request(...)`. For stale items, `manage_issue(action="add_note")`
   a nudge or (with approval) `action="close"`.
5. Report what changed and what needs human decisions.

Don't relabel/close anything without the user approving the specific items.
