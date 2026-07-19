> Last verified: 2026-07. Deployment products, serverless limits, and managed-agent options change quickly; re-check current hosting docs before committing to a platform.

# Packaging and Serving Agents

Production agents are not just API calls. They are stateful loops that call tools, write artifacts, wait on users, and sometimes run for minutes or hours. Pick a deployment shape that matches the loop, not just the HTTP entry point.

## Deployment Shapes

| Shape | Best for | Watchouts |
|---|---|---|
| CLI/local agent | Developer copilots, admin utilities, project-local automation | Hard to monitor centrally; user machine becomes the runtime |
| HTTP service wrapping an agent loop | Chat backends, ticket triage, app-embedded agents | Request timeouts, session affinity, streamed output, auth boundaries |
| Queue/worker consumer | Long-running tasks, batch jobs, retriable work | Idempotency and duplicate deliveries are mandatory |
| Event/webhook-triggered agent | CI alerts, inbound email, incident signals | Validate payloads; bound who can trigger work |
| Scheduled agent | Daily reports, periodic audits, stale-ticket cleanup | Jobs must be idempotent; do not let context drift silently |
| Embedded application agent | Product features where the agent is one component | Keep business logic outside the model; expose typed tools |

### Shape → When → Tradeoff → Concrete Example

The table above names the shapes; this one decides between them. Read it as: pick the shape whose tradeoff you can actually live with.

| Shape | Reach for it when... | Accept the tradeoff... | Concrete example |
|---|---|---|---|
| CLI/local | The user is one trusted operator on their own machine | No central monitoring, no multi-tenant isolation, runtime depends on the user's environment | A developer copilot that runs against a local repo and writes to the user's working directory |
| HTTP service | A user-facing chat or app feature needs synchronous responses with streaming | You own auth, session affinity, request timeouts, and tenant isolation | A support-triage endpoint that streams a draft reply back to the chat UI within a request window |
| Queue/worker | A run can exceed one request window or must survive restarts | You own idempotency keys, retry policy, dead-letter handling, and checkpoint state | A "summarize this 200-page PDF" job that fans out retrieval and may take minutes |
| Webhook + worker | An external system (CI, email, monitoring) triggers work | You must verify signatures, dedupe retries, and bound who can trigger side effects | A code-review bot that acts when a pull-request webhook fires |
| Scheduled | Work is periodic and not triggered by a user | Jobs must be idempotent and must not silently drift in context | A nightly job that closes stale issues and posts a summary |
| Embedded | The agent is one component of a larger product with its own auth and UI | Business logic must live in code, not the prompt; tools must be typed and scoped | An in-app assistant that drafts, but the app's own service layer sends and logs |

If two shapes look plausible, the tie-breaker is always state survival: whichever shape can lose a process without losing the run is the safer default.

## Current Managed Options

- The [Claude Agent SDK hosting docs](https://code.claude.com/docs/en/agent-sdk/hosting.md) describe a subprocess model: each SDK session spawns a `claude` CLI process with local transcripts, working-directory state, and a session lifecycle. That makes persistence, session affinity, and per-tenant filesystem isolation first-class deployment concerns.
- The same docs point to [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) when you want Anthropic to host the agent and sandbox instead of running your own data plane.
- [LangSmith Deployment](https://docs.langchain.com/langsmith/deployment) is now positioned as a framework-agnostic agent runtime for LangGraph, Claude Agent SDK, CrewAI, AutoGen, Google ADK, and other stacks, with cloud, self-hosted, and standalone server options.
- Durable-execution-backed workers remain the right answer when a workflow must survive crashes and resume safely. Use `deterministic-agents/references/durable-execution.md` for the runtime comparison rather than duplicating it here.

### Choosing Between Managed Options

The managed options above are not interchangeable; each one trades off control differently.

| Option | You keep control of... | You hand off... | Watch out for... |
|---|---|---|---|
| Self-hosted SDK subprocess (Claude Agent SDK hosting model) | Data plane, filesystem layout, session lifecycle | Nothing — you run it | Per-tenant filesystem isolation, session affinity, transcript durability |
| Managed Agents (provider-hosted agent + sandbox) | Prompts, tools, policy | Data plane, sandboxing, scaling | Vendor lock-in on the runtime; verify egress, storage, and audit controls |
| LangSmith Deployment (framework-agnostic runtime) | Framework choice (LangGraph, Claude Agent SDK, CrewAI, AutoGen, Google ADK) | Runtime hosting, scaling | Confirm which frameworks are first-class vs community-supported for your use |
| Durable-execution worker | Everything; framework-agnostic | Nothing | You own idempotency, checkpoints, and replay semantics |

The decision is not "managed vs self-hosted" in the abstract; it is "which layer do I want to own the incident for at 3 AM?" Own the layer where your requirements diverge from the default; hand off the layer where the default already meets your bar.

## Common Shape Combinations

Real deployments usually combine shapes rather than pick one. These combinations recur:

| Combination | Pattern |
|---|---|
| Serverless webhook + queue + worker | Webhook validates, signs, and enqueues in milliseconds; a worker owns the loop and the timeout budget. The most common shape for event-driven agents. |
| HTTP service + session store + async worker | The synchronous path streams a partial response; long work continues in a worker; the UI polls or subscribes for completion. |
| Scheduled trigger + worker + object storage | A clock fires a worker, which produces artifacts in durable storage and posts a summary. Idempotency key prevents double-runs. |
| Embedded agent + app service + tool gateway | The agent drafts; the application's own service layer performs and logs every side effect; the agent never holds credentials for sends. |

When you find yourself adding queueing, checkpoints, or a separate worker to a "simple HTTP service," you are rediscovering one of these combinations. Name it explicitly so the next person reads the architecture, not the accident.

## Containerization Rules

1. **Secrets enter at runtime.** Inject API keys through environment variables, workload identity, a secret manager, or a credential-injecting proxy. Never bake secrets into images, layers, examples, or test fixtures.
2. **State is external.** Session transcripts, memory, vector indexes, uploaded files, and output artifacts need durable storage. Container memory and ephemeral disk are caches, not records.
3. **The working directory is scoped.** One tenant or task per workspace unless you have a hard isolation reason and explicit path discipline.
4. **Health checks exercise the real path.** A `/healthz` that only says the process is alive misses the failure that matters: model auth broken, MCP server disconnected, queue stuck, or trace exporter failing. Add a lightweight synthetic agent turn or dependency probe.
5. **The image is boring.** Install exact dependencies, run as non-root where possible, set resource limits, and avoid post-start package installation except in disposable development environments.

### Containerization Checklist

Use this as a gate before the first image goes anywhere a user can reach it.

| Item | Done when... | Common failure |
|---|---|---|
| Secrets | Keys are injected at runtime from env, workload identity, secret manager, or proxy; none appear in image layers, build args, examples, or fixtures | An API key baked into a base image layer that survives every rebuild |
| State | Transcripts, artifacts, memory, and indexes live outside the container; a `docker kill` + restart loses no run | "We'll persist the transcript later" — the first crash loses the audit trail |
| Workspace scope | Each session or tenant gets its own working directory; cross-tenant path access is impossible by construction | One shared `/workspace` that lets session B read session A's uploads |
| Health check | `/healthz` fails when model auth, storage, queue, or a critical tool is broken — not only when the process is dead | A liveness probe that stays green while the agent returns 500s to every user |
| Resource limits | CPU, memory, and (where relevant) GPU limits are set; an runaway loop gets killed, not the node | No memory limit; one fan-out loop OOMs the host and takes other tenants with it |
| Image hygiene | Pinned dependencies from a lockfile, non-root user, no post-start `pip install`, minimal base | "It worked on the builder's laptop" because the laptop had extra packages installed |
| Egress | Outbound network is scoped to the model provider, retrieval source, and approved integrations; everything else is denied | An agent that can curl any URL because egress was left open |

## Serverless Versus Long-Running

Serverless works when each task is short, stateless, and can finish within the platform timeout. Many agent loops do not fit: they may need multi-turn user input, subagent fanout, streamed responses, tool retries, browser automation, or durable checkpoints.

Use serverless for thin ingress, webhook validation, task enqueueing, and small deterministic preprocessors. Use a long-running worker, container, or managed agent runtime for the actual loop when the task can exceed one request window or needs local workspace state.

### Timeout Math

Before choosing serverless for the loop itself, add up the worst plausible run. If the sum exceeds the platform's max execution window, serverless is the wrong shape for the loop (it may still be right for the ingress in front of it).

| Phase | Typical contributor | Example budget |
|---|---|---|
| Model turns | (turns) x (per-turn latency, including tool calls) | 6 turns x 8 s = 48 s |
| Tool calls | sum of slow-tool latencies (retrieval, browser, shell) | 1 browser call at 15 s + 2 retrieval calls at 3 s = 21 s |
| Retries | one retry per flaky dependency under a tight deadline | 1 x 10 s = 10 s |
| Streaming tail | time to flush the final response after the last model token | 2 s |
| Buffer | headroom for cold start, queueing, slow provider p99 | 20-30% of the above |

Worked example: the sum above is roughly 81 s plus buffer, so ~100-105 s. On a platform whose default function timeout is 60 s, the loop does not fit — even though the *median* run finishes in 30 s. The median lies; budget for the p99. If the platform cap is 15 minutes and your p99 is 100 s, serverless fits with margin. If the cap is 60 s and your p99 is 100 s, move the loop to a worker or managed agent runtime and keep serverless only for the webhook that enqueues.

The same arithmetic applies to cost ceilings: a serverless function that times out mid-loop has still spent the tokens. A cost cap that is only checked at the end of a run cannot prevent runaway inside one.

## Session and State Storage

Classify state explicitly:

| State | Storage |
|---|---|
| Conversation transcript | Session store, database, or object storage |
| Task artifacts | Object storage or project workspace volume |
| Memory and learned facts | Versioned memory store, database, or RAG index |
| Tool credentials | Secret manager or outbound proxy, not model context |
| Run metadata | Trace/span store plus relational run table |

The Claude Agent SDK docs note that session-store adapters mirror transcripts, not all memory files or working-directory artifacts. If you rely on resumability, test a real crash/restart path and verify every required artifact comes back.

## Release Checklist

- Image builds reproducibly from lockfiles.
- Runtime receives secrets from an approved injection path.
- Each session has a scoped workspace and tenant identity.
- Session persistence is tested by killing and resuming a run.
- Health checks cover model auth, storage, queue, and tool dependencies.
- Deployment has a cost ceiling, max turns, wall-clock bound, and loop detector.
- Rollback means restoring prompt/model/tool versions, not only container code.
