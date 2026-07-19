---
description: Bootstrap a group — create it, configure subgroups, members, labels, and policies
argument-hint: <group-path> [--parent <parent-id>] [--description "..."]
---

Set up **$ARGUMENTS** as a fully-configured group. Read `references/admin-and-self-hosting.md`
and `references/projects-repo-mrs-issues.md`. Each step shows the payload and requires its own
approval before `confirm=true`.

1. **Plan the structure**: confirm the group path (top-level under a namespace, or under a
   `--parent`), the display name, visibility (`private` | `internal` | `public`), and any
   subgroups to create. Resolve the parent id if `--parent` is a path
   (`groups(action="get", group=...)` → `id`).
2. **Create the group**: `groups(action="create", params={name, path, parent_id?,
   visibility}, confirm=true)`. Capture the new `id`.
3. **Settings + policies**: `gitlab_rest("PUT", "/groups/:id", body={
   description, project_creation_level: "maintainer"|"developer"|"noone",
   subgroup_creation_level: "maintainer"|"owner", require_two_factor_authentication: true,
   default_branch_protection: 2, ...}, confirm=true)` — apply the org's standard group policy.
4. **Members + roles**: for each (user, access_level) pair, `members(scope_type="group",
   scope_id=<gid>, action="add", user_id=<uid>, access_level=<N>, confirm=true)`. Add at least
   two Owners (avoid single-point orphaning). Invite external users via
   `membership_requests(scope_type="group", scope_id=..., action="invite", email=...,
   params={access_level, expires_at}, confirm=true)` if needed.
5. **Labels** (group-level): for each label, `labels(scope_type="group", scope_id=<gid>,
   action="create", name=..., params={color, description}, confirm=true)`. Standard set:
   `priority::high/med/low`, `type::bug/feature/chore`, `status::blocked/ready/in-progress`.
6. **Shared runners**: confirm `shared_runners_minutes_limit` if relevant (SaaS concept — N/A on
   self-hosted CE; the group inherits instance runners). Note any group-specific runner to
   register separately via `/gl-runner-manage`.
7. **Subgroups** (if planned): recurse — `groups(action="create", params={name, path,
   parent_id: <gid>, visibility}, confirm=true)` for each.
8. **Verify**: `groups(action="get", group=<path>)`, `members(..., action="list_all")`,
   `labels(..., action="list")`. Report the final structure (tree), the policy applied, and the
   owners list. Recommend running `/gl-onboard` for each project you'll create under it.

Don't grant Owner to a single user — always have ≥2 owners to prevent orphaning. For
compliance-sensitive groups, set `require_two_factor_authentication: true` (note: enforcement
needs the instance 2FA setting too).
