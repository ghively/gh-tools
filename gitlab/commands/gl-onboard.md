---
description: Bootstrap a new (or existing) GitLab project the right way — settings, protection, CI, templates, ownership
argument-hint: <namespace/name> [ci-template: node|python|docker-build-push|pages-static|go|generic|terraform]
---

Onboard the project **$ARGUMENTS** to the team standard. Read `references/templates.md` and
`references/workflows.md` first. Do each step, showing the user what you'll write and getting
approval before every `confirm=true` call.

1. **Project**: if it doesn't exist, `manage_project(action="create", params={name, namespace_id,
   visibility, initialize_with_readme:true}, confirm=true)`. Get its id/path.
2. **Hardened settings**: apply `templates/config/project-settings-hardened.json` via
   `manage_project(action="update", params=<preset>, confirm=true)` (MR-only merges, green-pipeline
   required, squash on, source branch auto-delete).
3. **Protect the default branch**: apply `templates/config/protected-branch-standard.json` via
   `protected(project, kind="branches", action="create", params=<preset>, confirm=true)`
   (developers can't push directly; maintainers merge; no force-push).
4. **CI/CD**: pick the bulletproof template from `templates/ci/<ci-template>.yml` (default
   `generic.yml`). `ci_lint(project, content=<template>)` to confirm it's valid on this instance,
   then `write_files(project, [{action:"create", file_path:".gitlab-ci.yml", content:<template>}],
   commit_message="ci: add pipeline", confirm=true)`.
5. **Repo scaffolding**: write `templates/project/.gitlab/issue_templates/{Bug,Feature}.md`,
   `.gitlab/merge_request_templates/Default.md`, `CODEOWNERS`, `.editorconfig`, `CONTRIBUTING.md`
   in one commit via `write_files(..., confirm=true)`.
6. **Badges** (optional): `badges(scope_type="project", scope_id=project, action="create",
   params={link_url, image_url}, confirm=true)` for a pipeline badge.
7. **Verify**: `get_project(project)`, `protected(project, kind="branches", action="list")`,
   `ci_lint(project, ...)` — confirm everything took. Summarize what was set up and the project URL.

Never create/modify without the user approving each step's exact payload.
