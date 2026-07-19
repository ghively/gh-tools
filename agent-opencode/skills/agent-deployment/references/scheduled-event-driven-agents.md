# Scheduled & Event-Driven Agents

Load this when the agent runs *without a human present*: cron schedules, webhooks, queue consumers, watchers, email-in handlers. The packaging-serving reference covers how to host these shapes; this one covers what changes in the design when nobody is watching the run.

The governing shift: an interactive agent can ask; a background agent can only **act within pre-granted authority, park work at a gate, or alert**. Everything below follows from designing those three exits explicitly.

## The Wake-Up Prompt

Each firing starts from nothing, so the trigger prompt is a complete standalone contract, not a conversation turn:

- **Identity and job sentence** — same discipline as stage 1, restated per run.
- **Where to find state** — the run reads its world (files, DB, API) fresh; it never assumes memory of prior runs. Facts worth keeping live in durable storage the prompt names.
- **What done looks like** — the artifact or state change that ends the run.
- **The three exits** — what it may do autonomously, what it parks for approval (and where the parking lot is), what triggers an alert.
- **Budget** — max turns / tokens / wall-clock, stated in the prompt AND enforced by the runtime (`max_turns`, timeouts). A looping background agent burns money silently by design.

Test the wake-up prompt like an API: golden eval cases run *against the prompt itself* (see `agent-evals`), fired manually before the schedule ever does.

## Idempotency and Overlap

Schedulers double-fire, webhooks redeliver, and retries happen. Two invariants:

| Invariant | Mechanic |
|---|---|
| Firing twice must be safe | Idempotency key per logical event (issue id, message id, date-bucket); check-then-act against durable state; see `deterministic-agents` idempotency reference |
| Runs must not overlap | Lock/lease (file lock, DB row, queue visibility timeout). On lock contention: skip and log, don't queue up — a backlog of stale runs executing at once is the classic incident |

A run that crashes mid-way must either resume from a checkpoint or start over harmlessly (idempotency again). If neither holds, the job needs durable execution (Temporal/Inngest/Restate — durable-execution reference), not a bigger try/except.

## Trigger Taxonomy

| Trigger | Design notes |
|---|---|
| Cron / schedule | The simplest and the most dangerous — fires whether or not the world changed. First step of the run: check whether there's anything to do, exit cheaply if not |
| Webhook | Verify the source (signature), dedupe on delivery id, ack fast and process async — webhook timeouts force half-done work |
| Queue consumer | Idempotency + visibility timeouts + dead-letter queue. Poison messages (one input that always crashes) must dead-letter, not block the queue |
| Watcher (file/inbox/feed) | Track a durable high-water mark; process the delta, never "everything that looks new" |
| Agent-scheduled (agent re-arms its own next check) | Powerful for babysitting external processes; cap the re-arm chain so a confused agent can't self-perpetuate forever |

## The Notification Contract

Background agents earn trust by being quiet correctly:

- **Report signal, not activity.** "3 PRs triaged, 1 needs your eyes: <link>" — never a transcript. If nothing noteworthy happened, say nothing (but record the run).
- **Alert = actionable.** An alert states what broke, what the agent already tried, and the one decision needed. Alerts that need investigation to understand get ignored within a week.
- **Parked work has a location.** Approve-before actions go to a durable parking lot (draft PR, pending-approval queue, dated file) with an expiry policy that fails closed — see `human-in-the-loop.md` in the agent-design skill.
- **Silence must be distinguishable from death.** A heartbeat record per run (even no-op runs) plus a "no run in N hours" alarm from the outside. Otherwise the agent that stopped firing three weeks ago looks identical to the agent with nothing to say.

## Operations

Each firing is one trace with the trigger payload at the root (see `observability.md`). The per-run record keeps: trigger, decisions, actions taken, cost, exit path (done / parked / alerted / no-op). Weekly review reads the exit-path distribution — a rising no-op rate means the schedule is wrong; rising parked rate means authority is scoped too tight; rising alert rate means the job is drifting out of its design.

Cost guardrail: schedule × cost-per-run is a budget line you set, not discover. Track it like the routing budget in `model-selection`, and alarm on per-run cost jumps — a 10× expensive run is a behavior change, not a billing event.

## Claude Code Shapes

| Shape | When |
|---|---|
| Headless `claude -p` from real cron/CI | Simplest; the wake-up prompt is the command argument; CI logs are the run record |
| GitHub Actions + agent | Repo-event-driven work (PR triage, issue labeling, CI babysitting); the workflow file is the trigger contract |
| Claude Code Routines / scheduled triggers | Managed schedule firing into a session (fresh-per-fire for standalone jobs; session-bound when continuity matters) |
| Agent SDK worker | Full control: your queue, your locks, your budget enforcement in code |

Whatever the shape: version the wake-up prompt like any other release artifact (versioning-rollout reference), and give every schedule an owner — an unowned cron agent is tomorrow's mystery incident.
