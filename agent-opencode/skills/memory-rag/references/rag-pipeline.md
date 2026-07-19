> Last verified: 2026-07. RAG libraries and evaluation APIs change frequently; verify package docs before copying code into production.

# RAG Pipeline

RAG has two phases: indexing and query-time use.

```
documents -> load -> chunk -> embed -> index
query -> rewrite? -> embed -> retrieve -> rerank -> assemble context -> generate -> verify
```

## Chunking Strategy

| Strategy | Boundary | Pros | Cons |
|---|---|---|---|
| Fixed token/char | Every N tokens with optional overlap | Simple and predictable | Splits sentences, tables, and code blocks. |
| Recursive/structure-aware | Sections, paragraphs, sentences, then token cap | Best first default | Needs clean document parsing. |
| Semantic | Split where embedding similarity drops | Topically coherent | Extra pass; less predictable size. |
| Window with overlap | Sliding chunks with 10-20% overlap | Reduces boundary misses | More chunks and duplicate retrieval. |

Default: recursive/structure-aware chunking with modest overlap, tuned against retrieval evals. Chunk size should fit the embedding model's practical context, not the generator's context.

### Worked Example: Fixed-Token vs Structure-Aware (Before/After)

Source: a Markdown runbook with a section like:

```
## Restart procedure
1. SSH to the host listed in the inventory.
2. Run `systemctl restart payments-api`.
3. If the health check at `/healthz` returns non-200, page on-call.
```

**Before — fixed 100-token chunks, no structure awareness:**

```
chunk_017: "...the host listed in the inventory. 2. Run `systemctl restart"
chunk_018: "payments-api`. 3. If the health check at `/healthz` returns non-200,"
chunk_019: "page on-call. ## Backup procedure 1. Snapshot the..."
```

Query: *"how do I restart the payments API?"* — retrieval returns chunk_017 (the verb `restart` is split off from `payments-api`) and chunk_018, but neither contains the full procedure. The answer model either hallucinates the host step or omits the health-check step.

**After — structure-aware chunking on Markdown headers:**

```
chunk_007: "## Restart procedure\n1. SSH to the host listed in the inventory.\n
           2. Run `systemctl restart payments-api`.\n
           3. If the health check at `/healthz` returns non-200, page on-call."
```

Same query now retrieves chunk_007, which contains the entire procedure. Recall@5 on this query goes from 0.5 (one of two relevant chunks) to 1.0, and answer faithfulness goes from "partially supported" to "fully supported."

The lesson is not "Markdown is special" — it is that **chunk boundaries should not cross semantic units the user will query as a unit**. Procedures, table rows, function bodies, and definition+example pairs are all units.

### Chunk Metadata to Record

Every chunk should carry enough metadata that an eval failure is reproducible and a citation is auditable:

| Field | Why |
|---|---|
| `chunk_id` (stable) | Lets eval cases reference specific chunks across rebuilds. |
| `source_path` + `version` | Provenance for citations and stale-chunk detection. |
| `section_path` (e.g., `doc > ## Restart procedure`) | Lets metadata filters narrow retrieval and lets humans navigate back. |
| `char_range` / `line_range` | Exact span for citation highlighting. |
| `embedding_model` + `dimension` | Prevents cross-model mismatch; required for safe rebuilds. |
| `ingested_at` | Freshness filtering for time-sensitive corpora. |

### Provenance and Licensing

What you ingest, you redistribute — RAG surfaces source text (often near-verbatim in a chunk) into answers and citations, so the corpus carries the same copyright, licensing, and terms-of-service obligations as any republication. Ingestion is the point to enforce this, because it is the only point where you still know where each chunk came from.

- **Copyright / licensing of the corpus.** Ingesting third-party documents, books, paywalled articles, or code under restrictive licenses does not neutralize their license. A chunk emitted verbatim in an answer can be an infringing copy, and mixing incompatible licenses (e.g., copyleft code) into a shared index contaminates downstream use. Clear the right to ingest *and to surface* each source before it enters the pipeline.
- **Attribution obligations.** Many licenses (CC-BY, most open-source licenses, some data agreements) require attribution or license notices to travel with the content. If your citations drop the source and license, a compliant corpus becomes a non-compliant product. Carry attribution through to the cited answer, not just the index.
- **Robots / ToS for scraped context.** Scraped web content is governed by the site's `robots.txt` and terms of service; "publicly reachable" is not "licensed to ingest." Honor crawl directives and rate limits, and record whether a source permitted ingestion — a live agentic web-fetch is the same obligation at query time (see `agentic-rag.md`, deep-research loop).
- **The mitigation is provenance metadata per chunk.** Extend the chunk metadata above with `source_license`, `attribution` (required notice/author), `source_url`, and `ingest_permission` (how the right to ingest was established). Then a license or takedown question becomes a metadata filter — surface only chunks whose license permits it, attach the required attribution to citations automatically, and evict a whole source by its provenance key when rights change. Chunks with unknown provenance are quarantined, not silently served.

## Retrieval Methods

| Method | Strength | Weakness |
|---|---|---|
| Dense vector | Paraphrase and semantic match | Misses exact IDs, rare terms, acronyms. |
| Sparse/BM25 | Exact terms, names, codes | Misses paraphrase. |
| Hybrid + reciprocal-rank fusion | Combines dense and sparse strengths | More moving parts and tuning. |
| Cross-encoder rerank | Better top-k precision | Too expensive for full-corpus search; use after first-stage retrieval. |
| Metadata filters | Reduces search space | Bad metadata silently hides relevant docs. |

## Context Assembly

Assemble context with source markers, stable ordering, and enough surrounding text for meaning. Avoid flooding the prompt with near-duplicates. For long-context models, place the most relevant material where the model attends reliably rather than burying it in the middle.

## Evaluation

Separate retrieval quality from answer quality.

| Metric | Measures |
|---|---|
| Precision@k | Fraction of retrieved chunks that are relevant. |
| Recall@k | Fraction of known relevant chunks retrieved. |
| MRR | Rank of the first relevant chunk. |
| nDCG | Ranking quality with graded relevance. |
| Faithfulness | Whether answer claims are supported by retrieved context. |

Use a labeled query set before tuning. RAGAS and similar tools can score faithfulness/context metrics, but LLM-judge calls require calibration and cost tracking.

### Worked Retrieval-Metrics Example

Suppose a labeled query set with 5 queries, each annotated with the set of chunk IDs that should answer it. You retrieve top-5 for each query. For one query the relevant chunk IDs are `{C2, C7}` and your retriever returns, in order, `[C7, C19, C2, C44, C3]`.

- **Precision@5** = relevant retrieved / retrieved = 2 / 5 = **0.40**. Two of five slots were wasted on irrelevant chunks; consider reranking or lowering k.
- **Recall@5** = relevant retrieved / total relevant = 2 / 2 = **1.00**. Nothing was missed; the problem is ranking, not coverage.
- **MRR** = 1 / rank of first relevant = 1 / 1 = **1.00**. The first result was relevant — good for "first answer wins" UIs.
- **nDCG@5** (binary relevance, graded): DCG = 1/1 + 0/2 + 1/log2(3) + 0/4 + 0/5 = 1 + 0.631 = 1.631. Ideal DCG (relevant first) = 1 + 1/log2(3) = 1.631. nDCG = 1.631 / 1.631 = **1.00**.

Aggregated across the 5-query set, suppose Precision@5 averages 0.40, Recall@5 averages 0.85, MRR averages 0.70, nDCG averages 0.78. The diagnosis:

| Pattern | Diagnosis | Action |
|---|---|---|
| High recall, low precision | Right chunks found, buried in noise | Add a cross-encoder reranker; lower k after reranking. |
| Low recall, high precision | Top results are relevant but chunks are missed | Raise k, improve chunking, or add query rewriting — not reranking. |
| Low MRR, decent recall | Relevant chunks present but ranked low | Reranker or hybrid fusion (RRF) tuning. |
| High retrieval metrics, low faithfulness | Retrieval is fine; generation is the problem | Fix the prompt, the model, or the context assembly — not the retriever. |

The single most common RAG debugging mistake is to tune the retriever when faithfulness is the failing metric. Always read retrieval metrics and answer metrics separately.

### Building the Labeled Query Set

A RAG eval is only as good as its labels. Minimum viable set:

1. **50-200 queries** drawn from real usage logs where possible, not invented queries that flatter the system.
2. **Per query, the set of chunk IDs** a human judged as relevant (binary or graded).
3. **Per query, the reference answer or required facts**, so faithfulness can be checked without re-reading the corpus.
4. **Difficulty mix**: include vague queries, multi-hop queries, and queries whose answer is "not in the corpus" — the system must be allowed to say "I don't know."
5. **Versioning**: freeze the set, version it, and re-run on every retrieval change so improvements are comparable.

## Engineering Rules

1. Keep chunk IDs stable so eval failures are reproducible.
2. Batch embedding calls during ingestion.
3. Store embedding model name, dimension, and version with every index.
4. Use hybrid retrieval for code, logs, IDs, product names, and acronyms.
5. Add reranking before increasing top-k blindly.
6. Require the generator to say when the retrieved context lacks an answer.
7. Rebuild or dual-write indexes when changing embedding models.
