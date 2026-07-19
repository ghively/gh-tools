# deploy-templates

Copyable last-mile artifacts for the packaging shapes in
`packaging-serving.md`. Each template embodies the doctrine from this skill's
references — locks, heartbeats, budgets, fail-closed defaults — so the ops
answers `/agent-foundry:ship-check` asks for exist on day one.

| Shape | Template | Doctrine it encodes |
|---|---|---|
| Container | `Dockerfile` | Non-root, pinned base, no secrets in image |
| Scheduled (host) | `cron-wrapper.sh` + `systemd/my-agent.service` + `systemd/my-agent.timer` | Overlap lock, heartbeat record, wall-clock budget, cheap no-op exit |
| Scheduled (CI) | `github-actions-scheduled.yml` | Headless `claude -p` run, wake-up prompt in-repo, run record as artifact |
| Webhook worker | `webhook-worker.py` | Signature verification, delivery-id dedupe, fast ack |

Adapt names/paths, then delete the rows you don't use from this README in
your copy. Details and trade-offs: `scheduled-event-driven-agents.md` and
`packaging-serving.md`.
