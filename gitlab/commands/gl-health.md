---
description: GitLab instance health check — version, stats, sidekiq, runners, storage
---

Run a health check of the GitLab instance using the gitlab MCP tools (read-only):

1. `gitlab_status()` — version, statistics, current user, token expiry (warn if
   the token expires within 60 days).
2. `admin_ops(area="sidekiq", action="compound_metrics")` — flag queues with
   backlog or busy/stuck workers.
3. `runners(action="list", scope="instance")` — flag offline/stale/never-contacted
   runners.
4. `admin_ops(area="statistics")` + `list_projects(statistics=true, limit=10, order_by="last_activity_at")`
   — note the largest/most active projects.
5. `gitlab_rest("GET", "/broadcast_messages")` — surface any active broadcasts.
6. `gitlab_rest("GET", "/application/settings")` — call out risky settings
   (signup enabled? default visibility public? webhooks to localhost allowed?).

Summarize as a short table: component / status / finding. Lead with anything
actionable (stuck queues, dead runners, expiring token). Read-only — do not
change anything.
