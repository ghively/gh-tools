---
description: Debug the latest failing pipeline for a GitLab project
argument-hint: <project path or id> [pipeline id]
---

Debug CI for **$ARGUMENTS** using the gitlab MCP tools:

1. Find the target pipeline: the given pipeline id, else
   `pipelines(action="list", status="failed", limit=5)` → most recent failure
   (fall back to `action="latest"`).
2. `jobs(action="list_pipeline", pipeline_id=...)` — identify failed jobs (and
   whether failures are in the same stage or cascade).
3. For each failed job (max 3): `jobs(action="log", tail=200)` — extract the real
   error (compile error, test failure, missing variable/secret, runner issue,
   timeout, OOM).
4. Cross-check config when relevant: `read_file(".gitlab-ci.yml")` and
   `ci_lint(project)`; check referenced variables exist via
   `ci_variables(action="list")` (names only — never print values).
5. If the failure looks infra-side (job stuck/pending), check
   `runners(action="list", scope="project", scope_id=...)` for offline/paused runners.

Report: root cause per failed job, then a concrete fix. Offer (don't execute)
next steps: retry via `pipelines(action="retry", confirm=true)` or a config fix
via `write_files` — both only with explicit approval.
