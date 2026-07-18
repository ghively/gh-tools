# GraphQL — endpoint, introspection, and when to use it over REST

GitLab exposes a GraphQL API alongside REST. It's **versionless** (additive, backward-
compatible — no `/v4`-style versioning) and, on GitLab 19.x, large (the existing plugin's
`gitlab_graphql` tool notes ~160 queries / ~622 mutations). Verified against docs.gitlab.com.

## Endpoint & tooling
- **Endpoint**: `POST https://<instance>/api/graphql` (this plugin: `gitlab_graphql(query, variables)`).
- **Auth**: same tokens as REST (PAT / project / group access token / OAuth) — `read_api` scope for
  queries, `api` for mutations.
- **Interactive explorer** (self-managed too): `https://<instance>/-/graphql-explorer` (GraphiQL).
- **Introspection** is fully supported — this is the **most reliable live schema-discovery path**
  (more exact than the static REST OpenAPI file, since it reflects the deployed version + edition).
  Enumerate roots live:
  ```graphql
  { __schema { queryType { fields { name } } mutationType { fields { name } } } }
  ```

## Limits & the big gotcha
- Query complexity ≤ 200 (unauth) / 250 (auth); max query size 10,000 chars; 30s timeout; blob
  data capped ~20 MB.
- **Authorization asymmetry (design gotcha):** an unauthorized *query field* silently returns
  **`null`** (no error) — so `null` can mean "doesn't exist," "you can't see it," **or** "EE-gated
  resolver with no license." Unauthorized *mutations* return explicit `errors[]` entries. Never infer
  "absent" from a null field without checking permissions/tier.

## When GraphQL beats REST
- **Deep nested, cross-entity reads in one round trip**: e.g. project → mergeRequests → notes →
  awardEmoji, or group → projects → pipelines → jobs, in a single query instead of N REST calls.
- **CI Catalog** resources (`ciCatalogResource(s)`), **runner fleet** queries (admin, role-gated not
  tier-gated — usable on CE), `ciMinutesUsage` (GraphQL-only), compliance framework templates.
- **Vulnerability management** is migrating to GraphQL-only (still Ultimate-gated — doesn't unlock on CE).
- **AI/Duo** roots (`aiCatalogItem(s)`, `aiChatAvailableModels`, `aiConversationThreads`).
- Admin-namespaced reads (`adminGroups`/`adminProjects`/`adminMemberRole(s)`).

## When REST is better (or the only option)
- **Mutating "action" endpoints** and **binary/multipart** work are REST-first or REST-only:
  trigger a pipeline, upload a file/repository-file CRUD, publish a package, upload a wiki/release
  attachment, download artifacts. Use REST (`gitlab_rest`) for these.

## Representative query roots (partial — introspect for the exact, version-correct set)
`project`, `projects`, `group`, `groups`, `namespace`, `currentUser`, `issue(s)`, `mergeRequest`,
`milestone`, `iteration`, `runner(s)`, `snippets`, `topics`, `containerRepository`, `ciCatalogResource(s)`,
`ciApplicationSettings`, `currentLicense`, `metadata`, `vulnerabilities`/`instanceSecurityDashboard`
(Ultimate), `boardList`, `blobSearch`.

## Practical pattern
For anything ergonomic and common, use the curated REST tools. For a bespoke deep read, hand-write
a GraphQL query through `gitlab_graphql`. To discover what's available on *this* instance/version/
edition, run introspection first rather than trusting any static list.
