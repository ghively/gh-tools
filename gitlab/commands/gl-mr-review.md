---
description: Review a GitLab merge request — diffs, discussions, CI, then draft feedback
argument-hint: <project> !<mr-iid>
---

Review merge request **$ARGUMENTS** using the gitlab MCP tools:

1. `get_merge_request(project, iid, include="all")` — description, diffs, commits,
   existing discussions, pipeline status, approval state.
2. Read the full diff; for context on non-trivial changes, pull surrounding code
   with `read_file(project, path, ref=source_branch)`.
3. Assess: correctness bugs, missed edge cases, security issues, CI status,
   unresolved discussions, merge conflicts (`detailed_merge_status`).
4. Draft the review: verdict (approve / needs changes), findings ranked by
   severity with file:line references.

Present the draft to the user first. Only after explicit approval:
- post comments via `mr_discussions(action="add", confirm=true)` (inline via
  `position` when tied to a specific diff line),
- approve via `manage_merge_request(action="approve", confirm=true)`,
- or merge via `manage_merge_request(action="merge", confirm=true)` — confirm
  merge options (squash? delete source branch?) before this one.
