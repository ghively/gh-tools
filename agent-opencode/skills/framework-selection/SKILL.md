---
name: framework-selection
description: "Choosing and getting productive in an agent framework or SDK: raw tool-call loops, LangGraph/LangChain, CrewAI, LlamaIndex, Microsoft Agent Framework, Claude Agent SDK, DSPy, Pydantic AI, smolagents, and profiling wrappers. Use after agent design establishes scope, task shape, tools, authority, and failure modes. Does not cover pre-code design (see agent-design), model choice (see model-selection), or durable/deterministic execution mechanics (see deterministic-agents)."
---

# Framework Selection

Framework choice is stage 7 of agent design. Choose it after the workload, tool surface, authority, and failure modes are known. The right default is often no framework: a provider SDK call with tools and a loop you can read.

## When to Use

- You have a designed agent/workflow and need to choose an implementation stack.
- You need a quickstart for LangGraph, CrewAI, LlamaIndex, DSPy, Microsoft Agent Framework, or NeMo Agent Toolkit.
- You are migrating from a stale framework or deprecated helper.
- You need to compare local-model support across frameworks.
- You need to decide whether a framework's abstraction earns its cost.

**Don't use for:** deciding whether the system should be an agent at all (`agent-design` skill), choosing cloud/local models (`model-selection` skill), making retries, replay, and side effects deterministic (`deterministic-agents` skill), or building the runtime loop itself (`agent-harness` skill — this skill helps you *pick* a framework; the harness skill covers what the framework's runtime actually does).

## Doctrine: Prototype the Raw Loop First

Before adopting a framework, write or sketch the minimal loop:

1. Send messages + tool schemas to the model.
2. Execute selected tool call.
3. Append result.
4. Stop on answer, max steps, budget, or validator success.

If the raw loop is enough, stop. Adopt a framework only when you need explicit graph state, checkpointing, human interrupts, multi-agent ergonomics, data/RAG integrations, typed dependency injection, optimizer support, or deployment/observability features.

## Decision Table

| Dominant need | Reach for |
|---|---|
| One model and a few tools | No framework; provider SDK loop |
| Standard tool-calling loop in LangChain ecosystem | `langchain.agents.create_agent` |
| Explicit branches, retries, checkpointing, HITL | LangGraph hand-built `StateGraph` |
| Role/task multi-agent prototype | CrewAI Crews |
| Production role/task app with stateful ordering | CrewAI Flows |
| Agent over indexes, query engines, RAG tools | LlamaIndex `FunctionAgent` / `AgentWorkflow` |
| Coding/filesystem/shell agent with Claude Code harness | Claude Agent SDK |
| Type-safe agent with dependency injection | Pydantic AI |
| Code-as-action local-first agent | smolagents |
| Microsoft stack or AutoGen/Semantic Kernel migration | Microsoft Agent Framework |
| Metric-driven prompt/program optimization | DSPy |
| Profiling/eval/observability wrapper over existing workflows | NeMo Agent Toolkit |

## Tie-Breakers

| Constraint | Implication |
|---|---|
| Local/open-model requirement | Prefer smolagents, LangGraph/LangChain, LlamaIndex, DSPy; avoid Claude-only stacks |
| Strict control flow | Prefer LangGraph, Pydantic AI durable execution, or plain workflows |
| Existing team stack | Existing codebase familiarity often beats marginal framework features |
| High churn tolerance is low | Prefer mature, small abstractions and pin versions |
| Tool-call reliability is critical | Test the exact model/framework/tool combo before rollout |

## Adoption Levels

Choose the smallest adoption level that buys a concrete capability.

| Level | What you adopt | Use when |
|---|---|---|
| 0. Provider SDK | Messages, tools, structured output | One loop, one process, minimal state |
| 1. Harness helper | Prebuilt agent loop | Standard ReAct/tool loop with little custom flow |
| 2. Graph/workflow | Nodes, edges, state, checkpoints | Branching, retries, HITL, resumability |
| 3. Domain framework | RAG/crew/typed/voice-specific stack | The domain abstraction matches the workload |
| 4. Platform wrapper | Eval, deploy, observe, profile | The agent is production enough to operate |

Do not jump from level 0 to level 4 because the docs look impressive.

## Framework Evaluation Checklist

Before choosing, answer:

| Question | Why it matters |
|---|---|
| Does it support the model/provider you must use? | Some SDKs are provider-specific |
| Can you inspect and test the control flow? | Hidden loops hide failure modes |
| Where does state live? | Memory, checkpointing, and replay differ |
| How are tools described and authorized? | Tool policy is a safety boundary |
| How does it handle human approval? | High-impact actions need gates |
| Can it run your eval suite? | Framework changes must be regression-tested |
| What is the migration/deprecation story? | Agent frameworks churn quickly |
| Can your team debug it at 3 a.m.? | Operational familiarity beats feature checklists |

## Local Model Reality Check

Local support means the framework can send requests to a local or OpenAI-compatible endpoint. It does not mean the model reliably emits valid tool calls, follows stop conditions, streams parseable ReAct traces, or respects safety instructions.

| Local-model issue | Design response |
|---|---|
| Malformed tool arguments | Schema validation and bounded repair |
| Tool-call text mixed with reasoning | Use native function calling where available; otherwise test parser hard |
| Weaker instruction hierarchy | Reduce authority and add deterministic gates |
| Context-window mismatch | Measure actual usable context, not advertised max |
| Slow generation | Move mechanical steps to code; batch offline work |

Read `local-model-pitfalls.md` before selecting local-first architecture.

## Migration Playbook

When moving off a stale or unsuitable framework:

1. Extract the stable agent design: tasks, tools, state, authority, evals.
2. Freeze behavior with golden tasks before porting.
3. Port one path at a time, starting with read-only tools.
4. Re-run evals after every path.
5. Keep old and new systems side-by-side until outputs and tool trajectories are understood.
6. Delete framework-specific dead abstractions after parity, not before.

Do not line-by-line port framework glue. Rebuild the design on the new primitives.

## Framework Selection Output

The decision should produce a small record:

```text
Chosen framework:
Why this one:
Alternatives rejected:
Required version/docs checked:
State/checkpoint story:
Tool authorization story:
Local/cloud model compatibility:
Known churn risks:
First smoke test:
```

This record is what future maintainers need when the framework changes names, imports, or deployment story.

## Framework Churn Rules

- Verify imports from primary docs when writing new quickstarts.
- Pin framework versions in real projects.
- Treat prebuilt helpers as convenience layers, not architecture.
- Read migration guides before porting AutoGen, Semantic Kernel, or deprecated LangGraph examples.
- Keep business logic outside framework-specific glue where possible.

## Reference Router

| Load | When |
|---|---|
| `references/framework-landscape.md` | Full July 2026 framework comparison and churn log |
| `references/claude-agent-sdk.md` | Building with the Claude Code harness as a library |
| `references/local-model-pitfalls.md` | Local/open-weight model tool-calling and streaming pitfalls |
| `references/langgraph-quickstart.md` | Current LangChain `create_agent`, hand-built `StateGraph`, checkpointer, HITL examples |
| `references/crewai-llamaindex-quickstarts.md` | CrewAI Flow/Crew and LlamaIndex FunctionAgent/AgentWorkflow starts |
| `references/dspy-msaf-nemo-quickstarts.md` | DSPy authoring, Microsoft Agent Framework migration, NeMo Agent Toolkit wrapper guidance |
| `references/framework-build-matrix.md` | How to translate a `.foundry/design.md` into each of the 13 harness frameworks (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop) — tools, authority, state, failure modes, verification per framework; design pattern mappings (HITL gate, read-only specialist, cost-capped run) |

## CI-Resident Wiring

Once a framework is chosen, the next question is often "how does it run in
CI?" — GitHub Actions, GitLab CI, GitHub Copilot cloud agent, or GitLab Duo
Workflow. The `agent-deployment` skill's `ci-resident-agents` reference
covers per-framework CI entrypoints and pitfalls for every framework in the
table above (LangGraph, CrewAI, LlamaIndex, MSAF, DSPy, Pydantic AI,
smolagents, NeMo Agent Toolkit, Vercel AI SDK, Mastra, Google ADK, Claude
Agent SDK, Copilot SDK, OpenAI Agents SDK, raw provider loop), plus the
platform-native Copilot and Duo surfaces.

## Pitfalls

1. **Defaulting to a framework before the design pass.** Fix: complete `agent-design` stages 1-6; then choose.
2. **Confusing framework relationships.** Fix: AutoGen, AG2, Semantic Kernel, and Microsoft Agent Framework are related but not interchangeable.
3. **Assuming NeMo Agent Toolkit replaces your agent framework.** Fix: use it to wrap/profile/evaluate workflows, not to avoid designing one.
4. **Treating local-model support as local-model reliability.** Fix: run tool-call evals against your exact local model and parser.
5. **Copying stale quickstarts.** Fix: fetch current docs for import paths, checkpointers, decorators, and project layout.
6. **Letting abstractions hide safety policy.** Fix: explicit tool permissions and approval gates live in your design, not in the framework logo.
7. **Picking the most powerful framework for a tiny task.** Fix: use adoption levels; start with a raw loop if it satisfies requirements.
8. **Ignoring team/debug fit.** Fix: choose the stack your team can inspect, operate, and upgrade safely.
