---
description: Find tokens nearing expiry, rotate them, and relay the new secrets (admin-leaning)
argument-hint: [project | group | "instance"] [--dry-run]
---

Audit and rotate tokens across **$ARGUMENTS**. Token rotations are irreversible and produce
secrets that exist exactly once — relay them immediately. Read `references/admin-and-self-hosting.md`
and `references/troubleshooting.md`. Default to **dry-run** (propose only) unless the user
explicitly approves rotation.

1. **Enumerate every token** in scope (read-only):
   - PATs: `user_tokens(action="list")` (admin, all users) — note `expires_at`, `last_used_at`,
     `scopes`, `active`. Flag any expiring within 30 days, expired-but-active, or never used.
   - Project tokens: `access_tokens(scope_type="project", scope_id=..., action="list")`.
   - Group tokens: `access_tokens(scope_type="group", scope_id=..., action="list")`.
   - Deploy tokens: `deploy_credentials(kind="tokens", scope_type="project"|"group",
     scope_id=..., action="list")`.
   - Pipeline trigger tokens: `pipeline_triggers(project, action="list")` (per-project only).
2. **Classify each**: ExpiringSoon (<30d) | ExpiredStillActive | LongLived(>1yr,risk) |
   NeverUsed | Healthy. Produce a table.
3. **Propose**: for each at-risk token, the exact rotate/revoke call. Default action for
   expiring-soon is `rotate` (preserves the token id + metadata, returns a new secret). For
   never-used and long-dead, propose `revoke` outright.
4. **Confirm-list**: show the proposed batch, get one explicit approval covering every
   `confirm=true` call.
5. **Apply**: loop, calling `user_tokens(action="rotate", token_id=N, confirm=true)` etc.
   **Capture and relay each new secret immediately** — the response is the only copy.
   Recommend storing in the org secret store (Ansible vault / 1Password).
6. **Verify**: re-list tokens; confirm rotations updated `last_used_at`/`expires_at` and
   that revoked tokens are gone. Summarize: rotated count, revoked count, secrets relayed.

If a token is a **CI/CD trigger or deploy token** that's referenced elsewhere (pipeline,
registry login), flag the dependent consumers in step 3 before rotating.
