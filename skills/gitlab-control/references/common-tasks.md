# Verified call recipes for non-curated jobs

All via `gitlab_rest` (writes need `confirm=true` + user approval). These paths
were live-verified (reads) or 400-probed (writes) on 19.x CE.

> **Many of these now have curated tools** (v0.4.0/v0.5.0) — prefer the curated tool when it
> exists. Mapping: emoji reactions → `award_emoji`, draft notes → `draft_notes`, suggestions →
> `suggestions`, time tracking → `time_tracking`, resource events → `resource_events`, secure
> files → `secure_files`, custom attributes → `custom_attributes`, markdown → `markdown`,
> remote mirrors → `remote_mirrors`, bulk imports → `bulk_imports`. The raw paths below remain
> the escape hatch for params the curated tools don't expose.

## Repo & files

```
# Blame a file
GET /projects/:id/repository/files/:enc_path/blame?ref=main
# Raw file (no JSON wrapper)
GET /projects/:id/repository/files/:enc_path/raw?ref=main
# Download repo archive (returns binary — prefer web_url for big repos)
GET /projects/:id/repository/archive.zip?sha=main
# Contributors / merge-base
GET /projects/:id/repository/contributors
GET /projects/:id/repository/merge_base?refs[]=main&refs[]=feature
# Commit comment / set commit CI status
POST /projects/:id/repository/commits/:sha/comments {note}
POST /projects/:id/statuses/:sha {state: success|failed|..., context}
```

## Collaboration extras

```
# Emoji reactions (issues/MRs/snippets + their notes)
GET|POST|DELETE /projects/:id/issues/:iid/award_emoji {name: thumbsup}
# Draft (pending) MR review notes
GET|POST /projects/:id/merge_requests/:iid/draft_notes
POST /projects/:id/merge_requests/:iid/draft_notes/bulk_publish
# Apply an MR suggestion
PUT /suggestions/:id/apply
# Issue boards
GET|POST /projects/:id/boards ; .../boards/:bid/lists
# Time tracking
POST /projects/:id/issues/:iid/time_estimate {duration: "3h"}
POST /projects/:id/issues/:iid/add_spent_time {duration: "1h"}
# Resource label events (audit trail of label changes)
GET /projects/:id/issues/:iid/resource_label_events
```

## CI/CD extras

```
# Trigger tokens
GET|POST /projects/:id/triggers ; trigger a pipeline:
POST /projects/:id/trigger/pipeline {token, ref, "variables[KEY]": val}
# Job artifacts (binary download)
GET /projects/:id/jobs/:jid/artifacts
GET /projects/:id/jobs/artifacts/:ref/download?job=build   # latest successful
# Job token scope allowlist
GET|PATCH /projects/:id/job_token_scope ; GET|POST|DELETE .../allowlist
```

## Admin extras

```
# Sidekiq queue purge (DANGEROUS)
DELETE /admin/sidekiq/queues/:queue_name
# Repository storage moves (instance migration)
GET|POST /project_repository_storage_moves
# Custom attributes (arbitrary admin metadata on users/projects/groups)
GET|PUT|DELETE /users/:id/custom_attributes/:key {value}
# Approve/reject pending users
POST /users/:id/approve ; POST /users/:id/reject
# Import a project export archive (multipart upload — use curl for the file part)
POST /projects/import  (file=@export.tar.gz, path=new-name)
# GitHub import
POST /import/github {personal_access_token, repo_id, target_namespace}
```

## Misc verified

```
POST /markdown {text, gfm: true, project}      # render GitLab-flavored markdown
GET  /avatar?email=someone@example.com
GET  /projects/:id/templates/gitignores        # + licenses|dockerfiles|gitlab_ci_ymls
GET  /namespaces/:path/exists
POST /topics/merge {source_topic_id, target_topic_id}
GET  /projects/:id/pages ; GET /pages/domains  # Pages status (admin)
# Badges
GET|POST /projects/:id/badges {link_url, image_url}
# Remote push mirrors
GET|POST /projects/:id/remote_mirrors {url, enabled} ; POST .../:mid/sync
# Project feature flags (deploy-time flags, CE-supported)
GET|POST /projects/:id/feature_flags {name, version: new_version_flag, strategies}
```

## Free-tier features verified on CE (probed 2026-07-15)

```
# Secure files (per-project credential/cert storage for CI)
GET /projects/:id/secure_files ; GET .../secure_files/:fid/download
# Direct transfer (bulk import from another GitLab) — enable first:
PUT /application/settings {bulk_import_enabled: true}
POST /bulk_imports {configuration: {url, access_token}, entities: [...]}
# Dependency proxy purge (group)
DELETE /groups/:id/dependency_proxy/cache
```

```graphql
# Work items / alerts / CI catalog / achievements / ML models — GraphQL-first on CE
{ project(fullPath: "homelab/hermes-vault") {
    workItems { count } alertManagementAlerts { nodes { iid title } }
    mlModels { count } } }
{ ciCatalogResources { count } }
{ group(fullPath: "homelab") { achievements { count }
    dependencyProxySetting { enabled } } }
```

## GraphQL one-shots

```graphql
# Nested fetch: project → open MRs → their pipelines, one round-trip
{ project(fullPath: "homelab/hermes-vault") {
    mergeRequests(state: opened) { nodes { iid title
      headPipeline { status } } } } }

# Work items (newer issue model; REST covers classic issues only)
{ workItemsByReference(refs: ["homelab/hermes-vault#1"]) { nodes { id title } } }

# CI config validation with includes resolved
{ ciConfig(projectPath: "homelab/hermes-vault", content: "...") {
    status errors mergedYaml } }
```
