---
description: Sync a baseline label set (name + color + description) across projects and/or groups
argument-hint: <labels-json | @file> (--targets ns/a,ns/b | --group ns)
---

Apply a consistent label taxonomy across multiple targets. Read `references/projects-repo-mrs-issues.md`.
Non-destructive to issues (labels in use can't be deleted without re-labeling).

1. **Parse the spec** (JSON: `[{"name": "priority::high", "color": "#d9534f", "description":
    "...", "ensure": true}, ...]`) — inline `$ARGUMENTS` or `@file`.
2. **Enumerate targets**: `--targets` (list each project) or `--group` (all projects in the
    group tree via `groups(action="projects")`).
3. **Diff per target** (read-only): `labels(scope_type, scope_id, action="list")` — for each
    label in the spec:
    - **missing** → create.
    - **color/description differs** → update (preserve issues already tagged).
    - **present, matches** → leave.
    Optionally: **label in target but NOT in spec** → flag for removal (don't auto-delete;
    issues may still reference it).
4. **Confirm-plan**: matrix of target × label → action. Get explicit approval.
5. **Apply**: loop with `confirm=true`:
    `labels(scope_type, scope_id, action="create"|"update", name=..., params={color, description})`.
6. **Verify**: re-`list` per target. Report: creates/updates per target, any orphaned labels
    flagged (in target, not in spec).

Standard label taxonomies to seed: priority (`priority::low/med/high`), type
(`type::bug/feature/chore/security`), status (`status::blocked/ready/in-progress/in-review`),
size (`size::S/M/L/XL`). Color consistency matters for dashboards — fix the hex, not just
the name.
