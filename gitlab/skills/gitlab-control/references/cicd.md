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

## CE vs EE (CI/CD)
Free: pipelines, jobs, artifacts, triggers, schedules, variables, runners, environments, releases,
feature flags, CI lint, child/parent pipelines. EE: merge trains, deployment approvals, protected-
environment approval rules, release evidence, multi-project pipeline graph visualization.
