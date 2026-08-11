---
name: agent-deployment
description: "Deploying agents to production and operating them there: packaging, serving, session persistence, observability, versioning, rollout, live-agent tuning, and closed-loop improvement. Use when shipping an agent as a CLI, service, worker, webhook handler, scheduled job, or embedded application. Does not cover GPU inference-serving infrastructure, eval construction (see agent-evals), or security hardening in depth (see agent-safety)."
---

# Agent Deployment

Production begins when an agent can affect real users, real systems, real money, or real operational load. This skill covers the SDLC after build: deploy, observe, improve, and roll back safely.

"What counts as production" is broader than "serves paying customers." An agent is in production the moment any of these is true: another person depends on its output, it can take an action you would not want to undo in front of a witness, it spends money on your behalf, it runs unattended, or its failure would embarrass you. A scheduled job that runs once a week on your own machine and emails a report is in production. Treat it that way and the jump to a user-facing deployment is small; skip it and the jump is an incident.

## When to Use

- You need to package an agent as a CLI, HTTP service, queue worker, webhook handler, scheduled task, or embedded application.
- You are deciding between self-hosting, managed agents, LangGraph/LangSmith-style deployment, or durable workers.
- You need session persistence, state storage, health checks, and runtime limits.
- You are adding traces, metrics, dashboards, alerts, or cost controls.
- You are rolling out a prompt/model/tool change and need canary or rollback discipline.
- You are debugging or tweaking an already deployed agent.

**Don't use for:** GPU model serving (outside agent-foundry's scope), eval methodology (`agent-evals` skill), or sandboxing/security hardening (`agent-safety` skill).

## Agent SDLC Loop

```text
design -> build -> evaluate -> deploy -> observe -> improve
            ^          |          |          |          |
            |          +-- eval gate before every deploy-+
            +------------- regression cases feed back -----
```

Non-negotiables:

1. **No deploy without a golden-suite gate.** Every prompt/model/tool/policy change that affects behavior runs the agent's golden suite first.
2. **No production loop without bounds.** Max turns, wall-clock timeout, cost ceiling, and loop detection are deployment requirements.
3. **No state in container memory only.** Session transcripts, artifacts, memory, and eval evidence need durable storage if anyone expects resumability or auditability.
4. **No silent drift.** Prompts, models, tools, memory, retrieval collections, and policy are versioned artifacts.
5. **Every production failure becomes learning.** Capture it, classify it, add a regression case, fix one thing, verify, and consolidate the lesson.

## From Dev Agent to Production Agent

A dev agent and a production agent can share a prompt, but they are not the same system. The deployment skill is the work of converting the left column below into the right one.

| Dimension | Dev agent | Production agent |
|---|---|---|
| State | In-process or working files | Durable store; survives crash and restart |
| Cost | The builder's wallet | Per-run and per-tenant ceilings with spend alerts |
| Failure | Read the transcript by hand | Alerts, regression evals, rollback bundle |
| Identity | "Latest" model alias; dashboard-edited prompt | Pinned versions in a release manifest |
| Authority | Whatever the builder typed in config | Enforced tool policy, sandbox, audit log |
| Observability | A few `print` statements | Trajectory traces, metrics, dashboards, retention |
| Change | Edit and re-run | One-change protocol, golden-suite gate, canary |

If a "production" deployment still looks like the left column, the deployment work has not happened yet. The rest of this skill, and every reference it routes to, exists to move one row at a time to the right.

## Deployment Shape Decision Table

| If the agent is... | Start with | Required controls |
|---|---|---|
| A developer-local helper | CLI/local plugin or skill | Clear install docs, local secrets, update path |
| A user-facing chat or support feature | HTTP service plus session store | Auth, tenant isolation, streaming, trace IDs |
| A long-running task executor | Queue/worker or durable workflow | Idempotency, retries, checkpoints, dead-letter handling |
| Triggered by external events | Webhook ingress plus worker | Signature verification, replay protection, payload sanitization |
| Scheduled | Scheduler plus isolated run | Idempotency key, failure alert, last-run audit |
| Part of a larger app | Embedded agent service/module | Typed tools, business logic outside the prompt, app-level auth |

If the agent being shipped started life as a Claude Code plugin, the conversion-side doctrine — strategy choice, capability audit, framework and runtime matrices — lives in the `opencode-authoring` skill's plugin-to-standalone-agent suite; this skill owns everything after the port.

## Picking a Shape — Decision Procedure

The shape table answers "what shape?" but not "how do I decide?" Work top-down so the trigger and the loop drive the choice, not the framework you already know.

1. **What triggers a run?** A human (HTTP/chat), a queue message (worker), an external event (webhook), a clock (scheduler), or another service (embedded). This narrows the table to one or two rows.
2. **How long can a run take, and what does it wait on?** Anything beyond a single request window, or that waits on a human, subagent, or browser, eliminates pure serverless and forces a worker, durable runtime, or managed agent.
3. **What state must survive?** If the answer is "transcript plus artifacts plus memory plus tool credentials," the shape must externalize all of those; a stateless function is already disqualified regardless of how cheap it looks.

Worked example: an agent that drafts replies to inbound support tickets. Trigger is a webhook on ticket creation. Duration is 20-90 seconds with one retrieval call and one model step. State is the transcript, kept for audit. Right shape: webhook validates and enqueues; a worker runs the loop; the transcript goes to a session store. Wrong shape: the entire loop inside the webhook handler, because the handler will time out on the slow case and lose the transcript on retry.

## Cost and Loop Discipline

Agents fail by doing too much as often as by doing too little. Production bounds must be enforced by the runtime, not hoped for in the prompt.

| Bound | What it prevents | Typical enforcement |
|---|---|---|
| Max turns / max steps | Infinite ReAct loops, ping-pong with a broken tool | Counter in the loop; hard stop with a recorded reason |
| Wall-clock timeout | Stuck on a slow tool, hung browser, deadlock | Outer deadline on the whole run |
| Cost ceiling | Token runaway, subagent fan-out explosion, silent model upgrade | Per-run and per-tenant spend cap; abort and alert |
| Loop detector | Repeated thoughts, repeated tool calls, no-progress retries | Hash recent steps; abort on repetition above a threshold |
| Concurrency cap | Thundering herd of subagents or tool calls against a shared dependency | Queue with bounded parallelism and backpressure |

A prompt sentence like "be efficient" is not any of these. The runtime enforces; the prompt only encourages. Detail lives in `references/packaging-serving.md` and `references/observability.md`.

## Release Gate

Before promotion, verify:

- Current prompt/model/tool/policy versions are recorded.
- Golden suite passes.
- Deployment has max turns, wall-clock timeout, and cost ceiling.
- Telemetry emits trace/session IDs and redacts sensitive content by default.
- Health checks exercise model/tool/storage dependencies, not just process liveness.
- Rollback restores the whole behavior bundle, not only code.

### Pre-Flight Walkthrough

Each gate item should produce a concrete artifact or signal before promotion. If any row is "we'll check it after launch," the gate failed.

| Gate item | Concrete evidence |
|---|---|
| Versions recorded | A release manifest committed or published with code, prompt, model, tool, retrieval, memory, eval, and policy versions |
| Golden suite passes | A CI or eval-run report showing pass/fail per case against the manifest above |
| Loop bounds present | Config showing max turns, wall-clock timeout, cost ceiling, and loop-detector threshold actually wired into the runtime |
| Telemetry redacts | A sample trace inspected by hand showing session/trace IDs present and sensitive content scrubbed |
| Health checks real | A `/healthz` or equivalent that fails when model auth, storage, queue, or a key tool dependency is broken |
| Rollback is whole | A tested rollback command that restores the entire previous manifest, not only the container image |

## Operating Cadence

Deployment is not a moment; it is a rhythm. Cadence prevents the two equal-opposite failures: never looking at production, and reacting to every transcript as if it were an incident.

| Cadence | Activity | Reference |
|---|---|---|
| Daily | Scan alerts: cost, error rate, loop detector, refusal rate. Triage anything that fired. | `observability.md` |
| Weekly | Review failed, high-cost, and long runs. Sample one success for drift. Check tool-error and permission-denial trends. | `operating-live-agents.md` |
| Per release | Record the manifest, run the golden gate, canary, watch metrics, archive the rollback bundle. | `versioning-rollout.md` |
| Monthly | Re-run the full golden suite against current production. Confirm provider deprecation notices. Consolidate lessons. | `self-improvement-loop.md` |
| On surprise | Contain, pin the run, decide scope, then diagnose. Do not edit the prompt under pressure. | `operating-live-agents.md`, `tweaking-live-agents.md` |

## Incident First Response

When an agent misbehaves in production, the first 15 minutes are for containing and preserving evidence, not for fixing.

1. **Decide contain vs. monitor.** If the agent is taking side effects (sends, writes, spend, deletes), route it to a no-side-effect mode or roll back to the previous manifest. If the failure is quality-only, monitor and capture.
2. **Pin the run.** Save trace ID, session ID, prompt/model/tool versions, and the user-visible symptom before they age out of retention. A trace you cannot replay is a failure you cannot diagnose.
3. **Check scope.** One user, one tenant, one task type, or all traffic? Scope decides incident vs. anomaly, and decides whether to roll back everyone or just isolate.
4. **Do not edit the prompt under pressure.** Diagnosis belongs to `operating-live-agents.md`; targeted fixes belong to `tweaking-live-agents.md`. A 3 AM prompt edit usually becomes tomorrow's incident.
5. **Record the decision.** Even "monitoring, no action" goes in the run log so the weekly review can catch a pattern that no single incident revealed.

## Reference Router

| Load | When |
|---|---|
| `references/packaging-serving.md` | Choosing CLI/service/worker/webhook/scheduled/embedded shapes; container rules; current Claude Agent SDK and LangSmith deployment options |
| `references/scheduled-event-driven-agents.md` | The agent runs unattended — cron/webhook/queue/watcher triggers, wake-up prompts, idempotency, overlap control, notification contract |
| `references/ci-resident-agents.md` | The CI system OR a platform-native AI runtime IS the runtime — GitHub Actions (claude-code-action), GitLab CI (headless CLI), GitHub Copilot cloud agent + automations + custom agents + skills + hooks + plugins, GitLab Duo Chat/Workflow/Agent Platform/Code Review, framework-aware CI wiring for every foundry framework (raw provider loop, OpenAI Agents SDK, LangGraph, CrewAI, LlamaIndex, Microsoft Agent Framework, DSPy, Pydantic AI, smolagents, NeMo Agent Toolkit, Vercel AI SDK, Mastra, Google ADK, Claude Agent SDK, Copilot SDK), OIDC auth, concurrency, prompt-injection defenses, platform-native-vs-CI-vs-webhook-service decision |
| `references/zai-provider-config.md` | ZAI (GLM) provider configuration: model IDs, auth (`ZAI_API_KEY`), OpenAI-compatible endpoint, per-framework wiring (OpenCode, Hermes, LangChain, CrewAI, OpenAI Agents SDK, Pydantic AI, Vercel AI SDK, smolagents, MAF, ADK, Copilot SDK, custom loop), container env-var patterns, Vertex AI (ZAI.org) alternative |
| `references/hermes-container-deploy.md` | The full Hermes runtime in a container: s6-overlay supervision tree, config.yaml, swarm profiles, gateway, bot, restic backup, multi-host fleet topology, ZAI-specific wiring |
| `references/opencode-container-deploy.md` | Running OpenCode itself in a container: server / one-shot / webhook shapes, opencode.json for container, persistent state, the 1.18.3 local-plugin bug workaround, multi-tenant, Kubernetes StatefulSet |
| `references/framework-deploy-matrix.md` | Per-framework Docker recipes for all 13 harnesses (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop) with provider config, health checks, pitfalls, and K8s patterns |
| `assets/deploy-templates/` | Copyable last-mile artifacts: Dockerfile, cron wrapper (lock/heartbeat/budget), systemd service+timer, GitHub Actions scheduled run, webhook worker |
| `assets/deploy-templates/docker-compose-templates/` | Seven worked docker-compose files: single-agent, multi-tenant, langgraph-checkpointer, hermes-s6, opencode-serve, cron-gardener, eval-runner. Pair with the framework Dockerfiles from `framework-deploy-matrix.md` |
| `references/streaming-and-progressive-ux.md` | Streaming agent output to users without breaking structured-output guarantees — SSE/WebSocket/polling transport choice, the progressive-disclosure UX ladder, event-envelope pattern, Claude API + Agent SDK streaming mechanics, backpressure/reconnection, progress UX for long tool calls. For the harness-layer streaming mechanics (token streams, partial JSON, backpressure at the loop), see the `agent-harness` skill |
| `references/observability.md` | Designing traces, metrics, dashboards, alerts, redaction, and agent-specific production signals |
| `references/versioning-rollout.md` | Versioning prompts, models, tools, memory, and rollout/rollback manifests; provider deprecation risk |
| `references/operating-live-agents.md` | Diagnosing a deployed behavior surprise from transcripts, traces, policy logs, and layer mapping |
| `references/tweaking-live-agents.md` | Making one targeted fix to a live agent without destabilizing adjacent behavior |
| `references/self-improvement-loop.md` | Turning observed failures into regression evals, fixes, and curated durable lessons |
| `references/infrastructure-and-scaling.md` | Production infrastructure layer: Kubernetes (StatefulSet/Deployment/CronJob, multi-replica, HPA, PDB), multi-region DR, container security (seccomp, AppArmor, read-only root, capabilities, admission control), sidecar patterns (OTel, Vault Agent, egress proxy), queue-based scaling (SQS/Kafka/Redis), provider rate limiting, FinOps (Helicone/Lunar/Portkey/Cloudflare, per-tenant cost attribution, spend alerts, chargeback/showback) |

## Pitfalls

1. **Deploying without a golden suite.** A demo transcript is not a regression gate. Build the suite in `agent-evals`, then make it a release blocker.
2. **No cost ceiling or loop detection.** Agents fail by doing too much as often as by doing too little. Set max turns, wall-clock limits, and spend alerts before launch.
3. **Prompt changes with no version tracking.** A dashboard edit at 3 PM becomes an unexplained incident at 5 PM. Treat prompts like code.
4. **Being surprised by model deprecation.** Providers retire models and move aliases. Inventory model use and run replacement evals early.
5. **Observability added after the incident.** If traces were absent during the failure, you cannot reconstruct the real trajectory. Instrument before traffic.
6. **Rollback that only rolls back code.** If the model, prompt, tool schema, or memory changed separately, restore the complete behavior manifest.
7. **Treating a dev agent as a production agent.** In-process state, "latest" model aliases, and dashboard-edited prompts are fine on the builder's machine and wrong in front of users. See the "From Dev Agent to Production Agent" table.
8. **Editing the prompt under incident pressure.** A 3 AM prompt change is rarely attributed, rarely eval-gated, and frequently the root cause of the next incident. Contain, pin the run, diagnose first.
9. **Observing only happy paths.** Teams that capture wins but not failures, near misses, hook blocks, and cost-ceiling aborts have no fuel for the self-improvement loop and repeat the same bug class quarter after quarter.
