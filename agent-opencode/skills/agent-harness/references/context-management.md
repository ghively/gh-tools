# Context Management During a Run

The context window is the harness's most contested resource. It fills
with every turn, every tool call, every tool result. Without active
management, the harness either overflows (provider rejects the request)
or spends escalating tokens on a growing prefix.

This reference covers what the harness does *during a run* to keep the
context usable. For the prompting side (what to put in the context in
the first place), see the `prompt-context-engineering` skill.

## The Budget

The harness maintains a token budget that is strictly less than the
model's context window:

```
Model context window:           200,000 tokens
Harness budget:                 160,000 tokens  (80% of window)
Reserve for response:            20,000 tokens
Reserve for tool results:        20,000 tokens
Usable for history + system:    120,000 tokens
```

The 80% rule leaves margin for the response and for tool results that
arrive mid-turn. A harness that fills the context to 100% will fail on
the next turn.

## The Compaction Trigger

Compaction must happen *before* the provider rejects the request, not
after. The harness tracks the current context size and compacts when:

```
current_context_size > (budget × compaction_threshold)
```

A typical threshold is 0.75 — compact when the context is 75% full,
before it reaches the 80% budget ceiling. Compaction at 75% leaves
room for the compaction operation itself (which adds a summary before
removing old turns).

## Compaction Strategies

| Strategy | What it does | When to use |
|---|---|---|
| **Truncate** | Drop oldest turns | Dev only; loses information |
| **Summarize** | Replace old turns with an LLM-generated summary | Default for most agents |
| **Evict tool results** | Replace large tool outputs with a short stub | When tool outputs dominate the context |
| **Selective preserve** | Keep recent turns verbatim; summarize older | Default; preserves recent-turn fidelity |
| **Hybrid** | Preserve recent N turns + summarize the rest + evict large tool outputs | Production |

The production default is hybrid: preserve the last 2–3 user turns
verbatim (the active task), summarize the middle, and replace any tool
result over a threshold (e.g., 2 KB) with a stub like `[tool:search
returned 47 results, top 3 shown in turn 5]`.

## Compaction Quality Rules

- **Never summarize the current task.** The user's most recent request
  and the agent's most recent response stay verbatim.
- **Preserve decisions.** If the agent chose a path in turn 3, the
  summary must mention the choice, not just "the agent considered
  options."
- **Preserve evidence.** Tool results that the agent cited in its
  reasoning are summarized with their key findings, not stubbed.
- **Emit the compaction as a span.** The operator must be able to see
  when compaction happened, what was preserved, and what was lost.

## Prompt-Cache Stability

Prompt caching (Anthropic, OpenAI, Gemini) gives a large discount when
the prefix is stable. The harness must preserve prefix stability across
turns:

| Part of context | Stability rule |
|---|---|
| System prompt | Frozen for the session |
| Instructions / AGENTS.md | Frozen for the session |
| Tool schemas | Sorted deterministically; frozen for the session |
| Early conversation | Frozen unless compaction rewrites it |
| Recent turns | Growing; appended at the end |

Compaction **busts the cache** when it rewrites early turns. The harness
should compact in chunks that preserve the cache prefix for as long as
possible: compact the middle, not the beginning.

See `prompt-context-engineering/references/long-horizon-context.md` for
the provider-specific cache mechanics.

## Eviction Policy

When tool results dominate the context, the harness evicts them before
summarizing conversation turns. Eviction order:

1. **Tool results over the size threshold** (e.g., > 2 KB) — replace
   with a stub.
2. **Tool results older than N turns** — replace with a stub.
3. **Tool results from abandoned subtasks** — replace with a stub.
4. **Old conversation turns** — summarize.

Never evict:
- The current user message.
- The most recent agent response.
- Tool results cited in the most recent agent response.

## Mid-Turn Compaction

Some harnesses compact *during* a turn, between tool calls, when the
context grows past the threshold mid-loop. This is more complex but
prevents overflow on long multi-tool turns.

Mid-turn compaction rules:

- Compact between tool dispatch and the next model call, never during a
  tool call.
- Preserve the current tool's input and output verbatim.
- Emit a span noting the mid-turn compaction.

## The Compaction Span

Every compaction emits a span:

```json
{
  "type": "compaction",
  "trigger": "threshold_75pct",
  "context_size_before": 121000,
  "context_size_after": 62000,
  "turns_preserved": 4,
  "turns_summarized": 12,
  "tool_results_evicted": 8,
  "summary_tokens": 1800,
  "cache_bust": true
}
```

The `cache_bust` field tells the operator whether this compaction
invalidated the prompt cache (a cost signal).

## Session-Level vs Run-Level Context

- **Run-level context** is the conversation within a single agent run
  (from the user's message to the agent's final response). Compaction
  applies here.
- **Session-level context** is the durable state across runs (memory,
  RAG, prior conversations). Managed separately; see `session-lifecycle.md`
  and the `memory-rag` skill.

The harness must not confuse the two. Compacting run-level context does
not write to session-level memory; writing to memory is an explicit tool
call the model makes, not a side effect of compaction.

## Pitfalls

1. **Compaction after overflow.** The provider returns a 400; the
   harness compacts and retries. Fix: compact at 75%, not at 100%.
2. **Summarizing the current task.** The summary drops the user's
   latest request; the agent loses the thread. Fix: the last N turns
   are never summarized.
3. **Cache-busting compaction every turn.** Each compaction rewrites
   the prefix; the cache misses every time. Fix: compact in the
   middle, not at the beginning; batch compaction rather than
   turn-by-turn.
4. **Evicting cited evidence.** The agent cited a tool result in turn
   5; compaction in turn 8 stubs it; the agent cannot defend its
   reasoning. Fix: cited results are preserved until the citing turn
   is itself summarized.
5. **No compaction span.** The operator cannot tell when or why the
   context shrank. Fix: emit a span for every compaction.
6. **Treating compaction as memory.** Compacted summaries are not
   durable; they die with the run. Fix: durable memory is a separate
   tool call, not a compaction side effect.
