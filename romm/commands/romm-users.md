---
description: Manage RomM users, roles, permission groups, and invite links
argument-hint: e.g. "add an account for the kids" or "audit access"
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
   Roles on RomM 5.x are ONLY **user** and **admin** (verified live — the
   server silently ignores anything else, e.g. the old viewer/editor).
   Everything finer-grained lives in **permission groups**.
3. **Change access** — `romm_user_update(id, fields_json='{"role": "admin"}'
   , confirm=True)`; disable instead of delete when in doubt
   (`'{"enabled": false}'`). Non-admin access is shaped by permission
   groups: inspect via `romm_permissions(scope="groups")` (built-ins
   include a "Viewer (legacy)" and "Editor (legacy)" group); check a user's
   effective grants with `romm_permissions(scope="user", user_id=N)` and
   change them via `romm_user_permissions_update(user_id, ..., confirm=True)`
   (group assignment and/or per-entity overrides); create/update/delete
   groups via `romm_permission_group(action=..., confirm=True)`; hide
   specific entities from a user/group via `romm_permission_hidden`.
4. **RetroAchievements** — link a user's RA account with
   `romm_user_update(id, fields_json='{"ra_username": "..."}')`; refresh their
   RA progress with `romm_call("POST", "/api/users/{id}/ra/refresh",
   confirm=True)`.
5. **Remove** — `romm_user_delete(id, confirm=True)` (destructive — their
   saves/states/props go with them; offer disable first).

## Output

Show the resulting state (`romm_users()` or `romm_user(id)`) as proof.
