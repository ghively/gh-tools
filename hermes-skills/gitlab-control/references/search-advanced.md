# Search — scopes, code search, and the Elasticsearch gate

GitLab's search has two tiers: **basic** (database-backed, works everywhere) and **advanced**
(Elasticsearch-backed, Premium-only on the instance but with one important CE carve-out for
per-project code search). Knowing which tier a scope needs determines whether your call
succeeds or 400s.

## The scope table

| Scope | What it finds | Tier on CE | Notes |
|---|---|---|---|
| `projects` | project name / description | basic | works everywhere |
| `issues` | issue title / description | basic | works everywhere |
| `merge_requests` | MR title / description | basic | works everywhere |
| `milestones` | milestone title | basic | works everywhere |
| `users` | username / name | basic | works everywhere |
| `snippet_titles` | snippet title / description | basic | works everywhere |
| **`blobs`** (code search) | file contents matching | **basic for project-scoped; advanced for global** | the carve-out below |
| `commits` | commit messages | advanced (project-scoped: basic) | limited without ES |
| `wiki_blobs` | wiki page content | advanced | needs ES |
| `notes` | comments on issues/MRs/snippets | advanced | needs ES |

**The CE carve-out for code search:** `search_gitlab(scope="blobs", project="ns/name")`
works **without Elasticsearch** on CE — GitLab falls back to a database/Git-backed search
for the single project. **Global** code search (`scope="blobs"` without `project=`) returns
a 400 error ("Elasticsearch is not enabled") on a CE instance without ES configured.

## Using the search tool

```
search_gitlab(term="TODO", scope="blobs", project="gregory/myproj", limit=20)
search_gitlab(term="auth", scope="commits", project="gregory/myproj")
search_gitlab(term="deploy", scope="projects")                      # global, basic
search_gitlab(term="incident", scope="issues", group="gregory")    # group-scoped
```

Params: `term` (required), `scope` (default `projects`), one of `project` / `group` (for
scoping; omit for instance-wide basic search), `limit` (default 20, max 100).

## Code search tips (per-project, the working CE path)

- **Regex supported**: `term="function\\s+\\w+\\("` finds function definitions.
- **File-path filter**: append to the API call via `gitlab_rest("GET",
  "/projects/:id/search", params={scope:"blobs", search:"TODO", filepath:"*.py"})` —
  the curated tool doesn't expose `filepath`, but the underlying endpoint does.
- **Case sensitivity**: code search is case-insensitive by default on this version.
- **Result shape**: each blob hit has `filename`, `basename`, `ref`, `startline`,
  `data` (the matching lines), `project_id`. Use `startline` + `filename` to jump to the
  hit in `read_file` or the web URL.

## When to use search vs other tools

- **Find a string in code** → `search_gitlab(scope="blobs", project=...)`.
- **Find a project by name** → `search_gitlab(scope="projects")` or `list_projects(search=...)`.
- **Find an issue/MR by content** → `search_gitlab(scope="issues"|"merge_requests")`.
- **Find a user** → `search_gitlab(scope="users")` or `users(action="list", search=...)`.
- **Enumerate everything matching** → GraphQL `projects(search:...)` with nested
  `mergeRequests`/`pipelines` for cross-entity reads in one query.

## Global code search on CE (the workaround)

If you need to search code across the whole instance and don't have ES:

1. Enumerate projects: `list_projects(...)` or GraphQL `projects { nodes { fullPath } }`.
2. For each, `search_gitlab(scope="blobs", project=<path>, term="...")`.
3. Aggregate. Slow but works.

This is what `/gl-search` (the workflow) does — it's the only way to do instance-wide code
search on Free.

## Elasticsearch (Premium) — what unlocks

With ES configured (Premium), global `blobs`, `commits`, `wiki_blobs`, `notes` all work
instance-wide in one fast call. Without it, you're limited to per-project code search and
the basic scopes.

You can tell whether ES is configured by trying `search_gitlab(scope="blobs", term="x")`
(no project) — a 400 with "Elasticsearch is not enabled" means no ES; a 200 means ES is
configured (Premium instance).

## Advanced search filters (when ES is configured)

- `search_gitlab` passes through to `GET /search?scope=blobs&search=...` — the API supports
  additional filters: `repository_ref` (limit to a branch), `filepath` (filename regex),
  `extension` (file extension). These work only with ES.
- For per-project code search (no ES), the same filters work but with smaller result sets.

## Common pitfalls

- **`scope="blobs"` without `project` 400s on CE without ES.** Always pass `project=` for
  code search on Free.
- **Pagination**: search returns max 20 by default; pass `limit=100` and follow
  `X-Next-Page` for more.
- **Special chars**: regex special chars in `term` need escaping. The API interprets `term`
  as a regex for blobs, as plain text for other scopes.
- **Case**: username/email search is case-insensitive; blob search is case-insensitive on
  recent versions.
- **Permission**: search respects access — you won't see results from private projects you
  can't read.
