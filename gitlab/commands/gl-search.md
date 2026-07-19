---
description: Structured search across the instance — code, issues, MRs, projects, users, milestones
argument-hint: <term> [--scope blobs|issues|merge_requests|projects|users|milestones] [--project ns/name] [--group ns]
---

Run a structured search and return ranked, deduplicated results across scopes. Read
`references/search-advanced.md`. Read-only.

1. **Determine the scope** (default: try all read-friendly scopes):
    - If `--scope` given, search only that one.
    - Else fan out to: `projects`, `issues`, `merge_requests`, `users`, `milestones`
      (and `blobs` if `--project` is given — global code search needs ES, not configured).
2. **Run the searches** (parallel where possible):
    ```
    search_gitlab(term=<term>, scope=<each-scope>, project=<if-given>, group=<if-given>, limit=20)
    ```
3. **For code hits (blobs)**: enrich each hit with `read_file(project, file_path, ref)` context
    if the user wants surrounding lines (offer this; don't auto-fetch for large result sets).
4. **For issue/MR hits**: include `state`, `web_url`, `labels` in the summary so the user can
    triage at a glance.
5. **Deduplicate**: the same item may appear in multiple scopes (e.g. a project name matches
    both `projects` and a repo path in `blobs`). Dedup by `web_url` / global id.
6. **Report**: grouped by scope, ranked by relevance (GitLab's order). For code hits, show
    `filename:startline` + the matching line. For issues/MRs, show `!iid`/`#iid` + title +
    state + web_url. For projects, name + description + web_url. For users, username + name.

**Quirks to honor**: `scope="blobs"` without `--project` returns a 400 on this CE instance
(needs Elasticsearch). `scope="commits"`/`"notes"`/`"wiki_blobs"` also need ES. If the user
asks for one of these globally, explain and fall back to per-project (or skip with a note).

For "search the entire instance's code": enumerate projects via `list_projects` and loop
`search_gitlab(scope="blobs", project=..., term=...)` per project — the only way on CE
without ES.
