> Last verified: 2026-07. Prompt-caching mechanics, batch discounts, model prices, and provider feature support change frequently; verify provider docs before relying on specific savings.

# Workflow Optimization — Measure, Collapse, Parallelize, Cache, Batch, Route

Optimization is not "make the prompt shorter". It is a systematic pass over traces to remove unnecessary model judgment, reduce repeated tokens, improve concurrency, and right-size each step without breaking correctness.

## The Optimization Loop

1. **Measure first.** Trace each step: input tokens, output tokens, cache reads/writes, latency, tool latency, model, retries, error rate, and cost.
2. **Classify each step.** Is the model doing judgment, transformation, routing, formatting, or work code could do?
3. **Collapse deterministic steps into code.** If no language judgment is needed, remove the LLM call.
4. **Parallelize independent work.** Run independent retrieval, validation, or analysis steps concurrently.
5. **Cache stable inputs and tool results.** Stabilize prompt prefixes and cache deterministic tool calls.
6. **Batch offline work.** Use batch APIs for evals, extraction, classification, and reports that do not need synchronous latency.
7. **Right-size models and context.** Use the cheapest capable model and the smallest sufficient context.
8. **Re-run evals.** Optimization that lowers quality is a regression, not a win.

## What to Measure

| Signal | Why it matters | Action if high |
|---|---|---|
| Tokens per step | Primary cost driver | Compress context, cache stable prefix, split data |
| Latency per step | User experience and throughput | Parallelize, cache, switch model, move offline |
| Tool latency | Model may not be bottleneck | Batch API calls, cache results, improve backend |
| Retry rate | Hidden cost and variance | Fix schema/tool errors; add deterministic validators |
| Cache hit rate | Determines whether caching is real | Stabilize prefix ordering and breakpoints |
| Model escalation rate | Shows routing quality | Improve classifier or default tier |
| Human approval wait | Critical path delay | Move approval earlier or bundle decisions |

## Collapse Agent Steps into Code

| LLM step | Replace with | Keep LLM only if |
|---|---|---|
| Date math | Library call | Natural-language ambiguity matters |
| Routing among fixed labels | Enum classifier or rules | Inputs are messy enough to need semantic judgment |
| JSON formatting | Serializer | Source text extraction is ambiguous |
| Sorting/ranking by numeric fields | Code | Criteria are subjective or implicit |
| Retrying failed tools | Retry policy in code | The alternate strategy needs reasoning |
| Termination decision | Explicit stop condition | Success itself is semantic and validated |

The fastest, cheapest, most deterministic LLM call is the one you deleted.

## Parallelize Independent Steps

Parallelize only when results do not depend on one another.

| Work | Parallelization pattern |
|---|---|
| Fetching independent documents | Concurrent I/O, then deterministic merge |
| Running independent eval cases | Batch or worker pool |
| Multi-source research | Bounded fan-out with per-source summaries |
| Multiple validators | Run in parallel; combine failures deterministically |
| Tool calls to same rate-limited API | Usually do not parallelize blindly; respect limits |

Always preserve deterministic merge order. Sort by stable key, not completion order.

## Prompt Caching Discipline

Prompt caching reduces cost/latency for repeated stable prefixes. It does not reduce context-window usage.

Current Anthropic docs distinguish automatic caching and explicit breakpoints. Cache reads require exact prefix matches; changes in tools, system content, message ordering, images, or unstable JSON key order can invalidate caches. Default TTL is 5 minutes; 1-hour TTL exists at higher write cost. Cache breakpoints should sit on the last block whose prefix remains identical across requests.

| Rule | Reason |
|---|---|
| Put stable tools/system/examples first | Cache prefixes are hierarchical |
| Keep timestamps and per-request data after breakpoint | Volatile suffix must not poison the prefix hash |
| Sort tool schemas and context chunks | Stable bytes improve cache hits and determinism |
| Track `cache_read_input_tokens` and `cache_creation_input_tokens` | Hit rate beats hope |
| Do not cache tiny prompts below provider minimums | Some providers silently skip caching |

Primary source: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

## Tool-Result Caching

Cache deterministic, read-only tool results by normalized arguments.

| Tool result | Cache? | Notes |
|---|---|---|
| Static docs lookup | Yes | Include document version or commit in key |
| Search results | Short TTL | Search freshness decays quickly |
| Account balance/status | Usually no | Freshness matters; cache only within explicit SLA |
| Expensive pure computation | Yes | Key on inputs and code version |
| Side-effecting operation | No | Journal effects instead; do not replay blindly |

## Batch APIs

Batch APIs are for high-volume asynchronous work: eval suites, classification backfills, document extraction, and offline report generation. Anthropic's Message Batches API currently advertises 50% standard API pricing, up to 100,000 requests or 256 MB per batch, asynchronous processing, and result retrieval by custom IDs. Batch output order is not guaranteed.

Batch when:

- The user is not waiting synchronously.
- Each item is independent.
- You can tolerate delayed completion and partial failures.
- You have per-item IDs and retry handling.

Do not batch when:

- A live conversation needs a response now.
- Requests depend on previous results.
- Data retention constraints forbid the batch feature.
- You need streaming.

Primary source: https://docs.anthropic.com/en/docs/build-with-claude/batch-processing

## Right-Size Models Per Step

Use `model-selection` for current matrices. The deterministic rule is stable: reserve expensive/frontier models for genuine judgment, not mechanical transformation.

| Step | Typical tier |
|---|---|
| Simple classification/extraction with schema | Budget/fast model after eval pass |
| Tool orchestration on untrusted input | Strong instruction-following model |
| Code generation or high-stakes synthesis | Strong coding/reasoning model |
| Summarizing tool output | Mid/budget model if factuality is checked |
| Final answer to customer | Model tier set by risk and brand quality |

## Cut Context

Context cost optimization is also quality optimization. Long context degrades recall and attention. Use `prompt-context-engineering` for the full treatment.

| Symptom | Optimization |
|---|---|
| Huge raw tool outputs | Summarize to findings before next model call |
| Repeated static instructions | Cache prefix and remove duplicates |
| Retrieved chunks never used | Improve retrieval or reduce k |
| Long conversation drift | Compact at task boundaries; restart if poisoned |
| Subagent returns walls of text | Require conclusion/evidence format |

## Escalation Ladder

1. Delete unnecessary LLM calls.
2. Replace model-controlled flow with code-owned flow.
3. Shorten and stabilize context.
4. Cache stable prompts and pure tool results.
5. Parallelize independent work.
6. Batch offline work.
7. Route cheap-first, escalate only on verified failure.
8. Change framework/runtime only if measurement shows orchestration overhead is the bottleneck.

## Pitfalls

1. **Optimizing by vibes.** Fix: compare traces and eval scores before/after.
2. **Caching volatile prefixes.** Fix: move timestamps, user messages, and changing retrieval results after cache breakpoints.
3. **Parallelizing dependent steps.** Fix: draw the dependency graph; only independent nodes run concurrently.
4. **Using batch APIs for interactive work.** Fix: batch only asynchronous workloads.
5. **Right-sizing without evals.** Fix: cheaper model must pass the same task suite.
6. **Merging parallel results by completion order.** Fix: sort by stable IDs before synthesis.
