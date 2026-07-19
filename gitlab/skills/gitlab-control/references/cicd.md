# CI/CD — pipelines, jobs, runners, environments, releases, and `.gitlab-ci.yml`

All paths relative to `/api/v4`. `:id` = numeric project id or URL-encoded path. Verified
against docs.gitlab.com for GitLab ~19.x. Nearly all of this is **Free/CE** (exceptions flagged).

## Pipelines
- `GET /projects/:id/pipelines` (filters: `status`, `ref`, `sha`, `username`, `updated_after/before`,
  `source`, `order_by`, `sort`) · `GET .../pipelines/latest?ref=` · `GET .../pipelines/:pid`
- `GET .../pipelines/:pid/variables` · `.../test_report` · `.../test_report_summary`
- `GET .../pipelines/:pid/jobs` (`scope[]=`, `include_retried`) · `.../bridges` (child/downstream
  trigger jobs — current docs also expose `.../trigger_jobs`; **verify which path form your 19.x
  accepts** via a live call)
- `POST .../pipeline?ref=<ref>` body `{ variables: [{key,value,variable_type}] }` — run a pipeline
- `POST .../pipelines/:pid/retry` · `.../cancel` · `DELETE .../pipelines/:pid`
- Merged/lint config: `POST /projects/:id/ci/lint` with `{content, dry_run, include_jobs, ref}`
  (there's no separate merged-config GET — use ci/lint). Global `/ci/lint` is deprecated.

## Jobs & artifacts
- `GET /projects/:id/jobs` (`scope[]=`) · `.../pipelines/:pid/jobs` · `GET .../jobs/:jid`
- `GET .../jobs/:jid/trace` (log) · `POST .../jobs/:jid/{retry,cancel,play,erase}` (`play` body:
  `job_variables_attributes`)
- Artifacts: `GET .../jobs/:jid/artifacts` (zip) · `.../jobs/:jid/artifacts/:artifact_path` (one
  file) · `GET .../jobs/artifacts/:ref/download?job=<name>` (latest by ref) ·
  `.../jobs/artifacts/:ref/raw/:path?job=<name>` · `POST .../jobs/:jid/artifacts/keep` ·
  `DELETE .../jobs/:jid/artifacts` · `DELETE /projects/:id/artifacts` (all expired). **This is
  the CE path to security-scan SARIF: run the SAST/Secret-Detection template, then pull the artifact.**

## Triggers & schedules
- **Trigger tokens**: `GET/POST/PUT/DELETE /projects/:id/triggers[/:trigger_id]`. Fire a pipeline:
  `POST /projects/:id/trigger/pipeline` with form `token=<trigger_token>&ref=<ref>&variables[KEY]=val`.
- **Pipeline schedules**: `GET/POST/PUT/DELETE /projects/:id/pipeline_schedules[/:sid]` (`description`,
  `ref`, `cron`, `cron_timezone`, `active`). `POST .../:sid/play` · `.../take_ownership` ·
  schedule variables `POST/PUT/DELETE .../:sid/variables[/:key]` · `GET .../:sid/pipelines`.

## CI/CD variables
`GET/POST/PUT/DELETE` at three scopes: `/projects/:id/variables[/:key]`, `/groups/:id/variables[/:key]`,
`/admin/ci/variables[/:key]` (instance). Fields: `key`, `value`, `variable_type` (`env_var`|`file`),
`protected`, `masked`, `raw`, `environment_scope` (project = Free; **group `environment_scope` = EE**),
`description`. Filter a project var by env: `?filter[environment_scope]=`.

## Runners
- `GET /runners` (owned) · `/runners/all` (admin, all) · `/projects/:id/runners` · `/groups/:id/runners`
- `GET /runners/:id` · `PUT /runners/:id` (pause: `active=false`) · `DELETE /runners/:id` · `.../jobs`
- Enable/disable on a project: `POST /projects/:id/runners {runner_id}` · `DELETE /projects/:id/runners/:runner_id`
- **New registration flow** (legacy registration tokens disabled by default since 17.0): create a
  runner first via `POST /user/runners` (`runner_type`, `group_id`/`project_id`, `description`,
  `tag_list`, `run_untagged`, `locked`) → returns a runner + auth token used by `gitlab-runner register`.
- Runner managers: `GET /runners/:id/managers`.

## Environments & deployments
- `GET/POST/PUT/DELETE /projects/:id/environments[/:eid]` · `POST .../environments/:eid/stop` ·
  `GET .../environments/:eid` (with deployments). Deployments: `GET/POST /projects/:id/deployments`,
  `GET/PUT .../deployments/:did`, `GET .../deployments/:did/merge_requests`.
- **EE**: protected environments (`/protected_environments`), deployment approvals.

## Releases
`GET/POST/PUT/DELETE /projects/:id/releases[/:tag_name]`. Create body: `{name, tag_name,
description, ref, milestones:[...], assets:{links:[{name,url,link_type,direct_asset_path}]}}`.
Release links sub-resource: `GET/POST/PUT/DELETE .../releases/:tag_name/assets/links[/:link_id]`.
`GET .../releases/permalink/latest`. (Release **evidence** collection is EE.)

## Feature flags (Free/CE — moved to Free in 13.5)
`GET/POST/PUT/DELETE /projects/:id/feature_flags[/:name]` (strategies: `default`, `gradualRolloutUserId`,
`userWithId`, `flexibleRollout`; scopes per environment). User lists:
`/projects/:id/feature_flags_user_lists`.

## CI_JOB_TOKEN scope
`GET/PATCH /projects/:id/job_token_scope`, allowlist `GET/POST/DELETE .../job_token_scope/allowlist`
(and `/groups_allowlist`). Controls which projects a job token from *this* project may access —
central to cross-project CI and to the GitLab-CI opencode/agent recipes.

## `.gitlab-ci.yml` cheat-sheet
- **Structure**: `stages:`, per-job `stage`/`script`/`before_script`/`after_script`, `image`,
  `services`, `variables`, `tags` (runner selection).
- **Flow**: `workflow:rules:` (whether a pipeline runs at all), per-job `rules:` (`if:`, `changes:`,
  `exists:`, `when: on_success|manual|never|delayed|always`, `allow_failure`). Common `if`:
  `$CI_PIPELINE_SOURCE == "merge_request_event"`, `$CI_COMMIT_TAG`, `$CI_PIPELINE_SOURCE == "schedule"`.
- **DAG / order**: `needs: [job]` (run out of stage order), `dependencies:` (artifact passing).
- **Artifacts/cache**: `artifacts: {paths, reports:{junit,sast,...}, expire_in, when}`, `cache:{key,paths}`.
- **Reuse**: `include:` (`local`, `project`+`file`, `remote`, `template`) and **CI/CD components**
  `include: - component: $CI_SERVER_FQDN/<path>@<version>` from the component catalog.
- **Child/downstream**: `trigger:` (`include:` for child pipeline, or `project:`+`branch:` for
  multi-project). **Merge trains** are EE.
- **Predefined vars**: `CI_PROJECT_ID`, `CI_COMMIT_SHA/REF_NAME/TAG`, `CI_PIPELINE_SOURCE`,
  `CI_MERGE_REQUEST_IID`, `CI_JOB_TOKEN`, `CI_REGISTRY`/`CI_REGISTRY_IMAGE`,
  `CI_API_V4_URL`, `CI_SERVER_URL`, `CI_DEFAULT_BRANCH`.
- **Lint before commit**: `POST /projects/:id/ci/lint {content}` validates in the project's context.

## Resource groups (concurrency control, Free)

`resource_groups` tool — limits how many jobs referencing the same resource key run concurrently.
Job declares `resource_group: deploy-prod` in `.gitlab-ci.yml`; GitLab serializes jobs with the
same key. Process modes (`resource_group_default_process_mode` on the project):
- `unordered` (default) — a queued job waits for the running one to finish; order not guaranteed.
- `ordered` — queued jobs run in the order they were created.
- `oldest_first` — the oldest pending job (by creation) goes first.

Manage via `resource_groups(project, action="list"|"get"|"upcoming_jobs"|"update")`. Use cases:
serialize prod deploys, throttle DB migrations, prevent concurrent Docker tag pushes.

## DAG: `needs` / `dependencies` / `parallel:matrix`

- **`needs: [job_a, job_b]`** — this job starts as soon as its needs finish, **without waiting
  for the whole stage**. Stages become a fallback ordering; `needs` creates a DAG. Artifacts from
  `needs` jobs are downloaded automatically.
- **`dependencies: [job_a]`** — override artifact downloading. Use when you want stage ordering
  but only specific artifacts (or `dependencies: []` to skip artifact download entirely).
- **`parallel: N`** — runs N copies of the job with `CI_NODE_INDEX` / `CI_NODE_TOTAL` injected.
  Good for test-sharding.
- **`parallel: matrix:`** — runs the job once PER combination of variables:
  ```yaml
  test:
    parallel:
      matrix:
        - REGION: [us, eu]
          SUITE: [unit, integration]
    script: ./run-tests "${REGION}" "${SUITE}"
  ```
  Produces 4 jobs (`us/unit`, `us/integration`, `eu/unit`, `eu/integration`), each with distinct
  `CI_NODE_*` and the variables set. Pair with `needs:` referencing a specific matrix instance:
  `needs: ["test: [us, unit]"]`.

## Rules (the modern `if`/`changes`/`exists`/`when` system)

- **`workflow: rules:`** — top-level; decides whether a pipeline runs AT ALL. Combine with
  `auto_cancel_pending_pipelines` on the project to de-dupe branch pushes.
- **Per-job `rules:`** — list of `{if, changes, exists, when, allow_failure, variables}`.
  Evaluated in order; first match wins; if none match, the job is `never`.
- **`changes:`** — paths (glob); job runs only if those paths changed in the push/MR. Pairs with
  `if:` to scope: `if: $CI_PIPELINE_SOURCE == "merge_request_event"; changes: [src/**/*]`.
- **`exists:`** — run only if a file exists at pipeline-creation time (e.g. `exists: [Dockerfile]`).
- **Avoid mixing `rules:` with `only/except:`** — deprecated and confusing. `rules:` is the future.

## Manual / delayed / retry / timeout

- **`when: manual`** — job must be triggered by hand (UI or `jobs(action="play")`). The pipeline
  shows as `blocked` until played. Pair with `environment:` for deploy gates.
- **`when: delayed` + `start_in: 5 minutes`** — auto-run after a delay (rate limiting, blue/green).
- **`retry: N`** or `retry: {max: 2, when: [runner_system_failure, stuck_or_timeout_failure]}` —
  automatic retry on specific failure types. The job's `CI_JOB_STATUS` reflects the final attempt.
- **`timeout: 2 hours`** (per-job) overrides the project default `build_timeout` (default 1h; cap
  via `manage_project(..., params={build_timeout: SECONDS})`).

## Environments & deployment jobs

```yaml
deploy:staging:
  environment: { name: staging, url: https://staging.example.com }
  script: ./deploy.sh staging
  rules: [{if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH}]

deploy:prod:
  environment: { name: production, url: https://example.com }
  script: ./deploy.sh prod
  when: manual
  rules: [{if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH}]
```
Environments are first-class via `environments(project, action=...)`. `deployment_tier` on the
environment (production/staging/testing/development/other) drives the UI grouping. Stop an
environment (spin down review apps): `environments(action="stop", environment_id=N, confirm=true)`.
**Protected environments** (which roles can deploy) are Premium.

## Secure files in CI

Files managed via `secure_files(project, action=...)` are downloaded into the job workspace by
the runner. Reference in `.gitlab-ci.yml`:
```yaml
prepare:
  script:
    - curl -s --header "JOB-TOKEN: $CI_JOB_TOKEN" \
        "$CI_API_V4_URL/projects/$CI_PROJECT_ID/secure_files/<id>/download" -o ~/.kube/config
```
Use for: kubeconfigs, .npmrc, gcloud service-account JSON, signing keys — anything too long or
too binary for a masked variable.

## `.gitlab-ci.yml` include patterns

- **`include: local:`** — another file in the same repo. Good for splitting a long config.
- **`include: project:` + `file:` + `ref:`** — from another project on this instance. Good for
  org-wide job templates.
- **`include: remote:`** — a URL. Avoid for security (the remote can change).
- **`include: template:`** — GitLab's built-in templates (`Security/SAST.gitlab-ci.yml` etc.).
- **`include: component:`** — CI Catalog components: `git.hively.dev/<path>@<version>`. Publish
  your own via `git push` to a project with the catalog feature on; version by tag.

## CE vs EE (CI/CD)
Free: pipelines, jobs, artifacts, triggers, schedules, variables, runners, environments, releases,
feature flags, CI lint, child/parent pipelines, resource groups, secure files, matrix, DAG.
EE: merge trains, deployment approvals, protected-environment approval rules, release evidence,
multi-project pipeline graph visualization, CI/CD for external repos (GitHub PR mirroring).
