---
name: memory-rag
description: "Designing retrieval-augmented generation and agent memory systems: chunking, embeddings, vector and hybrid retrieval, reranking, RAG evaluation, memory backends, and agentic retrieval loops. Use when building a knowledge-base chatbot, grounding answers in documents, choosing a memory backend, or debugging bad retrieval. Does not cover context-window prompt management itself (see prompt-context-engineering) or GPU serving for embedding/rerank models (outside agent-foundry's scope)."
---

# Memory and RAG

RAG is not "put documents in a vector database." It is a retrieval system with an answer generator attached. Agent memory is not a transcript dump. Both require explicit indexing, retrieval, assembly, verification, and freshness policy.

## When to Use

- You need answers grounded in private docs, source code, tickets, policies, PDFs, notes, or web research.
- Retrieval returns the wrong chunks, too many chunks, or plausible but unsupported answers.
- You need durable memory across sessions or across multiple agents.
- You are choosing between files, vector stores, graph memory, and user-model memory.
- You want retrieval as an agent tool for deep research or multi-hop tasks.

**Don't use for:** prompt-only context packing (`prompt-context-engineering` skill), model choice (`model-selection` skill), or eval-suite construction beyond RAG-specific metrics (`agent-evals` skill).

## RAG Pipeline

```
INDEXING:  documents -> parse -> chunk -> embed -> upsert index
QUERY:     question -> retrieve -> rerank -> assemble -> generate -> verify
MEMORY:    observe -> decide what to store -> write -> consolidate -> retrieve
```

### Phase Responsibilities

The pipeline diagram hides three disciplines that fail silently if neglected:

- **Indexing is offline and auditable.** Chunk boundaries, embedding model, and metadata must be reproducible from a config + a corpus version. If you cannot rebuild the same index from scratch, you cannot reason about a retrieval regression.
- **Query-time is where cost and latency live.** Each stage (retrieve → rerank → assemble → generate → verify) has its own budget; the verifier is the only stage that prevents bad answers from shipping.
- **Memory is governed, not dumped.** The `observe → decide → write → consolidate → retrieve` loop has a policy at `decide` (what to remember) and a gate at `consolidate` (what to promote). Without both, memory grows until it floods every prompt.

### Common Shape Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| No verifier at query time | Bad answers ship confidently | Add a faithfulness/citation check; require "I don't know" as an allowed output. |
| Indexing not reproducible | Retrieval regression after a rebuild, cause unknown | Version the chunking config + embedding model + corpus hash. |
| Retrieve-then-generate with no rerank | Top-k floods the prompt with near-duplicates | Add a cross-encoder reranker; cap k at the precision plateau. |
| Memory written directly to durable store | Contradictions and hallucinated facts accumulate | Route all writes through consolidation; never write durable in-run. |
| One index for everything | Mixed corpora (code + prose + IDs) all miss different ways | Use hybrid (dense + sparse) retrieval for mixed corpora; see the table below. |

## Chunking Quick Table

| Strategy | Use when | Avoid when |
|---|---|---|
| Fixed token/char | Quick prototype, uniform text | Tables, code, sections, legal/policy docs. |
| Recursive/structure-aware | Default for docs/code/markdown | Source structure is unavailable or misleading. |
| Semantic | Topic shifts matter more than layout | You need predictable sizes and cheap ingestion. |
| Overlap windows | Answers straddle boundaries | Corpus is huge and duplication hurts cost. |

Default to structure-aware chunking with modest overlap, then tune using retrieval evals.

### Chunking Decision Procedure

1. **Inspect the source shape.** Markdown with headers, code with function boundaries, PDFs with sections, and chat logs are not the same problem. Pick the strategy that respects the source's natural units first.
2. **Start at structure-aware with ~10-15% overlap.** This is the safe default that beats fixed-token on almost every real corpus.
3. **Cap chunk size to the embedding model's practical context**, not the generator's. A 2k-token chunk that fits a 32k embedding model is fine; an 8k chunk is not, even if the generator could read it.
4. **Preserve provenance in metadata**: source file, section path, line/char range, version. Without this, citations are impossible and eval failures are not reproducible.
5. **Tune against a labeled query set**, not by reading sample chunks. "Looks reasonable" is not a retrieval metric.

## Retrieval Quick Table

| Method | Best at | Pair with |
|---|---|---|
| Dense vector | Meaning/paraphrase | BM25 for exact terms. |
| Sparse/BM25 | IDs, names, error strings | Dense retrieval for synonyms. |
| Hybrid + RRF | Mixed corpora | Reranker for top-k precision. |
| Cross-encoder rerank | Sorting candidates accurately | Small first-stage candidate set. |
| Graph retrieval | Relationships and multi-hop facts | Source provenance and freshness checks. |

### Choosing a Retrieval Method

The default for almost any real corpus is **hybrid + RRF + rerank**, because real corpora mix prose (where dense wins) with identifiers (where sparse wins). The reasons to deviate:

| If your corpus is… | Use | Because |
|---|---|---|
| Pure prose, no IDs | Dense only | Sparse adds cost without recall. |
| Pure identifiers (logs, SKUs, error codes) | Sparse/BM25 only | Dense misses exact strings. |
| Mixed prose + code/IDs/names | Hybrid + RRF | Each method covers the other's blind spot. |
| Relationship-heavy (who-owns-what, dependencies) | Graph retrieval | Joins are the query; vector proximity is the wrong tool. |
| Large top-k that floods context | Add a cross-encoder reranker | Rerank raises precision so you can lower k. |

### Tuning Order (Avoid Random Knobs)

When retrieval is bad, teams reach for `k`, embedding models, and chunk size in random order. Use this order instead:

1. **Inspect the eval set.** Are the labels right? Is the failure a class of queries or one anecdote?
2. **Check chunking.** Did a semantic unit get split? (Most retrieval bugs are chunking bugs.)
3. **Add or tune a reranker.** Cheaper than re-embedding the corpus and usually the biggest precision win.
4. **Switch to hybrid.** If dense alone misses exact terms, hybrid is the fix.
5. **Re-chunk or re-embed.** Last resort; it invalidates chunk IDs and forces an eval re-baseline.

## Memory Escalation Ladder

| Rung | Start/upgrade trigger |
|---|---|
| Files/markdown | Default; small, auditable, human-readable memory. |
| Keyword/FTS DB | Too many files or exact search needs. |
| Vector store | Measured semantic recall failures. |
| Hybrid vector + sparse | Corpus has both concepts and exact identifiers. |
| Graph/user-model memory | Multi-hop relationships, personalization, or cross-agent shared memory are core requirements. |

### Concrete Triggers Per Rung

The ladder exists so you do not jump to a graph database on day one. Each upgrade must be justified by a *named failure* of the current rung, with a metric:

| Move | Trigger (with signal) | Do not move if |
|---|---|---|
| Files → keyword/FTS | Agents repeatedly re-ask for facts already in files; file count > a few hundred; grep latency or correctness is the bottleneck. | You have not tried a directory convention + an index file first. |
| Keyword/FTS → vector | Measured recall@k on a labeled query set is low for paraphrased concepts (e.g., recall@5 < 0.6 where the miss is synonyms, not exact terms). | The misses are exact-term lookups — those are an FTS problem, not a vector problem. |
| Vector → hybrid (vector + sparse) | Dense retrieval misses IDs, names, error strings, or codes that FTS would have caught; measured on the eval set. | Your corpus is pure prose with no identifiers — hybrid adds cost without recall. |
| Hybrid → graph/user-model | Multi-hop relationship questions dominate the failures (e.g., "who owns the service that depends on X"), or personalization across sessions is the product. | Single-hop retrieval already answers your queries; graph construction cost is not justified. |

### Metrics That Justify a Move

| Metric | What it tells you | Threshold to act |
|---|---|---|
| Recall@k | Are the right chunks being found? | Drop below your baseline (e.g., < 0.7) on the labeled set. |
| Precision@k | Are the top chunks relevant, or is context flooded? | Drop means reranking or smaller k, not a backend change. |
| MRR | Is the first relevant chunk ranked high? | Drop points at reranking, not at the backend. |
| Faithfulness | Are answer claims supported by retrieved context? | Drop means retrieval *or* generation changed; isolate before moving backend. |
| Manual-search frequency | How often do humans find what the agent missed? | Rising trend is the strongest signal that the backend is the bottleneck. |

Move backends only when retrieval metrics on a labeled set show the current rung cannot meet the target. Moving for fashion or for a single hard query is how teams end up running a graph database to answer five questions a day.

## Non-Negotiables

- No RAG tuning without a labeled query set.
- Store embedding model and dimension with the index.
- Separate retrieval metrics from answer faithfulness.
- Cite sources in generated answers when claims depend on retrieved text.
- Keep durable memory small and reviewed.
- Treat auto-extracted memory as untrusted until verified.

### Why Each Non-Negotiable Exists

| Rule | What breaks without it |
|---|---|
| No tuning without a labeled set | Every knob change is a guess; you cannot tell improvement from noise. |
| Store embedding model + dimension with the index | Silent nonsense after a model swap; cross-model matches are meaningless. |
| Separate retrieval metrics from faithfulness | You tune the retriever when the generator is the problem (or vice versa). |
| Cite sources | Unsupported claims ship as if grounded; no audit trail for errors. |
| Keep durable memory small and reviewed | Every turn pays token cost for stale or irrelevant facts. |
| Treat auto-extracted memory as untrusted | Hallucinated or wrong facts enter durable storage and influence future runs. |

### Concrete Thresholds to Adopt

These are starting values to calibrate against your own eval, not laws:

| Threshold | Starting value | Purpose |
|---|---|---|
| Labeled query set size | 50-200 cases | Small enough to label by hand, large enough to spot regressions. |
| Recall@k floor | ≥ 0.7 on the labeled set | Below this, the right chunks are not being found — fix retrieval first. |
| Faithfulness floor | ≥ 0.9 on generated answers | Below this, answers are not grounded — fix generation or retrieval. |
| Precision@k plateau | The k where precision stops rising | Cap k there; larger k floods context without precision gain. |
| Memory review cadence | Weekly durable audit | Catches stale/contradictory facts before they accumulate. |
| Auto-promotion evidence | ≥ 2 independent observations | Single observations are noise; require corroboration. |

## Reference Router

| Load | When |
|---|---|
| `references/rag-pipeline.md` | Designing chunking, embedding, retrieval, reranking, context assembly, and RAG metrics. |
| `references/memory-system-design.md` | Designing layered durable/working/knowledge memory and consolidation policy. |
| `references/backend-and-architectures.md` | Expanded comparison: Pinecone, Weaviate, Milvus, FAISS, pgvector, Qdrant, Chroma; embedding model selection (MTEB leaderboard, late-interaction, ZAI/local); reranker guidance; cognitive memory taxonomy (episodic/semantic/procedural); MemGPT/Letta/Mem0/Cognee architectures; managed/hosted offerings |
| `references/agentic-rag.md` | Using retrieval as a tool, query decomposition, Self-RAG/corrective loops, GraphRAG, and deep-research patterns. |

## Pitfalls

1. **Chunking purely by token count.** Fixed chunks split semantic units and corrupt retrieval. Prefer structure-aware chunks and validate with retrieval cases.
2. **Tuning with zero eval set.** If you do not know which chunks should answer known questions, every top-k tweak is guesswork. Build evals; see `agent-evals`.
3. **Jumping to graph memory too early.** Graph memory is expensive to build and debug. Exhaust files, keyword search, vector search, and hybrid retrieval first.
4. **Embedding/index mismatch.** Changing embedding models or dimensions without rebuilding the index produces nonsense. Dual-write or rebuild deliberately.
5. **Context flooding.** More chunks can reduce answer quality. Rerank, deduplicate, compress, and keep the prompt focused.
6. **Letting memory become policy.** Memory stores facts; operating rules belong in project instructions or skills.

### Pitfalls With Concrete Fixes

| Pitfall | Symptom | Concrete fix |
|---|---|---|
| Token-count chunking | Tables/code/sections split mid-unit | Switch to structure-aware chunking; add a retrieval eval case per split-prone source type. |
| No labeled query set | Every top-k change is a guess | Build 50-200 labeled (query, relevant-chunk-id) pairs before touching knobs. |
| Graph-too-early | Graph DB running for <10 queries/day | Revert to hybrid retrieval; only revisit when multi-hop failures dominate the eval set. |
| Embedding swap without rebuild | Retrieval returns nonsense after a model change | Store `embedding_model` + `dimension` + `version` per index; dual-write during migration, then cut over. |
| Context flooding | Answer quality drops as k rises | Add a cross-encoder reranker; cap k at the point where precision@k plateaus on the eval set. |
| Memory-as-policy | Agent follows a "rule" that lives only in memory | Move operating rules to project instructions or skills; keep memory to facts and preferences. |
| Stale durable memory | Every turn pays token cost for outdated facts | Run periodic consolidation; archive or demote facts not referenced in N days. |
| Auto-promotion of unverified facts | Wrong facts enter durable memory | Require candidate → review → promotion; auto-promote only low-risk facts with a rollback path. |
