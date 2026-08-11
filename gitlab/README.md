# gitlab — full control of a self-hosted GitLab CE instance

A Claude Code plugin for deep control of a self-hosted GitLab CE server.
Built and live-verified against **GitLab 19.0.0 CE** with an admin token,
following the deep-integration-builder methodology.

## What's inside

- **MCP server** (`mcp/gitlab_server.py`, self-provisioning via `uv run --script`):
  - Generic layer: `gitlab_rest` (any of 177 REST resource groups), `gitlab_graphql`
    (160 queries / 622 mutations), `gitlab_status`, `gitlab_api_search`.
  - **75 curated tools** (79 total with the generic layer): projects, repo tree/files/commits/branches/tags/extras,
    protected refs+environments, merge requests + approvals + review discussions + draft notes
    + suggestions, issues/boards/labels/milestones/links/time tracking, pipelines/jobs/artifacts/
    triggers/schedules/variables/runners/lint/resource groups/secure files, feature flags,
    environments/deployments/freeze periods, releases, Pages + custom domains, users/tokens,
    project&group access tokens, groups/members/invitations, badges, packages/registry,
    webhooks/integrations, snippets/wikis, **ML model registry + MLflow experiments**, **CI/CD
    catalog**, GitLab's built-in file templates, project import/export, bulk imports, admin
    settings + sidekiq + system hooks, search, todos/events, **secure files, terraform state,
    resource groups, award emoji, notes, markdown render, remote mirrors, notifications, freeze
    periods, time tracking, issue links, draft notes, cluster agents, dependency proxy,
    suggestions, custom attributes, resource events, uploads, error tracking**.
  - `--selftest`: read-only live audit of every domain (113 checks).
- **Skill** `gitlab-control` with **19 references** (2,700+ lines): how to drive it,
  safety, the full API map, conventions, CI/CD (deep), projects/MRs/issues, admin &
  self-hosting (deep), honest CE-vs-EE gating, GraphQL with verified query/mutation examples,
  the templates catalog, workflow playbooks for all 33 commands, the AI/model-registry story,
  troubleshooting decision tree, runners deep-guide, migrations & imports guide, members &
  access deep-guide, webhooks deep-guide, packages & registry deep-guide, work items, advanced
  search.
- **Bulletproof templates** (`templates/`): **22 `.gitlab-ci.yml` pipelines** **each
  live-validated against this instance's CI Lint API** (`valid:true` on 19.0.0) —
  node/python/go/generic/docker/pages/terraform/release-on-tag/security-ce/mr-only
  + java-maven/rust/ruby/dotnet/monorepo/pre-commit/helm + php/cpp/scala/android/ios — plus
  project scaffolding (issue/MR templates, CODEOWNERS, .editorconfig, CONTRIBUTING, SECURITY.md,
  renovate.json) and **8 config presets** (protected-branch/tag rulesets, hardened project/group
  settings, webhook, CI variables, Slack + Jira integrations).
- **33 workflow commands**: all v0.4.0 commands plus `/gl-member-sync`, `/gl-label-sync`,
  `/gl-milestone-plan`, `/gl-mirror-setup`, `/gl-cluster-agent`, `/gl-time-report`,
  `/gl-storage-audit`, `/gl-wiki-seed`, `/gl-apply-suggestions`, `/gl-search`.

## Setup

1. `cp config.example.json config.local.json` and fill in `base_url` + a PAT with
   `api` scope (admin user for instance-level control). The file is git-ignored.
2. Install via the marketplace at the repo root, then `/reload-plugins`.

## Safety model

Every write requires `confirm=true`, which the skill instructs Claude to set only
after your explicit approval. EE-only endpoints 404 on CE; the tools' error hints
and the skill's api-map keep that honest instead of calling it a bug.

## Verified state (2026-07-19)

- **Reads:** 103/103 selftest checks (94 CE-applicable domains + 10 new v0.4.0
  tool probes verified live), plus all 69 curated-tool call paths.
- **Writes:** proven end-to-end with a reversible live proof — created a throwaway
  project, committed + read back a file, opened/closed an issue, deleted and
  permanently purged it (instance restored to exact baseline). Further write
  families 400-probed (exist, params validated) without mutating.
- **CI templates:** all 17 `.gitlab-ci.yml` templates return `valid:true` from the
  live CI Lint API on 19.0.0.
- **CE hard limits (confirmed 404/rejected at runtime):** epics, iterations,
  merge trains, approval rules, audit events, `/license`, group hooks, group
  wikis, protected environments, and **all GitLab Duo/AI** (GraphQL introspection
  lists `ai*`/`duo*` fields on CE but runtime rejects them — a documented trap).
- **Free-tier features verified working:** secure files, ML model registry,
  work items, alert management, CI/CD catalog, achievements, group dependency
  proxy, terraform state/module registry, service desk (needs incoming-email
  config), direct-transfer imports (`bulk_import_enabled` flipped on and verified),
  resource groups, award emoji, freeze periods, remote mirrors.
- **Quirks captured:** delayed project deletion renames the project and
  `permanently_remove` needs the renamed path; repository-files endpoint requires
  `ref`; per-project code search works without Elasticsearch, global doesn't;
  terraform states aren't REST-listable (terraform CLI protocol).
