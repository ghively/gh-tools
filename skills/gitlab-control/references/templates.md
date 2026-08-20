# Bulletproof templates — catalog & how to apply

The plugin ships ready-to-use templates under `templates/`. The CI templates are
**live-verified**: every one was validated against this instance's CI Lint API
(`POST /projects/:id/ci/lint` on GitLab 19.x) and returned `valid: true` — they are known-good
on your GitLab, not just plausible. Re-lint (`ci_lint(project, content=...)`) after any edit.

## CI/CD pipelines — `templates/ci/*.yml` (all `valid:true` on 19.x)

| File | What it does | Notes |
|---|---|---|
| `node.yml` | npm ci (cached) → lint → test (JUnit) → build (dist artifact) | scripts optional via `--if-present`; runs on MR + default branch |
| `python.yml` | pip cache → ruff lint → pytest (JUnit) | `requirements.txt` optional |
| `docker-build-push.yml` | docker build → push to THIS project's registry | uses auto `CI_REGISTRY*` vars — no secrets; tags `latest` on default branch |
| `pages-static.yml` | deploy `public/` to GitLab Pages | the special `pages:` job; adjust the copy step |
| `go.yml` | go vet → test -race -cover → build | module + build cache |
| `generic.yml` | language-agnostic lint→test→build→deploy(manual) skeleton | fill in scripts; the rules/structure are the bulletproof part |
| `security-ce.yml` | SAST + Secret-Detection templates | CE: findings in the **artifact** only (see ce-vs-ee-and-security.md); Dep-Scan/DAST are Ultimate |
| `release-on-tag.yml` | auto GitLab Release on a `vX.Y.Z` tag | uses release-cli + the `release:` keyword |
| `terraform.yml` | validate → plan (artifact) → apply (manual, default branch) | |
| `mr-only.yml` | run only on MRs/tags/default branch, no duplicate branch pipelines | the canonical `workflow:rules:` pattern |
| `java-maven.yml` | Maven verify (JUnit) + package (.jar artifact) | Maven repo cache per `pom.xml` |
| `rust.yml` | fmt (advisory) → clippy (strict) → test → release build | cargo registry + target cache per `Cargo.lock` |
| `ruby.yml` | bundle install → rubocop → rspec (JUnit) | bundle cache per `Gemfile.lock` |
| `dotnet.yml` | dotnet test (JUnit + Cobertura) + publish | .NET 8 SDK |
| `monorepo.yml` | parent pipeline → per-package child pipelines | triggers only on changed package paths |
| `pre-commit.yml` | run all hooks from `.pre-commit-config.yaml` | env cache per config file |
| `helm.yml` | `helm lint` every chart in `charts/*` + package `.tgz` | push snippet included in comments |
| `php.yml` | composer install + phpcs (advisory) + phpunit (JUnit) | vendor cache per `composer.lock` |
| `cpp.yml` | cmake configure + build + ctest (JUnit), ccache | build→test stage order with `needs:` |
| `scala.yml` | sbt scalafmt (advisory) + test + assembly (.jar) | coursier + target cache per `build.sbt` |
| `android.yml` | gradle lintDebug + testDebugUnitTest (JUnit) + assembleRelease | APK artifact on default/tag |
| `ios.yml` | Fastlane test + build | requires a macOS runner (tags: macos, xcode) |

**Apply**: read the file, `ci_lint(project, content=<yaml>)` to reconfirm, then
`write_files(project, [{action:"create", file_path:".gitlab-ci.yml", content:<yaml>}],
commit_message="ci: add pipeline", confirm=true)`. To layer several, use `include:` rather than
overwriting. `/gl-ci-bootstrap` does this end-to-end.

## Project scaffolding — `templates/project/`

Drop-in repo files (mirror the repo root):
- `.gitlab/issue_templates/Bug.md`, `.../Feature.md` — selectable in the issue description dropdown; pre-labeled, with severity checkbox + evidence block.
- `.gitlab/merge_request_templates/Default.md` — MR checklist + `Closes #` + risk/rollback section.
- `CODEOWNERS` — auto-assign reviewers (owner *enforcement* is EE; assignment works on CE).
- `.editorconfig` — cross-editor consistency (PEP 8 for Python, tabs for Go/Rust, 2-space for JS/YAML).
- `CONTRIBUTING.md` — how to contribute.
- `SECURITY.md` — vulnerability disclosure policy (private channel, scope, disclosure window).
- `renovate.json` — dependency-update bot config (weekly schedule, patch auto-merge, vuln alerts).

**Apply**: one commit via `write_files(project, [{action:"create", file_path:..., content:...}, ...],
confirm=true)`. `/gl-onboard` writes the whole set.

## Config presets — `templates/config/*.json`

Each JSON documents its target tool in `_apply_with` and holds the exact `params` (strip the
`_comment`/`_apply_with`/`_keys`):
- `protected-branch-standard.json` → `protected(project, kind="branches", action="create", params=...)`.
- `project-settings-hardened.json` → `manage_project(project, action="update", params=...)`.
- `webhook-ci-notify.json` → `webhooks(scope_type="project", scope_id=project, action="create", params=...)`.
- `ci-variables-example.json` → apply each entry via `ci_variables(..., action="create", params=<entry>)`.

### v0.5.0 additions

- `tag-protection-standard.json` → `protected(project, kind="tags", action="create", params=...)` — release-tag ruleset (maintainers create `v*` tags).
- `group-settings-hardened.json` → `gitlab_rest("PUT", "/groups/:id", body=...)` — 2FA, restricted project/subgroup creation, default-branch protection.
- `slack-integration.json` → `integrations(project, name="slack", action="update", params=...)` — MR + pipeline events to a Slack channel via incoming webhook.
- `jira-integration.json` → `integrations(project, name="jira", action="update", params=...)` — link MRs to Jira issues by project key.

## GitLab's own built-in templates (`templates` tool)

Separate from the bundled ones: `templates(kind="gitignores|licenses|dockerfiles|gitlab_ci_ymls",
action="list"|"get", name=...)` fetches GitLab's built-in file templates. With `project=...` it
also surfaces the repo's `.gitlab/` issue/MR templates. Use these for a quick `.gitignore` or
`LICENSE` when scaffolding.

## The bulletproof guarantee

CI templates: proven `valid:true` on GitLab 19.x via the live CI Lint API. Config presets: param
shapes matched to verified-working endpoints (protected_branches / project PATCH / webhooks /
variables all returned 200 in the gap audit). Scaffolding: static, structure-verified. If you edit
a CI template, **re-lint before committing** — that's the whole point.
