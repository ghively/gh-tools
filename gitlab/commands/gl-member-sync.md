---
description: Sync a baseline membership (roles + expiries) across projects and/or groups
argument-hint: <members-json | @file> (--targets ns/a,ns/b | --group ns) [--dry-run]
---

Apply a consistent membership baseline across multiple targets so role sprawl is corrected.
Read `references/members-access-deep.md`. **Reassigns/removes** are destructive — enumerate
first, confirm-list, then apply.

1. **Parse the spec** (JSON: `[{"user_id": N, "access_level": 30, "expires_at": "...", "mode":
    "ensure"|"remove"}, ...]`) — from inline `$ARGUMENTS` or `@file`. Validate each user_id
    via `users(action="get")`.
2. **Enumerate targets** (read-only):
    - `--targets`: list each; `get_project` to confirm.
    - `--group`: `groups(action="projects", group=...)` for all projects in the group tree.
3. **Diff per target** (read-only): `members(..., action="list_all")` — for each (user, target):
    - **already correct** (level + expiry match) → leave.
    - **level/expiry differs** → update.
    - **present but spec says remove** → remove (only direct; warn if inherited).
    - **absent and spec says ensure** → add.
4. **Confirm-plan matrix**: target × user → action. Flag any **removal that drops the Owner
    count below 2** (orphan risk — block and require a replacement first). Get explicit approval.
5. **Apply**: loop with `confirm=true`:
    `members(..., action="add"|"update"|"remove", user_id, access_level, params={expires_at})`.
6. **Verify**: re-`list_all` per target. Report: per-target adds/updates/removes, any
    orphan-risk blocks, final Owner count per target.

Pair with `/gl-user-offboard` when a user is leaving (this corrects the baseline AFTER the
offboard). Pair with `/gl-group-setup` when establishing a new group's membership.
