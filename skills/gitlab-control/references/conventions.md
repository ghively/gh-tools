# GitLab API conventions & quirks (verified on 19.x CE)

## Auth

- REST: `PRIVATE-TOKEN: <pat>` header. GraphQL: `Authorization: Bearer <pat>`.
  The MCP server handles both; config comes from `config.local.json` (git-ignored)
  or `GITLAB_URL`/`GITLAB_TOKEN` env vars.
- The configured PAT has the `api` scope on an **admin** user — admin endpoints
  (`/users` writes, `/application/settings`, `/admin/ci/variables`, sidekiq,
  `/features`, all-PATs listing) all verified working.
- Token self-inspection: `GET /personal_access_tokens/self`.

## Identifiers

- Projects and groups accept a numeric id **or** URL-encoded full path
  (`homelab%2Fhermes-vault`). Curated tools encode paths automatically.
- Issues/MRs use per-project `iid` (what the UI shows), not global `id`.
- File paths inside `/repository/files/...` must be URL-encoded (handled by
  `read_file`/`write_files`).

## Pagination

- Offset style: `page` + `per_page` (max 100). Response headers: `x-total`,
  `x-total-pages`, `x-next-page`, `link`. Collections >10k rows drop `x-total`
  and require keyset pagination (`pagination=keyset&order_by=id`).
- `gitlab_rest(..., paginate=true, max_pages=N)` auto-follows pages on GETs.

## Errors (observed live)

| Response | Meaning |
|---|---|
| 400 `{"error": "x is missing"}` | Required param missing — endpoint exists |
| 401 | Bad/expired token |
| 403 | Scope/role insufficient, or feature disabled for the project |
| 404 `{"error"\|"message": "404 ... Not Found"}` | Missing resource **or EE-only feature on CE** |
| 405 | Endpoint exists, method wrong |
| 409/422 | State conflict / validation failure (e.g. MR not mergeable) |

**The 404 ambiguity is the #1 gotcha on CE.** Before declaring a bug, check the
EE-only lists in `api-map.md`.

## Quirks found while building

- `GET /projects/:id/error_tracking/settings` → 404 until error tracking is first
  configured for that project (then GET/PATCH work). Not an EE limit.
- `GET /projects/:id/ci/lint` still works on 19.0 (docs mark it deprecated);
  `POST .../ci/lint {content}` is the future-proof call.
- Global code search (`scope=blobs` without a project) needs Elasticsearch →
  400 `Scope not supported`; **per-project** `blobs` search works fine on CE.
- Runner registration tokens are deprecated in 19.0 — create runners with
  `POST /user/runners` (returns the new-style `glrt-` token once).
- Instance feature flags (`/features`) are GitLab's internal gates — powerful and
  dangerous; only touch with explicit user intent.
- **GraphQL introspection over-reports on CE (verified live):** the introspected
  schema lists EE/Duo root fields (`duoSettings`, `aiChatAvailableModels`,
  `vulnerabilities`, ...), but executing them fails validation with
  "Field '...' doesn't exist on type 'Query'". Trust runtime errors, not the
  schema dump. Free-tier GraphQL that DOES work on CE (verified): `workItems`,
  `alertManagementAlerts`, `ciCatalogResources`, `achievements`,
  `dependencyProxySetting`, `mlModels`.
- GitLab Duo / AI features are entirely absent on CE at runtime: REST
  `/code_suggestions/*` and `/ai/duo_workflows/*` 404, all `ai*`/`duo*` GraphQL
  fields are rejected. Only the rate-limit knobs exist in settings. Needs a paid
  tier on an EE build — a CE build can't even accept a license.
- `GET /bulk_imports` (direct transfer) 404s until the admin setting
  `bulk_import_enabled` is turned on — a settings gate, not a tier gate.
  (Enabled on this instance 2026-07-15; endpoint verified live.)
- Container registry is live at `gitlab.example.com:5050` (verified: the
  `homelab-ansible` project hosts an `ansible-ci` image). Pages is enabled
  (per-project access levels; no custom domains configured).
- Rate limiting: no `RateLimit-*` headers observed on this instance (defaults
  off for authenticated admin), but 429s are possible if enabled later.
- **Delayed deletion (verified live):** `DELETE /projects/:id` only *marks* the
  project for deletion and GitLab renames it to `<path>-deletion_scheduled-<id>`.
  To destroy immediately, call DELETE again with
  `?permanently_remove=true&full_path=<the RENAMED full path, URL-encoded>` —
  using the original path 400s ("full_path is incorrect"). Restore before the
  purge date with `POST /projects/:id/restore`.

## Write safety model

Every mutating tool takes `confirm` and refuses without it. The gate covers:
non-GET `gitlab_rest`, GraphQL mutations, and every curated write action.
Reversible-proof pattern for verification: create throwaway → verify listed →
delete → verify gone (only with the user's go-ahead).
