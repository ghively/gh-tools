# Runners — the deep guide (registration, tags, fleet health, the v16+ flow)

CI/CD runners are the compute layer. On a self-hosted CE instance you own them
entirely — there is no GitLab.com shared fleet and no CI-minutes billing. This
file covers the runner lifecycle, the **new v16 registration flow** (which
replaced the legacy runner registration token), fleet health signals, and the
`/gl-runner-manage` workflow. Read alongside `references/cicd.md` for how
runners interact with pipelines/jobs.

## Runner types (pick at creation)

- **`instance_type`** — available to every project on the instance. Best for a
  shared org fleet. Created via `POST /user/runners` with admin token.
- **`group_type`** — scoped to one group and its subgroups. Created with a
  group-scoped token or `POST /groups/:id/runners`.
- **`project_type`** — scoped to one project. Created with
  `POST /projects/:id/runners` or `POST /user/runners` with `project_id`.

A runner's type is fixed at creation. To "move" a runner you delete + recreate.

## The v16+ registration flow (current — use this)

The legacy **runner registration token** (the `GRSSION-...` token printed by
`POST /projects/:id/runners` and shown in project settings) is **deprecated and
disabled by default** in GitLab 16.0+. The replacement is the
**`POST /user/runners` endpoint** (added 16.0), which authenticates with a
normal PAT / project / group access token and returns a **runner authentication
token** directly.

### Create a runner (instance type, admin)
```
runners(action="create", params={
  "runner_type": "instance_type",
  "description": "unraid-host docker runner",
  "tag_list": ["docker", "linux", "gpu"],
  "run_untagged": false,
  "locked": false
}, confirm=true)
```
Response includes `token` — **the only time it's ever returned**. Relay it
immediately (same rule as access-token secrets). Configure the runner binary:
```
gitlab-runner register-v2 --token <returned-token> --url https://gitlab.example.com
```
or use it directly in a `config.toml`:
```toml
[[runners]]
  url = "https://gitlab.example.com"
  token = "<returned-token>"
  executor = "docker"
```

### Create per-group / per-project
```
runners(action="create", params={
  "runner_type": "group_type", "group_id": <gid>,
  "description": "...", "tag_list": [...]
}, confirm=true)

runners(action="create", params={
  "runner_type": "project_type", "project_id": <pid>,
  "description": "...", "tag_list": [...]
}, confirm=true)
```

### Reset the authentication token (if leaked or for rotation)
`runners(action="...")` doesn't directly expose reset — use the
`runnersRegistrationTokenReset` GraphQL mutation (instance/group/project) or
`POST /runners/:id/reset_authentication_token` REST. Returns a **new** token;
the old one stops working immediately.

## Legacy registration tokens (you'll still see them)

The settings UI still shows a "registration token" for backward compat. It's
**off by default** since 16.0; the instance admin setting
`register_runner_interval` / `runner_registration_token` feature flags control
whether the legacy flow works. Don't rely on it for new runners — use
`POST /user/runners`. If a user pastes a legacy `GRSSION-...` token expecting
it to "create a runner," explain the deprecation and use the new flow.

## Runner attributes that matter

- **`tag_list`** — job tags AND-match against runner tags. A job with
  `tags: [docker, gpu]` only runs on a runner with **both** `docker` AND `gpu`.
  Order doesn't matter; presence does.
- **`run_untagged`** — if `true`, the runner also picks up jobs with no tags.
  Defaults `true` for instance/group runners, `false` for project. Set
  explicitly at creation.
- **`locked`** — if `true`, the runner cannot be assigned to another project/
  group. Lock a project runner before archiving the project to prevent
  orphaning.
- **`active` / `paused`** — `paused: true` means new jobs won't be assigned
  but running ones finish. Use `runners(action="pause")` / `"resume"`.
- **`access_level`** — `not_protected` (any branch, including forks) vs
  `ref_protected` (only protected branches). Set via update.
- **`maximum_timeout`** — override the job's own timeout if lower.

## Fleet health — what to monitor

| Signal | Where | Meaning |
|---|---|---|
| `contactStatus: "never_contacted"` | GraphQL `runner`/`runners` | runner never checked in — not actually running |
| `contactedAt` stale (>1h on an active queue) | GraphQL | runner process died or host offline |
| `version` mismatch vs server | GraphQL `runner.version` | upgrade needed; mismatches cause job-submission quirks |
| `active: false` | REST/GraphQL | runner paused or marked inactive |
| `paused: true` | REST/GraphQL | admin hit pause — jobs queue but don't dispatch |
| `job_queue_size` high + runners idle | sidekiq metrics | tag mismatch — jobs waiting for a runner nobody has |
| `runnerUsage`/`runnerUsageByProject` | GraphQL | which projects are burning the fleet (admin) |

**The classic "pipeline stuck in `created`/`pending`" cause:** job has tags no
runner has, OR all matching runners are `paused`/`active:false`/`locked` to
other projects, OR `run_untagged: false` on every runner and the job is
untagged. `jobs(action="list", scope=["running"])` + `runners(action="list")`
cross-referenced with tag lists pinpoints it.

## Inspecting and managing (REST + GraphQL)

### List all runners an admin can see
```
runners(action="list", scope="instance")    # /runners/all — admin
runners(action="list", scope="group", scope_id=<gid>)
runners(action="list", scope="project", scope_id=<pid-or-path>)
```
Filter by `scope_type`/`status`/`tag_list` via params on the underlying REST
call: `GET /runners/all?status=active&tag_list=docker`.

### Jobs a runner has run
```
runners(action="jobs", runner_id=N)    # GET /runners/:id/jobs
```

### Pause / resume / delete
```
runners(action="pause",  runner_id=N, confirm=true)
runners(action="resume", runner_id=N, confirm=true)
runners(action="delete", runner_id=N, confirm=true)   # irreversible
```

### Bulk operations (GraphQL, admin)
```graphql
mutation($input: RunnerBulkPauseInput!) {
  runnerBulkPause(input: $input) { runners { id } errors }
}
```
And `bulkRunnerDelete`, `runnerCacheClear` (clears the runner's CI cache —
useful when a cached layer is corrupted).

### GraphQL fleet read (admin, role-gated, NOT tier-gated — works on CE)
```graphql
query {
  runners(first: 50) {
    nodes {
      id description runnerType active paused locked
      tagList version architecture platform
      contactStatus contactedAt
      projectCount
    }
  }
}
```

## Executors (binary-side, not API)

The `gitlab-runner` binary supports several executors; pick per host:
- **`docker`** — most common; each job runs in a container. Needs Docker on the
  host and the runner user in the `docker` group.
- **`shell`** — jobs run directly on the host shell. Fast, no isolation — only
  for trusted jobs.
- **`instance`** — autoscales on ephemeral VMs (AWS/SCW/GCP via Docker Machine).
  Docker Machine itself is deprecated; GitLab is moving to a new autoscaler.
- **`kubernetes`** — each job is a pod. Needs cluster access.
- **`ssh`**, **`parallels`**, **`virtualbox`** — legacy, rarely used.

CE has **no CI-minutes quota** (that's a GitLab.com/SaaS concept). On
self-hosted CE, the only fleet limits are: the runners you've configured, your
host's CPU/RAM/disk, and (for `docker`) image-pull throughput.

## The `/gl-runner-manage` workflow (proposed)

1. **Fleet inventory**: `runners(action="list", scope="instance")` + GraphQL
   fleet read for contact status. Output table: runner, type, tags, version,
   contactedAt, status.
2. **Flag**: never-contacted, stale-contacted, version-mismatched, orphaned
   (project deleted but runner locked), paused-with-pending-jobs.
3. **Propose**: pause stale runners, delete confirmed-dead ones, reset auth
   tokens for leaked ones, tag gap-fill recommendation (which tags to add to
   which runners to drain a queue).
4. **Confirm-list → apply**: loop with `confirm=true`. Relay any reset tokens
   immediately.
5. **Verify**: re-read the fleet; confirm the queue drains.

## Runner security notes

- **`access_level: ref_protected`** for any runner that touches prod secrets.
  Otherwise forks/MRs can exfiltrate via pipeline. Set on shared fleet runners.
- **Don't commit the runner `token`** to the repo. It's a credential. Store in
  Ansible vault / 1Password / the host's secret store.
- **`config.toml` permissions** — `chmod 600`; the file contains the auth token.
- **Runner tags as access control** — a job with `tags: [deploy-prod]` only
  runs on a runner with `deploy-prod`. Pair with `ref_protected` for a real
  boundary.
- **`run_untagged: false`** on prod runners — don't let random MR pipelines
  land on the deploy host.

## Common pitfalls

- **Tag mismatch is the #1 cause of stuck pipelines.** Cross-check job tags vs
  runner tags before anything else.
- **`run_untagged: true` on every runner** + an untagged job = random
  assignment. Fine for a generic fleet, bad if runners have different
  capabilities.
- **Locked runner after project archive** — the runner is stuck. Unlock via
  `runners(action="update", runner_id=N, params={locked: false}, confirm=true)`
  before reassigning.
- **Executor mismatch** — `.gitlab-ci.yml` uses Docker images (`image:`), but
  the runner is `shell` executor. Job fails immediately. Either switch the
  runner to `docker` or remove `image:` from the job.
- **Host resource exhaustion** — too many concurrent jobs on one runner host
  starves CPU/RAM. Cap concurrency in `config.toml` (`concurrent = N`).
