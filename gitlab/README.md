# gitlab — full control of a self-hosted GitLab CE instance

A Claude Code plugin for deep control of a self-hosted GitLab CE server.
Built and live-verified against **GitLab 19.0.0 CE** with an admin token,
following the deep-integration-builder methodology.

## What's inside

- **MCP server** (`mcp/gitlab_server.py`, self-provisioning via `uv run --script`):
  - Generic layer: `gitlab_rest` (any of ~170 REST domains), `gitlab_graphql`
    (160 queries / 622 mutations), `gitlab_status`, `gitlab_api_search`.
  - ~35 curated tools: projects, repo tree/files/commits/branches/tags, merge
    requests + review discussions, issues/labels/milestones, pipelines/jobs/
    variables/schedules/runners/lint, users/tokens/groups/members, admin settings
    + sidekiq + instance feature flags, search, releases, environments/deployments,
    deploy keys/tokens, webhooks, integrations, snippets, wikis, packages,
    container registry, todos/events.
  - `--selftest`: read-only live audit of every domain (93 checks).
- **Skill** `gitlab-control`: how to drive it, safety rules, the CE hard-limit map,
  full API enumeration, conventions/quirks, recipes for the long tail.
- **Commands**: `/gl-health`, `/gl-project`, `/gl-ci-debug`, `/gl-mr-review`.

## Setup

1. `cp config.example.json config.local.json` and fill in `base_url` + a PAT with
   `api` scope (admin user for instance-level control). The file is git-ignored.
2. Install via the marketplace at the repo root, then `/reload-plugins`.

## Safety model

Every write requires `confirm=true`, which the skill instructs Claude to set only
after your explicit approval. EE-only endpoints 404 on CE; the tools' error hints
and the skill's api-map keep that honest instead of calling it a bug.

## Verified state (2026-07-15)

- **Reads:** 84/84 CE-applicable domains verified live (93-check selftest) plus
  all 52 curated-tool call paths.
- **Writes:** proven end-to-end with a reversible live proof — created a throwaway
  project, committed + read back a file, opened/closed an issue, deleted and
  permanently purged it (instance restored to exact baseline). 13 further write
  families 400-probed (exist, params validated) without mutating.
- **CE hard limits (confirmed 404/rejected at runtime):** epics, iterations,
  merge trains, approval rules, audit events, `/license`, group hooks, group
  wikis, protected environments, and **all GitLab Duo/AI** (GraphQL introspection
  lists `ai*`/`duo*` fields on CE but runtime rejects them — a documented trap).
- **Free-tier features verified working:** secure files, ML model registry,
  work items, alert management, CI/CD catalog, achievements, group dependency
  proxy, terraform state/module registry, direct-transfer imports
  (`bulk_import_enabled` flipped on and verified).
- **Quirks captured:** delayed project deletion renames the project and
  `permanently_remove` needs the renamed path; repository-files endpoint requires
  `ref`; per-project code search works without Elasticsearch, global doesn't.
