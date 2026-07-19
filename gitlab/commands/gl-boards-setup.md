---
description: Create issue boards and lists (by label, milestone, or assignee) for a project or group
argument-hint: <project | group> [--name "..."] [--lists label:a,label:b,...]
---

Set up issue boards for **$ARGUMENTS**. Read `references/projects-repo-mrs-issues.md`. Boards
are CE-working at both project and group scope. List types supported on CE: **label**, **assignee**,
**milestone**. Iteration-based lists need Premium iterations — flag honestly.

1. **Pre-flight (read-only)**:
   - `boards(scope_type=..., scope_id=..., action="list")` — existing boards.
   - `labels(scope_type=..., scope_id=..., action="list")` — confirm the labels you'll use as
     list bases exist; create missing ones first (`labels(..., action="create", ...)`).
   - `milestones(scope_type=..., scope_id=..., action="list")` — same for milestone-based lists.
2. **Plan the board**: name (default: the project/group name + " board"), and the lists in
   column order. Each list is `{label_id}` (or `milestone_id` / `assignee_id`). The classic
   Kanban set: `Open` (no label) → `In Progress` → `Review` → `Blocked` → `Closed`. The
   leftmost "Open" / backlog and rightmost "Closed" lists are convention; GitLab auto-adds a
   "Closed" list if missing.
3. **Create the board**: `boards(scope_type=..., scope_id=..., action="create", params={name},
   confirm=true)`. Capture `board_id`.
4. **Add lists in order** (left → right is the order you add them): for each label-based list,
   `boards(scope_type=..., scope_id=..., action="list_create", board_id=<bid>,
   params={label_id: <lid>}, confirm=true)`. For milestone-based: `params={milestone_id: <mid>}`.
   For assignee-based: `params={assignee_id: <uid>}`.
5. **Optional — list position/metadata**: `boards(..., action="list_update", board_id=<bid>,
   list_id=<lid>, params={position: N}, confirm=true)` to reorder if you added out of order.
6. **Verify**: `boards(scope_type=..., scope_id=..., action="lists", board_id=<bid>)` — confirm
   lists + positions. Open the board URL (`web_url` from the create response) so the user can
   see it. Report: board name + URL, lists in order with their basis (label/milestone/assignee).

Iteration-based boards (per-sprint) are Premium. For a CE equivalent, use milestone-based
lists — one board per active milestone, or a single board with milestone lists for the next
2-3 milestones. Epic boards (`epic_board*`) are entirely Premium.
