---
description: Batch-apply code-review suggestions left as inline diff comments on an MR
argument-hint: <project> <merge_request_iid> [--all] [--dry-run]
---

Apply the ```suggestion blocks left by reviewers on a merge request's diff — creates a single
commit per suggestion (or one bulk commit). Read the suggestions tool docstring. The MR's
source branch must be writable by the caller.

1. **Inspect the MR** (read-only): `get_merge_request(project, iid=N, include="discussions")`.
    Find all notes containing ```suggestion code blocks.
2. **Collect suggestion IDs**: for each inline diff note with a suggestion, the note's body
    contains a fenced `suggestion` block; the suggestion has a `suggestion_id` (visible via
    `suggestions(project, action="get", suggestion_id=N)` once you have the IDs).
3. **Classify each**: applicable (source unchanged since suggestion was made), stale (the
    lines moved / were already edited), already-applied.
4. **Confirm-plan**: table of suggestion → file:line → proposed change → applicability.
    Get explicit approval (applying creates commits on the source branch).
5. **Apply**:
    - **Single** (`--all` unset): loop, `suggestions(project, action="apply",
      suggestion_id=N, confirm=true)` — one commit per.
    - **Bulk** (`--all` set): `suggestions(project, action="batch_apply",
      suggestion_ids=[...], confirm=true)` — one commit applying all at once (cleaner history).
6. **Verify**: `get_merge_request(project, iid=N, include="commits")` shows the new commit(s);
    the diff reflects the applied suggestions. Report: applied count, stale count, the commit
    SHAs, and whether the MR pipeline needs a re-run.

Common pattern: reviewer leaves 5 suggestions on a PR; author reviews, applies all 5 via
`batch_apply` (one commit), pipeline re-runs, MR merges. Avoids manual copy-paste-edit per
suggestion.
