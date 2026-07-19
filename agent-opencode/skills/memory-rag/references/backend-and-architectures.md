# Vector Backends, Memory Architectures & Embeddings

> Last verified: 2026-07. The vector-DB and agent-memory market shifts
> fast — Pinecone serverless, Weaviate Embeddings-4, Milvus 2.5, Qdrant
> 1.13, Letta 0.x APIs, Cognee v0.2. Verify against current docs before
> locking a backend choice.

This reference expands the `memory-backend-matrix.md` comparison table
with the four marquee production vector DBs missing from the original
matrix (Pinecone, Weaviate, Milvus, FAISS), adds the canonical cognitive
memory taxonomy (episodic / semantic / procedural), covers the
foundational agent-memory architectures (MemGPT/Letta, Mem0, Cognee), and
provides concrete embedding and reranker guidance.

## Expanded Vector Backend Comparison

### Pinecone

**Type:** Managed vector DB (serverless + pod-based).
**Strengths:** Zero-ops; serverless scales from zero; metadata filtering
native; namespaced per-tenant isolation built-in; SOC 2 Type II.
**Weaknesses:** No self-host option; pricing per pod-hour favors
steady-state workloads.
**Best for:** Production RAG where ops burden is the bottleneck.
**Embedding dimensions:** Up to 20,096 (serverless).
**Max vectors:** Billions (serverless).
**Pinecone Serverless vs Pod:** Serverless for variable workloads; pod
for steady-state with predictable throughput.
**ZAI / GLM note:** Use the OpenAI-compatible embedding endpoint with
Pinecone's client; set `api_key` and `base_url` to ZAI.

### Weaviate

**Type:** Open-source vector DB with managed cloud.
**Strengths:** Hybrid search (vector + keyword + BM25) native; GraphQL
API; multi-tenancy; self-hostable; generative search built-in.
**Weaknesses:** Heavier than pgvector for small datasets; management
overhead for self-hosted.
**Best for:** Hybrid search (vector + keyword + filtering) in one query.
**Modules:** `text2vec-*` (embedding), `reranker-*`, `generative-*`.
**ZAI / GLM note:** Use `text2vec-openai` module pointed at ZAI's
base URL; set `OPENAI_BASEURL` and `OPENAI_APIKEY`.

### Milvus

**Type:** Open-source vector DB (cloud-native, 2.5+ with hybrid).
**Strengths:** Cloud-native; horizontal scaling; hybrid search (dense +
sparse); GPU acceleration; RBAC + audit; self-hostable.
**Weaknesses:** Heavier ops than Pinecone serverless; overkill for
< 10M vectors.
**Best for:** Large-scale (100M+ vectors) production; teams with K8s
expertise.
**Hybrid Search (2.5+):** Combine BM25 + dense in one query; weighted
fusion with configurable coefficients.
**ZAI / GLM note:** Milvus 2.5+ supports any embedding model via a
gRPC RESTful proxy; register ZAI's OpenAI-compatible endpoint.

### FAISS

**Type:** Meta's open-source library (local, no server).
**Strengths:** Blazing fast on single-machine GPU/CPU; HNSW, IVF, PQ
indexes; pure local (no network); zero cost.
**Weaknesses:** No server, no multi-tenancy, no persistence out of the
box (pair with SQLite or LMDB for index persistence); write-heavy
workloads degrade HNSW.
**Best for:** Local-first dev, eval fixtures, single-user RAG, research.
**Index types:** HNSW (fastest reads, high memory), IVF (balanced),
PQ (low memory, lower recall).
**ZAI / GLM note:** FAISS is embedding-agnostic — you pass vectors, not
text. Generate vectors via ZAI's embedding endpoint then index with
FAISS.

### pgvector

**Type:** Postgres extension.
**Strengths:** You already have Postgres; zero new infrastructure; ACID;
row-level security for multi-tenancy; HNSW + IVFFlat indexes.
**Weaknesses:** Slower than dedicated vector DBs at > 10M vectors; no
hybrid search without DIY; analytics queries compete with vector reads.
**Best for:** Adding vector search to an existing Postgres app; < 10M
vectors.
**HNSW support:** pgvector 0.7+; tune `m` and `ef_construction` per
the docs.

### Qdrant

**Type:** Open-source vector DB with managed cloud (Qdrant Cloud).
**Strengths:** Payload filtering (arbitrary JSON) is first-class; fast
filtered search; Rust-native; multi-tenant via collections; on-disk
storage for large indexes.
**Weaknesses:** Smaller ecosystem than Pinecone/Weaviate; fewer managed
cloud regions.
**Best for:** Filtered vector search where payload shape is complex.
**Quantization:** Scalar, product, and binary quantization for memory
savings.

### Chroma

**Type:** Open-source, embedding-native, local-first.
**Strengths:** Zero-config for dev; embedding function auto-wrapped;
Pythonic API; simple cloud option.
**Weaknesses:** Not production-hardened at scale; fewer index options
than FAISS/Milvus.
**Best for:** Rapid prototyping; small-to-medium RAG; embedding-native
workflows.

## Embedding Model Guidance

### How to Choose

| Factor | Decision |
|---|---|
| **Dimension** | Higher = more discriminative, more storage + compute. 1024 → 1536 → 3072 → 4096. Start at 768 or 1024; go higher only if recall benchmarks show gain. |
| **Language** | Multilingual models (`multilingual-e5`, `bge-m3`, `text-embedding-3-large`) cover 100+ languages. Monolingual models are smaller and faster when language is known. |
| **Task** | Retrieval (`bge`, `e5`, `gte`), classification (`instructor-xl`, `gte`), clustering, STS. |
| **Provider** | OpenAI (`text-embedding-3-small`, `text-embedding-3-large`), Cohere (`embed-v3`), Voyage (`voyage-3`), Google (`textembedding-gecko`), ZAI/GLM (`embedding-2`), local (`bge-m3` via ONNX/sentence-transformers). |
| **MTEB leaderboard** | https://huggingface.co/spaces/mteb/leaderboard — the canonical retrieval benchmark. Check BOTH retrieval score AND classification/clustering if those tasks matter. |

### ZAI / GLM Embedding

```python
from openai import OpenAI
client = OpenAI(
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
response = client.embeddings.create(
    model="embedding-2",
    input=["Find open P1 tickets"],
    dimensions=1024,
)
vector = response.data[0].embedding
```

### Local Embedding (Ollama / sentence-transformers)

```python
# via Ollama
curl http://localhost:11434/api/embeddings -d '{"model":"bge-m3","prompt":"..."}'

# via sentence-transformers
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("BAAI/bge-m3")
vectors = model.encode(["Find open P1 tickets"])
```

### Late-Interaction Models (ColBERT)

ColBERT (`jina-colbert-v2`) stores per-token vectors and computes
MaxSim at retrieval time. Not a single-vector model — query and document
are both matrices. Best for high-recall, high-precision retrieval; more
storage and slower queries than single-vector.

## Reranker Guidance

### Cross-Encoder vs LLM-as-Reranker

| Type | Speed | Cost | Accuracy | Best for |
|---|---|---|---|
| Cross-encoder (Cohere Rerank v3.5, BGE-reranker-v2-m3) | Fast (ms) | Low | High | Top-20 reordering; production default |
| LLM-as-reranker (GLM-4.5-air, GPT-5.6-Luna) | Slow (s) | Medium (per-token) | Highest | Top-5 final pass; "which ONE chunk?" |
| Late-interaction (ColBERT) | Medium | Low | High | Retrieval-time (no separate rerank) |

### Default Rerank Pipeline

```python
# 1. Retrieve top-50 candidates (dense)
results = vector_db.search(query_vector, top_k=50)

# 2. Rerank top-20 with fast cross-encoder
from cohere import Client
reranked = cohere.rerank(
    model="rerank-v3.5",
    query=query,
    documents=[r.content for r in results[:20]],
)

# 3. Take top-5; optional LLM final pass for "which ONE?"
# Only for high-stakes answers; skip for throughput-oriented RAG
```

### ZAI / GLM as a Reranker

```python
response = client.chat.completions.create(
    model="glm-4.5-air",  # cheap, fast
    messages=[{
        "role": "system",
        "content": "Which of the following passages BEST answers the question? Return only the index (1-5)."
    }, {
        "role": "user",
        "content": f"Question: {query}\n\n" + "\n\n".join(
            f"[{i+1}] {doc}" for i, doc in enumerate(top5)
        )
    }],
    response_format={"type": "json_object"},
)
```

## Memory Architectures

### The Cognitive Taxonomy

| Memory type | What it stores | Analog in agent systems |
|---|---|---|
| **Episodic** | Specific events and experiences (timeline) | Session transcripts, user interactions, dated facts |
| **Semantic** | Facts, concepts, and general knowledge | The wiki, the knowledge base, the RAG corpus |
| **Procedural** | How to do things (skills, workflows) | Agent skills, prompts, operating rules |

Most agent systems implement episodic via session history, semantic via
RAG, and procedural via skills/prompts. The canonical papers: MemGPT
(OS-style virtual memory for agents), Letta (productionized MemGPT),
Mem0 (graph + vector dual memory), Cognee (cognify graph extraction).

### MemGPT (the Architecture)

MemGPT introduced OS-style virtual memory for LLMs: hierarchical context
blocks, paging between main context and external storage, FIFO eviction.
The key insight: the agent treats its context window like an OS treats
RAM — paging less-relevant content out to long-term storage.

- **Main context:** The active window (like RAM). Limited by the model's
  context budget.
- **External memory:** The durable store (like disk). SQLite, Postgres,
  a vector DB.
- **Memory manager:** The agent itself (or a sub-routine) decides what
  to page in and out.

Letta is the productionized successor. Key additions: memory blocks as
typed records, block-level CRUD, and multi-agent memory sharing.

### Mem0

Dual-memory model: graph (entity relationships) + vector (semantic
retrieval). Memories are created via tool calls (`mem0.add()`,
`mem0.search()`). The agent reads from Memory0's API; memory is a tool,
not a hidden side effect.

### Cognee

Cognify pipeline: ingest documents, extract entities and relationships,
build a knowledge graph, support natural language queries. Closer to a
GraphRAG engine than a memory runtime — the output is the graph, not
the session state.

### Layer Mapping: Which Tool for Which Concern

| Concern | Tool | When |
|---|---|---|
| Durable session memory | Letta, SQLite, Postgres | Cross-session state |
| Long-term user profile | Mem0, Honcho | Multi-session user modeling |
| Knowledge graph over documents | Cognee, Zep, Graphiti | Entity/relationship queries |
| RAG over a corpus | Pinecone, Weaviate, Milvus, Qdrant, pgvector, Chroma | Answer grounding |
| Local-first dev | FAISS, Chroma, LanceDB | No-network RAG |

## Managed / Hosted Offerings

| Platform | Vector DB | Embedding | Reranker | LLM | Self-host option? |
|---|---|---|---|---|---|
| Pinecone | Serverless | — (BYO) | Partner (Cohere) | — | No |
| Weaviate Cloud | Weaviate | Built-in + BYO | Built-in + BYO | Built-in (generative) | Yes |
| Qdrant Cloud | Qdrant | — (BYO) | — | — | Yes |
| Vertex AI Vector Search | Google's | Vertex AI | Vertex AI | Vertex AI | No |
| Azure AI Search | Azure's | Azure OpenAI | Microsoft | Azure OpenAI | No |
| AWS OpenSearch Serverless | OpenSearch + vector | — (BYO) | — | — | No |
| Vercel AI SDK | RAG via `@ai-sdk` | BYO | BYO | Built-in | No |

## Pitfalls

1. **Pinecone for dev-only workloads.** Serverless scales to zero in
   price, not to zero in latency — cold starts are real. Fix: keep a pod
   for steady-state; serverless for variable.
2. **pgvector for 100M+ vectors.** It works; it will be slow. Fix: move
   to Milvus or Pinecone at that scale.
3. **FAISS with no persistence wrapper.** Container restart → index lost.
   Fix: `faiss.write_index()` to disk on shutdown; `faiss.read_index()`
   on startup; or use LanceDB which wraps FAISS-style indices with
   persistence.
4. **Forgetting the embedding dimension at creation.** Create a 768-dim
   index with a 1024-dim model → silent failures. Fix: store
   `embedding_model` + `dimension` beside the index.
5. **Reranker on every retrieval.** Adds cost and latency. Fix: rerank
   only the top-K candidates; bypass for throughput-oriented queries.
6. **Cognee as a general-purpose memory store.** It's a graph extraction
   pipeline, not a session store. Fix: Cognee for knowledge graphs;
   Letta or Mem0 for session memory.
