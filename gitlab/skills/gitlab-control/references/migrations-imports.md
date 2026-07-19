# Migrations & imports/exports — moving data in and out of GitLab

Four distinct mechanisms, each for a different job. Pick by what you're moving
and where it's going:

| Mechanism | Moves | Best for |
|---|---|---|
| **Project export/import** | One project (repo, issues, MRs, milestones, labels, CI config, wiki, etc.) as a tarball | Backup, snapshot, instance-to-instance move, GitHub-mirror fallback |
| **Group export/import** | A group + its direct resources (subgroups walk recursively) | Bulk move a whole tree |
| **Direct-transfer / bulk import** | Live instance-to-instance via API | Migrating from another GitLab without tarball round-trips |
| **Foreign import** (GitHub/Bitbucket etc.) | Issues + pull requests + wiki from a foreign VCS host | One-way adoption of a GitHub project |

File-upload import (multipart tarball via `/projects/:id/import`) is the only
path that doesn't fit a JSON tool cleanly — drive it via `gitlab_rest` or the UI.

Verified live on `git.hively.dev` 19.0.0: project export/import works;
`bulk_import_enabled: true` since 2026-07-15.

## What's in a project export tarball

Included: repository (git bundle), wiki, issues (with notes, time tracking,
labels, milestones, iterations-as-milestones, design thumbnails), MRs (with
notes, approvals-basic, diffs), pipelines history metadata (not artifacts by
default), CI variables (**masked/plain, NOT protected-only** — confirm before
exporting secrets), labels, milestones, boards, releases, upload attachments,
 snippets (project-scoped).

**NOT included:** CI/CD runner tokens (instance-specific), container registry
images (use registry-level mirroring), package registry contents (re-push),
Terraform state (export separately via the state API), secure files (re-add on
the target), LFS objects (sometimes — depends on version + size; verify), error
tracking / external integrations (reconfigure on target).

## Project export → download → verify

The 3-step async flow. Status-poll between steps.

### 1. Start the export
```
project_import_export(project="ns/name", action="export_start", confirm=true)
```
Returns `202 Accepted` + a message. The export runs in sidekiq.

### 2. Poll status until "finished"
```
project_import_export(project="ns/name", action="export_status")
```
Response: `export_status: "queued" | "started" | "finished" | "none" |
"regeneration_in_progress"`. Poll every ~10s for small projects, longer for
big repos. On `finished`, `_links.api_url` points at the download endpoint.

### 3. Download the tarball
```
project_import_export(project="ns/name", action="export_download")
```
Returns the binary tarball (`Content-Type: application/gzip`). The MCP server
returns it as bytes/base64 — write to disk. **Don't try to read it as JSON.**

### Pre-export checklist
- Confirm no large binaries you don't want (LFS, uploads).
- Decide on CI variables: scrub secrets first (export includes them).
- Pause pipeline schedules if you don't want them firing mid-migration.
- Note the project id + path + default branch for post-import verification.

## Import the tarball into a target project

Two paths:

### a. File-based (multipart) — via `gitlab_rest`
```
POST /projects/import
Content-Type: multipart/form-data
  path=<new-path>
  namespace=<target-ns-id-or-path>
  name=<display-name>
  file=@<tarball>
```
The MCP `gitlab_rest` tool accepts a `body` but multipart is finicky — for a
real import, drop into the UI (`New project → Import project → GitLab export`)
or shell out to `curl`. Poll import status:
```
project_import_export(project="ns/name", action="import_status")
```
Status: `scheduled | started | finished | failed`. On failure, read
`import_error`.

### b. Remote-URL import (tarball at a URL)
```
manage_project(action="import", params={
  "url": "https://origin-instance/path/-/export/status/download",
  "path": "new-path", "namespace": "target-ns",
  "name": "Display Name"
}, confirm=true)
```
GitLab fetches the tarball from the URL. Useful when the origin exposes a
download URL with a token. The body is JSON, so this works cleanly through
`gitlab_rest` / `manage_project`.

## Group export/import

Same shape as project, scoped to a group:
```
project_import_export(... action="export_start" ... project=group_path)   # works for groups via /groups/:id/export
```
Actually group export is at `/groups/:id/export` and group import at
`/groups/import` — drive via `gitlab_rest` or check the curated tool's scope
handling. Group export includes subgroups recursively; useful for moving an
entire team's namespace.

## Direct-transfer / bulk import (`/bulk_imports`)

The highest-fidelity instance-to-instance migration: GitLab-to-GitLab, API-
driven, no tarball staging. **Requires `bulk_import_enabled: true`** in source
admin settings (verified on here) and a source token with `api` scope.

### Flow
1. **Configure source instance connection** — admin settings on the target:
   `bulk_import_enabled: true`, plus allowed source instances if allow-listed.
2. **Create a bulk import**:
   ```
   POST /bulk_imports
   {
     "configuration": {"url": "https://origin", "access_token": "<src-pat>"},
     "entities": [
       {"source_type": "group_entity", "source_full_path": "origin-group",
        "destination_slug": "target-slug", "destination_namespace": "target-ns"},
       {"source_type": "project_entity", "source_full_path": "origin-group/proj",
        "destination_slug": "proj", "destination_namespace": "target-ns"}
     ]
   }
   ```
   Drive via `gitlab_rest("POST", "/bulk_imports", body=..., confirm=true)`.
3. **Poll status**: `GET /bulk_imports/:id` → top-level `status`, plus
   `GET /bulk_imports/:id/entities` for per-entity progress.
4. **Failures**: per-entity `status: "failed"` + `status_message`. Common
   causes: source token lacks scope, destination namespace permission, name
   collision (override `destination_slug`).

### What direct-transfer moves vs project export
Direct-transfer preserves **more** than tarball import on recent versions:
preserves more of the project's graph (MR discussion threads, design files,
some CI config). Both are best-effort; verify after.

### Entity types
`group_entity` (migrates a group + descendants), `project_entity`,
`snippet_entity` (instance snippets bulk). New types land with versions.

## Foreign import (GitHub / Bitbucket / etc.)

Instance-level endpoint, usually driven from the web UI but API-accessible:
```
POST /import/github
POST /import/bitbucket
POST /import/bitbucket_server
```
Needs a personal access token (or app password) for the source host in the
admin "import sources" config. Moves: issues, pull requests (→ MRs), wiki,
milestones, labels. **Does NOT move git history** — that's a separate mirror
push or `git clone --mirror` + `git push --mirror`.

Configure allowed import sources via admin:
```
admin_settings(action="get")  # check import_sources
admin_settings(action="update", params={"import_sources": ["github","bitbucket"]}, confirm=true)
```

## The `/gl-backup` workflow (proposed)

1. **Identify targets** — project(s) or a whole group.
2. **Pre-export**: scrub/rotate any CI secrets you don't want in the tarball;
   note the default branch + project id for verification.
3. **Export → poll → download** per project (or group).
4. **Verify**: re-import into a throwaway namespace on the same instance (or a
   staging instance) and diff: `repo_tree`, `list_issues`, `list_merge_requests`,
   `commits(action="refs")`. Confirm MR count, issue count, commit count match.
5. **Store**: tarball to your backup target (gh-storage via the synology agent,
   S3, etc.). Retain per policy.
6. **Report**: project, size, item counts, verification status.

## Pre-migration checklist (any method)

- [ ] **Source token**: `api` scope, admin if moving groups.
- [ ] **Target token**: `api` scope, Owner on the target namespace.
- [ ] **DNS/network**: target can reach source (for direct-transfer + remote-URL
      import); if source is behind VPN/tailnet, run from a host that can reach it.
- [ ] **Namespace planning**: decide destination paths/slug collisions.
- [ ] **Secrets inventory**: CI variables, deploy tokens, webhooks secrets,
      runner tokens — none of these migrate cleanly. Plan to rotate + re-set.
- [ ] **Integrations**: Slack/Jira/etc. need reconfiguring on target.
- [ ] **Container registry + packages**: re-push or mirror separately.
- [ ] **Runners**: re-register on target (the v16 flow — see
      `references/runners-deep.md`).
- [ ] **Webhooks**: re-create on target; flag any with
      `enable_ssl_verification: false`.
- [ ] **Protected branches/tags**: re-create (rules don't always survive import).
- [ ] **Users**: target-instance users must exist with matching username/email
      for issue/MR authorship to map correctly. Mismatched → attributed to the
      importing user.

## Post-migration verification

For each migrated project, diff against the source:

```
get_project(target) vs get_project(source)      # settings
repo_tree(target, recursive=true) vs source      # file tree
commits(target, action="list", limit=100) vs source   # recent history
list_issues(target) vs source                    # count + spot-check
list_merge_requests(target, state="all") vs source
pipelines(target, action="latest")               # CI runs
read_file(target, ".gitlab-ci.yml")              # CI config survived
ci_variables(target)                              # secrets migrated?
webhooks(scope_id=target, action="list")         # re-created?
```

Discrepancies are expected in: CI variables (scrubbed), webhooks (re-create),
runners (re-register), container registry (re-push), LFS (verify),
collaborators (re-add). Report each gap explicitly — don't claim "100%
migrated" without checking.

## Limits & gotchas

- **Tarball size** — no hard API cap but very large repos (>5 GB) can timeout
  mid-export. Use direct-transfer for those.
- **Rate limits** — exports + imports are sidekiq jobs; a flood of concurrent
  exports can starve other workers. Stagger.
- **`none` export_status** means the project has never been exported — start
  one. `regeneration_in_progress` means a prior export is being rebuilt.
- **Direct-transfer entity `failed`** — almost always source-token scope or
  destination permission. Re-issue source token with `api` and retry that entity.
- **Authorship attribution** — issues/MRs are reattributed to the importing
  user when the original author doesn't exist on the target. Pre-create users
  (matching email/username) to preserve attribution.
- **CI variable protection** — a `protected: true` variable may not survive
  import if the target branch isn't protected yet. Protect first, then import.
- **LFS** — sometimes omitted from tarball; verify with `repo_extras` or a
  fresh clone test. Re-push LFS separately if missing.
- **Wiki** — exported as a separate repo inside the tarball; imports cleanly on
  recent versions but verify by listing wiki pages post-import.
