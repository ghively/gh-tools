---
description: Apply a baseline set of CI/CD variables across projects and/or environments
argument-hint: <variables-json | @file> (--projects ns/a,ns/b | --group ns | --instance) [--dry-run]
---

Synchronize CI variables across multiple targets so pipelines share a consistent secret/config
baseline. Read `references/cicd.md` and `references/conventions.md`. **Variables may be
secrets** — handle the JSON as a credential, never echo `masked` values back in full.

1. **Parse the variables spec** (JSON object: `{"KEY": {value, masked, protected,
   environment_scope, raw}, ...}`) — from inline `$ARGUMENTS` or `@file`. Validate each entry:
   masked values must match the masked-value rules (≥8 chars, single line, no spaces, matches
   `^[a-zA-Z0-9_+/=:.-]+$`); flag any that violate.
2. **Enumerate targets** (read-only):
   - `--projects`: list each; `get_project` to confirm existence + id.
   - `--group`: `groups(action="projects", group=...)` to enumerate; include subgroups if desired.
   - `--instance`: confirm admin; `ci_variables(action="list", scope_type="instance")` for the
     current instance-level set.
3. **Diff per target**: `ci_variables(action="list", scope_type=..., scope_id=...)` — for each
   target, build the diff: **create** (key not present), **update** (present but value/flags
   differ — note that `value` isn't returned for existing masked vars, so diff by metadata +
   assume update if flags differ or user said `--force`), **leave** (matches). Produce a matrix
   table: target × variable → action.
4. **Confirm-plan**: show the matrix (count of creates/updates per target, environment_scope
   if set). Get explicit approval for the batch.
5. **Apply**: loop targets × variables:
   `ci_variables(action="create"|"update", scope_type=..., scope_id=..., key=KEY,
   params={value, masked, protected, environment_scope, raw}, confirm=true)`.
   For deletes (if the spec marks a key `null`): `ci_variables(action="delete", ..., confirm=true)`.
6. **Verify**: re-list each target's variables; confirm keys + flags match the spec (values
   can't be read back for masked vars — trust the create response). Report: per-target creates/
   updates/deletes, any masked-value-rule failures, and which environment_scopes were touched.

Use cases: rotate a shared deploy key across every project in a group, push a new
`REGISTRY_PASSWORD` to dev/staging/prod `environment_scope` values, or establish a baseline
(`CI_IMAGE`, `DEPLOY_TIMEOUT`) on newly onboarded projects. Pair with `/gl-token-rotate` when
the variable value is itself a token about to expire.
