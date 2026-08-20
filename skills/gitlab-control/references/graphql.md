# GraphQL — endpoint, introspection, when to use it, and worked examples

GitLab's GraphQL API sits alongside REST. It is **versionless** (additive,
backward-compatible — no `/v4`), and on 19.x it is large: **160 root queries**
and **622 mutations** (from live introspection on this instance). This file is
the practical guide: when to reach for it, the gotchas that bite, and verified
query/mutation examples you can copy and adapt.

## Endpoint & tooling

- **Endpoint**: `POST https://<instance>/api/graphql`. Here: `gitlab_graphql(query, variables, confirm)`.
- **Auth**: same tokens as REST (PAT / project / group access token / OAuth /
  CI `CI_JOB_TOKEN`). `read_api` for queries, `api` for mutations.
- **Interactive explorer** (self-managed too): `https://<instance>/-/graphql-explorer`
  (GraphiQL). Good for building a query interactively before pasting it into a tool call.
- **MCP tool**: `gitlab_graphql` runs queries freely; **mutations require
  `confirm=true`** exactly like REST writes.

## Limits & the big gotchas

- **Complexity:** ≤ 200 unauthenticated / 250 authenticated. Over-complex →
  `errors[].message: "Query complexity exceeds..."` → trim fields or paginate.
- **Max query size** 10,000 characters; **30s** timeout; blob data capped ~20 MB.
- **List fields are cursor-paginated** (`first`/`after`/`before`/`last` + a
  `pageInfo { hasNextPage endCursor }` and `nodes`/`edges`). Default page size is
  100. Use `first: 100, after: "<cursor>"` to walk.
- **The authorization-asymmetry gotcha (critical):** an unauthorized *query
  field* silently returns **`null`** — no error entry. So `null` can mean
  *"doesn't exist,"* *"you can't see it,"* **or** *"EE resolver with no license."*
  Unauthorized *mutations* DO return explicit `errors[]`. **Never infer
  "absent" from a null field.**

### Worked example of the null gotcha (run live on this instance)

```
query { project(fullPath: "homelab/gh-tools") { name webUrl } }
```
returns
```json
{ "data": { "project": null } }
```
Three indistinguishable causes: the path doesn't exist, the caller can't see
it, or (hypothetically here) it's resolver-gated. On CE the same pattern fires
for EE-only resolvers — `query { epic(...) { title } }` returns `null` on CE
even when handed a real id. Always pair a suspicious null with a REST call
(`get_project`) or a permission check before concluding "not found."

## Introspection — the version-exact discovery path

Introspection reflects the **deployed** version + edition + license state, so
it's more truthful than any static OpenAPI file. Use it whenever you're unsure a
field exists on this instance.

### List all root queries and mutations
```graphql
query {
  __schema {
    queryType    { fields { name } }
    mutationType { fields { name } }
  }
}
```
(The api-map.md reference contains the full enumerated list for 19.x.)

### Inspect a single type's fields + arguments
```graphql
query {
  __type(name: "Project") {
    fields {
      name
      args { name type { name kind ofType { name kind } } }
      type { name kind ofType { name kind } }
    }
  }
}
```

### Find every input field a mutation needs
```graphql
query {
  __type(name: "MergeRequestCreateInput") {
    inputFields {
      name
      type { name kind ofType { name kind } }
      defaultValue
    }
  }
}
```
Use this *before* writing a mutation — argument names change between versions,
and introspection is the source of truth.

## When GraphQL beats REST

- **Deep nested reads in one round trip.** Project → mergeRequests → notes →
  awardEmoji. Group → projects → pipelines → jobs. REST would take N+1 calls.
- **Cursor pagination over huge collections** (keyset-style, consistent).
- **Fields that don't exist in REST at all** on this version: `ciMinutesUsage`,
  `runnerUsage`, `runnerUsageByProject`, `workItems` (CE-working replacement for
  the Premium `issues`-with-epics surface), `ciCatalogResource(s)`,
  `complianceFrameworkTemplates`, `memberRolePermissions` (Ultimate — gated).
- **Admin-namespaced reads**: `adminGroups`, `adminProjects`, `adminMemberRole(s)`.
- **CI Catalog** (`ciCatalogResource(s)`) — the component marketplace.
- **Runner fleet** reads (`runner`, `runners`, `runnerPlatforms`, `runnerSetup`)
  — admin/role-gated but NOT tier-gated, so usable on CE.
- **Work items** — the modern issue/task layer. CE-working. Many of the
  Premium "epics"-style operations land here first.

## When REST is better (or the only option)

- **Mutating "action" endpoints**: trigger a pipeline, run a schedule, retry/
  cancel a job, merge an MR, play a manual job.
- **Binary/multipart**: repository-file CRUD (with content), package upload,
  release attachment upload, wiki attachment upload, artifact upload, avatar
  upload, snippet file create.
- **Downloads**: artifact download, repository archive, raw blob, export tarball.
- **Anything where the curated REST tool already exists** — it handles edge
  cases (URL-encoding paths, ID-vs-IID, pagination headers) for you.

## Verified query examples (tested on this instance)

### 1. Self + group tree in one call
```graphql
query {
  currentUser { id username name }
  groups(first: 5) {
    nodes { id name fullPath
      projects(first: 2) { nodes { name } }
    }
  }
}
```
Returns real group + project data. Good smoke-test query.

### 2. Deep project read — settings + recent MRs + pipeline counts
```graphql
query {
  project(fullPath: "GROUP/PROJECT") {
    name fullPath webUrl
    visibility defaultBranch
    statistics { commitCount storageSize repositorySize }
    mergeRequests(state: merged, first: 5) {
      nodes { iid title state mergedAt
        author { username }
        labels(first: 5) { nodes { name } }
      }
    }
  }
}
```
Replaces ~4 REST calls with one. **Confirm the path exists first** with
`get_project` if you're not sure — remember the null gotcha.

### 3. Group → projects → recent pipelines → failing jobs (3 levels deep)
```graphql
query {
  group(fullPath: "GROUP") {
    projects(first: 10) {
      nodes {
        name
        pipelines(status: FAILED, first: 3) {
          nodes {
            id status finishedAt
            jobs(status: FAILED) {
              nodes { name stage allowFailure traceHtml # large
              }
            }
          }
        }
      }
    }
  }
}
```
This is the classic GraphQL-over-REST win — a fleet status read in one query.
(Trim `trace` from production queries — large.)

### 4. Cursor pagination across all issues in a project
```graphql
query($cursor: String) {
  project(fullPath: "GROUP/PROJECT") {
    issues(first: 100, after: $cursor) {
      nodes { iid title state }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```
Loop with `variables: {"cursor": "<endCursor>"}` until `hasNextPage` is false.
Consistent across deletions (unlike REST offset pagination).

### 5. Work items (CE-working — the modern issue surface)
```graphql
query {
  project(fullPath: "GROUP/PROJECT") {
    workItems(first: 20) {
      nodes {
        id iid workItemType { name }
        title state
        assignees(first: 3) { nodes { username } }
        widgets { type ... on WorkItemWidgetDevelopment { ... } }
      }
    }
  }
}
```
Work items are Free and unify issues/tasks/incidents/test-cases/requirements.
Use these where you previously needed epics (Premium) — limited but real.

### 6. CI Catalog resources (Free, reusable components)
```graphql
query {
  ciCatalogResources(first: 20) {
    nodes {
      name description
      webPath
      versions(first: 3) { nodes { tagName createdAt } }
    }
  }
}
```
Pair with the `include: - component: gitlab.example.com/<webPath>@<version>` CI
syntax. See `references/cicd.md` for the include syntax.

### 7. Runner fleet (admin — role-gated, not tier-gated)
```graphql
query {
  runners(first: 50, paused: false) {
    nodes {
      id description runnerType active paused locked
      tagList
      version
      architecture
      platform
      contactStatus
      contactedAt
      projectCount
    }
  }
}
```
`contactStatus: "never_contacted"` or stale `contactedAt` = stale/offline
runner — flag in `/gl-audit` and `/gl-runner-manage`.

### 8. Introspect one type's args precisely
```graphql
query {
  __type(name: "MergeRequestSetReviewersInput") {
    inputFields {
      name
      type { name kind ofType { name kind } }
      defaultValue
    }
  }
}
```
Run this **before** composing any mutation — argument shapes drift between
GitLab versions, and this is the exact deployed contract.

## Mutation examples (require `confirm=true`)

### M1. Set MR reviewers
```graphql
mutation($input: MergeRequestSetReviewersInput!) {
  mergeRequestSetReviewers(input: $input) {
    mergeRequest { iid reviewers(first: 10) { nodes { username } } }
    errors
  }
}
```
with `variables: {"input": {"projectId": "gid://gitlab/Project/N",
"iid": 42, "reviewerUsernames": ["alice","bob"]}}`. Always read `errors[]` —
empty = success.

### M2. Create an issue with work-item features (Free, modern path)
```graphql
mutation($input: WorkItemCreateInput!) {
  workItemCreate(input: $input) {
    workItem { id iid title state }
    errors
  }
}
```

### M3. Toggle an award emoji (thumbs-up an issue)
```graphql
mutation($input: AwardEmojiToggleInput!) {
  awardEmojiToggle(input: $input) { errors }
}
```

### M4. Add a note to a noteable
```graphql
mutation($input: CreateNoteInput!) {
  createNote(input: $input) {
    note { id body }
    errors
  }
}
```

**Always** echo `errors` back from mutations — empty array = success. Non-empty
= read the messages, fix, retry. Mutation calls through `gitlab_graphql` require
`confirm=true`; state the change before calling.

## Patterns to internalize

1. **Connection shape**: every list field returns `{ nodes: [...], pageInfo:
   { hasNextPage, endCursor, hasPreviousPage, startCursor }, count }`. Use
   `first: N` + `after: $cursor` to page forward.
2. **Global IDs** (`gid://gitlab/Project/4`) — required as inputs to mutations.
   The REST numeric ID goes inside the `gid://gitlab/<Type>/<id>` envelope.
3. **Fragments & `... on Type`** — use inline fragments to pull widget-specific
   fields on union/interface types (e.g. `WorkItemWidget`).
4. **Aliases** to fetch the same field with different args in one query:
   `open: issues(state: opened) { ... } closed: issues(state: closed) { ... }`.
5. **Complexity budget** — deep nesting + large `first:` burns it fast. Prefer
   `first: 20-100` and paginate over huge sets.
6. **Don't trust introspection for tier** — EE/Duo fields *appear* in the
   schema on CE but reject at runtime. Verify any `ai*`, `duo*`, `epic`,
   `iteration`, `vulnerabilities`, `auditEvent*` field against
   `references/ce-vs-ee-and-security.md` before relying on it.

## Practical workflow in this plugin

1. For anything ergonomic and common, use the curated REST tools first.
2. For a deep bespoke read, hand-write a GraphQL query via `gitlab_graphql`.
3. To discover argument shapes for a specific mutation, run a `__type` query first.
4. To discover *what exists* on this instance/version/edition, introspect —
   don't trust any static list, including this file's (it was accurate at the
   time of writing; GitLab ships 2-3 releases a year).
