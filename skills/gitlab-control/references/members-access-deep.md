# Members & access — the deep guide

Access control on GitLab is layered: **role** (access_level number) × **scope** (where the role
is granted) × **inheritance** (how roles flow down the group tree). Getting any of the three
wrong is the most common audit finding. This file is the practical map.

## Access levels (the numeric ladder)

| # | Constant | What it can do |
|---|---|---|
| 0 | NO_ACCESS | nothing (explicit deny) |
| 5 | MINIMAL_ACCESS | read project overview (no repo), trigger via webhook — for CI/automation accounts |
| 10 | GUEST | read repo + issues, comment on MRs, pull container images |
| 15 | PLANNER | (Ultimate-only tier — on Free behaves like Guest) read issues + create, no repo |
| 20 | REPORTER | read + pull, issues, MR comments, code search, download packages |
| 25 | SECURITY_MANAGER | (Ultimate-only) read vuln mgmt + security policies |
| 30 | DEVELOPER | push to non-protected branches, create branches/tags/MRs, run pipelines, write packages |
| 40 | MAINTAINER | push to protected (if allowed), merge MRs, manage runners/settings/members(developer-), delete registry tags |
| 50 | OWNER | transfer/delete project, manage all members, manage CI/CD settings, group deletion (for groups) |

**On CE without a license:** passing `15` (Planner) or `25` (Security Manager) silently
falls back to the next-lower valid tier (`10` Guest). Don't use them on Free.

## Three places a role can be granted

1. **Direct membership** — the user is added to this specific project or group.
   `members(scope_type, scope_id, action="add", user_id, access_level, confirm=true)`.
2. **Inherited from a parent group** — if a user is an Owner of `gregory`, they're
   effectively Owner of every subgroup and project under `gregory/archive/...` unless
   overridden. Inheritance is additive (max wins), never subtractive.
3. **Shared group** (group-to-group or group-to-project sharing) — a group shares access
   to one of its projects with another group, at a capped access level.
   `gitlab_rest("POST", "/groups/:id/share", body={group_id, group_access, expires_at},
   confirm=true)`. The invited group's members get the capped access to the target.

**Where a user's effective access comes from** — always check all three:
`members(..., action="list_all")` returns the **effective** list including inherited +
shared entries (each row shows `membership_type`: direct / inherited / shared group ancestor).
This is the authoritative read for "who can do what here."

## The Owner-orphaning trap (the #1 offboarding failure mode)

A group/project with zero Owners is **orphaned** — no one can delete it, transfer it, or
manage its members via the UI. Recovery requires an admin via the Rails console. **Always
add a replacement Owner BEFORE removing/blocking the current sole Owner.**

```
# safe order:
1. members(..., action="add", user_id=<new-owner>, access_level=50, confirm=true)
2. verify members(..., action="list_all") shows ≥2 Owners
3. THEN block/deactivate/remove the departing user
```

`/gl-user-offboard` does this; `/gl-group-setup` enforces ≥2 Owners at creation.

## Membership types (what `list_all` returns)

| `membership_type` | Meaning |
|---|---|
| `direct` | added to THIS project/group specifically |
| `inherited` | added to a parent group (shows `source_id` / `source_parent_id`) |
| `shared group ancestor` / `shared group into project` | arrived via a group share |

Use `list` (not `list_all`) to see ONLY direct members you can manage here; use `list_all`
for the full effective footprint (audit, offboarding).

## Common operations

### Add a member
```
members(scope_type="project", scope_id=<pid>, action="add", user_id=<uid>,
        access_level=30, params={expires_at: "2027-01-01"}, confirm=true)
```
`expires_at` is the single most underused access-control feature — set it for contractors,
rotations, and any non-permanent access.

### Update / remove
```
members(..., action="update", user_id=<uid>, access_level=40, confirm=true)
members(..., action="remove", user_id=<uid>, confirm=true)  # removes direct membership only
```
Removing a direct membership doesn't touch inherited access — the user may still have
effective access via a parent group. Check `list_all` after.

### Invite (by email, when the user doesn't exist yet)
```
membership_requests(scope_type="project", scope_id=<pid>, kind="invitations",
    action="invite", email="alice@example.com", params={access_level: 30, expires_at: "..."},
    confirm=true)
```

### Access requests (user-initiated)
```
membership_requests(..., kind="access_requests", action="list")
membership_requests(..., kind="access_requests", action="approve", user_id=<uid>,
    params={access_level: 20}, confirm=true)
```

## Audit patterns (for `/gl-audit`)

- **Over-privileged direct members** — Reporter/Developer who should be inherited from a
  parent group (consolidate). Flag any direct Owner that duplicates a group-level Owner.
- **External users with broad access** — `users(action="get")` → `external: true` +
  high access_level. External users should be scoped tightly.
- **Stale invites** — `membership_requests(..., kind="invitations", action="list")` —
  invitations older than 30 days are likely abandoned.
- **No expiry on contractors** — `members(..., action="list_all")` → rows with no
  `expires_at` on non-Owner direct memberships.
- **Sole-Owner resources** — group/project with exactly one Owner — orphan risk.

## SSH / deploy keys (a separate access channel)

SSH keys authenticate git-over-SSH pushes; deploy keys are project-scoped read[/write] SSH
keys for automation. Both are managed separately from role-based access:

- `deploy_credentials(kind="keys", action="list"|"create"|"delete", ...)`.
- Personal SSH keys: `users(action="keys", ...)` or user self-manages.

A blocked user's SSH keys stop working; a deactivated user's keys also stop. PATs and
project/group access tokens are the API-auth equivalent.

## What CE doesn't have (Premium/Ultimate)

- **Custom member roles** (`member_role_id`, granular permissions) — Ultimate.
- **LDAP/SAML group sync** (auto-assign roles based on IdP group) — Premium.
- **Approval-based membership** (admin approves join requests to a group) — Premium.
- **Group billable members** counting — Premium.

On Free, role assignment is manual (or via the API you're reading about). There is no
"this user is in the `developers` LDAP group → automatically Developer on these projects"
automation without Premium.

## Practical defaults (the org-policy row)

For a typical project:
- **2+ Owners** (avoid orphaning).
- **Maintainers** are the people who merge (a small set, e.g. tech leads).
- **Developers** are the people who push branches and open MRs (the team).
- **Reporters** are cross-team reviewers / QA.
- **Guests** are issue-only collaborators (PMs, stakeholders).
- Set `expires_at` on everyone who isn't permanent staff.
- Use **group-level membership** instead of per-project wherever possible — one change
  at the group propagates to every project under it, vs. N changes.

`/gl-group-setup` and `/gl-onboard` apply this by default; `/gl-member-sync` applies it
across an existing fleet.
