> Last verified: 2026-07. Model lineups and prices shift monthly — verify against provider pricing pages before committing to a production choice.

# Cloud Task-Model Matrix

This is a July 2026 routing snapshot, not a contract. Treat it as the place to refresh when a provider changes model IDs, context windows, or prices.

Routing on **Amazon Bedrock** (Bedrock-specific model IDs, endpoints, the direct-API feature gaps, inference profiles, and lifecycle/EOL) lives in `./bedrock-model-matrix.md` — use it when the deployment target is Bedrock rather than a provider's own API. **Azure OpenAI Service** is covered at the end of this file (deployment IDs, data residency, PTU, content-filter policy).

Primary sources checked: [Anthropic models](https://docs.anthropic.com/en/docs/about-claude/models/overview), [OpenAI models](https://platform.openai.com/docs/models), [Google Gemini models](https://cloud.google.com/vertex-ai/generative-ai/docs/models), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing), [Alibaba Bailian / Qwen](https://help.aliyun.com/zh/model-studio/getting-started/models), [Zhipu GLM models](https://docs.bigmodel.cn/cn/guide/start/model-overview), [xAI Grok models](https://docs.x.ai/docs/models), [Mistral API pricing](https://mistral.ai/pricing/api/), [Azure OpenAI Service models](https://learn.microsoft.com/azure/ai-services/openai/concepts/models), [Cohere platform models](https://docs.cohere.com/docs/models).

## Current Provider Anchors

| Provider | Current top/value/budget anchor | Context | Price signal | Tool-use note |
|---|---|---:|---|---|
| Anthropic | Claude Fable 5 / Opus 4.8 / Sonnet 5 / Haiku 4.5 | 1M on Fable/Opus/Sonnet, 200k on Haiku | Fable $10/$50, Opus $5/$25, Sonnet $3/$15, Haiku $1/$5 per MTok | Excellent agentic coding and long-running tool use; pin exact IDs. |
| OpenAI | GPT-5.6 Sol / Terra / Luna | 1.05M | Sol $5/$30, Terra $2.50/$15, Luna $1/$6 per MTok | Strong built-in function calling and hosted tool stack. Also deployable via Azure OpenAI Service (see Azure section). |
| [Google](https://cloud.google.com/vertex-ai/generative-ai/docs/models) | Gemini 3.1 Pro (frontier) / Gemini 3.5 Flash & Gemini 3 Flash (value) / Gemini 3.1 Flash-Lite (budget); Gemini 2.5 Pro/Flash still GA | 1M+ on Pro; Flash/Lite shorter — confirm per-SKU on the model page | Pricing page unreachable at refresh — **verify on provider pricing page** (AI Studio / Vertex Generative AI pricing) | Strong multimodal, long-context, and grounding tools; native function calling; tool quality varies by surface (AI Studio vs Vertex). |
| [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing) | deepseek-v4-pro (reasoning frontier) / deepseek-v4-flash (value, chat); legacy `deepseek-chat` & `deepseek-reasoner` deprecated 2026-07-24 (map to v4-flash non-thinking / thinking) | 1M context, up to 384K output | v4-pro $0.435 in / $0.87 out per MTok (cache miss); v4-flash $0.14 in / $0.28 out per MTok; cache hit ≈ $0.003–0.004/M input | Supports thinking mode, tool/function calls, JSON output; strong value. Rate limits and operational maturity vary by host. |
| [Qwen](https://help.aliyun.com/zh/model-studio/getting-started/models) | qwen3.7-max (frontier) / qwen3.7-plus / qwen3.6-flash (value), via Alibaba Bailian (Model Studio); also Qwen 3 Next 80B, Qwen 3 Coder, Qwen 3 235B on Vertex MaaS | Up to 1M on long-context SKUs; varies by model | Low-cost band undercutting frontier providers — verify on Bailian / Vertex MaaS pricing page | Function calling supported; strong open-weight + hosted value; evaluate schema adherence before production. |
| [GLM (Zhipu)](https://docs.bigmodel.cn/cn/guide/start/model-overview) | GLM-5.2 (flagship: 1M ctx, 128K out, open SOTA coding) / GLM-4.7 / GLM-4.7-FlashX; free tier GLM-4.7-Flash; GLM-5V-Turbo (vision). Also on Vertex as "GLM 5"/"GLM 4.7" (ZAI.org) | 1M on GLM-5.2; 200K on GLM-5 / GLM-5.1 / GLM-4.7 | See [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing); free Flash models exist | Native tool calling; strong coding and Chinese-language; good value fallback. |
| [Grok (xAI)](https://docs.x.ai/docs/models) | grok-4.5 (flagship, "most intelligent/fastest") / grok-4.3 & grok-4.20 family (value, 1M ctx) / grok-build-0.1 (code) | grok-4.5 500K; grok-4.3 / grok-4.20 1M; grok-build 256K | grok-4.5 $2 in / $6 out; grok-4.3 & grok-4.20 $1.25 in / $2.50 out per MTok | Strong reasoning; realtime via web/X search tools; function calling supported; knowledge cutoff Feb 1 2026. Also on Vertex. |
| [Mistral](https://mistral.ai/pricing/api/) | Mistral Medium 3.5 (frontier) / Mistral Large 3 (open flagship) / Mistral Small 4 (open, Apache-2.0 value); Devstral 2 (agentic coding), Magistral (reasoning), Codestral (completion) | Large context; varies by model | Medium 3.5 $1.5 in / $7.5 out; Large 3 $0.5 in / $1.5 out; Small 4 $0.15 in / $0.6 out per MTok | Function calling + hosted agent/tools API; EU data residency; strong open-weight option. |
| [Cohere](https://docs.cohere.com/docs/models) | Command A (frontier, 400K ctx, tool-use) / Command R+ 08-2024 (value); Embed v3 (english/multilingual), Rerank v3.5, Aya 23/Expanse for multilingual | 256K (Command A); 128K (Command R+) | Command A ≈ $2.5/$10 per MTok; Embed/Rerank priced per 1M tokens separately | Strong enterprise/RAG positioning; grounded tool calls; **note**: Cohere Command R / R+ on Bedrock EOL 2026-08-19 — migrate to Command A or direct API. |
| [Azure OpenAI Service](https://learn.microsoft.com/azure/ai-services/openai/concepts/models) | Same model families as OpenAI direct (GPT-5.x, o-series) plus Microsoft-hosted deployment IDs (e.g. `gpt-5.6-sol`, `o5-pro`); Provisioned Throughput Units (PTU) for reserved capacity | Same per-model as OpenAI direct | Pay-as-you-go matches OpenAI pricing; PTU is a flat-rate reservation for predictable workloads | **Same SDK shape** as OpenAI direct (`api_type="azure"` / `azure_endpoint=`). Distinct concerns: data residency, content-filter policy (default stricter than OpenAI), deployment-IDs-vs-model-names, and Microsoft Entra ID auth (no API key required for managed-identity deployments). Required for many regulated industries (FedRAMP, HIPAA, EU data boundary). |

### How to Use the Anchor Table

The table is a *price map*, not a recommendation. Use it to:

1. **Translate a route into expected cost.** If your route sends a coding step to a value tier at ~$3/15 per MTok, an 8k-in/2k-out step costs ~$0.054. Multiply by call volume for a weekly budget.
2. **Pick a fallback in a different failure-correlation class.** If the primary is on one provider, pick the first fallback on a *different* provider so quota and outage windows do not coincide.
3. **Compare value options across providers.** Several providers occupy the same value band; pick by your eval, not by familiarity.
4. **Watch the "verify on provider pricing page" flags.** Where the table could not confirm a price at refresh, treat that row as unverified until you check.

### Price Bands (Illustrative Groupings)

Grouping the anchors by effective price helps reason about tiers without memorizing every number:

| Band | Illustrative input/output per MTok | Examples from the anchors above |
|---|---|---|
| Budget | ~$1 in / ~$5-6 out | Haiku 4.5, Luna, Gemini Flash-Lite, GLM-4.7-Flash (free tier exists), Mistral Small 4. |
| Value | ~$2-3 in / ~$10-15 out | Sonnet 5, Terra, Gemini Flash tiers, DeepSeek v4-flash, grok-4.3/4.20, Mistral Large 3. |
| Frontier | ~$5-10 in / ~$25-50 out | Fable 5, Opus 4.8, Sol, Gemini 3.1 Pro, DeepSeek v4-pro, grok-4.5, Mistral Medium 3.5. |

These bands are a routing shorthand, not a contract. Always multiply by your real token volumes and confirm against the provider pricing page — and remember cache-read pricing can cut effective input cost dramatically for repeatable prompts.

## Task Matrix

| Task class | Best tier | Value tier | Budget tier | Selection note |
|---|---|---|---|---|
| Agentic coding | Claude Fable 5, Claude Opus 4.8, GPT-5.6 Sol | Claude Sonnet 5, GPT-5.6 Terra | GPT-5.6 Luna, strong hosted Qwen/DeepSeek coder | Tool reliability and patch discipline matter more than leaderboard score. |
| Tool-calling/orchestration | Claude Sonnet 5, GPT-5.6 Terra/Sol | Claude Haiku 4.5 for simple routes, Gemini pro tier | GPT-5.6 Luna, Qwen hosted | Measure JSON/schema adherence and recovery from tool errors. |
| Long-context analysis | Claude Fable 5/Opus 4.8/Sonnet 5, GPT-5.6, Gemini long-context SKUs | Gemini value tiers, Sonnet 5 | Luna/Haiku if retrieval can shrink context | Long context is not a substitute for retrieval quality. |
| Deep reasoning | GPT-5.6 Sol high reasoning, Claude Fable 5/Opus 4.8 | GPT-5.6 Terra, Claude Sonnet 5 | DeepSeek reasoning hosted | Use only where the task genuinely needs judgment. |
| High-volume classification/extraction | Claude Haiku 4.5, GPT-5.6 Luna | Gemini budget/pro tiers | Small hosted open models | Prefer structured outputs and batch APIs; do not pay frontier prices. |
| Creative writing | Claude Fable/Sonnet, GPT-5.6 Sol/Terra | Gemini pro, Mistral frontier | Luna/Haiku | Judge style on your own brand examples. |
| Vision | Claude current family, GPT-5.6, Gemini multimodal | Gemini value tiers | Smaller multimodal hosted models | Check image limits, OCR behavior, and safety filters. |
| Embeddings | Provider embedding SKUs, Voyage/Cohere/Jina where appropriate | OpenAI/Google low-cost embedding SKUs | Local embeddings if latency/privacy wins | Lock dimensionality; changing model means rebuilding the index. |

### How to Read the Matrix (Selection Procedure)

The table looks like a menu; it is a decision procedure. Use it in this order:

1. **Pick the row by task class.** If the work fits two rows (e.g., "code over a long context"), pick the row whose *verifier* you actually have — coding's verifier is tests; long-context's verifier is retrieval faithfulness.
2. **Start at the Value tier, not the Best tier.** The Best tier is for escalated failures, not first attempts. Run the Value tier against your eval set first.
3. **Drop to Budget only if the verifier is mechanical** (schema, regex, length). Budget tiers fail judgment tasks silently.
4. **Escalate to Best tier when a named verifier fails**, not when the prompt feels long. A 100k-token prompt that the Value tier answers correctly is not a Best-tier task.
5. **Re-measure on every model change.** A model ID alias can silently point at a new version; treat any alias change as a route change requiring an eval re-run.

### Worked Example: Picking a Tier for a Real Task

Task: "Read a 60-page PDF contract and extract 12 structured fields (parties, dates, liability caps, governing law) into a JSON schema."

- **Task class:** High-volume classification/extraction (the row), even though the input is long.
- **Verifier:** JSON schema + a field-presence check + a faithfulness spot-check (does the cited clause support the value?).
- **First attempt:** Budget tier (Haiku 4.5 / Luna) with strict schema. Most fields populate correctly; two are missing or hallucinated.
- **Diagnosis:** Faithfulness check fails on the liability-cap field — the model is paraphrasing, not quoting. This is a *verified* failure, not a hard prompt.
- **Escalation:** Re-run only the failing field on the Value tier with "quote the exact clause, then extract." Pass.
- **Cost shape:** ~95% of calls on budget tier, ~5% on value tier. Effective cost is close to the budget tier price, not the value tier price.

The mistake this procedure prevents: sending the whole 60-page PDF to the frontier reasoning model "because contracts are hard," paying frontier prices for work a budget model with a schema verifier can do.

## Practical Routing Defaults

Start with a value model for most agent steps. Escalate to a best-tier model only when a verifier catches a concrete failure: invalid patch, failed tests, bad extraction, insufficient reasoning, or an explicit uncertainty threshold. Use budget models for high-volume mechanical work with schemas and validators.

### Default-Then-Deviate Decision Table

| Situation | Default | Deviate when |
|---|---|---|
| New agent step, unknown difficulty | Value tier | Verifier fails twice → escalate one rung. |
| Bulk extraction with schema | Budget tier + batch API | Schema invalidation rate > 1% → add a validator pass, not a bigger model. |
| Coding patch with tests | Value coding tier | Tests fail or patch complexity > threshold → frontier coding tier. |
| Long-context Q&A | Retrieve + value tier (short context) | Retrieval cannot surface the evidence → long-context value/frontier tier. |
| Final answer that triggers an external send | Frontier reasoning + reviewer | Reviewer disagrees → human. |

### Cost-Per-Task Sanity Check

Before locking a route, multiply it out. Illustrative example using a mid-tier cloud model at ~$3/15 per MTok (input/output):

- A coding step averaging 8k input + 2k output tokens = $0.024 + $0.030 = **$0.054 per step**.
- A 12-step run with two escalations to a frontier tier at ~$10/50: 10 steps × $0.054 + 2 steps × (8k×$10/M + 2k×$50/M) = $0.54 + 2 × $0.18 = **$0.90 per run**.
- If the same run defaulted to the frontier tier for all 12 steps: 12 × $0.18 = **$2.16 per run**.

The ladder cuts cost ~2.4x at the same pass rate. Numbers are illustrative; substitute your real prices from the provider anchors above.

## Refresh Checklist

1. Re-check model IDs and aliases.
2. Re-check input/output prices, batch discounts, cache discounts, and regional price variants.
3. Re-check context and max-output limits.
4. Re-run a small tool-calling eval for every model you route to production.
5. Update the matrix and the `Last verified` banner together.

### Refresh Cadence and Owners

| Trigger | Cadence | Owner |
|---|---|---|
| Routine price/model drift | Monthly, before the `Last verified` banner ages past 45 days | Route owner. |
| Provider deprecation notice | On receipt of notice, before the deprecation date | Route owner + on-call. |
| Observed pass-rate drop | Within 24h of a regression alert | Route owner. |
| Quarterly audit | Once per quarter, full eval re-run | Eval owner. |

### Signs the Matrix Is Stale (Even Before the Banner Expires)

- A model alias that used to pass your eval now fails — the alias may have been silently repointed to a new version.
- Effective cost per task drifts more than ~20% with no route change — a price changed, a cache ratio changed, or output length changed.
- Tool-call exactness drops on a model you did not touch — provider-side template or system-prompt change.
- A provider's status page lists degradation in the window your pass-rate dropped.

Any of these is a reason to re-verify the relevant row before the monthly cadence forces it.
