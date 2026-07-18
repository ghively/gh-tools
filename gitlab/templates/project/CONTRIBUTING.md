# Contributing

## Workflow
1. Create an issue (use the Bug/Feature template) describing the change.
2. Branch from the default branch: `git switch -c <type>/<short-desc>` (`feat/…`, `fix/…`, `chore/…`).
3. Commit with clear messages (Conventional Commits encouraged: `feat: …`, `fix: …`).
4. Open a merge request against the default branch; fill in the MR template; link the issue with `Closes #NNN`.
5. Ensure CI is green and at least one approval before merge. Squash on merge; delete the source branch.

## Local checks before pushing
- Run the linter and tests locally (see the project README / `.gitlab-ci.yml`).
- Never commit secrets. Use CI/CD variables (masked + protected) for tokens.

## Branch protection
The default branch is protected: no force-push, merges via MR only. See the repo's
protected-branch settings.

## Reporting security issues
Do not open a public issue for vulnerabilities — contact the maintainers directly.
