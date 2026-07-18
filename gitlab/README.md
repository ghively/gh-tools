# gitlab — full control of a self-hosted GitLab CE instance

A Claude Code plugin for deep control of a self-hosted GitLab CE server.
Built and live-verified against **GitLab 19.0.0 CE** with an admin token,
following the deep-integration-builder methodology.

## What's inside

- **MCP server** (`mcp/gitlab_server.py`, self-provisioning via `uv run --script`):
  - Generic layer: `gitlab_rest` (any of 177 REST resource groups), `gitlab_graphql`
    (160 queries / 622 mutations), `gitlab_status`, `gitlab_api_search`.
  - **59 curated tools**: projects, repo tree/files/commits/branches/tags/extras,
    protected refs+environments, merge requests + approvals + review discussions,
    issues/boards/labels/milestones, pipelines/jobs/artifacts/triggers/schedules/
    variables/runners/lint, feature flags, environments/deployments, releases,
    Pages + custom domains, users/tokens, project&group access tokens, groups/members/
    invitations, badges, packages/registry, webhooks/integrations, snippets/wikis,
    **ML model registry + MLflow experiments**, **CI/CD catalog**, GitLab's built-in
    file templates, project import/export, admin settings + sidekiq + system hooks,
    search, todos/events.
  - `--selftest`: read-only live audit of every domain.
- **Skill** `gitlab-control` with **11 references**: how to drive it, safety, the full
  API map, conventions, CI/CD, projects/MRs/issues, admin & self-hosting (incl. SSH-only
  hard limits), honest CE-vs-EE gating, GraphQL, the templates catalog, workflow playbooks,
  and the AI/model-registry story.
- **Bulletproof templates** (`templates/`): 10 `.gitlab-ci.yml` pipelines **each
  live-validated against this instance's CI Lint API** (`valid:true` on 19.0.0), project
  scaffolding (issue/MR templates, CODEOWNERS, .editorconfig, CONTRIBUTING), and config
  presets (protected-branch ruleset, hardened project settings, webhook, CI variables).
- **13 workflow commands**: `/gl-onboard`, `/gl-ci-bootstrap`, `/gl-audit`, `/gl-cleanup`,
  `/gl-user-offboard`, `/gl-triage`, `/gl-release`, `/gl-mr-review`, `/gl-security-scan`,
  `/gl-ci-debug`, `/gl-model-registry`, `/gl-project`, `/gl-health`.

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
