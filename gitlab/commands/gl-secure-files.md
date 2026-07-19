---
description: Manage CI/CD secure files for a project (list, add, remove) — distinct from variables
argument-hint: <project> [list | add <file> | remove <id>]
---

Manage **secure files** for **$ARGUMENTS**. Secure files are full file credentials (kubeconfig,
`.npmrc`, signing keys, gcloud service-account JSON) stored at the project level and injected
into CI jobs via `$CI_PROJECT_DIR` download — distinct from CI variables (which are short
string values). Read `references/cicd.md`.

1. **Identify the project**: `get_project(project)` → capture `id`. Secure files use the REST
   surface `/projects/:id/secure_files` (not currently a curated tool — drive via `gitlab_rest`).
2. **List** (read-only): `gitlab_rest("GET", "/projects/:id/secure_files")` — each row has
   `id`, `name`, `checksum`, `created_at`, `expires_at` (if set). Report the inventory.
3. **Add** (multipart — special case): secure-file upload is a multipart form, which doesn't fit
   `gitlab_rest` cleanly. Two options:
   - **UI**: Project → Settings → CI/CD → Secure files → upload.
   - **Shell**: `curl --request POST --header "PRIVATE-TOKEN: <token>" --form "name=<alias>" \
     --form "file=@/path/to/file" https://git.hively.dev/api/v4/projects/:id/secure_files`.
   For larger batches, drop into the shell. **Confirm the file's contents are appropriate to
   store in GitLab** (it becomes a project credential — treat like a secret).
4. **Remove**: `gitlab_rest("DELETE", "/projects/:id/secure_files/:file_id", confirm=true)`.
   Irreversible. Confirm the exact file name + id before calling.
5. **Rotate/update**: there's no in-place update — remove the old, add the new. If a file has
   an `expires_at`, surface it in `/gl-audit` and `/gl-token-rotate`.
6. **Verify**: re-`list`. Report: count, names, checksums, any expiry dates, and how to consume
   them in CI (the `secure_files` download keyword in `.gitlab-ci.yml`, or the
   `secure_files:` entry in the gitlab-runner config).

Secure files are CE-working and a good home for things too long or too binary for a masked
variable. They do NOT travel in project export by default — re-add on the target after a
migration (see `references/migrations-imports.md`).
