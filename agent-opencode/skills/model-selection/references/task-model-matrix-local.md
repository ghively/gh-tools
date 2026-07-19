> Last verified: 2026-07. Open-weight model releases, quant quality, and tool-calling templates change quickly — verify model cards and serving runtime support before deployment.

# Local/Open-Weight Task-Model Matrix

Local models are selected by memory budget first, then task quality. The mistake is choosing a model that barely loads and then discovering it cannot reliably emit tool calls under real context.

## VRAM Tiers

| Tier | Practical model class | Good uses | Avoid |
|---|---|---|---|
| 8 GB | 4B-8B Q4/Q5 text, small embeddings | Simple chat, extraction, routing, local privacy demos | Heavy coding, long context, reliable multi-step tools |
| 12-16 GB | 8B-14B Q4/Q5, small vision models, rerankers | Coding assist, RAG answerer, task classifier, small tool agents | Assuming frontier reasoning or flawless JSON |
| 24 GB | 14B-32B Q4/Q5, stronger coder models | Local coding, RAG synthesis, richer tool use | Large MoE without careful offload |
| 48 GB+ | 32B-70B quantized, some MoE active-parameter models | High-quality local assistants, private code review | Treating local as cheaper if utilization is low |
| Multi-GPU | 70B+, MoE, high context | Specialized private deployments | Operational complexity without eval proof |

### Sizing a Model to a Tier (Procedure)

1. **Pick the model first**, then the quant. A 14B model at Q5 is a different animal from a 32B at Q3; comparing across both axes at once is how teams buy the wrong GPU.
2. **Compute weights + KV cache headroom.** Rule of thumb: weights at the chosen quant plus ~20-30% for KV cache, activations, and the rest of the stack. A "fits in 24 GB" claim that ignores KV cache will OOM under real context.
3. **Reserve headroom for concurrent requests.** A single-stream benchmark that fills the card tells you nothing about 2-4 concurrent agents sharing it.
4. **Leave a quant step of slack when possible.** A model that *just* fits at Q4 has no escape hatch if quality is too low — dropping to Q3 is rarely a rescue. Prefer a model that fits at Q5 with room.

### Per-Tier Failure Modes (Concrete)

| Tier | Most common failure | Detection signal |
|---|---|---|
| 8 GB | Tool-call JSON malformed under real context | Tool-call exactness < 0.9 on a 50-case set. |
| 12-16 GB | Hallucinated function arguments when context grows past ~6k | Pass rate falls as input length rises — plot pass-rate-vs-length. |
| 24 GB | Context-window optimism: "advertised 128k, usable ~32k" | Retrieval/answer quality degrades past a measured threshold; find it, document it. |
| 48 GB+ | Low utilization makes "local is cheaper" false | Cost-per-task higher than cloud equivalent at < ~30% GPU utilization. |
| Multi-GPU | Cross-GPU communication dominates latency; MoE routing overhead | p99 latency > 2x p50; throughput scales sublinearly with GPU count. |

## Current Families to Check

| Family | Strengths | Tool-calling note |
|---|---|---|
| Qwen 3.x | Strong general/coding/value coverage across sizes | Good templates, but measure function-call exactness per runtime. |
| Llama 4.x | Broad ecosystem and fine-tune support | Tool quality depends heavily on instruct variant and chat template. |
| DeepSeek distills | Strong reasoning/coding per parameter | Reasoning traces can interfere with streaming ReAct parsers; see `framework-selection/references/local-model-pitfalls.md`. |
| Gemma | Efficient smaller models and embeddings-adjacent options | Good for constrained tasks, not default for complex orchestration. |
| GLM | Competitive agent/coding models | Verify licenses and serving support. |
| Mistral/Devstral | Coding and agent-friendly variants | Strong candidates in 24 GB+ tiers. |
| Phi | Small efficient reasoning/extraction | Great budget tier; not a full agent brain by default. |

### Family Selection Notes

The "tool-calling note" column is doing a lot of work. Three things it implies but does not state:

- **"Good templates" is runtime-dependent.** A family with strong chat templates on one serving runtime can emit broken tool calls on another, because the template is applied by the runtime, not the model weights. Pin the runtime *and* the template version.
- **"Reasoning traces can interfere" is a parsing problem, not a quality problem.** A reasoning model that emits `<think>…</think>` before the tool call is fine if your parser strips it; it is broken if your parser treats it as the tool call. The fix is in the runtime, not the model.
- **"Verify licenses and serving support" is a procurement step, not a technical one.** Some families have non-commercial clauses or region restrictions; some serving runtimes support a family's tool format and some do not. Check both before committing.

### Family-to-Tier Quick Map

Illustrative pairings (verify the specific model card before deploying):

| VRAM tier | Families that typically fit at a useful quant |
|---|---|
| 8 GB | Phi (small), Gemma (small), Qwen 3.x small variants. |
| 12-16 GB | Qwen 3.x 8B-14B, GLM small, Mistral small, Gemma medium. |
| 24 GB | Qwen 3.x / Devstral / DeepSeek coder 14B-32B, Llama 4.x mid. |
| 48 GB+ | 70B-class coders/assistants across families, some MoE. |
| Multi-GPU | 70B+ and large MoE across families. |

This map is a starting point for "which families should I shortlist at my tier," not a deployment decision. The deployment decision needs the tool-call eval and the quant quality check below.

## Quantization Guide

| Quant | Fit | Quality cost | Use when |
|---|---|---|---|
| Q8/FP8/BF16 | Needs more memory | Low | Quality-sensitive evals or server GPU has room. |
| Q5 | Good balance | Low-medium | Default for important local agent work. |
| Q4 | Broadest fit | Medium | You need the model to fit on 8-24 GB. |
| Q3/Q2 | Emergency fit | High | Only for drafts or routing, never unverified tool use. |

### Choosing a Quant (Decision Table)

| You have… | Pick | Reason |
|---|---|---|
| Headroom for Q5 or better on the target tier | Q5+ | Quality cost is low-medium and recoverable; this is the safe default for agent work. |
| A model that fits at Q4 with no slack | Step down a model size, then Q5 | A smaller model at Q5 usually beats a bigger one at Q4 for structured tasks. |
| A model that *only* fits at Q3/Q2 | Stop — wrong model for the tier | Q3/Q2 is for drafts and routing, never for an agent controller or tool caller. |
| A quality-sensitive eval (coding, RAG answer) | Q8/FP8/BF16 if it fits | Spend the memory where the verifier is strict. |
| A throughput-bound classification pipeline | Q4 | Volume rewards the smaller footprint; schema verifier catches errors. |

### Quant Quality Check (Procedure)

1. Run your frozen eval set at the highest quant that fits comfortably (e.g., Q5 or Q8).
2. Run the same set at the target deployment quant (e.g., Q4).
3. Compare pass rate, tool-call exactness, and answer faithfulness. A drop of more than a few points on any of these means the quant is too aggressive for that role.
4. Record the quant in the route entry alongside the model name. A `qwen3-coder-14b` at Q5 and at Q3 are different models for routing purposes.

## Task Matrix

| Task | 8 GB | 12-16 GB | 24 GB | 48 GB+ |
|---|---|---|---|---|
| Agentic/tool use | Small Qwen/Phi only after eval | Qwen/GLM/Mistral 8B-14B | Qwen/Devstral/DeepSeek coder 14B-32B | 70B-class or strong MoE |
| Coding | 7B-8B coder Q4 | 14B coder Q4/Q5 | 32B coder Q4/Q5 | 70B+ coder |
| RAG answer synthesis | 7B-8B instruct | 8B-14B instruct | 14B-32B | 70B if answers are high stakes |
| Embeddings | Small embedding model CPU/GPU | Better multilingual/domain embeddings | Add reranker | Dedicated embedding/rerank service |
| Vision | Small vision-language | 7B-12B VLM | Strong VLM | Larger VLM/multimodal stack |

## Hard Rules

1. Run a tool-call eval before using a local model as an agent controller.
2. Keep context well below the advertised maximum until you test degradation.
3. Do not mix embeddings generated by different models in one index.
4. Prefer smaller reliable models over larger models that barely fit.
5. Track actual throughput and utilization; idle local hardware is not free.

## Pitfalls

| Pitfall | Symptom | Concrete fix |
|---|---|---|
| Chat-template drift across runtimes | Same model gives different tool-call quality on two servers | Pin the chat template version; record it next to the model ID in the route entry. See `framework-selection/references/local-model-pitfalls.md`. |
| Trusting advertised context window | Quality collapses past ~25-50% of the claimed window | Measure pass-rate-vs-context-length on your eval; document the *usable* window, not the advertised one. |
| Streaming ReAct parser breaks on reasoning traces | Agent hangs or emits malformed tool calls | Strip `<think>`/reasoning blocks before parsing, or use a runtime that handles reasoning models natively. |
| Mixing embedding models in one index | Retrieval returns nonsense after a model swap | Store `embedding_model` + `dimension` + `version` per vector; rebuild or dual-write on change. |
| Treating local as automatically cheaper | Cost-per-task higher than cloud at low utilization | Compute break-even: only below ~30-40% sustained GPU utilization does cloud win; above that, owned/leased compute tends to. |
| Quant too aggressive for the role | Tool-call exactness drops, JSON malformed | Re-run the quant quality check; step up one quant level or step down one model size. |
| No eval gate before promotion | A local model silently degrades an agent | Require tool-call exactness ≥ threshold (e.g., 0.95) and a coding-pass-rate ≥ threshold before a local model is allowed as a controller. |
| Single-GPU congestion under concurrency | p99 latency balloons when 2+ agents share the card | Queue per-GPU; cap concurrency to what fits KV-cache headroom, or shard across GPUs deliberately. |

## When Local Beats Cloud (Concrete Criteria)

Local is the right call when **at least one** of these is true and you can name the metric:

| Criterion | Threshold / signal |
|---|---|
| Privacy / data residency | Data cannot leave the host or region, by contract or regulation. |
| Sustained utilization | GPU utilization is above ~30-40% over a rolling week; below that, cloud pay-per-token is usually cheaper. |
| Latency | p99 round-trip to cloud is too high for interactive use and a local tier meets the latency target on eval. |
| Offline operation | The agent must run with no network dependency. |
| Cost at volume | Cost-per-task on local is lower than cloud at your measured throughput, with utilization accounted for. |

If none of these is true with a number attached, default to cloud — local carries serving, upgrade, and utilization cost that is easy to underestimate.
