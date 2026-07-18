---
description: Add or replace a project's CI pipeline with a bulletproof, live-linted template
argument-hint: <project> [stack: node|python|docker-build-push|pages-static|go|terraform|generic]
---

Set up CI for **$ARGUMENTS**. All templates in `templates/ci/` are validated against this
instance's CI Lint API, so they're known-good — but re-lint after any edit.

1. Detect the stack if not given: `repo_tree(project)` + `read_file` for `package.json`
   (node), `requirements.txt`/`pyproject.toml` (python), `Dockerfile` (docker-build-push),
   `go.mod` (go), `*.tf` (terraform). Pick the matching `templates/ci/<stack>.yml`, else `generic.yml`.
2. Show the user the chosen template. If they want changes, edit the YAML, then **always**
   `ci_lint(project, content=<edited-yaml>)` and confirm `valid: true` before writing.
3. Check for an existing `.gitlab-ci.yml`: `read_file(project, ".gitlab-ci.yml")`. If present,
   ask whether to replace or merge (offer `include:` to layer templates instead of overwriting).
4. Commit it: `write_files(project, [{action:"create"|"update", file_path:".gitlab-ci.yml",
   content:<yaml>}], commit_message="ci: add pipeline", confirm=true)`.
5. Trigger a run on the default branch: `pipelines(project, action="create", params={ref:<default>},
   confirm=true)`, then `pipelines(project, action="latest")` / `jobs(..., action="list_pipeline")`
   to watch it. Report pass/fail with the job that failed, if any.

For registry pushes, remind the user the `docker-build-push` template uses the auto-provided
`CI_REGISTRY*` variables — no secrets to configure.
