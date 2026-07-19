---
description: Audit storage usage across projects/groups and flag the space hogs
argument-hint: [group <id> | instance]
---

Inventory storage consumption and propose cleanup targets. Read `references/cicd.md` (artifact
expiration), `references/packages-registry-deep.md` (registry cleanup), and
`references/migrations-imports.md`. Read-only — propose, don't purge.

1. **Enumerate projects** (read-only):
    - `--group`: `groups(action="projects", group=...)` for all in the tree.
    - `instance`: `list_projects(per_page=100, paginate=true)` (admin).
2. **For each, gather statistics**: `get_project(project, statistics=true)` returns
    `statistics: {storage_size, repository_size, lfs_objects_size, job_artifacts_size,
    pipeline_artifacts_size, packages_size, container_registry_size, uploads_size, snippets_size}`.
    For groups, the GraphQL `group { ... }` returns rollups.
3. **Rank & classify**: sort projects by total storage_size. For each top-N, identify the
    dominant component:
    - **job_artifacts_size** → `pipelines(action="list")` + artifact expiration policy.
    - **container_registry_size** → `container_registry(action="tags_bulk_delete")` opportunity.
    - **packages_size** → `packages(action="list")` + cleanup policy.
    - **repository_size** → housekeeping (`manage_project(action="housekeeping")`), LFS audit.
    - **lfs_objects_size** → LFS audit (rarely prunable; identify the files).
4. **Propose** per top-N project: the dominant component, current size, proposed action
    (set expiration policy, bulk-delete old tags, prune packages, run housekeeping), estimated
    space recovered (best-effort).
5. **Report**: ranked table (project → total → dominant component → proposed action → est.
    savings). Sum the total instance storage + the addressable portion.

Instance-wide: `admin_settings(action="get")` for any repository-storage limits;
`gitlab_rest("GET", "/application/statistics")` for the global counts. The actual cap depends
on whether you've set plan limits (admin) — on a self-hosted Free instance there is no hard
cap; storage grows until the disk fills.
