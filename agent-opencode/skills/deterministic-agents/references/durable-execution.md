# Durable Execution for Agents — Crash-Safe, Resumable, Auditable Runs

> Last verified: 2026-07. This space is moving fast — Temporal's OpenAI Agents SDK integration went GA March 2026, Cloudflare shipped Dynamic Workflows May 2026, AWS added AgentCore Step Functions integrations March 2026. Re-verify product specifics before committing.

Agent runs are long (minutes to days), expensive (every step is a paid LLM call), and interrupted constantly — deploys, OOMs, provider 529s, and human-approval pauses that last a weekend. Durable execution makes a run **survive its process**: every completed step's result is journaled; after a crash, the run resumes from the journal, skipping (not re-paying, not re-sending) everything already done.

## The core model

All the runtimes below share one architecture, with different packaging:

1. **Workflow code** (the orchestration function) must be *deterministic*: on replay it re-executes from the top, and recorded step results are substituted for real execution. Random numbers, `now()`, network calls, and LLM calls are **banned in workflow code** — each runtime provides deterministic substitutes (`workflow.now()`, side-effect wrappers).
2. **Steps/Activities** are where nondeterminism lives: LLM calls, tool calls, HTTP, anything. Each step's result is journaled on completion. **The LLM call always sits inside a step, never in the workflow body** — that's what makes crash-recovery skip a completed $2 reasoning call instead of re-running it.
3. **Retries with backoff** are per-step policy (max attempts, backoff curve, non-retryable error types) — declared, not hand-rolled.
4. **Pauses** (human-in-the-loop, timers) are first-class: the run consumes no compute while waiting days for an approval signal.

Note the pairing with `idempotency-and-replay.md`: the journal gives you *at-least-once step execution* (a step that crashed mid-flight re-runs), so effectful steps still need idempotency keys. Durable execution removes *lost progress*; idempotency removes *duplicate effects*. You need both.

## The options (July 2026)

### Temporal
The heavyweight incumbent — self-host the OSS server or use Temporal Cloud. Workflows in Python/TS/Go/Java/.NET; every step is an Activity with rich retry policy; event-history replay; Signals/Updates for human-in-the-loop; `workflow.patched()` API for versioning in-flight runs. Agent story is now first-class: the [OpenAI Agents SDK integration went GA March 2026](https://temporal.io/blog/announcing-openai-agents-sdk-integration) (`TemporalRunner` wraps each agent invocation as an Activity; `activity_as_tool` turns activities into agent tools), plus documented patterns for the Vercel AI SDK and agentic sandboxes. OpenAI, Replit, and Lovable run agents on it. Watch: event-history size limits (don't stuff full transcripts through workflow state — pass references to blob storage), and the determinism rules are real (a stray `datetime.now()` in workflow code breaks replay).

### Inngest (+ AgentKit)
TypeScript-first, serverless-native: functions run on your existing deploy target (Vercel/Lambda/containers); Inngest delivers events and journals `step.run()` results — nothing to operate. [AgentKit](https://agentkit.inngest.com/) is its agent framework: Agents composed into Networks with a Router, every model/tool call a durable step by construction; `useAgent` React hook streams the durable run to a frontend. The fastest path from "TypeScript team" to "durable agent in production this week." Watch: TS-centric (Python support is thinner); step granularity is yours to get right.

### Restate
Lightweight self-hostable journaling engine — a single binary, no database, no separate workers. Durable functions + **Virtual Objects**: stateful entities keyed by e.g. conversation ID with built-in state and single-writer concurrency — a natural fit for durable *sessions* (one object per conversation, serialized turns, state that survives). Deliberately SDK-agnostic: documented [integrations wrap Pydantic AI, the OpenAI Agents SDK, Vercel AI SDK, and Google ADK](https://docs.restate.dev/ai/patterns/durable-agents) in durable execution rather than replacing them. Watch: smaller ecosystem than Temporal; you host it (that's also its appeal).

### LangGraph checkpointers + LangGraph Platform
In-framework persistence: a checkpointer (Postgres/SQLite/Redis/DynamoDB backends) saves graph state every superstep, enabling resume-from-checkpoint, time-travel, and `interrupt()` for human-in-the-loop. **Know exactly what this is: checkpointing, not full durable execution.** Open-source LangGraph gives you saved state, but no execution guarantee around it — no distributed lease preventing two workers from resuming the same `thread_id` concurrently, no managed retry/backoff worker, no queueing; those are yours to build, or you buy **LangGraph Platform** (the hosted runtime), which adds the task queue, retries, and scaling around the checkpointer. Alternatively, run a LangGraph graph *inside* a Temporal/Restate/Inngest step. Watch: the "my checkpointer = durability" assumption is the #1 way teams get burned here.

### Cloudflare Workflows + Durable Objects (+ Agents SDK)
Edge-native durable execution: `step.do(name, cb)` persists each step's result; interrupted workflows resume from the last successful step; `step.sleep()` for long pauses. Durable Objects give single-threaded stateful actors (the Agents SDK makes *an agent = a Durable Object*, with WebSocket state and per-agent storage); `AgentWorkflow` bridges the two so a workflow can report progress to live clients. 2026 brought serious scale (50k concurrent instances/account, 300 creates/sec) and [Dynamic Workflows](https://blog.cloudflare.com/dynamic-workflows/) (MIT-licensed): workflow *code* that differs per tenant/agent/request — the primitive for agents that write plans which then execute as real durable workflows (plan-then-execute from `explicit-control-flow.md`, made durable). Watch: you're on Workers runtime (JS/TS/WASM, CPU-time limits per step); ecosystem lock-in is the trade for near-zero ops.

### AWS Step Functions
Managed state machines defined in ASL (JSON/YAML), not general code — the most "workflow, least code" option. Per-state retry/backoff/catch declared in the definition; `waitForTaskToken` callbacks give human-in-the-loop pauses up to a year (Standard workflows); Map states fan out agents in parallel. March 2026 added [direct Bedrock AgentCore integrations](https://aws.amazon.com/about-aws/whats-new/2026/03/aws-step-functions-sdk-integrations/) — invoke agent runtimes with built-in retries, no Lambda glue. Executions are fully audited state-transition histories. Watch: ASL is awkward for complex logic (you'll push it into Lambdas anyway); 256KB payload limit between states (pass S3 references); Express vs Standard choice matters (Express: 5-min max, at-least-once — Standard for agents).

## Comparison

| | Where the LLM call sits | Retry/backoff | Human-in-the-loop pause | Versioning in-flight runs | Hosting |
|---|---|---|---|---|---|
| **Temporal** | Activity | Per-activity policy, rich | Signals/Updates; pauses cost nothing | `workflow.patched()` — explicit, powerful, fiddly | Self-host or Cloud |
| **Inngest** | `step.run()` / AgentKit step | Per-step config | `step.waitForEvent()` (days+) | Function versioning; in-flight runs finish on old code | SaaS + your serverless compute |
| **Restate** | Journaled handler step | Per-invocation policy | Durable promises/awakeables | Service versioning; journal replays against registered version | Self-host (single binary) or Cloud |
| **LangGraph OSS** | Graph node | **Yours to build** | `interrupt()` + checkpointer | Yours (checkpoint schema compat) | Yours entirely |
| **LangGraph Platform** | Graph node | Managed queue + retries | `interrupt()`, managed | Deployment revisions | Hosted / hybrid |
| **Cloudflare** | `step.do()` | Per-step config | `step.waitForEvent()` / DO alarms | Gradual deployments; instances pinned to version | Cloudflare only |
| **Step Functions** | Task state (Bedrock/AgentCore/Lambda) | Per-state ASL policy | `waitForTaskToken` (≤1 year) | New state-machine version/alias; in-flight finish on old | AWS only |

## Decision table by need

| Your situation | Reach for |
|---|---|
| Polyglot org, complex long-lived workflows, ops capacity or budget for Cloud | **Temporal** |
| TypeScript team on serverless, want durable agents shipping this week, zero infra | **Inngest AgentKit** |
| Want self-hosted + lightweight; conversation/session-keyed agents; keep your existing agent SDK | **Restate** |
| Already deep in LangGraph, need pause/resume + time-travel, single-worker or willing to buy Platform | **LangGraph checkpointer (+ Platform for production)** |
| Edge/Workers stack; agents that generate plans to execute durably; per-agent stateful actors | **Cloudflare Workflows + DO/Agents SDK** |
| AWS shop, audit-heavy, orchestrating Bedrock/AgentCore + AWS services, minimal custom code | **Step Functions** |
| Short-lived agent (<minutes), acceptable to re-run whole thing on failure | **None — a bounded loop + idempotent tools + result cache is enough.** Durable execution is for runs whose loss or duplication hurts |

## Pitfalls

1. **Nondeterministic workflow code.** `now()`, `random()`, dict-ordering, or — the agent-specific classic — an LLM call in the workflow body instead of a step. Symptom: replay diverges from history and the runtime errors (Temporal: non-determinism error) or silently mis-resumes. Every model call goes in a step/activity. No exceptions.
2. **Transcripts through workflow state.** Multi-hundred-KB message histories blow event-history/payload limits (Temporal history caps, Step Functions' 256KB). Store transcripts in blob storage/DB; pass IDs through the workflow.
3. **Step granularity wrong in both directions.** One giant step ("run the whole agent") = a crash re-runs everything, journaling bought nothing. A step per token = journal overhead dominates. Right size: one step per LLM call and per effectful tool call.
4. **Retrying non-retryable failures.** A 400 (bad schema), a content refusal, or a validation failure will fail identically 10 times — classify errors and mark these non-retryable; retry budget is for 429/5xx/timeouts. Pair with the bounded-repair loop from `structured-outputs.md` for the fixable subset.
5. **Deploying workflow-code changes over in-flight runs.** Runs mid-flight replay against the *new* code and diverge from their journal. Use the runtime's versioning mechanism (patch/pin/version-alias) — "we deploy and old runs break" is a choice, not fate.
6. **Assuming the journal dedupes your side effects.** It dedupes *completed* steps. A step that crashed after the HTTP call but before journaling re-runs — the idempotency key inside the step (see `idempotency-and-replay.md`) is what makes that safe.
7. **Human-approval pauses without expiry.** A run parked on approval forever is a leak — and an approval granted three weeks later may authorize a stale plan. Timers alongside waits: escalate, re-validate the plan hash (see dry-run/apply in `idempotency-and-replay.md`), or expire.
