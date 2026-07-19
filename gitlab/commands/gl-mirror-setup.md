---
description: Configure pull and/or push remote mirrors for a project
argument-hint: <project> <mode: pull|push|both> <remote-url> [--branches regex] [--only-protected]
---

Set up repository mirroring to/from another git host. Read `references/projects-repo-mrs-issues.md`
and `references/migrations-imports.md`. Mirror URLs with embedded credentials are secrets —
handle carefully, don't echo in full.

1. **Inspect current state** (read-only): `remote_mirrors(project, action="list")` — existing
    mirrors, their enabled state, direction. `get_project(project)` for the default branch.
2. **Validate the remote URL**:
    - **pull**: the remote must be readable by GitLab (network reachable; credentials if needed).
    - **push**: GitLab writes to the remote (needs write credentials embedded in the URL or
      an SSH deploy key).
    - URL forms: `https://user:token@host/path.git` (embed creds) or
      `git@host:path.git` (SSH key, configured separately).
3. **Build params**:
    - `url`: the remote URL (treat as secret if it contains credentials).
    - `enabled`: true.
    - `only_protected_branches`: true (mirror only protected branches) or false (all).
    - `keep_divergent_refs`: true (don't force-overwrite diverged branches on the target).
    - `mirror_branch_regex`: branch name regex (if scoping).
4. **Confirm-plan**: show the mirror config (REDACT credential portion of the URL). Get explicit
    approval.
5. **Apply**: `remote_mirrors(project, action="create", params=<above>, confirm=true)`.
6. **Trigger initial sync**: `remote_mirrors(project, action="sync", mirror_id=N, confirm=true)`.
7. **Verify**: `remote_mirrors(project, action="get", mirror_id=N)` — confirm last sync status +
    `update_status`. Report: mirror direction, URL (redacted), branch filter, last sync result.

Common patterns: mirror GitHub → GitLab for CI (pull); mirror GitLab → backup host (push);
keep a fork in sync with upstream (pull, only-protected). Mirrors respect branch protection
on the target — push mirrors won't force-push to protected branches unless allow_force_push.
