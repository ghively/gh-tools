---
description: Export a project (or group) as a tarball, download, and verify it's restorable
argument-hint: <project | group> [output-dir]
---

Back up **$ARGUMENTS** to a verified-restorable tarball. Read `references/migrations-imports.md`.
Exports are async — start, poll, download, verify. All steps except the read-only `export_start`
are non-mutating to the source (exports don't modify the project).

1. **Pre-flight**: `get_project`/`groups(action="get")` to capture the baseline (id, path,
   default branch, statistics — commit count, sizes, MR/issue counts). Note CI variables:
   `ci_variables(project, action="list")` — flag any secrets that will land in the tarball;
   offer to rotate/scrub first if the backup leaves the trusted environment.
2. **Start export**: `project_import_export(project, action="export_start", confirm=true)`
   → returns `202`. (For a group, use `gitlab_rest("POST", "/groups/:id/export", confirm=true)`.)
3. **Poll status** every ~10s (longer for big repos): `project_import_export(project,
   action="export_status")`. Wait until `export_status: "finished"`. On
   `"failed"` or stuck >10m, abort and report (sidekiq overload / Gitaly timeout).
4. **Download**: `project_import_export(project, action="export_download")` → binary tarball.
   Write to `output-dir` (default: current dir) as `<safe-path>-<YYYYMMDD>.tar.gz`.
5. **Verify** the tarball is non-empty and has the expected structure (loose check: file
   size ≥ a few KB; `tar -tzf` lists `tree/`, `issues/`, `merge_requests/`, etc.). For full
   verification, import into a throwaway namespace on the same instance and diff:
   `repo_tree`, `list_issues`, `list_merge_requests`, `commits(action="list", limit=20)` —
   counts should match the pre-flight baseline.
6. **Report**: project, tarball path, size, item counts (pre vs post), verification status,
   and what was NOT captured (runners, registry images, packages, webhooks secrets — re-push
   or reconfigure separately). Recommend storage target (nas-host via the synology agent).

Never claim "100% backed up" without the verify step. CI secrets travel in the tarball — treat
the backup file as a credential.
