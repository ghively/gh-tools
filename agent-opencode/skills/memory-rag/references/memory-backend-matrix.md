> Last verified: 2026-07. Memory backends, hosted offerings, and extraction features change quickly; verify project docs and service pricing before choosing.

# Memory Backend Matrix

## Backend Categories

| Backend | Recall type | Infrastructure cost | Ingest model | Multi-agent sharing | Maturity |
|---|---|---|---|---|---|
| Plain files/markdown/wiki | Exact human-readable facts, project notes | None/low | Caller writes explicitly | Easy through shared repo/docs | Highest simplicity, limited semantic search |
| SQLite/Postgres text + FTS | Keyword and metadata recall | Low | Explicit writes | Good with normal DB access | Mature |
| pgvector | Semantic recall inside Postgres | Low-medium | Explicit embeddings/upserts | Good | Mature and operationally familiar |
| Qdrant | Dedicated vector search/filtering | Medium | Explicit embeddings/upserts | Good | Mature vector DB |
| Chroma | Local/simple vector apps | Low | Explicit embeddings/upserts | Limited to app architecture | Good for prototypes/local apps |
| LanceDB | Embedded/local vector and hybrid workloads | Low | Explicit embeddings/upserts | Good if shared storage is designed | Strong local/dev fit |
| Zep/Graphiti | Conversation/user memory with graph extraction | Medium | Auto-extracts memories and graph edges | Designed for app/user scopes | Active, evaluate fit |
| Cognee | Graph + vector memory/RAG | Medium | Extract/cognify/load pipeline | Possible with shared backend | Active, evaluate ops |
| Honcho | User modeling and relationship memory | Managed/service | Auto/user-model oriented | Designed for multi-agent/user context | Managed maturity varies by use case |
| mem0 | Agent memory service/library | Low-managed to managed | Auto and explicit memory patterns | Supports shared/user scopes | Popular, evaluate privacy/pricing |
| Letta | Stateful agent memory/runtime | Medium | Agent/runtime-managed memory | Good inside its runtime model | Mature for stateful agents |

### Reading the Backend Table

- **Recall type** is the question you should be answering first. If your queries are keyword-shaped ("error E-4821"), an FTS backend beats a vector backend. If they are meaning-shaped ("how do we handle late invoices?"), you want semantic recall.
- **Ingest model** matters as much as retrieval. "Caller writes explicitly" means *you* decide what is stored; "auto-extracts" means the backend decides, and you inherit its extraction quality (and its hallucinations).
- **Multi-agent sharing** is a product decision, not an optimization. If agents must read each other's memory, the backend's isolation model becomes a security boundary.
- **Maturity** is a proxy for operational pain. "Active, evaluate fit" is honest code for "promising but you will hit edges."

### Backend Selection Procedure

1. **Name the recall type** your queries need (exact, semantic, hybrid, relational). This eliminates most of the table.
2. **Decide the ingest trust model.** Explicit writes (you control what is stored) vs. auto-extraction (the backend controls it). Auto-extraction is faster to start and riskier to operate.
3. **Check the sharing/isolation requirement.** Multi-tenant or multi-agent memory narrows the field further.
4. **Pick the least mature backend that meets the above.** Simpler backends are easier to operate, back up, migrate, and reason about. Add maturity only when a simpler option cannot meet the requirement.
5. **Verify provenance and migration *before* adopting.** If you cannot answer "where did this fact come from?" and "how do I move it?", do not adopt the backend for durable memory.

## Escalation Ladder

1. **Files.** Use when memory is small, human-audited, and retrieval can be explicit.
2. **Keyword/FTS database.** Use when file count grows and exact search matters.
3. **Vector store.** Use when semantic recall misses are real and measured.
4. **Hybrid retrieval.** Use when both paraphrase and exact identifiers matter.
5. **Graph/user-model memory.** Use when relationships, temporal facts, user preferences, or cross-agent personalization are central.

### Cost of Each Rung (Operational Reality)

Each rung up the ladder buys capability and costs operational complexity. The costs are real and recurring:

| Move up to | Capability gained | Recurring cost you accept |
|---|---|---|
| Keyword/FTS | Fast exact search over many files | Schema, indexes, backups, query tuning. |
| Vector store | Semantic recall | Embedding pipeline, re-embed on model change, index rebuilds, dimension migrations. |
| Hybrid retrieval | Both exact and semantic | Two indexes to keep in sync; fusion tuning (RRF weights). |
| Graph memory | Multi-hop joins | Graph extraction pipeline, edge freshness, contradiction resolution, re-extraction on source change. |
| User-model memory | Personalization at scale | Tenant isolation, privacy review, service dependency, vendor/portability risk. |

The pattern: **capability and operational cost rise together.** A rung is worth adopting only when the capability is measured to be needed and the team can carry the recurring cost. Adopting a rung you cannot operate is worse than staying simpler — an unmaintained graph database gives confidently wrong answers.

## Triggers to Move Up

- Move from files to search when agents repeatedly ask for facts already written down.
- Move to vectors when keyword search misses paraphrased concepts.
- Move to hybrid when dense retrieval misses IDs, names, commands, or exact errors.
- Move to graph memory when multi-hop relationship questions dominate.
- Move to user-model memory when preferences and long-term personalization are the product.

### Move-Up Decision Table (With Concrete Thresholds)

| Current rung | Signal that justifies moving up | Metric to log before moving |
|---|---|---|
| Files | Agents re-ask for facts already in files; or `manual_lookup` rate rises | `repeat_question_rate`, `files_count`, average time to find a fact manually |
| Keyword/FTS | Recall@k on labeled set is low for paraphrases; exact-term recall is fine | `recall@5_paraphrase` vs. `recall@5_exact` |
| Vector | Dense retrieval misses IDs, names, error codes, commands | `recall@5_exact_terms` (dense alone) |
| Hybrid | Multi-hop relationship questions fail repeatedly | `multi_hop_pass_rate` on labeled cases |
| Graph/user-model | Single-hop is solved but personalization or cross-agent memory is the product | Product requirement, not a retrieval metric |

### Move-Up Anti-Signals (Do Not Move On These)

| Anti-signal | Why it is not a reason | What to do instead |
|---|---|---|
| "Vector DBs are trendy" | Fashion is not a failure signal | Stay on files/FTS until a retrieval metric fails. |
| "One hard query failed" | Anecdote, not a pattern | Add it to the eval set; move only if a class of failures emerges. |
| "We want memory to fix unclear rules" | Memory cannot substitute for instructions | Write the rules in project instructions or skills. |
| "The new backend has a feature we might use" | Speculative features rot | Move when you use the feature, not when you might. |
| "Graph DBs feel more advanced" | Graph construction cost is real | Move only when multi-hop failures dominate the eval set. |

## Do Not Move Up Because

- The backend is fashionable.
- You have not built retrieval evals.
- You want memory to compensate for unclear operating rules.
- You need provenance but picked a backend that hides it.

## Hybrid and Multi-Backend Patterns

You are not required to pick one backend. Most production systems run **several rungs at once**, each where it earns its cost:

| Pattern | When | Example shape |
|---|---|---|
| Files + FTS | Durable facts in files, transcribed/searchable in a DB for speed | Markdown memory of record; FTS index as a cache. |
| FTS + vector | Mixed corpus with IDs and prose | Hybrid retrieval with RRF; one corpus, two indexes. |
| Vector + graph | Semantic recall plus relationship joins | Vector for "find the doc," graph for "what depends on it." |
| Files (durable) + user-model (personalization) | Project memory separate from user memory | Different trust levels, different backends, different review cadences. |

### Multi-Backend Pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Two sources of truth | Same fact in files and DB, drifting apart | Pick a primary; derive the other; never write both independently. |
| Cross-backend ID drift | Vector IDs and graph node IDs disagree after a rebuild | Use stable IDs derived from source content, not from insertion order. |
| Embedding model divergence | One backend re-embedded, the other did not | Store `embedding_model` per index; gate cross-backend joins on matching model + version. |
| Mixed trust levels | Untrusted auto-extracted facts read as if verified | Tag every entry with trust level; verifiers refuse to read below threshold for high-risk tasks. |
| Provenance loss at the join | Graph edge has no source; vector chunk lost its metadata | Require provenance at write time; reject entries without it. |

The discipline: each backend has one job, one trust level, and one provenance requirement. Composing backends is fine; blurring their roles is not.

## Operational Concerns Per Backend

| Concern | Files | FTS/SQLite/Postgres | pgvector / Qdrant / Chroma / LanceDB | Graph (Zep/Graphiti, Cognee) | User-model (Honcho, mem0, Letta) |
|---|---|---|---|---|---|
| Provenance / audit trail | Trivial (diff in git) | Good (row + timestamp) | Good if metadata stored | Depends on extraction logs | Depends on service; verify |
| Backup / restore | File copy | DB dump | DB dump + index rebuild | Graph dump + extraction state | Service-dependent; verify SLA |
| Migration cost | Low (move files) | Low-medium (SQL) | Medium (re-embed on model change) | High (re-extract graph) | High (vendor lock-in risk) |
| Privacy control | Full (host-local) | Full | Full if self-hosted | Full if self-hosted | Varies; check service terms |
| Stale-data handling | Version + archive | TTL columns | `ingested_at` filter | Edge freshness policy | Service-dependent |
| Multi-tenant isolation | Directory per tenant | Schema/row-level | Collection per tenant | Graph namespace | Service-dependent |

The pattern: **provenance and migration cost are inversely correlated with backend complexity.** The fancier the backend, the harder it is to answer "where did this fact come from, and can I move it?" Plan for both before adopting.
