# Agent Patterns — The Core Vocabulary

Every agent framework, product, and architecture diagram is a variation on a small set of patterns. Learn the vocabulary here; pick among them during Stage 3 of the design process (`agent-design-workflow.md`).

## The agent loop, minimally

Every agentic system reduces to one loop:

```
        ┌─────────────────────────────┐
        │                             │
   state ──> LLM decides an action ───┤
        │    (tool call, hand-off,    │
        │     answer, stop)           │
        │                             │
        └──── action executes ────────┘
              result feeds back
              as new state
```

An LLM sees state, decides an action, the action executes, the result feeds back as new state. Frameworks differ mainly in **how explicit that loop is** — a graph you control (LangGraph-style nodes/edges) versus an abstraction you configure (CrewAI-style roles) versus a harness that owns the loop (Claude Code, Claude Agent SDK). The pattern vocabulary below describes shapes of this loop, not framework features.

## Workflow vs agent — Anthropic's distinction

From Anthropic's [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents):

- A **workflow** is a system where LLMs and tools are orchestrated through **predefined code paths** — control flow is fixed by code you wrote.
- An **agent** is a system where the LLM **dynamically directs its own process and tool usage** — control flow is decided at runtime by the model (the ReAct-shaped loop above).

This is the single most important distinction in agent design. Workflows buy predictability and consistency for well-defined tasks; agents buy flexibility for open-ended ones — at the price of latency, cost, and variance. Start simple; add a framework or an agent loop only when the abstraction earns its cost. Full decision tree: `workflow-vs-agent.md`.

## The seven core patterns

| Pattern | Shape | Fixes / Costs |
|---|---|---|
| **ReAct** ([Yao et al. 2022](https://arxiv.org/abs/2210.03629)) | Thought → Action → Observation, looped | Grounds steps in tool results vs. hallucination-prone pure chain-of-thought; extra round-trips |
| **Tool-use / function-calling** | Structured call (name + JSON args); harness executes, returns result | Deterministic parsing vs. unparseable free-text; needs a schema per tool |
| **Planner-executor** | Whole plan up front; executors run without re-planning unless a step fails | Saves tokens vs. re-reasoning every step; brittle if the world changes mid-plan |
| **Reflection / evaluator-optimizer** | Generator produces output; critic grades against a rubric; revise N times | Catches errors a single pass misses; 2-3x calls, needs a hard stop condition |
| **Orchestrator-worker** | One LLM decomposes, routes to workers, synthesizes results | Avoids one agent's context overloading; coordination overhead |
| **Graph state machine** | Explicit nodes/edges, typed shared state | Resumable retries/branches/human-in-the-loop vs. implicit loops; you maintain the graph |
| **Memory-augmented** | Agent reads/writes a persistent store across turns | Beats finite context; adds latency + stale-recall risk — depth in the `memory-rag` skill |

### ReAct
The default single-agent shape: the model interleaves reasoning ("Thought") with tool calls ("Action") and reads results ("Observation") until it can answer. Use when steps can't be predicted but a single context window can hold the whole task. Failure signatures: loops that never converge (add a step budget), reasoning that ignores observations (tool results too long — summarize them), tool thrashing (too many overlapping tools — consolidate the tool surface).

### Tool-use / function-calling
Not really a control-flow pattern — the substrate under everything else. The model emits a structured call; your harness executes it and returns the result. Design rules: one tool per task-level operation (not per API endpoint), schemas the model can't misread, and low temperature for tool-calling reliability (for providers that still honor it — current Anthropic models reject `temperature` outright; see the `deterministic-agents` skill). Depth: `tool-mcp-engineering`.

### Planner-executor
Plan the whole task once, then execute steps without re-engaging the planner unless something fails. Cheaper and more predictable than ReAct for multi-step tasks whose structure is knowable up front. The brittleness is the point of failure: if the world changes mid-plan (a file moved, an API errored differently than expected), a pure executor plows ahead. Always define the "step failed → re-plan" edge.

### Reflection / evaluator-optimizer
A generator produces; an evaluator critiques against explicit criteria; the generator revises. Worth its 2-3x cost only when (a) clear evaluation criteria exist and (b) iterative refinement measurably improves output (translation, code with tests, rubric-scored writing). **Always cap iterations and define a pass condition** — a reflection loop with no stop condition burns tokens indefinitely. If the evaluator can be a program (tests, linter, schema check) instead of an LLM, make it a program.

### Orchestrator-worker
A lead LLM decomposes an unpredictable task, delegates to workers (each with its own fresh context), and synthesizes the results. This is Anthropic's recommended shape for tasks where subtasks can't be predefined — e.g., a code change touching an unknown set of files, research fanning across sources. The costs are real: task prompts must carry all context workers need (they inherit nothing), coordination overhead, and multiplied token spend. Runtime mechanics — handoffs, shared state, supervision, fleets — belong to the `multi-agent-orchestration` skill.

### Graph state machine
Nodes (LLM steps, tool steps, human gates) and typed edges over shared state. What it buys over an implicit loop: resumability (checkpoint and continue after a crash), branching you can test, retries scoped to a node, and clean human-in-the-loop interrupts. What it costs: you now maintain a graph, and the "agent" is really a workflow with agentic nodes — often exactly what production wants. See the `deterministic-agents` skill for the fully-deterministic end of this spectrum.

### Memory-augmented
Any of the above, plus a persistent store the agent reads at session start and writes as it learns. The design questions are what to store (declarative facts, not instructions-to-self; never task progress that's stale in a week), when to consolidate, and how to handle staleness (a memory snapshot is frozen — never trust it for *current* state; re-verify with live tools). Depth: `memory-rag`.

## Composition — real systems mix patterns

Production systems are compositions, not single patterns:

- A **coding agent** is ReAct (the main loop) + tool-use (edit/run/search tools) + orchestrator-worker (sub-agents for parallel exploration) + memory-augmented (project rules files).
- A **deep-research product** is orchestrator-worker (lead agent + parallel searchers) + reflection (source verification pass) + memory-augmented (notes accumulated across the run).
- A **support agent** is routing (a workflow!) in front of ReAct specialists + evaluator gates before anything customer-visible.

When composing, name each layer's pattern explicitly in the design doc. "It's agentic" is not an architecture.

## Mapping platform vocabulary onto the patterns

If you build on Claude Code / the Claude Agent SDK, the constructs map cleanly:

| Platform construct | Pattern position |
|---|---|
| The main assistant loop | ReAct + tool-use |
| **Skills** | Procedural memory — trigger-matched instructions loaded into the loop |
| **Subagents** (Task/Agent tool) | Orchestrator-worker, spawn depth 1 |
| **Hooks** | Guardrails enforced by code, not by the model — they sit outside the loop |
| **MCP servers** | Tool transport — the function-calling substrate |
| **CLAUDE.md / rules files** | Memory-augmented (always-loaded durable layer) |
| **Scheduled/background runs** | Event-pipeline shape around any loop |

Equivalent mappings exist in LangGraph (graph state machine natively; `create_react_agent` for the one-liner ReAct), CrewAI (orchestrator-worker via Crews; graph-ish control via Flows), LlamaIndex (event-driven workflow steps), and the Claude Agent SDK (harness-owned ReAct + subagents). Choosing among them is the `framework-selection` skill — and it happens at Stage 7, never before.

## Pattern-selection quick rules

1. **Fixed steps, checkable outputs** → not an agent pattern at all; write a workflow (`workflow-vs-agent.md`).
2. **Unpredictable steps, one context window suffices** → ReAct.
3. **Knowable plan, many steps** → planner-executor with a re-plan edge.
4. **Quality gate with objective criteria** → evaluator-optimizer (prefer programmatic evaluators), capped.
5. **Subtasks unknown until runtime, or context too big for one window** → orchestrator-worker.
6. **Needs resumability, audited branches, or human gates** → graph state machine.
7. **Anything spanning sessions** → add memory-augmented to whichever of the above you picked.

## Pattern-level pitfalls

- **Reflection loops with no stop condition** — cap iterations, define pass/fail.
- **Planner-executor with no failure edge** — the world changes; plans must be revisable.
- **Orchestrator-worker where a for-loop would do** — if decomposition is static, it's parallelization (a workflow), not orchestration.
- **Treating the prebuilt ReAct helper as the only shape** — hand-build the graph when routing goes beyond one tool loop.
- **Non-zero temperature on tool-calling loops** — flaky calls, malformed args (where the provider still honors `temperature`; current Anthropic models reject it — see `deterministic-agents`).
- **Workers assumed to inherit context** — they don't; task prompts carry everything.
- **Memory treated as current state** — memory is a snapshot; verify live state with live tools before acting on it.
