---
description: Manage RomM users, roles, permission groups, and invite links
argument-hint: e.g. "add viewer account for the kids" or "audit access"
---

# RomM user & access management

Administer users with the `romm` MCP tools. Parse the request from
`$ARGUMENTS`. Every mutation below is confirm-gated — state exactly what will
change and get the user's go-ahead before passing `confirm=True`.

1. **Audit** — `romm_users()` (roles, enabled, last active),
   `romm_permissions(scope="groups")` for permission groups,
   `romm_api_keys(action="list_all")` for outstanding API keys.
2. **Create an account** — either directly
   (`romm_user_create(username, email, password, role, confirm=True)`) or,
   better for humans, mint an invite link
   (`romm_user_invite(role=..., confirm=True)`) and hand the URL to the user.
   Roles: **viewer** (browse/play), **editor** (+library edits), **admin**
   (everything).
3. **Change access** — `romm_user_update(id, fields_json='{"role": "editor"}'
   , confirm=True)`; disable instead of delete when in doubt
   (`'{"enabled": false}'`). Fine-grained grants beyond roles live in
   permission groups: inspect via `romm_permissions`, manage via
   `romm_call("POST"/"PUT", "/api/permissions/groups...", confirm=True)`.
4. **RetroAchievements** — link a user's RA account with
   `romm_user_update(id, fields_json='{"ra_username": "..."}')`; refresh their
   RA progress with `romm_call("POST", "/api/users/{id}/ra/refresh",
   confirm=True)`.
5. **Remove** — `romm_user_delete(id, confirm=True)` (destructive — their
   saves/states/props go with them; offer disable first).

## Output

Show the resulting state (`romm_users()` or `romm_user(id)`) as proof.
