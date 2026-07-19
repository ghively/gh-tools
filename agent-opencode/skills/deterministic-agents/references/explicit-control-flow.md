# Explicit Control Flow — Code Owns the Loop

> Last verified: 2026-07. Framework APIs referenced (LangGraph 1.x StateGraph) are stable post-1.0 (GA October 2025, 1.2 shipped May 2026); pattern taxonomy itself doesn't go stale.

The most consequential determinism decision in any agent system is **who owns the control flow**. In a fully agentic loop, the model decides what to do next, whether to continue, and when it's done — three decisions that can each go differently on identical input. Every pattern below moves some of those decisions into code. The art is moving *enough* of them without destroying the flexibility you needed a model for.

This file assumes you've already decided the task warrants model involvement at all — the workflow-vs-agent decision is the `agent-design` skill. Framework choice is the `framework-selection` skill; LangGraph appears here only because StateGraph is the clearest widely-deployed embodiment of the typed-graph pattern.

## Pattern catalog

Ordered from most deterministic to least. Prefer the earliest pattern that fits — each step down the list adds capability and subtracts predictability.

### 1. LLM-as-function — one call, one job, no loop

The model is a pure(ish) function: typed input → one call → schema-validated typed output. No tools, no loop, no conversation state.

```
classify(ticket: str) -> RouteDecision        # enum-constrained, see structured-outputs.md
extract(pdf_text: str) -> Invoice
summarize(diff: str, max_words: int) -> str
```

- **Buys you:** the strongest determinism available with a model in the loop. Trivially cacheable, batchable, testable (input → output pairs), replaceable (swap models per call site). Composes into ordinary code — `map`, `filter`, retry decorators all just work.
- **Costs you:** nothing, when it fits. The failure mode is *pretending* it fits: cramming a multi-step task into one mega-prompt produces a brittle call that does five jobs badly.
- **Use when:** classification, extraction, transformation, scoring, single-shot generation. Most "agent" steps in production systems should secretly be these.

### 2. Prompt chaining with checkpoints

A fixed sequence of LLM-as-function calls, with **programmatic validation between every step** — a checkpoint that either passes typed output forward or stops the chain.

```
outline = draft_outline(brief)          # step 1
check(outline)                          # gate: sections present? within length? cites sources?
sections = [write_section(outline, s) for s in outline.sections]   # step 2 (parallelizable)
check_all(sections)
final = assemble_and_polish(sections)   # step 3
```

- **Buys you:** each model call does one job at full attention; failures are localized to a step (retry *that* step, not the run); intermediate artifacts are inspectable and resumable; steps with no data dependency parallelize.
- **Costs you:** latency (N sequential calls) and rigidity — the sequence is fixed at design time.
- **Key discipline:** the checkpoint is code, not another model call. `len(outline.sections) in range(3, 8)` beats "review this outline for quality" — save model-graded gates for qualities code can't check, and even then bound them (pattern 7).

### 3. Router with enumerable branches

One enum-constrained classification call chooses a branch; **code does the dispatch**; each branch is its own deterministic pipeline (often a prompt chain), with prompts, tools, and model tier specialized per branch.

```python
decision = classify(request)             # -> Literal["refund", "bug", "sales", "escalate"]
handler = HANDLERS[decision.route]       # plain dict dispatch — not model judgment
result = handler(request)
```

- **Buys you:** separation of concerns (each branch optimized independently); the only nondeterministic decision is a single constrained classification; misroutes are measurable (routing accuracy is an ordinary eval) and hedgeable (a `confidence` field + threshold → escalate).
- **Costs you:** you must enumerate the branches. Inputs that fit no branch need an explicit `escalate`/`other` member — never let the router improvise a new category.
- **Scaling note:** past ~10–15 branches, route hierarchically (coarse → fine) rather than growing one giant enum.

### 4. Plan-then-execute with frozen plans

A planner call produces a **structured, schema-validated plan** (steps, dependencies, per-step tool + arguments). The plan is then *frozen* — optionally shown to a human — and an executor (mostly code, with model calls only inside steps that need them) walks it.

- **Buys you:** the expensive, creative, nondeterministic act (planning) happens **once**, up front, where it can be validated, priced, previewed, and approved. Execution is then auditable and resumable step-by-step. This is the natural home for dry-run gating (`idempotency-and-replay.md`) and for durable execution — a frozen plan maps 1:1 onto workflow steps (`durable-execution.md`; Cloudflare's Dynamic Workflows exists precisely to turn agent-written plans into real durable workflows).
- **Costs you:** stale plans. If step 3 discovers the world differs from what the planner assumed, the executor must not silently improvise — that's the agent loop sneaking back in. Correct move: halt, surface the discrepancy, and **replan as an explicit, gated event** (new plan, new validation, new approval if the old one was approved).
- **Use when:** multi-step tasks with side effects, anything needing human approval of *what will happen* before it happens, batch operations.

### 5. State machine / typed graph

Control flow as an explicit graph: typed shared state, nodes that transform it, edges (including conditional edges) that code evaluates. [LangGraph's StateGraph](https://docs.langchain.com/oss/python/langgraph/overview) is the reference implementation (1.0 GA since Oct 2025):

```python
class State(TypedDict):
    ticket: str
    route: str
    draft: str | None
    approved: bool

g = StateGraph(State)
g.add_node("classify", classify_node)
g.add_node("draft", draft_node)
g.add_node("human_review", review_node)
g.add_conditional_edges("classify", lambda s: s["route"])      # code evaluates the branch
g.add_edge("draft", "human_review")
app = g.compile(checkpointer=checkpointer)                     # persistence per superstep
app.invoke(state, config={"recursion_limit": 25})              # hard stop built in
```

- **Buys you:** every possible execution path is visible in the graph definition — reviewable, diagrammable, testable per-node. Cycles are *allowed but explicit and bounded* (`recursion_limit`). Checkpointing per superstep gives pause/resume and human-in-the-loop interrupts. State is typed, so inter-node contracts are checked.
- **Costs you:** upfront modeling; a graph is exactly as flexible as you drew it. Also note checkpointing is persistence, not full durable-execution semantics — see `durable-execution.md` for the distinction.
- **Use when:** flows with branches *and* cycles *and* state — approval loops, multi-stage pipelines with retry-to-earlier-stage, anything a whiteboard diagram of arrows describes. If your graph is a straight line, you wanted pattern 2; if one node is "agent decides everything," you've drawn a loop around pattern 6 and gained little.

### 6. Bounded agent loop with hard stops

Sometimes you genuinely need the model to choose tools dynamically — open-ended debugging, research, exploration. Then the loop itself is still yours, and it enforces limits the model never gets to negotiate:

```python
MAX_TURNS, MAX_TOKENS, MAX_SECONDS = 20, 200_000, 600
spent_tokens, t0 = 0, time.monotonic()
seen_calls: set[tuple] = set()

for turn in range(MAX_TURNS):
    if spent_tokens > MAX_TOKENS or time.monotonic() - t0 > MAX_SECONDS:
        return finalize_partial("budget exhausted")
    resp = client.messages.create(..., tools=TOOLS)
    spent_tokens += resp.usage.input_tokens + resp.usage.output_tokens
    if resp.stop_reason != "tool_use":
        return resp                                     # model is done — code confirms
    for call in tool_calls(resp):
        sig = (call.name, canonical(call.input))
        if sig in seen_calls:                           # no-progress detection:
            inject_note("You already ran this exact call; do something different or stop.")
        seen_calls.add(sig)
        gate_if_destructive(call)                       # see proof-contracts.md
        results.append(execute(call))                   # idempotent — see idempotency-and-replay.md
```

- **Buys you:** the model's full tool-choosing flexibility with a guaranteed termination envelope: turn cap **and** token budget **and** wall clock **and** repeated-call detection, whichever trips first. (Providers are converging on server-side versions of this — e.g. Anthropic's task budgets give the model a visible token countdown for the whole loop — but your loop keeps its own hard caps regardless.)
- **Costs you:** everything inside the envelope is still nondeterministic — tool order, tool arguments, number of turns. Use for exploration; don't wrap one around a task that patterns 1–5 could pin down.
- **Non-negotiable:** limits are multiple and simultaneous. A turn cap alone doesn't stop a loop that makes one enormous call per turn; a token budget alone doesn't stop a loop of tiny calls to a slow tool.

### 7. Evaluator–optimizer (bounded repair)

Generator call → programmatic and/or model evaluator → targeted feedback → regenerate. This is the structured-outputs repair loop generalized to quality, and it inherits the same rules: **bounded iterations (2–3), named defects, stall detection, terminal escalation path**. Treat it as a component you embed inside patterns 2–5, not an architecture. An unbounded "reflect until good" loop is SKILL.md pitfall #1.

## Choosing

| Pattern | Model decides | Code decides | Determinism | Reach for it when |
|---|---|---|---|---|
| 1. LLM-as-function | content of one output | everything else | ★★★★★ | classify / extract / transform / generate |
| 2. Prompt chain + checkpoints | content of each step | sequence, gates, retries | ★★★★☆ | fixed multi-step pipelines |
| 3. Router | one enum choice | dispatch + each branch | ★★★★☆ | heterogeneous inputs, known categories |
| 4. Plan-then-execute | the plan (once, gated) | validation, execution, replan trigger | ★★★☆☆ | side-effecting multi-step work, approvals |
| 5. State machine / typed graph | per-node content, branch *inputs* | topology, edges, limits, state shape | ★★★☆☆ | branches + cycles + state |
| 6. Bounded agent loop | tool choice, sequencing, args | budget envelope, gates, stop | ★★☆☆☆ | genuine exploration |
| 7. Evaluator–optimizer | fixes | defect list, iteration bound | (inherits host) | quality gates inside 2–5 |

Composition is normal and encouraged: a router (3) whose branches are chains (2) with repair loops (7), one branch escalating to a bounded agent loop (6), the whole thing running as durable workflow steps (`durable-execution.md`).

## Pitfalls

1. **The "smart step" that re-agentifies your pipeline.** One chain step prompted with "handle whatever comes up, use your judgment, call tools as needed" quietly converts pattern 2 into pattern 6 without the budget envelope. If a step needs judgment, give it the *envelope* too.
2. **Model-evaluated gates where code would do.** "Does this JSON have five sections?" is `len()`, not a judge call. Every model-graded checkpoint adds cost, latency, and its own nondeterminism — spend them only on qualities code can't check.
3. **Conditional edges that ask the model mid-graph.** In a typed graph, edge functions should read *already-produced structured state* (`lambda s: s["route"]`), not make a fresh LLM call to decide where to go — otherwise your graph topology is decorative.
4. **Replanning-by-improvisation.** Executor hits a surprise and "just handles it." Now the executed work matches neither the approved plan nor any log. Halt-and-replan is a feature; silent divergence is an incident.
5. **A single limit instead of an envelope.** See pattern 6 — caps must be plural (turns AND tokens AND wall clock) because each alone has a bypass.
6. **Graphs drawn to look agentic.** Twenty nodes whose edges all route back through one "orchestrator LLM" node is pattern 6 wearing pattern 5's clothes — you pay the modeling cost and get none of the predictability.
