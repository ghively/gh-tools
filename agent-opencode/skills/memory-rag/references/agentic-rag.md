> Last verified: 2026-07. Agentic retrieval patterns and library implementations evolve quickly; verify framework docs before relying on a named feature.

# Agentic RAG

Agentic RAG makes retrieval a decision the agent can take during a task, rather than a fixed pre-step. It is more powerful and easier to break.

## Patterns

| Pattern | Use when | Risk |
|---|---|---|
| Retrieval as a tool | The agent must decide if/when/what to retrieve | Agent skips retrieval or loops. |
| Query rewriting | User query is vague or conversational | Rewrite loses important constraints. |
| Query decomposition | Answer needs multiple subquestions | More calls and more merge errors. |
| Multi-hop retrieval | Evidence spans related entities/documents | Harder evals and provenance tracking. |
| Self-RAG | Model decides whether passages support answer | Requires strong verifier behavior. |
| Corrective RAG | Detect bad retrieval and retry differently | Loop risk without hard caps. |
| Deep-research loop | Search/read/synthesize iteratively over open web or large corpus | Expensive; citations must be audited. |
| GraphRAG | Relationship-heavy corpus needs entity/edge reasoning | Graph construction cost and stale edges. |

### Choosing a Pattern

Plain RAG (retrieve → rerank → answer) is the default. Move to an agentic pattern only when retrieval *strategy* depends on intermediate findings. Use this decision table:

| If your queries are… | Use | Because |
|---|---|---|
| Stable corpus, predictable queries, answer in 1-2 chunks | Plain RAG | Agentic overhead buys nothing here. |
| Conversational, vague, or underspecified | Query rewriting | A good rewrite is cheaper than a bigger index. |
| "Compare X and Y across these docs" | Query decomposition | One retrieval cannot serve both halves well. |
| "Who owns the service that depends on X?" | Multi-hop / GraphRAG | Joins are the query; single-hop retrieval will miss. |
| High-stakes answers that must be grounded | Self-RAG | The model must justify or refuse, not infer. |
| Retrieval quality varies by query | Corrective RAG | Detect-and-retry differently beats retry-same. |
| Open-ended research over web/large corpus | Deep-research loop | Iterative search/read/synthesize; budget the cost. |
| Relationship-heavy corpus with entity/edge queries | GraphRAG | Graph joins beat vector proximity for relationships. |

### Pattern Composition

Patterns are not mutually exclusive. A common production shape is **query rewrite → hybrid retrieve → rerank → Self-RAG-style faithfulness check → Corrective RAG fallback on low faithfulness**. The composition is fine *if every stage has a budget and a hard cap*. Composing patterns without caps is how a "smarter" pipeline becomes an unbounded cost generator.

## When Plain RAG Wins

Use ordinary retrieve-then-rerank-then-answer when the corpus is stable, query patterns are predictable, latency matters, and the answer usually lives in one or two chunks. Agentic RAG earns its cost only when retrieval strategy genuinely depends on intermediate findings.

## Loop Controls

- Maximum retrieval iterations.
- Maximum documents/chunks read.
- Query budget and cost budget.
- Deduplication by document/chunk ID.
- Stop when new retrieval adds no novel evidence.
- Final answer must cite the specific evidence used.

### Self-RAG / Corrective RAG Pseudocode

The point of these patterns is a *controlled* loop with hard caps, not an open-ended "keep searching until it looks good."

**Self-RAG shape** — the model decides whether retrieved passages support the answer, and whether to retrieve at all:

```
1. classify query: needs_retrieval?
   - no  -> answer directly from parametric knowledge, mark "unsupported"
   - yes -> retrieve top_k
2. for each retrieved chunk: assess_relevance(chunk, query) -> {relevant, irrelevant}
3. if no relevant chunks -> answer "not enough evidence" (do NOT fabricate)
4. draft answer from relevant chunks
5. critique: is each claim in the answer supported by a cited chunk?
   - yes -> emit answer with citations
   - no  -> either re-draft with stricter instruction, or emit partial answer marked unsupported
6. hard caps: max_retrieval_calls = 1, max_redrafts = 2, total_tokens_budget
```

**Corrective RAG (CRAG) shape** — detect bad retrieval and retry differently, rather than retrying identically:

```
1. retrieve top_k for query
2. score retrieval confidence:
   - high   (>= threshold_A) -> proceed to generate
   - low    (<  threshold_B) -> discard retrieval, web-search / broaden query, re-retrieve
   - medium (between A and B) -> refine: dedupe, rerank, keep best subset, then generate
3. generate answer from the (possibly corrected) context
4. faithfulness check on the generated answer
   - pass -> emit with citations
   - fail -> mark unsupported, or loop once with a reworded query
5. hard caps: max_corrective_rounds = 1-2, max_total_chunks_read, wall_clock_budget
```

The two thresholds (`A`, `B`) and the hard caps are the parts that make these safe. Without them, "corrective" RAG becomes an unbounded loop that burns tokens retrying the same failing query. Pick `A` and `B` from your eval set — they are retrieval-confidence percentiles, not guesses.

## Failure Modes

1. **Unbounded retrieval loop.** Fix with iteration, token, wall-clock, and novelty caps.
2. **Context flooding.** Fix with reranking, clustering, compression, and the `prompt-context-engineering` skill.
3. **Evidence laundering.** The final answer cites retrieved docs that do not actually support the claim. Fix with faithfulness checks.
4. **Query drift.** Rewrites slowly move away from the user's question. Keep the original question visible to the planner/verifier.
5. **Graph mysticism.** A graph does not fix bad extraction or stale source data. Evaluate graph answers against labeled multi-hop cases.

### Failure-Mode Table (With Concrete Detection and Fixes)

| Failure mode | How it shows up | Detection signal | Concrete fix |
|---|---|---|---|
| Unbounded retrieval loop | Agent keeps searching, never answers | Retrieval-call count per run is an outlier (e.g., > p99); wall-clock exceeds budget | Hard cap on `max_iterations`, `max_chunks_read`, `max_tokens`, `wall_clock`; force a "best effort with citations" answer at the cap. |
| Context flooding | Answer quality drops as more chunks are added | Precision@k drops while recall stays flat; faithfulness drops | Cross-encoder rerank; cap k at the precision plateau; cluster-and-summarize near-duplicates before assembly. |
| Evidence laundering | Final answer cites chunks that don't support the claim | Faithfulness score < threshold (e.g., 0.9) on the eval set | Per-claim citation check before emit; refuse-with-citation instead of unsupported assertion. |
| Query drift | Rewrites slowly move off-topic across hops | Cosine similarity between original and current query drops below threshold | Carry the original query in the prompt; verifier checks final answer against the *original* query, not the last rewrite. |
| Retrieval skipping | Agent answers without retrieving when it should | "Unsupported" answers on queries whose answer is in the corpus | Calibrate the `needs_retrieval?` classifier; default to retrieving when uncertain. |
| Retrieval over-confidence | Agent retrieves once and trusts garbage | High answer confidence with low faithfulness | CRAG-style confidence scoring; discard low-confidence retrieval and re-broaden. |
| Graph mysticism | GraphRAG answers look confident but are stale or wrong | Multi-hop eval cases fail despite a populated graph | Evaluate graph answers against labeled multi-hop cases; treat extracted edges as untrusted until verified; refresh edges on source change. |
| Citation hallucination | Answer cites chunk IDs that don't exist or weren't retrieved | Cited IDs not in the retrieval log | Constrain generation to a provided ID allowlist; post-check citations against retrieved set. |

### Hard Caps (Concrete Defaults)

Treat these as starting values to tune against your own latency and cost budgets, not as laws:

| Cap | Starting value | What it bounds |
|---|---|---|
| `max_retrieval_iterations` | 2-3 per query | Total retrieve-rerank rounds. |
| `max_chunks_read` | 10-20 per query | Total evidence scanned, including discarded. |
| `max_total_tokens` | per-query budget | Input + output across all rounds. |
| `wall_clock_budget` | e.g., 30-60s interactive, longer for background | Forces a "best effort" answer rather than hanging. |
| `novelty_floor` | e.g., < 10% new tokens in retrieved set vs. previous round | Stop when a new round adds no new evidence. |
| `max_query_rewrites` | 1-2 | Bounds drift before the verifier checks against the original. |
