---
description: Seed a project wiki with a standard page set (Home, Architecture, Runbook, ADRs)
argument-hint: <project> [--pages home,architecture,runbook,decisions]
---

Initialize a project wiki with a structured starting set of pages. Read
`references/projects-repo-mrs-issues.md`. Each page is one create call.

1. **Inspect current state** (read-only): `wikis(project, action="list")` — existing pages;
    don't overwrite. `get_project(project)` to confirm `wiki_enabled` (it's on by default).
2. **Plan the page set** (default: home, architecture, runbook, decisions):
    - **Home** — project overview, links, quickstart.
    - **Architecture** — system diagram, components, data flow, dependencies.
    - **Runbook** — operational procedures: deploy, rollback, debug, on-call.
    - **Decisions** — ADR (Architecture Decision Record) index.
    User can override via `--pages` (comma-separated).
3. **Generate content** for each page (templates — adapt per project):
    - Home: title, one-paragraph purpose, "Getting started" (clone, build, test), key links
      (issues, MRs, pipelines), contact.
    - Architecture: components list, diagram placeholder, data flow, external deps, scaling notes.
    - Runbook: deploy steps, common incidents + fixes, rollback, monitoring URLs, escalation.
    - Decisions: ADR template + index table (status, date, title, link).
4. **Confirm-plan**: list pages + their section structure. Get approval.
5. **Apply**: loop with `confirm=true`:
    `wikis(project, action="create", params={title: "...", content: "...", format: "markdown"},
    confirm=true)`.
6. **Verify**: `wikis(project, action="list")` + report the wiki URL and per-page web URLs.

Wiki pages are versioned git under the hood (the wiki is a separate repo); you can also
clone and edit locally. For a more structured docs site, consider GitLab Pages with a static
generator instead — but the wiki is zero-config and good enough for most teams.
