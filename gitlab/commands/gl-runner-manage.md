---
description: Inventory the CI runner fleet, flag stale/unhealthy runners, propose cleanup
argument-hint: [instance | group <id> | project <id>]
---

Audit the runner fleet under **$ARGUMENTS** and propose health actions. Read
`references/runners-deep.md`. Read-only until the confirm-list; never bulk-delete without a
reviewed list.

1. **Inventory** (read-only):
   - Instance fleet: `runners(action="list", scope="instance")` (admin, `/runners/all`).
   - Group fleet: `runners(action="list", scope="group", scope_id=<gid>)`.
   - Project fleet: `runners(action="list", scope="project", scope_id=<pid-or-path>)`.
   - GraphQL deep read for health signals:
     ```graphql
     query { runners(first: 100) { nodes { id description runnerType active paused locked
       tagList version architecture platform contactStatus contactedAt projectCount } } }
     ```
2. **Classify each runner**:
   - **Healthy**: `contactStatus: "ok"`, recent `contactedAt`, `version` matches server.
   - **Stale**: `contactedAt` older than 1h on a runner with pending jobs.
   - **Never-contacted**: `contactStatus: "never_contacted"` — registered but never ran.
   - **Version-mismatched**: `version` older than server's `metadata.version` — upgrade needed.
   - **Orphaned**: locked to a deleted/archived project (`projectCount: 0` + project_type).
   - **Paused-with-queue**: `paused: true` AND pending jobs matching its tags.
3. **Tag-gap analysis** (optional): `jobs(scope=["pending"])` per project — list the tag-sets
   jobs are waiting for and which runners have them. Recommend adding specific tags to drain
   a queue, or adding a runner with the missing tags.
4. **Propose** per runner: `pause` (noisy/stale), `resume` (accidentally-paused),
   `delete` (confirmed-dead/orphaned after reassigning work), reset auth token (suspected leak).
5. **Confirm-list**: table of runner → action → reason. Get one approval for the batch.
6. **Apply**: loop with `confirm=true`. If any auth-token reset, **relay the new token
   immediately** (it's the only copy — see `references/runners-deep.md`).
7. **Verify**: re-run inventory; confirm the queue drains and dead runners are gone. Report:
   counts by category, actions taken, any tokens relayed, follow-up (runner binary upgrade,
   new runner needed).

Common follow-ups: upgrade stale `gitlab-runner` binaries (host-side, may need the `ansible`
agent for gh-Nvidia); re-register runners on the v16 flow if still on legacy registration
tokens; right-size `concurrent =` in `config.toml` if a host is overloaded.
