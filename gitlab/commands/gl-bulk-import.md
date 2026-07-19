---
description: Drive a direct-transfer (bulk) import from another GitLab instance via /bulk_imports
argument-hint: <source-url> <source-token> <entities...>
---

Migrate projects/groups from another GitLab instance into this one via direct-transfer. Read
`references/migrations-imports.md`. Requires `bulk_import_enabled: true` on the target
(verify via `admin_settings(action="get")`) and an `api`-scope source token.

1. **Pre-flight (read-only)**: confirm `bulk_import_enabled` on target. List the source
   entities the user named and resolve their full paths on the source (via `gitlab_rest("GET",
   "<source-url>/api/v4/projects/<urlencoded-path>" ...) ` or ask the user to confirm paths).
   Decide destination namespace + slug for each (avoid collisions — `list_projects`/`groups
   (action="get")` on target to check).
2. **Build the entities payload**: array of `{source_type: "group_entity"|"project_entity",
   source_full_path, destination_slug, destination_namespace}`.
3. **Confirm-plan**: show the user the full POST body (source URL redacted token, entities,
   destinations). Get explicit approval.
4. **Create the bulk import**: `gitlab_rest("POST", "/bulk_imports", body={
   configuration: {url: <source>, access_token: <src-pat>}, entities: [...]}, confirm=true)`.
   Capture the returned `id`.
5. **Poll**: `gitlab_rest("GET", "/bulk_imports/:id")` → top-level `status` (`started` →
   `finished` | `failed`). Per-entity detail: `gitlab_rest("GET", "/bulk_imports/:id/entities")`
   → each row's `status`, `status_message`, `links`. Poll every ~30s for large migrations.
6. **Failures**: per-entity `failed` → read `status_message` (almost always source-token scope
   or destination permission). Re-issue the source token with `api` scope or fix the
   destination Owner, then re-create a NEW bulk_import for just the failed entities.
7. **Verify**: for each migrated project, diff source vs target — `repo_tree`, `commits(action=
   "list", limit=20)`, `list_issues`, `list_merge_requests`. Re-create on target what didn't
   survive (CI variables, webhooks, runners, protected branches, registry images — see the
   checklist in `references/migrations-imports.md`).
8. **Report**: entities migrated/failed/partial, item counts per project, what needs manual
   follow-up (secrets, runners, integrations).

Direct-transfer preserves more graph structure than tarball import (MR threads, designs) but
is still best-effort. The verify step is the contract.
