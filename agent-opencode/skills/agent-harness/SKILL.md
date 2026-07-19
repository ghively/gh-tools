---
name: agent-harness
description: "The agent runtime loop itself — the harness that wraps the model: tool-call dispatch and parallelism, context-window management during a run (compaction, eviction, summarization), session lifecycle (create, resume, fork, share), mid-turn error recovery (tool failure, model refusal, rate limit), streaming and progressive output, step caps and doom-loop prevention, human-in-the-loop interrupts at the harness layer, harness-level caching, and observability spans. Use when building, debugging, or operating the agent loop, choosing a harness (Claude Agent SDK, OpenAI Agents SDK, LangGraph, custom), or diagnosing stuck/looping/OOMing runs. Does not cover framework selection (see framework-selection), deterministic execution mechanics (see deterministic-agents), or deployment packaging (see agent-deployment)."
---

# Agent Harness

The harness is the runtime loop that wraps the model. It sends messages,
executes tool calls, manages the context window, recovers from mid-turn
failures, streams output, and decides when to stop. The model is the
reasoner; the harness is everything around it that turns reasoning into
a running system.

## When to Use

- You are building or maintaining the agent loop (not just calling a
  provider SDK for a one-shot).
- A run is stuck, looping, OOMing, or hitting rate limits and you need
  to diagnose where the harness is failing.
- You need to choose a harness (Claude Agent SDK, OpenAI Agents SDK,
  LangGraph, Vercel AI SDK, custom) and want the decision criteria.
- You are implementing context compaction, session resume, step caps,
  streaming, or HITL interrupts at the harness layer.
- You are wiring observability (spans, token accounting) into the loop.

**Don't use for:** choosing a framework by feature matrix (`framework-selection`),
making outputs deterministic (`deterministic-agents`), packaging the agent
for deployment (`agent-deployment`), or designing the agent's job
(`agent-design`). The harness is the runtime, not the design or the package.

## The Loop Anatomy

Every agent harness implements some shape of this loop:

```
┌──────────────────────────────────────────────────────────┐
│  1. ASSEMBLE CONTEXT                                     │
│     system + instructions + tools + history + memory     │
│     (apply context engineering: select, compress)        │
├──────────────────────────────────────────────────────────┤
│  2. CALL THE MODEL                                       │
│     stream tokens; capture tool calls; respect stop      │
├──────────────────────────────────────────────────────────┤
│  3. DECIDE WHAT TO DO                                    │
│     text-only → return to user                           │
│     tool call(s) → dispatch (sequential or parallel)     │
│     refusal/error → recover or surface                   │
├──────────────────────────────────────────────────────────┤
│  4. EXECUTE TOOL CALLS                                   │
│     enforce permission; capture output; bound duration   │
├──────────────────────────────────────────────────────────┤
│  5. APPEND RESULTS TO CONTEXT                            │
│     (may trigger compaction if over budget)              │
├──────────────────────────────────────────────────────────┤
│  6. CHECK STOP CONDITIONS                                │
│     step cap, wall clock, budget, doom-loop detector,    │
│     user interrupt                                       │
└──────────────────────────────────────────────────────────┘
        │
        └─► back to 1 unless stopped
```

The harness's quality is measured by how well it handles the edge cases
at each step: a tool that hangs, a model that loops, a context that
overflows, a rate limit that hits mid-stream.

## Harness Decisions

| Decision | Options | Default |
|---|---|---|
| Tool-call dispatch | Sequential, parallel, batch | Sequential unless calls are independent |
| Context overflow | Truncate, summarize, compact, evict | Compact with recent-turn preservation |
| Stop conditions | Step cap, wall clock, token budget, doom-loop | All four; step cap is the hard floor |
| Streaming | Token stream, tool-call stream, both | Both; user-facing tokens stream, tool output streams on completion |
| Error recovery | Retry, escalate, surface, abort | Retry transient; escalate destructive; surface everything |
| Session state | In-process, checkpointed, durable | In-process for dev; durable for production |
| HITL interrupts | Pre-tool, post-tool, on-signal | Pre-tool for destructive; the harness blocks, not the model |

## Harness Quality Signals

A well-built harness:

- Never silently loops forever — step caps and doom-loop detection are
  wired and tested.
- Streams the first token within the provider's time-to-first-token
  budget; does not buffer the whole response.
- Compacts context *before* the provider rejects the request, not after.
- Captures every tool call as a span with input, output, duration, and
  cost — not just the final answer.
- Recovers from a 429 mid-stream without losing the work already done.
- Resumes a session from durable state after a crash, not just a clean
  shutdown.
- Enforces step caps even when the model insists it is "almost done."
- Surfaces harness-level decisions (compaction, retry, interrupt) in the
  transcript so the operator can reconstruct what happened.

## The Harness–Framework Boundary

A framework (LangGraph, CrewAI, Claude Agent SDK) provides abstractions
on top of the harness. The harness is the runtime; the framework is the
shape. When choosing, the question is not "which framework" but "which
framework's harness do I trust to handle the edge cases above."

See `framework-selection` for the framework comparison. This skill is
about what the harness does, regardless of which framework wraps it.

## Reference Router

| Load | When |
|---|---|
| `references/harness-comparison.md` | Choosing a harness — coverage matrix for the 13 production harnesses (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop) across all nine concerns below |
| `references/agent-loop.md` | The loop itself — dispatch, stop conditions, the six steps in depth, with worked code |
| `references/context-management.md` | Compaction, eviction, summarization, mid-run context window engineering, prompt-cache stability |
| `references/session-lifecycle.md` | Create, resume, fork, share, export, end; durable vs in-process state; the session-state contract |
| `references/error-recovery.md` | Mid-turn recovery: tool failure, model refusal, rate limit, stream interruption, partial completion |
| `references/streaming.md` | Token streaming, tool-call streaming, progressive UX at the harness layer, backpressure |
| `references/hitl-interrupts.md` | Human-in-the-loop at the harness layer: pre-tool, post-tool, on-signal; the harness blocks, not the model |
| `references/harness-observability.md` | Spans, token accounting, cost tracking, trace export, the harness-level signals that matter |
| `references/harness-cache.md` | Prompt cache, response cache, tool-result cache, cache invalidation, the cache hierarchy |
| `references/doom-loop-prevention.md` | Step caps, repetition detection, cost ceilings, the doom-loop taxonomy and defenses |

## Pitfalls

1. **Trusting the model to stop.** The model says "I'm done" but the
   harness has no step cap. Fix: the harness owns the stop decision,
   not the model.
2. **Buffering the whole response.** First-token latency measured in
   seconds, not milliseconds. Fix: stream from the provider; never
   wait for the full completion before emitting.
3. **Compaction after overflow.** The provider rejects the request;
   the harness compacts and retries. Fix: compact *before* the
   threshold, with margin for the next turn.
4. **Silent retry storms.** A 429 triggers retry; the retry triggers a
   429. Fix: exponential backoff with jitter; circuit-break after N
   retries; surface persistent failures.
5. **No span capture.** Tool calls happen but only the final text is
   logged. Fix: every tool call is a span; the transcript reconstructs
   the trajectory.
6. **State only in memory.** Process crashes; the session is gone.
   Fix: durable checkpoint at turn boundaries; resume after crash is
   a tested path, not an aspiration.
7. **Destructive tool without interrupt.** The model calls `rm -rf`;
   the harness dispatches immediately. Fix: the harness gates
   destructive tools with a pre-tool interrupt, independent of model
   judgment.
8. **Prompt-cache instability.** The harness reorders system messages
   every turn; cache miss every time. Fix: stable prefix discipline;
   see `harness-cache.md`.
9. **Treating the framework as the harness.** The framework's defaults
   are fine for prototypes and wrong for production. Fix: understand
   the harness layer the framework wraps; override its defaults
   deliberately.
10. **No doom-loop detector.** The model repeats the same tool call
    with the same arguments across turns. Fix: hash recent tool-call
    signatures; break on repetition.
