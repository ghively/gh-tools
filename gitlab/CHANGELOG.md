# Changelog

All notable changes to the **gitlab** gh-tools plugin.
Versioning follows the plugin's own line (independent of the gh-tools marketplace).

## [0.5.1] — 2026-08-11

Maintenance release: offline review fixes, no new tools or endpoints.

### Fixed

- **`mcp/gitlab_server.py`** — removed a UTF-8 BOM that preceded the `#!` shebang
  (broke direct `./gitlab_server.py` execution; `uv run --script` was unaffected).
- **`mcp/gitlab_server.py`** — repaired cp1252 mojibake (double-encoded em dashes,
  arrows, etc.) in 38 docstring/comment lines.
- **`mcp/gitlab_server.py`** — deduplicated `API_CATALOG` keys (`draft notes` and
  `error tracking` were each defined twice; the first definitions were dead code).
- **`mcp/gitlab_server.py`** — network-level failures (DNS, refused connection,
  TLS, timeout) in `rest()`, `gql()`, job-log and secure-file downloads now return
  a structured `{error, kind, message, hint}` dict instead of raising through the
  tool, so timeouts and unreachable instances are reported honestly.
- **Docs** — corrected the curated-tool count: 75 curated + 4 generic = 79 total
  (plugin.json, README.md, SKILL.md previously called all 79 "curated").

### Added

- **`mcp/_smoketest.py`** — read-only smoke test (modeled on radarr-control's):
  verifies confirm-gating offline with zero network calls, then runs 11 read-only
  curated-tool probes against the configured instance; exits 0 with a SKIP notice
  when no config.local.json / GITLAB_URL+GITLAB_TOKEN is present.

### Verification (this release; offline environment — no live instance, no uv/mcp)

- `python3 -m py_compile` clean on both .py files; `python3 -m json.tool` clean on
  all 12 JSON files; AST audit confirms 79 `@mcp.tool` functions and no remaining
  duplicate catalog keys. Live selftest/smoke test NOT re-run (needs the instance).

## [0.5.0] — 2026-07-19

The "deepen everything" release. Tool count 69 → 79, references 14 → 19, workflow commands
23 → 33, CI templates 17 → 22, config presets 4 → 8. Every existing reference that was thin got
expanded substantially.

### Added — curated MCP tools (10, round 2)

Surfacing more verified-working CE features:

- **`time_tracking`** — estimates + spent time on issues & MRs (add/reset/set).
- **`issue_links`** — relate issues (blocks / is blocked by / relates to), cross-project.
- **`draft_notes`** — MR draft review notes (list/get/create/update/delete/bulk-publish).
- **`cluster_agents`** — GitLab Kubernetes Agents (list/get/create/delete/tokens/create_token).
- **`dependency_proxy`** — group Docker proxy settings (GraphQL) + manifests + cache purge.
- **`suggestions`** — apply inline code-review suggestions (single or batch_apply).
- **`custom_attributes`** — admin key/value metadata on users/projects/groups.
- **`resource_events`** — label/state/milestone event audit trail on issues & MRs.
- **`uploads`** — project file attachments (list/get/delete).
- **`error_tracking`** — project error-tracking (Sentry-like) settings + client keys.

### Added — skill references (5 new, 3 expanded)

- **`members-access-deep.md`** (new) — access levels, inherited vs direct vs shared group
  membership, the Owner-orphaning trap, audit patterns, SSH/deploy keys, CE-vs-Premium role gaps.
- **`webhooks-deep.md`** (new) — every event payload shape, X-Gitlab-Token signing, retry
  behavior, SSL verification, the `allow_local_requests` SSRF control, system hooks, debugging.
- **`packages-registry-deep.md`** (new) — every package format (npm/pypi/maven/generic/helm/
  conan/nuget/debian/composer/conan/rubygems/terraform-modules), push/pull patterns, cleanup
  policies, container registry, dependency proxy integration.
- **`work-items.md`** (new) — the modern issue/task/incident/test-case surface, work item types,
  widgets, hierarchies as the CE epic replacement, GraphQL-first usage patterns.
- **`search-advanced.md`** (new) — search scopes, the Elasticsearch gate, per-project code
  search on CE vs global-needs-ES, advanced filters, the instance-wide workaround.
- **`cicd.md`** (expanded 92 → 200+ lines) — added resource groups, DAG/needs/dependencies/
  parallel:matrix deep dive, rules complexity, manual/delayed/retry/timeout, environments with
  deployment jobs, secure files in CI, include patterns, the full CE-vs-EE CI/CD table.
- **`admin-and-self-hosting.md`** (expanded 70 → 180+ lines) — admin mode, user lifecycle state
  machine, broadcast messages, instance feature flags, topics, OAuth applications, 2FA
  enforcement, email config, the SSH handoff pattern.
- **`ai-and-model-registry.md`** (expanded 54 → 130+ lines) — full ML model lifecycle, MLflow
  tracking setup + code, experiment/candidate model, CI Catalog component authoring, what Duo
  would unlock if a license were applied.

### Added — workflow commands (10, round 2)

- **`/gl-member-sync`** — baseline membership across projects/groups (orphan-safe).
- **`/gl-label-sync`** — baseline label taxonomy across targets.
- **`/gl-milestone-plan`** — release-cadence milestone generation.
- **`/gl-mirror-setup`** — pull/push remote mirrors.
- **`/gl-cluster-agent`** — Kubernetes agent bootstrap (token relayed).
- **`/gl-time-report`** — time-tracking aggregate by assignee/milestone/state.
- **`/gl-storage-audit`** — storage consumption ranking + cleanup targets.
- **`/gl-wiki-seed`** — structured wiki page set (Home/Architecture/Runbook/Decisions).
- **`/gl-apply-suggestions`** — batch-apply MR review suggestions.
- **`/gl-search`** — structured multi-scope instance search.

### Added — CI templates (5, all `valid:true` on 19.0.0)

- **`php.yml`** — composer install + phpcs (advisory) + phpunit (JUnit).
- **`cpp.yml`** — cmake configure + build + ctest (JUnit), ccache; `needs:` DAG.
- **`scala.yml`** — sbt scalafmt + test + assembly.
- **`android.yml`** — gradle lintDebug + testDebugUnitTest + assembleRelease (APK).
- **`ios.yml`** — Fastlane test + build (macOS runner tags).

### Added — config presets (4)

- **`tag-protection-standard.json`** — release-tag ruleset (`v*` → maintainers).
- **`group-settings-hardened.json`** — 2FA, restricted subgroup/project creation, default-branch protection.
- **`slack-integration.json`** — Slack service with MR + pipeline events.
- **`jira-integration.json`** — Jira service linking MRs to issues by project key.

### Changed

- **SKILL.md** — curated tools list updated (69 → 79, with v0.5.0 call-out); references list
  updated (14 → 19); instance facts refreshed.
- **README.md** — full rewrite of counts and capability lists.
- **plugin.json** + **marketplace.json** — version 0.4.0 → 0.5.0; description updated.
- **`templates.md`** — catalog updated with 5 new CI templates + 4 new config presets.
- **`workflows.md`** — roster updated (23 → 33 commands) with per-command playbooks for the
  10 new commands.
- **`common-tasks.md`** — added a "now-curated" mapping at the top cross-referencing the new
  tools against the raw REST recipes below.

### Verification (this release)

- **Selftest:** 113 checks, 9 failures (all expected EE-only 404s). All 20 v0.4.0+v0.5.0
  domain probes pass.
- **CI templates:** all 22 `.gitlab-ci.yml` files return `valid:true` from the live CI Lint API
  on 19.0.0 (5 new this release + 17 re-confirmed from v0.4.0).
- **MCP server syntax:** clean on the final 2,766-line file.

## [0.4.0] — 2026-07-19

The "broaden + deepen" release. Every dimension of the plugin grew, all verified
live against the same GitLab 19.0.0 CE instance. Tool count 59 → 69, references
11 → 14, workflow commands 13 → 23, CI templates 10 → 17.

### Added — curated MCP tools (10)

Surfacing verified-working CE features that previously required raw `gitlab_rest`:

- **`secure_files`** — CI/CD file credentials (kubeconfig, .npmrc, signing keys):
  list / get / download (base64) / delete. Upload is multipart (shell/UI).
- **`terraform_state`** — state registry admin: get / delete / lock / unlock.
  `list` returns an honest "not REST-listable" message (terraform CLI protocol).
- **`bulk_imports`** — direct-transfer instance-to-instance migration:
  list / get / entities / create.
- **`resource_groups`** — CI/CD concurrency control: list / get / upcoming_jobs / update.
- **`award_emoji`** — reactions on issues / merge_requests / snippets:
  list / get / add / remove.
- **`notes`** — standalone comments on issues / merge_requests / snippets:
  list / get / add / update / delete. (MR threads stay on `mr_discussions`.)
- **`markdown`** — GitLab-Flavored Markdown → HTML render (side-effect-free, no confirm).
- **`remote_mirrors`** — pull / push mirror config: list / create / update / delete / sync.
- **`notifications`** — user / group / project notification settings: get / update.
- **`freeze_periods`** — deployment freeze windows: list / get / create / update / delete.

### Added — skill references (3 new, 2 expanded)

- **`troubleshooting.md`** (new) — the failure-mode decision tree: HTTP status →
  cause → test. IID-vs-ID confusion, pagination, delayed-deletion/requires-ref/
  never-contacted-runner quirks, webhook delivery failures, GraphQL null/complexity
  errors, MCP-server failures, honest-reporting checklist.
- **`runners-deep.md`** (new) — runner types, the v16+ `POST /user/runners` flow
  (replaces the deprecated registration token), tag matching, fleet-health signals,
  executor trade-offs, security boundaries, the `/gl-runner-manage` playbook.
- **`migrations-imports.md`** (new) — project/group export→download→import,
  direct-transfer `/bulk_imports`, foreign (GitHub/Bitbucket) import, pre-migration
  checklist, post-migration verification diff, the `/gl-backup` playbook, what each
  method does/doesn't preserve.
- **`ce-vs-ee-and-security.md`** (expanded 65 → 255 lines) — now the full
  EE-gating trap map: how to tell which tier, the three-causes-of-failure triage
  tree, categorized "works on Free" / "Premium-gated" / "Ultimate-gated" / "degraded
  on Free" tables, and the CE security-scanning recipe end-to-end.
- **`graphql.md`** (expanded 50 → 331 lines) — 8 verified query examples (self+groups,
  deep project read, group→projects→pipelines→jobs, cursor pagination, work items,
  CI catalog, runner fleet, introspection) and 4 mutation examples, plus a worked
  null-means-unauthorized example run live on this instance.
- **`workflows.md`** (rewritten 46 → ~150 lines) — full step-by-step playbook for
  every one of the 23 commands, grouped (read-only / setup / operate / diagnose /
  lifecycle), plus cross-cutting orchestration patterns and composed-workflow recipes.

### Added — workflow commands (10)

- **`/gl-token-rotate`** — sweep expiring PATs + project/group/deploy/trigger tokens;
  classify; propose rotate/revoke; relay each new secret immediately.
- **`/gl-backup`** — project/group export → poll → download → verify (import-and-diff).
- **`/gl-bulk-import`** — direct-transfer `/bulk_imports` from another GitLab, with
  per-entity status polling and verification.
- **`/gl-pages-deploy`** — Pages enable + custom domain + SSL + force-HTTPS.
- **`/gl-runner-manage`** — fleet inventory + health classification + tag-gap analysis
  + propose pause/delete/reset actions.
- **`/gl-branch-strategy`** — branch/tag protection + merge-gate + CE-basic approvals
  + CODEOWNERS, with explicit Premium-gap flags.
- **`/gl-variables-sync`** — apply a baseline CI-variables spec across projects /
  groups / environments with a confirm-list matrix.
- **`/gl-group-setup`** — bootstrap a group: create, policy, members (≥2 owners),
  labels, subgroups.
- **`/gl-secure-files`** — manage CI/CD secure files (list / add via shell / remove).
- **`/gl-boards-setup`** — issue boards with label / milestone / assignee lists.

### Added — CI templates (7, all `valid:true` on 19.0.0)

- **`java-maven.yml`** — Maven verify (JUnit) + package, repo cache per `pom.xml`.
- **`rust.yml`** — fmt (advisory) + clippy (strict) + test + release build, cargo cache.
- **`ruby.yml`** — bundle install + rubocop + rspec (JUnit).
- **`dotnet.yml`** — dotnet test (JUnit + Cobertura) + publish.
- **`monorepo.yml`** — parent pipeline → per-package child pipelines on path changes.
- **`pre-commit.yml`** — run all hooks from `.pre-commit-config.yaml`.
- **`helm.yml`** — `helm lint` + package `.tgz` for `charts/*`.

### Added — project scaffolding (6 files)

- `.gitlab/issue_templates/Bug.md` + `Feature.md` — pre-labeled, with severity +
  evidence + definition-of-done sections.
- `.gitlab/merge_request_templates/Default.md` — summary + changes + how-to-test +
  risk/rollback + checklist.
- `.editorconfig` — cross-editor consistency (PEP 8 / Go tabs / 2-space JS-YAML).
- `SECURITY.md` — vulnerability disclosure policy (private channel, scope, window).
- `renovate.json` — dependency-update bot (weekly schedule, patch auto-merge, vuln alerts).

### Changed

- **SKILL.md** — curated tools list updated (59 → 69, with v0.4.0 call-out);
  references list updated (11 → 14); instance facts refreshed (134 projects / 40
  groups / 8 users / 6 active as of 2026-07-19).
- **README.md** — full rewrite of the "What's inside" + "Verified state" sections
  to reflect the new counts and the additional verified-working CE features.
- **plugin.json** + **marketplace.json** — version 0.3.0 → 0.4.0; description updated.
- **`templates.md`** — catalog updated with the 7 new CI templates + 6 new
  scaffolding files.

### Verification (this release)

- **Selftest:** 103 checks, 9 failures (all expected EE-only 404s — epics, iterations,
  merge_trains, audit_events, license, group hooks, group wikis, protected
  environments, error-tracking). The 10 new v0.4.0 domain probes all pass.
- **CI templates:** all 17 `.gitlab-ci.yml` files return `valid:true` from the live
  CI Lint API on 19.0.0 (7 new this release + 10 re-confirmed).
- **MCP server syntax:** `python3 -c "import ast; ast.parse(...)"` clean on the
  final 2,490-line file.
- **Live probes:** every new tool's read path exercised against a real project
  (`gregory/archive/hermes-backup`) — endpoints confirmed alive.

## [0.3.0] — 2026-07-15

- Added curated tools: `model_registry`, `ci_catalog`, `templates`.
- Added references: `ai-and-model-registry.md`.
- Enabled + verified `bulk_import_enabled` (direct-transfer imports).

## [0.2.0] — 2026-07-10

- Added curated tools: `pages`, `boards`, `feature_flags`, `pipeline_triggers`,
  `access_tokens`, `membership_requests`, `protected` (granular), `badges`,
  `project_import_export`, `repo_extras`.

## [0.1.0] — 2026-07-05

- Initial release: 45 curated tools, 8 references, 10 CI templates, 9 workflow
  commands. Live-verified against GitLab 19.0.0 CE with an admin token.
