# Harness Comparison

Every framework wraps a harness; the harness is what actually runs the
loop, dispatches tools, manages context, and recovers from failures.
This reference maps the major 2026 harnesses to the nine concerns
covered in the other reference files here.

Use this to choose a harness once you know which concerns matter most
for your agent. If you have not yet picked a framework at all, start
with `../../framework-selection/SKILL.md` and come back here to
pressure-test the choice from the harness side.

## The 13 Harnesses

The 2026 production harness landscape, in rough order of "blessed by the
model provider" to "build your own":

| Harness | Vendor / Source | Language(s) | One-liner |
|---|---|---|---|
| **Claude Agent SDK** | Anthropic | Python, TypeScript | The Claude Code harness as a library |
| **OpenAI Agents SDK** | OpenAI | Python, TypeScript (via JS SDK) | Swarm's production successor; handoffs + tool loop |
| **Copilot SDK** | GitHub | Node.js, .NET | Drive Copilot sessions programmatically; fleet mode built in |
| **Google ADK** | Google | Python | Vertex-AI-blessed harness for Gemini |
| **Microsoft Agent Framework (MAF)** | Microsoft | Python, .NET | AutoGen successor; multi-agent runtime host |
| **LangGraph** | LangChain | Python, JavaScript | Graph state machine with checkpointer + interrupts |
| **CrewAI** | CrewAI | Python | Role-based Crews + Flows for stateful ordering |
| **LlamaIndex** | LlamaIndex | Python, TypeScript | FunctionAgent / AgentWorkflow over indexes |
| **Pydantic AI** | Pydantic | Python | Typed agent with dependency injection |
| **smolagents** | Hugging Face | Python | Code-as-action local-first agent |
| **Vercel AI SDK** | Vercel | TypeScript | JavaScript-native generateText/streamText + tool loop |
| **Mastra** | Mastra | TypeScript | JS/TS workflows + agent primitives |
| **Custom / raw provider-SDK loop** | You | Any | The 50-line loop from `agent-loop.md` |

## Concern Coverage Matrix

The nine concerns covered in this skill's reference files. For each
harness: ✅ = built-in and production-ready, ⚠️ = supported but requires
wiring, ❌ = not built-in (you implement).

| Harness | Loop | Context mgmt | Sessions | Error recovery | Streaming | HITL | Observability | Cache | Doom-loop |
|---|---|---|---|---|---|---|---|---|---|
| Claude Agent SDK | ✅ | ✅ compaction | ✅ durable | ✅ retries | ✅ token+tool | ✅ permission modes | ✅ OTel | ✅ prompt cache | ⚠️ step caps |
| OpenAI Agents SDK | ✅ | ⚠️ manual | ⚠️ manual | ✅ retries | ✅ token+tool | ✅ handoffs | ✅ OTel | ✅ prompt cache | ⚠️ step caps |
| Copilot SDK | ✅ | ✅ | ✅ cloud sessions | ✅ | ✅ | ✅ hooks | ✅ OTel | ✅ | ✅ fleet mode |
| Google ADK | ✅ | ⚠️ manual | ⚠️ | ✅ | ✅ | ⚠️ | ✅ Vertex traces | ✅ | ⚠️ |
| MAF | ✅ | ⚠️ manual | ✅ runtime host | ✅ | ✅ | ⚠️ | ✅ Azure Monitor | ✅ | ⚠️ |
| LangGraph | ✅ graph | ✅ checkpoint | ✅ checkpointer | ⚠️ manual | ✅ | ✅ interrupt_before | ✅ OTel/LangSmith | ✅ | ⚠️ step caps |
| CrewAI | ✅ flow | ⚠️ manual | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ✅ OTel | ⚠️ | ⚠️ |
| LlamaIndex | ✅ workflow | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ✅ OTel | ✅ | ⚠️ |
| Pydantic AI | ✅ | ⚠️ manual | ⚠️ | ✅ retries | ✅ | ⚠️ | ✅ OTel | ✅ | ⚠️ |
| smolagents | ✅ code-action | ⚠️ | ❌ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| Vercel AI SDK | ✅ | ⚠️ manual | ⚠️ | ✅ | ✅ streamText | ⚠️ | ✅ OTel | ✅ | ⚠️ |
| Mastra | ✅ workflow | ⚠️ | ✅ memory | ⚠️ | ✅ | ⚠️ | ✅ OTel | ⚠️ | ⚠️ |
| Custom loop | you build | you build | you build | you build | you build | you build | you build | you build | you build |

Read the matrix as: vendor-blessed SDKs (Claude, OpenAI, Copilot, ADK,
MAF) ship production defaults for most concerns. Graph and workflow
frameworks (LangGraph, CrewAI, LlamaIndex, Mastra) give you the shape
but require wiring for production concerns. Typed and code-as-action
frameworks (Pydantic AI, smolagents) optimize for correctness in a
narrow niche. The custom loop is the escape hatch when nothing fits.

## Per-Harness Notes

### Claude Agent SDK

The closest to a "batteries-included" harness. Built-in compaction,
durable sessions, permission modes (`acceptEdits`, `plan`, `default`,
`bypassPermissions`), prompt-cache-aware context assembly, and OTel
export. The harness Claude Code runs is this SDK; you inherit its
production hardening.

- **Loop**: tool-use loop with `stop_reason` handling.
- **Context**: automatic compaction at provider threshold; preserves
  recent turns.
- **Sessions**: durable across process restarts; resume by session ID.
- **HITL**: permission modes + `PreToolUse` hooks (in the SDK host) or
  the OpenCode plugin equivalent.
- **Observability**: OTel via `cl_typegen_traceprocessor`; structured
  tool spans.
- **Doom-loop**: step cap via `max_turns`; no repetition detector
  built in.
- **Best for**: Claude-first agents that want Claude Code's runtime
  without the CLI. The default-pick if you are on Anthropic.

### OpenAI Agents SDK

The production successor to Swarm. Handoffs are the signature primitive
— an agent can hand off to another agent mid-turn, with the receiving
agent inheriting the conversation.

- **Loop**: tool-use loop with handoffs.
- **Context**: manual; you write the compaction. The SDK does not
  auto-compact.
- **Sessions**: manual; the SDK is stateless across process restarts.
  Pair with a session store.
- **HITL**: handoffs can route to a human-in-the-loop agent; no
  built-in permission mode.
- **Observability**: OTel via the SDK's trace processor.
- **Doom-loop**: `max_turns` per agent; no cross-agent repetition
  detector.
- **Best for**: multi-specialist agents on OpenAI models where
  handoffs are the natural shape.

### Copilot SDK

Drive Copilot programmatically: create sessions, register custom
agents, attach hooks, dispatch fleet (parallel sub-agents). Cloud
sessions persist on GitHub's infrastructure.

- **Loop**: Copilot's loop, driven from your code.
- **Context**: managed by Copilot; you steer via skills and
  instructions.
- **Sessions**: cloud-resident; resume from any device.
- **HITL**: hooks (`pre-tool-use`, `post-tool-use`) enforce
  structurally.
- **Observability**: OTel; per-session event stream.
- **Doom-loop**: built-in via fleet mode and session limits.
- **Best for**: GitHub-resident workflows where the platform already
  owns identity, audit, and approval flow.

### Google ADK

Vertex-AI-blessed harness for Gemini. Workload Identity Federation
for auth; runs equally well on Vertex or direct API.

- **Loop**: tool-use loop with Gemini's function-calling.
- **Context**: manual compaction; the ADK does not auto-compact.
- **Sessions**: manual; pair with a session store.
- **HITL**: not built-in; implement via tool annotations.
- **Observability**: Vertex AI traces; OTel export.
- **Doom-loop**: step cap; no repetition detector.
- **Best for**: Gemini-first agents, especially on Vertex with
  Workload Identity.

### Microsoft Agent Framework (MAF)

The AutoGen + Semantic Kernel successor. `AgentRuntime` hosts the
loop; multi-agent conversations are first-class (`GroupChat`,
selector models).

- **Loop**: runtime-hosted; you register agents and the runtime
  drives the loop.
- **Context**: manual; compaction is your job.
- **Sessions**: runtime-managed; durable across runtime restarts.
- **HITL**: conversational interrupt pattern; not built-in per-tool.
- **Observability**: Azure Monitor / Application Insights native.
- **Doom-loop**: max conversational rounds; no repetition detector.
- **Best for**: Azure-stack shops; multi-agent conversations where
  AutoGen's GroupChat was the prior shape.

### LangGraph

Graph-based harness. Nodes are LLM or tool steps; edges are routing
logic; state is a typed dict that flows through the graph. The
checkpointer is the signature feature — durable, resumable, HITL
interrupts survive process death.

- **Loop**: the graph itself; cycles are explicit.
- **Context**: manual compaction; the checkpointer preserves state
  across turns, not within a turn.
- **Sessions**: checkpointer-backed (SQLite, Postgres, Redis); resume
  by `thread_id`.
- **HITL**: `interrupt_before` / `interrupt_after` nodes; the graph
  checkpoints and STOPS until resumed with a verdict.
- **Observability**: OTel + LangSmith native.
- **Doom-loop**: step cap on the graph executor; no repetition
  detector.
- **Best for**: explicit-graph agents where branching, retries, and
  HITL are the core shape.

### CrewAI

Role-based Crews (autonomous delegation) inside Flows (event-driven
stateful ordering). Flows are the production shape; Crews embed inside
Flow steps.

- **Loop**: Flow-driven; each step may run a Crew.
- **Context**: manual.
- **Sessions**: manual; Flows have internal state but not durable
  persistence by default.
- **HITL**: CrewAI's `human_input=True` on tasks; coarse.
- **Observability**: OTel; CrewAI's own dashboard.
- **Doom-loop**: max iterations per task; no cross-task detector.
- **Best for**: role-specialist agents (researcher + writer + reviewer)
  where delegation is the natural shape.

### LlamaIndex

FunctionAgent (single agent) or AgentWorkflow (multi-agent) over
LlamaIndex's indexing/retrieval layer. Strong when the agent reads
from indexed sources.

- **Loop**: tool-use loop; AgentWorkflow coordinates multiple agents.
- **Context**: manual; LlamaIndex's indexing layer is separate from
  the conversation context.
- **Sessions**: manual; AgentWorkflow has internal state but not
  durable by default.
- **HITL**: not built-in.
- **Observability**: OTel; LlamaIndex's own tracing.
- **Doom-loop**: max iterations per agent; no workflow-level
  detector.
- **Best for**: agents over indexes, query engines, or RAG-heavy
  workflows.

### Pydantic AI

Typed agents with dependency injection. The signature feature: tool
arguments and agent outputs are typed Pydantic models, validated at
runtime.

- **Loop**: tool-use loop with typed tools.
- **Context**: manual.
- **Sessions**: manual.
- **HITL**: not built-in; implement via typed permission rules.
- **Observability**: OTel; Logfire native.
- **Doom-loop**: `usage_limits` per run; no repetition detector.
- **Best for**: type-safe agents where schema correctness is the
  priority; great for multi-model eval gates.

### smolagents

Code-as-action: the agent writes and executes Python instead of
calling tools. The harness sandboxes the execution.

- **Loop**: code-action loop; the agent emits Python, the harness
  executes it.
- **Context**: manual.
- **Sessions**: none; smolagents is single-run by default.
- **HITL**: not built-in.
- **Observability**: minimal.
- **Doom-loop**: max steps; no repetition detector.
- **Best for**: data analysis, ETL, and local-first tasks where the
  agent benefits from writing actual code. Requires aggressive
  sandboxing — see `../../agent-safety/references/sandboxing-tiers.md`.

### Vercel AI SDK

TypeScript-native. `generateText` / `streamText` / `generateObject`
with a tool loop. Pairs naturally with Vercel's edge and serverless
runtime.

- **Loop**: tool-use loop via `streamText` with `tools` and
  `maxSteps`.
- **Context**: manual.
- **Sessions**: manual; pair with a session store.
- **HITL**: not built-in.
- **Observability**: OTel via `experimental_telemetry`.
- **Doom-loop**: `maxSteps`; no repetition detector.
- **Best for**: TypeScript codebases, especially Vercel/Next.js
  deployments.

### Mastra

TypeScript-native workflows + agent primitives. Workflows support
ordered, stateful execution; agents are the LLM-call layer inside
workflow steps.

- **Loop**: workflow-driven; agents are called from steps.
- **Context**: manual.
- **Sessions**: Mastra Memory for cross-run state.
- **HITL**: step-level suspend/resume.
- **Observability**: OTel.
- **Doom-loop**: workflow step caps; no repetition detector.
- **Best for**: multi-step TypeScript workflows where ordered state
  matters more than free-form agent loops.

### Custom / Raw Provider-SDK Loop

The 50-line loop from `agent-loop.md`. You implement every concern
yourself, exactly to spec.

- **Loop**: yours.
- **Context**: yours.
- **Sessions**: yours.
- **HITL**: yours.
- **Observability**: yours.
- **Doom-loop**: yours.
- **Best for**: when no framework's defaults fit (unusual tools,
  non-standard provider, research codebase, learning the loop
  mechanics). The first version of any production agent should be a
  custom loop — you understand the framework defaults better once you
  have built the loop yourself.

## Choosing

Use this rough decision tree:

1. **Single-model, single-agent, vendor-blessed?** Pick that vendor's
   SDK (Claude / OpenAI / Copilot / ADK / MAF).
2. **Explicit graph with branching, retries, HITL?** LangGraph.
3. **Multi-specialist delegation?** CrewAI Flows or OpenAI Agents SDK
   handoffs.
4. **Over indexes / RAG-heavy?** LlamaIndex.
5. **Type-safety is the priority?** Pydantic AI.
6. **Code-as-action analysis?** smolagents.
7. **TypeScript end-to-end?** Vercel AI SDK or Mastra.
8. **None of the above fit?** Custom loop; add concerns as you need
   them.

The harness you pick sets the default values for every concern in the
matrix above. Read the matrix cell before you commit — a "manual"
cell means you write that concern; a "⚠️" cell means you should not
trust the framework's default in production.

## The Cross-Concern Test

Whatever harness you pick, verify it against the nine concerns:

- Does it expose a hook at every model call, every tool call, every
  compaction? (Observability.)
- Does it have a step cap and a doom-loop detector? (Loop safety.)
- Does it persist sessions at turn boundaries? (Session lifecycle.)
- Does it surface mid-turn errors to the model as tool results? (Error
  recovery.)
- Does it stream the first token within the provider's TTFT budget?
  (Streaming.)
- Does it gate destructive tools with a pre-tool interrupt? (HITL.)
- Does it preserve the prompt-cache prefix across turns? (Caching.)
- Does it compact at 75%, not 100%? (Context management.)
- Does it resume after a crash without re-executing side effects?
  (Session lifecycle, error recovery.)

Any "no" or "manual" is work you do. A harness that answers "yes" to
all nine is rare; the Claude Agent SDK and Copilot SDK come closest in
2026.

## See Also

- `../../framework-selection/SKILL.md` — the framework decision table
  (which framework to pick by feature).
- `../../framework-selection/references/framework-landscape.md` — the
  full 2026 framework comparison and churn log.
- `../../agent-deployment/references/ci-resident-agents.md` — how each
  harness runs as a CI-resident agent.
- `agent-loop.md` (this skill) — the loop every harness implements.
