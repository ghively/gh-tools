---
description: Offboard a user — audit their access, then block/deactivate and revoke tokens (admin)
argument-hint: <username-or-id>
---

Offboard **$ARGUMENTS** cleanly and reversibly-where-possible. This is high-impact — show the full
plan and get explicit approval before any `confirm=true` call. Read `references/admin-and-self-hosting.md`.

1. **Identify + audit** (read-only): `users(action="get", ...)` for the user; their memberships
   (`users(action="memberships", ...)` or scan `members(...)` across their projects/groups), their
   personal access tokens (`user_tokens(action="list")` filtered by user_id, admin), SSH/GPG keys,
   and owned projects/groups. Present the full access footprint.
2. **Decide the mode with the user**:
   - **Deactivate** (`users(action="update"/deactivate...)`, reversible) for a leave-of-absence.
   - **Block** (blocks sign-in + API, reversible) for immediate access cut.
   - **Ban/Delete** (delete is irreversible; use `hard_delete` only if contributions must go — else
     contributions reassign to Ghost User) for permanent removal.
3. **Revoke tokens/keys**: for each PAT, `user_tokens(action="revoke", ...)`; remove SSH/GPG keys.
   Revoke any project/group access tokens they created (`access_tokens(..., action="revoke")`).
4. **Reassign ownership**: for sole-Owner groups/projects, add a replacement Owner BEFORE removing
   the user (`members(..., action="add"/"update", confirm=true)`), else the resource is orphaned.
5. **Execute** the chosen block/deactivate with `confirm=true`, then **verify**: `users(action="get")`
   shows the new state; confirm tokens are revoked. Summarize every action taken.

Prefer block/deactivate over delete unless the user explicitly wants permanent deletion.
