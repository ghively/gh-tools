> Last verified: 2026-07. Bedrock's catalog, pricing, and model lifecycle shift monthly — verify against aws.amazon.com/bedrock/pricing/ and each model's card before any production commitment.

# Bedrock Model Matrix

This is the Bedrock-specific catalog and mechanics reference for the `model-selection` doctrine: **classify → route to the cheapest capable model → escalate on verified failure.** It owns *how models behave on Bedrock* (IDs, endpoints, feature gaps, inference profiles, lifecycle). For cross-provider task-tier guidance and price bands, use `references/task-model-matrix-cloud.md` — this file does not duplicate it.

**Confidence discipline (read first).** AWS's own Bedrock pricing page was JS-rendered and returned contradictory numbers at refresh. Every Bedrock dollar figure below is marked **approximate** and carries a **verify at aws.amazon.com/bedrock/pricing/ before committing** flag. Direct Anthropic API prices are high-confidence (platform.claude.com) and are stated plainly as a parity anchor — they are *not* Bedrock prices. Never route a production budget off an approximate number in this file.

### How to Use This Reference

The sections answer different questions; read them in the order the job demands:

| Job | Read order | Why |
|---|---|---|
| "Can Bedrock host this agent at all?" | §3 feature gaps → §1 endpoints | A missing server-side feature is a hard no before catalog or price matters. |
| "Which model for this agent role?" | §5 role matrix → §2/§4 tables → §6 lifecycle | Pick the role's tier, confirm the model's capabilities, then confirm it is not near EOL. |
| "What will this cost on Bedrock?" | §2/§4 prices (hedged) → §7 tiers → verify live | Every number here is a starting estimate to confirm against the live pricing page. |
| "A model I pinned is being deprecated" | §6 lifecycle → §5 role matrix | Find the EOL date, then the same-role replacement. |

Then always close the loop with the pillar doctrine: name the verifier, route to the cheapest capable model, and escalate only when that verifier fails.

## 1. Why Bedrock for Agents

Bedrock puts model calls inside your AWS account. That buys three things an agent platform actually needs:

- **IAM/billing boundary.** Model access is an IAM policy, spend lands on the AWS bill, and there is no Anthropic (or other provider) API key to provision, rotate, or leak. For a fleet of agents this collapses secret management into the IAM you already run.
- **Data-plane locality.** Requests stay within AWS networking and your chosen geography (see inference profiles below), which is often what a residency requirement actually demands.
- **One tool-call surface across families.** The Converse API's `toolConfig` gives a unified tool-use shape across Claude, Nova, Llama, Mistral, and the rest — so a router can swap model families without rewriting tool definitions.

### The Two Endpoints

| Endpoint | Shape | Use for |
|---|---|---|
| `bedrock-runtime` | `InvokeModel` / `Converse` — AWS-native request/response | Legacy Claude integrations, and non-Claude families that only expose the Converse path. |
| `bedrock-mantle` | `https://bedrock-mantle.{region}.api.aws/anthropic/v1/messages` — native Messages API shape, SSE streaming | **Recommended for new Claude integrations.** Same request body as the direct Anthropic API, so code ports with an endpoint + auth swap. Also serves some third-party models over OpenAI-compatible paths (e.g. Mistral Large 3). |

Prefer `bedrock-mantle` for Claude: it keeps your Messages-API code identical to direct-API code, which makes "same agent, swap the endpoint" a config change rather than a rewrite.

## 2. The Claude Table

Current Claude models on Bedrock. IDs, context, and capabilities are high-confidence (AWS model cards). The direct-API price columns are high-confidence Anthropic list prices shown as a **parity anchor only** — Bedrock's own numbers are hedged in the note below.

| Model | Bedrock ID | Ctx | Max out | Tools | Thinking | Cache | Cutoff | Inference profiles |
|---|---|---:|---:|:---:|---|---|---|---|
| Opus 4.8 | `anthropic.claude-opus-4-8` | 1M | 128K | Y | adaptive | Y (4096 min/ckpt, 4 ckpts, 5m/1h) | Jan 2026 | us/eu/jp/au + global |
| Sonnet 5 | `anthropic.claude-sonnet-5` | 1M | 128K | Y | always-on adaptive, effort config | Y | Jan 2026 | us/eu/au + global (no jp at refresh) |
| Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` (runtime) / `anthropic.claude-haiku-4-5` (mantle) | 200K | 64K | Y | supported | Y | Feb 2025 | us/eu/au/jp + global |
| Fable 5 | `anthropic.claude-fable-5` | 1M | 128K | Y | always-on | Y | — | — (not enumerated at refresh) |

Note the Haiku 4.5 ID **differs between endpoints** — a dated `...-v1:0` string on `bedrock-runtime`, a bare alias on `bedrock-mantle`. Pin the correct one per endpoint; a copy-pasted ID from the wrong endpoint is a silent 400.

### Direct-API Pricing (Parity Anchor — HIGH Confidence, per MTok)

These are Anthropic list prices, not Bedrock prices. Use them to reason about the *shape* of Bedrock cost, then verify the real Bedrock number.

| Model | Input | Output | Cache write 5m/1h | Cache read | Batch in/out |
|---|---:|---:|---:|---:|---:|
| Opus 4.8 | $5 | $25 | $6.25 / $10 | $0.50 | $2.50 / $12.50 |
| Sonnet 5 (intro, thru Aug 31 2026) | $2 | $10 | $2.50 / $4 | $0.20 | $1 / $5 |
| Sonnet 5 (from Sep 1 2026) | $3 | $15 | $3.75 / $6 | $0.30 | $1.50 / $7.50 |
| Haiku 4.5 | $1 | $5 | $1.25 / $2 | $0.10 | $0.50 / $2.50 |

### Bedrock Pricing Note (HEDGED)

- **Parity claim — MEDIUM confidence.** An aggregator reports Bedrock at exact parity with direct-API list (e.g. Opus 4.8 at $5/$25), consistent with the historical pattern. AWS's own page could not be fetched to confirm. **Treat as approximate; verify at aws.amazon.com/bedrock/pricing/ before committing.**
- **Regional-endpoint knob — HIGH confidence.** Calling a model through a single-region (in-region) endpoint costs **+10%** vs a global inference profile. Geo profiles carry no premium. This is a real, documented Bedrock-only cost lever — see §6 pitfalls.
- **Batch on Bedrock — do not assume.** The direct-API Batch column above does **not** exist as the Anthropic Batch API on Bedrock (see §3). Bedrock has its own batch-inference mechanism with separate pricing; do not carry the direct-API batch discount into a Bedrock budget.
- **"Claude Platform on AWS" is a different product.** Anthropic-operated, sold via AWS Marketplace in CCUs (~$0.01), with same-day feature parity to the direct API. It is **not** Bedrock and is priced separately. Use it when you need direct-API features on an AWS contract (see §3).

## 3. The Feature-Gap Table (Decision-Critical)

Claude on Bedrock is the Messages API **minus** the server-hosted feature surface. This table is the routing gate: if an agent's design depends on a "NOT on Bedrock" row, Bedrock cannot host that agent — route it to the direct API or to Claude Platform on AWS.

| Capability | Bedrock / mantle | Direct API | Routing consequence |
|---|:---:|:---:|---|
| Messages API, streaming | Y | Y | Core path works; port via `bedrock-mantle`. |
| Prompt caching | Y | Y | Same cache mechanics; big lever on repeated system prompts. |
| Extended / adaptive thinking | Y | Y | Reasoning roles fine on Bedrock. |
| Client-side tools (Bash, Computer Use, Memory, Text Editor) | Y | Y | You execute the tool; model just emits calls. |
| Citations, structured outputs | Y | Y | RAG-answer and extraction roles fine. |
| **Server-side tools: web search, web fetch, code execution, advisor** | **N** | Y | Agent needing hosted search/exec must use direct API or Platform on AWS, or you build the tool client-side. |
| **MCP connector** | **N** | Y | No server-side MCP over the Messages API — run your own MCP client, or use direct API. |
| **Message Batches API** | **N** | Y | Use Bedrock's own batch-inference (different API/pricing), not the Anthropic Batch API. |
| **Files API / URL image & doc sources** | **N** | Y | Inline content only; no server-side file store. |
| **Agent Skills over the Messages API** | **N** | Y | No hosted Skills; package capability yourself. |
| **Claude Managed Agents** | **N** | Y | No server-hosted agent loop; orchestrate it yourself (or AgentCore, which is model-agnostic). |
| Models / Admin / Compliance / Usage-Cost APIs, server-side fallbacks param | **N** | Y | Governance/observability must come from AWS-side tooling. |

**The one-line rule:** *an agent that needs server-side web search/fetch, code execution, the MCP connector, the Batch API, the Files API, Managed Agents, or Messages-API Agent Skills is not a Bedrock agent.* Route it to the direct API or Claude Platform on AWS (distinct product, CCU billing, same-day parity). Everything else — Messages, caching, thinking, client-side tools, citations, structured outputs — ports cleanly.

## 4. Non-Claude Families for Agent Roles

Capabilities are from AWS model cards (structural facts high-confidence; per-model *tool-use quality* tables rendered as placeholders and are **LOW confidence — unverifiable from docs**). Every price below is **approximate — verify at aws.amazon.com/bedrock/pricing/ before committing.** The honest caveat applies to all of them: **marketing "agent" labels are not eval results. Measure per-model tool-use exactness on your own task before routing (cross-ref `agent-evals`).**

### Amazon Nova (cost floor)

| Model | Ctx | Max out | Notable | Approx $/MTok in/out | Agent fit |
|---|---:|---:|---|---|---|
| Nova 2 Lite | 1M | 64K | tools + vision + video; cache (1K min ckpt, 5m only, 20K max cacheable); us/eu/jp + global | not found | High-volume worker/classifier with huge context. |
| Nova Micro | — | — | text-only cost floor | ~$0.035 / $0.14 (med) | Bulk extraction, schema-validated. |
| Nova Lite | — | — | multimodal budget | ~$0.06 / $0.24 (med) | Bulk extraction/classification. |
| Nova Pro | 300K | 5K | no global profile; latency-optimized available | ~$0.80 / $3.20-or-$2.40 (UNRESOLVED) | Mid-tier worker; note the 5K output cap. |
| Nova Premier | — | — | **LEGACY, EOL Sep 14 2026** | ~$2.50 / $12.50 (med) | Do not pin — EOL imminent (§6). |

"Nova 2 Pro" appears in marketing but was **not** in the enumerated catalog — existence/ID unverified; do not route to it.

### Meta Llama

| Model | ID / notes | Ctx | Approx $/MTok | Agent fit |
|---|---|---:|---|---|
| Llama 4 Maverick 17B | `meta.llama4-maverick-17b-instruct-v1:0`; 8K out; vision; tools via Converse `toolConfig`; no mantle, no cache field; us-geo only | 1M | ~$0.24 / $0.97 (med) | Long-context budget worker; AWS lists it as an "agent" pick — verify tool-use yourself. |
| Llama 4 Scout 17B | vision; Converse tools | — | ~$0.17 / $0.66 (med) | Cheaper Maverick sibling. |
| Llama 3.1 405B / 70B | latency-optimized inference available (405B: 11K combined-token cap in that mode) | — | not verified | Latency-critical open-weight path. |

### Mistral

| Model | ID / notes | Ctx | Approx $/MTok | Agent fit |
|---|---|---:|---|---|
| Mistral Large 3 | `mistral.mistral-large-3-675b-instruct`; 32K out; cache on runtime; **both** runtime + mantle (OpenAI-compatible) | 256K | ~$0.50 / $1.50 (med-high, 2 sources) | Solid value generalist; AWS "agent" pick. |
| Devstral 2 123B | coding-specialized | — | not verified | Coding subagent candidate (hedged — eval it). |

### DeepSeek

| Model | Notes | Approx $/MTok | Agent fit |
|---|---|---|---|
| DeepSeek V3.2 | general/reasoning | ~$0.62 / $1.85 (med-high) | Value reasoning/worker; AWS "agent" pick. |
| DeepSeek R1 | reasoning | ~$1.35 / $5.40 (med) | Deep-reasoning budget option. |

### Qwen

| Model | Notes | Agent fit |
|---|---|---|
| Qwen3 Coder 480B A35B / Coder Next / Coder-30B-A3B | present in catalog; **IDs, ctx, pricing NOT verified** | Coding subagent candidate — **hedged**; confirm ID and eval tool-use before routing. |
| Qwen3 235B A22B 2507 / 32B / Next 80B A3B / VL 235B | present | General/value; verify specifics. |

### OpenAI on Bedrock (fact worth knowing)

GPT-5.5, GPT-5.4, `gpt-oss-120b`/`20b`, and GPT OSS Safeguard are **present in the Bedrock catalog** — a notable fact by itself (frontier OpenAI models routable inside AWS IAM/billing). Details were not fetched; treat as "available, unverified" and evaluate before routing.

## 5. Agent-Role Selection Matrix

Map roles to Bedrock picks under the pillar doctrine: **default to the cheapest capable model, escalate only on a verified failure, and pin per role in multi-agent systems** (a planner and a classifier should not float to the same tier). Primary picks are Claude (verifiable capabilities); non-Claude alternatives are hedged and must be eval'd.

| Agent role | Bedrock primary | Alternatives (hedged — eval first) | Rationale |
|---|---|---|---|
| Orchestrator / deep reasoning | Opus 4.8, Sonnet 5 | DeepSeek R1/V3.2 | Decomposition + judgment quality drives all downstream cost; don't under-power. |
| High-volume worker / classifier | Haiku 4.5 | Nova 2 Lite, Nova Micro/Lite | Schema-validated, cheap, high call volume; Nova 2 Lite adds 1M context. |
| Coding subagent | Sonnet 5 | Qwen3 Coder (hedged), Devstral 2 | Patch discipline + tool reliability matter more than leaderboard rank; eval on your repo. |
| Latency-critical interactive | latency-optimized Haiku 4.5 / Sonnet 4.6 | latency-optimized Nova Pro, Llama 3.1 405B/70B | Interactive p50 target; latency-optimized inference is a preview (§7). |
| Cost-floor bulk extraction | Nova Micro / Lite (prices hedged) | Haiku 4.5 with strict schema | Mechanical, schema-verified work belongs on the budget tier, never the frontier. |
| Reviewer / auditor | Different family from the builder | e.g. Claude builder → DeepSeek/Nova reviewer | Two models from the same family that agree is weak evidence — force a cross-family check on high-risk work. |

**Per-role pinning on Bedrock:** pin the exact model ID *and endpoint* per role in env vars (§6). A multi-agent system where every role floats to one default is the anti-pattern the doctrine exists to prevent — see the `model-selection` skill's Per-Role Pinning table.

### Worked Example: Routing a Coding Swarm on Bedrock

Task: an orchestrator dispatches multi-file patches to coding workers; patches are test-verified.

1. **Classify.** Orchestrator = judgment-heavy (planner). Worker = agentic coding, machine-validated by tests. Reviewer = high-risk (touches shipping code).
2. **Gate on §3.** Do the workers need server-side code execution? On Bedrock that tool is **not available** — so the sandbox runs client-side (you execute tests), which Bedrock supports. No blocker; stay on Bedrock.
3. **Route cheapest-capable.** Orchestrator → Sonnet 5 (`bedrock-mantle`, global profile). Worker first attempt → Sonnet 5, *not* Opus — the doctrine reserves Opus for verified failures. A hedged Qwen3 Coder / Devstral worker is allowed **only after** it passes a tool-call exactness eval on your repo (`agent-evals`).
4. **Verify + escalate.** Tests pass → done, log cost. Tests fail with an unclear cause twice → *verified* failure → escalate that patch to Opus 4.8. Reviewer runs on a **different family** (e.g. DeepSeek V3.2) so builder and reviewer don't share blind spots.
5. **Pin.** Each role's (model ID, endpoint, inference profile) is an env var so a Sonnet 4 EOL (2026-10-14) or a Qwen swap is config-only.

Most patches finish at the Sonnet tier; Opus is touched only on the minority that fail tests — the same 5-10x cost gap the pillar's ladder buys elsewhere, now on Bedrock IDs.

## 6. Lifecycle / EOL

High-confidence (AWS model-lifecycle page, exact table). **Legacy rules:** existing customers keep on-demand access through the EOL date; new customers are blocked; no new provisioned throughput. Pinning a model past its EOL is a hard outage waiting on a calendar.

| Model | EOL date | Flag |
|---|---|---|
| Claude 3 Sonnet, 3.5 Sonnet (+v2), 3.7 Sonnet (GovCloud) | **2026-07-30** | **URGENT — ~2 weeks out. Migrate now.** |
| Claude 3 Haiku | 2026-09-10 | Migrate to Haiku 4.5. |
| Claude Sonnet 4 | 2026-10-14 | Plan replacement (Sonnet 5). |
| Nova Premier + Sonic | 2026-09-14 | Do not pin for new work. |
| Cohere Command R / R+ | 2026-08-19 | Legacy; migrate off. |
| AI21 Jamba 1.5 | 2026-11-26 | Legacy. |
| Claude Opus 4.1 | 2027-01-08 | Longer runway; still deprecated. |

**Standing rule:** check the model-lifecycle page **before pinning any model**, and pin via environment variables so a swap is a config change, not a code change — see the `agent-deployment` skill (versioning-rollout) for the rollout mechanics. An agent hard-coding a model ID inherits that model's EOL as its own downtime.

## 7. Service Tiers, Quotas, Latency-Optimized Inference

Heavily hedged — the tier multipliers below are single-source/low-confidence; **verify at aws.amazon.com/bedrock/pricing/ before committing.**

- **Service tiers (availability varies per model):** Standard; Priority (~75% premium — LOW confidence); Flex (~50% discount — LOW confidence); Reserved. Observed per-model: Opus 4.8 Standard-only; Haiku 4.5 Standard + Reserved; Nova Pro/Premier Standard + Priority + Flex.
- **Latency-optimized inference (preview):** Claude Haiku 4.5, Claude 3.5 Haiku, Sonnet 4.6, Nova Pro, Llama 3.1 405B/70B (med-high confidence). Use for the latency-critical interactive role; confirm current availability before depending on it.
- **Quotas (unreconciled).** Opus 4.8 model card: 20M in-TPM / 4M out-TPM (mantle), 30M TPM (runtime), no RPM cap. The Anthropic guide separately says 2M default / 4M on request — likely a tier baseline vs card ceiling; **do not size a fleet off these until reconciled with your account's actual quotas.**

## 8. Pitfalls

1. **Pinning a Legacy model.** Legacy status means new customers are blocked and the on-demand endpoint dies on the EOL date. *Fix:* before pinning, check the model-lifecycle page; reject any model whose EOL is inside your planning horizon, and add a CI check that fails when a pinned ID appears on the Legacy list. Claude 3.x dies **2026-07-30** — audit today.
2. **Assuming Bedrock has direct-API features.** Web search, code execution, MCP connector, Batch API, Files API, Managed Agents, and Messages-API Agent Skills are **not on Bedrock** (§3). *Fix:* gate the agent's design against the feature-gap table before choosing Bedrock; if a "NOT on Bedrock" row is load-bearing, route to the direct API or Claude Platform on AWS.
3. **Trusting aggregator prices as Bedrock's real cost.** Every non-direct-API dollar figure here is approximate; AWS's own page was unfetchable. *Fix:* pull the live number from aws.amazon.com/bedrock/pricing/ (or a `GetFoundationModelAvailability`-backed calculator) before locking a budget; treat this file's prices as order-of-magnitude only.
4. **Using the regional endpoint unknowingly (+10%).** An in-region single endpoint costs 10% more than a global inference profile for the same call — easy to eat silently at fleet scale. *Fix:* default routes to a global (or geo) inference profile; make in-region an explicit, justified choice (residency requiring it), and log which profile each route uses.
5. **Assuming every model has global profiles.** The central cross-region page's "global is only Sonnet 4" claim is **stale** — Opus 4.8 / Sonnet 5 / Haiku 4.5 / Nova 2 Lite cards all list global; conversely Nova Pro has **no** global profile. Profile sets live only on each model card. *Fix:* read the specific model card for its profile set; never infer profile availability from another model or from the cross-region overview page.
6. **Treating marketing "agent-fit" claims as eval results.** AWS labeling a model an "agent" pick (Llama 4 Maverick, Mistral Large 3, Nova 2 Lite, DeepSeek V3.2, etc.) is not a measurement, and per-model tool-use quality tables are unverifiable from docs. *Fix:* run a tool-call exactness eval on your own task before routing any non-Claude family to a controller role (cross-ref `agent-evals`); require the same pass bar you'd demand of a local model.
7. **Copy-pasting a model ID across endpoints.** Haiku 4.5 (and others) use a dated `...-v1:0` ID on `bedrock-runtime` but a bare alias on `bedrock-mantle`. *Fix:* store IDs per (model, endpoint) pair; a wrong-endpoint ID is a silent 400, not a fallback.
8. **Carrying the direct-API Batch discount into a Bedrock budget.** The Anthropic Batch API does not exist on Bedrock; Bedrock's own batch inference is a different API and price. *Fix:* model batch savings from Bedrock's documented batch pricing, never from the direct-API batch column above.
