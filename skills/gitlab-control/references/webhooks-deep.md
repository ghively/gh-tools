# Webhooks — payloads, signing, delivery, and security

Webhooks are GitLab's push notification system: HTTP POST to your URL when an event happens.
This file covers what each event payload looks like, how to verify authenticity, retry
behavior, and the security settings that bite.

## Project vs system vs group webhooks

| Type | Scope | Events | Tier |
|---|---|---|---|
| **Project webhooks** | one project | push, MR, issue, note, pipeline, wiki, tag, release, deployment, subgroup, member, etc. | Free |
| **System hooks** | whole instance | user/group/project CRUD, key add/remove, push, tag, group/transfer | Free (admin) |
| **Group webhooks** | one group (all its projects) | similar to project | **Premium** — 404 on CE |

Use **project webhooks** (`webhooks` tool) for per-project automation. Use **system hooks**
(`admin_ops(area="system_hooks")`) for instance-wide audit (user created, project deleted).
Group webhooks aren't available on CE — for group-wide automation on Free, either enumerate
projects and add a webhook to each, or use a system hook with path filtering in your handler.

## Configuring a webhook

```
webhooks(scope_type="project", scope_id=<pid>, action="create", params={
    url: "https://handler.example.com/gitlab",
    token: "<shared-secret>",              # sent as X-Gitlab-Token header
    push_events: true,
    merge_requests_events: true,
    enable_ssl_verification: true,         # audit-flag if false
    confidential_note_events: false,       # include confidential issue/MR notes?
}, confirm=true)
```

The `token` is the **only** integrity check GitLab provides by default — it's sent as the
`X-Gitlab-Token` header on every delivery. Your handler MUST verify it (`if req.headers
["X-Gitlab-Token"] != EXPECTED: return 401`). Without this check, anyone who knows the URL
can forge events.

## Event payloads (what to expect in the body)

Every payload has `object_kind` as the top-level discriminator. Common shapes:

### `push_events` (branch push)
```json
{"object_kind": "push", "ref": "refs/heads/main",
 "project": {"id": N, "path_with_namespace": "...", "web_url": "...", ...},
 "commits": [{"id": "abc...", "message": "...", "author": {"name","email"},
              "added": [], "modified": ["path/file"], "removed": []}],
 "user_name": "...", "user_id": N, ...}
```
Triggered on every non-tag push. **Not** triggered for MR push (that's `merge_request` event).

### `merge_requests_events`
```json
{"object_kind": "merge_request",
 "object_attributes": {"action": "open"|"update"|"close"|"reopen"|"merge",
                       "iid": N, "state": "opened", "title": "...",
                       "source_branch": "...", "target_branch": "...",
                       "source": {...project...}, "target": {...project...}},
 "labels": [...], "changes": {"labels": {...}}, "user": {...}, "object_kind": "merge_request"}
```
`action` is the important field — filter to `open`/`merge` to avoid noise.

### `pipeline_events`
```json
{"object_kind": "pipeline",
 "object_attributes": {"id": N, "status": "success"|"failed"|"running",
                       "stages": [...], "ref": "...", "commit": {...}},
 "project": {...}, "user": {...}, "builds": [{"id", "stage", "name", "status", ...}]}
```

### `issues_events`, `note_events`, `tag_push_events`, `release_events`, `deployment_events`
Each follows the same `object_kind` + `object_attributes` + `user` shape. Full schemas in
the GitLab docs (https://docs.gitlab.com/ee/user/project/integrations/webhook_events.html).

## Delivery behavior

- **Method:** POST. **Content-Type:** `application/json`.
- **Headers:** `X-Gitlab-Token` (the configured secret), `X-Gitlab-Event` (e.g.
  `"Push Hook"`, `"Merge Request Hook"`), `X-Gitlab-Webhook-Id`, `X-Gitlab-Delivery-id`.
- **Timeout:** GitLab waits up to ~8 seconds for a `2xx` response. Anything else (3xx
  redirect, 4xx, 5xx, timeout) counts as a failure.
- **Retry:** unsent/failed webhooks are retried with backoff (queue-based). View failed
  deliveries in the UI (Project → Settings → Webhooks); via API you can trigger a test:
  `webhooks(scope_id=..., action="test", params={trigger: "push_events"}, confirm=true)`.
- **Body size:** payloads over 25 MB are not delivered (truncated or skipped). Large diffs
  trigger `push_events` with a `commits` array that may be truncated.

## SSL verification — the audit-flag setting

`enable_ssl_verification: true` (the default) means GitLab verifies the target's TLS cert
on delivery. **Setting it to `false`** disables verification — useful for self-signed
internal services (e.g. a handler on the tailnet), but it opens the delivery to MITM. Flag
any webhook with `enable_ssl_verification: false` in `/gl-audit` and prefer fixing the cert
chain or pinning a CA.

## `allow_local_requests_from_web_hooks_and_services` (admin)

Whether webhooks/integrations can target RFC1918 / localhost URLs. **Off by default** for
security (SSRF protection). For internal automation (tailnet handlers), an admin enables it:

```
admin_settings(action="update", params={
    allow_local_requests_from_web_hooks_and_services: true
}, confirm=true)  # instance-wide — confirm twice
```

This is the single setting most likely to be the cause when a webhook to an internal URL
returns a delivery error mentioning "URL is blocked."

## Retry & idempotency

GitLab retries failed deliveries, so **your handler MUST be idempotent** — receiving the
same event twice should produce the same end state. Strategies:
- Deduplicate by `X-Gitlab-Delivery-id` (unique per delivery attempt — actually per event,
  so retries share it... verify). Actually: use the combination of `X-Gitlab-Webhook-Id` +
  a content hash for true dedup.
- Make side effects idempotent (PUT not POST, "upsert by id" not "create").
- Process events async with a durable queue.

## Security checklist (the `/gl-audit` webhook row)

- [ ] `token` is set (not empty) — verify with `webhooks(action="list")`.
- [ ] Handler validates `X-Gitlab-Token` header on every request.
- [ ] `enable_ssl_verification: true` (or document why it's false).
- [ ] URL uses HTTPS (not HTTP).
- [ ] `confidential_note_events: false` unless the handler is trusted with confidential data.
- [ ] Handler is idempotent (survives retries).
- [ ] Handler responds in <8 seconds (offload slow work to a queue).
- [ ] `allow_local_requests_from_web_hooks_and_services` is deliberately set (audit).

## System hooks (instance-wide)

```
admin_ops(area="system_hooks", action="list")
admin_ops(area="system_hooks", action="create", params={url, token}, confirm=true)
```
Events: `user_create`, `user_destroy`, `user_add_to_team`/`remove_from_team`, `user_update_for_team`,
`project_create`/`destroy`, `group_create`/`destroy`, `key_create`/`destroy`, `push`, `tag_push`.
Useful for: auto-provisioning on project create, auditing user changes, syncing to external
identity systems. Same payload shape + `X-Gitlab-Token` auth as project webhooks.

## Alternatives when webhooks aren't enough

- **Integrations** (`integrations` tool) — for named services (Slack, Jira, Discord,
  Mattermost, etc.) GitLab posts formatted payloads; you don't write a handler.
- **GraphQL subscriptions** — not available (GitLab has no subscriptions over the API).
- **Polling** — for low-frequency needs, poll the events/todos API. Less elegant than
  webhooks but trivial to implement and no inbound network exposure.

## Debugging a failing webhook

1. `webhooks(action="test", params={trigger: "<event>"}, confirm=true)` — fires a test
   event with sample data. Returns the HTTP status + response body GitLab got.
2. Check the handler's logs for the delivery id.
3. Verify `allow_local_requests...` if the URL is internal.
4. Verify `enable_ssl_verification` if the cert is self-signed.
5. Check the handler responds `2xx` within 8 seconds.
