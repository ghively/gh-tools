---
name: model-selection
description: "Choosing and routing models per task: cloud model matrices, local/open-weight model fit, router architecture, fallback chains, and cost tracking across providers. Use when deciding Claude vs GPT vs Gemini vs local models, building a model router, controlling token spend, or assigning models to agent roles. Does not cover serving infrastructure such as vLLM/TensorRT/Triton, prompt design (see prompt-context-engineering), or framework choice (see framework-selection)."
---

# Model Selection

Model selection is an engineering control, not a brand preference. The right model is the cheapest one that reliably passes the task's verifier under the latency, privacy, and context constraints you actually have.

## When to Use

- You need a cloud or local model for an agent, subagent, evaluator, RAG answerer, classifier, or coding worker.
- You are building routing logic across providers or local/open-weight models.
- Your agent is too expensive, too slow, or unreliable at tool calls.
- You need fallback behavior for provider outages or quota exhaustion.
- You are assigning different models to planner, worker, reviewer, and summarizer roles.

**Don't use for:** prompt design (`prompt-context-engineering` skill), durable execution (`deterministic-agents` skill), GPU serving infrastructure or PEFT/LoRA fine-tuning of open-weight models (outside agent-foundry's scope; this skill covers *choosing and routing* models, not adapting their weights), or agent eval suite design (`agent-evals` skill).

### Symptoms That Point Here

| Symptom | Likely cause | Where this skill helps |
|---|---|---|
| Token bill rising faster than usage | Frontier tier used as default; no ladder | Routing doctrine, per-role pinning. |
| Agent passes in chat, fails on tools | Wrong model class for structured output | Task-to-tier matrix, local tool-call eval. |
| Provider outage takes down the agent | No fallback chain, or fallback drops constraints | Routing architecture, failure handling. |
| Reviewer agrees with builder too often | Same family on both roles | Per-role pinning (different family for reviewer). |
| Same task costs 5x on different days | No per-run budget; retries unbounded | Cost tracking, budget alerts. |
| Local model "looks good" but breaks in prod | Tool-call exactness never measured | Local matrix, quant quality check. |

## Routing Doctrine

1. **Classify first.** Determine task class, risk, context size, latency target, modality, and whether the output is machine-validated.
2. **Route to the cheapest capable model.** Default to value/budget tiers for mechanical work; reserve frontier tiers for judgment-heavy failures or genuinely hard tasks.
3. **Verify the result.** Schema validation, tests, citations, retrieval metrics, or reviewer checks decide whether the output is good enough.
4. **Escalate only on verified failure.** Do not pay frontier prices because the prompt looks scary.
5. **Log cost and behavior.** Every model call should be attributable to a run, role, prompt version, and budget owner.

### Worked Example: Classify → Cheapest-Capable → Escalate

A coding agent receives: "Refactor the billing module to support proration and update the docs."

1. **Classify.** Task class = agentic coding (multi-file edit + docs). Risk = medium (touches billing). Context = moderate (module + tests + docs). Latency = non-interactive (background job). Output is machine-validatable (tests must pass).
2. **Route to cheapest capable.** The default for verified-test coding work is a value coding model. Send the planner step + first patch attempt to the value tier.
3. **Verify.** Run the test suite and a patch lint. Three outcomes:
   - Tests pass and diff is clean → done, log cost, no escalation.
   - Tests fail with a clear cause → let the same value model iterate (still cheaper than frontier), bounded to N retries.
   - Tests fail with unclear cause, or the value model emits a malformed patch twice → this is a *verified* failure, not a scary-looking prompt.
4. **Escalate one rung.** Hand the failing test output plus the prior patch to a frontier reasoning/coding model with "fix the failing test, do not redesign."
5. **Log.** Record: value-model spend, retry count, escalation trigger (test failure reason), frontier-model spend, final verdict.

The cost difference between this ladder and "send everything to the frontier model by default" is usually 5-10x for the same pass rate, because most tasks either pass at the value tier or fail in a way the frontier tier also catches.

### Per-Role Model Pinning (Mini Table)

In a multi-agent system, pin models to **roles**, not to projects. Roles have stable capability requirements; projects do not.

| Role | Default tier | Why |
|---|---|---|
| Classifier / router | Budget | High volume, schema-validated, cheap. |
| Retriever / RAG answerer | Value | Quality matters but errors are catchable by faithfulness checks. |
| Planner | Value reasoning | Decomposition quality drives downstream cost; don't under-power it. |
| Worker / coder | Value coding | Most steps; escalate per the doctrine. |
| Reviewer / auditor | Different family from builder | Reduces correlated mistakes; sample for low-risk work, mandatory for high-risk. |
| Summarizer | Budget | Mechanical compression with a length cap. |
| Final-answer / external-send | Frontier (high-risk only) | Reserved for irreversible or money-moving actions. |

The reviewer must be a **different model family** from the builder when feasible — two Sonnets that agree is weaker evidence than a Sonnet and a GPT-tier model that agree.

## Task to Tier Quick Reference

| Task | Cloud default | Local default | Escalate when |
|---|---|---|---|
| Classification/extraction | Budget model + schema | 4B-8B/8B-14B instruct | Schema/semantic validator fails. |
| Tool routing | Value model | 8B-14B only after tool eval | Tool-call exactness fails. |
| Agentic coding | Value coding model | 14B-32B coder if tested | Tests fail or patch is complex. |
| Deep reasoning | Frontier/value reasoning | 32B+ or cloud | Verifier detects bad chain or uncertainty. |
| RAG answer synthesis | Value model | 8B-14B for low-risk, 24 GB+ for higher quality | Faithfulness or citation checks fail. |
| Long-context analysis | Long-context value/frontier | Avoid unless local context is proven | Retrieval cannot preserve necessary evidence. |
| Review/audit | Different strong model from builder | Strongest local feasible | Findings disagree or risk is high. |
| Embeddings/reranking | Dedicated embedding/rerank model | Local embedding + optional reranker | Retrieval eval misses known answers. |

### Reading the Quick Reference

- **Cloud default** is the *first attempt*, not the only option. Most rows escalate one rung on verified failure; few need to start at the frontier.
- **Local default** is conditional on a passed tool/retrieval eval. "It loads" is not "it works."
- **Escalate when** is a *verifier* condition, not a difficulty feeling. If you cannot name the verifier, you do not have a route — see the doctrine above.
- For tasks that span two rows (e.g., "coding over a long context"), pick the row whose verifier you actually have and start there.

## Cloud vs Local Decision

| Choose cloud when | Choose local/open-weight when |
|---|---|
| You need top reasoning/coding quality now. | Privacy, cost at sustained utilization, or offline operation matter. |
| You need managed availability and no inference ops. | You can operate serving, upgrades, and hardware utilization. |
| Tool/function reliability is proven on your evals. | You have measured local tool-call reliability, not assumed it. |
| Spiky usage makes pay-per-token cheaper. | High steady volume makes owned/leased compute cheaper. |

### Decision Procedure (Cloud vs Local)

Run the rows of the table as a sequence of explicit questions, in this order — earlier questions dominate later ones:

1. **Is there a privacy, residency, or offline constraint?** If yes, local (or a region-bound cloud route) is mandatory; cost is secondary.
2. **Is sustained GPU utilization above ~30-40%?** Below that, cloud pay-per-token is usually cheaper than owned/leased compute even at volume. Above it, the math flips.
3. **Have you measured local tool-call exactness on your eval?** If not, you cannot yet claim local works for an agent controller — measure first, decide second.
4. **Is the usage spiky?** Spiky traffic (bursts of 100x the median) favors pay-per-token; flat traffic favors owned capacity.
5. **Do you have the ops capacity?** Serving, upgrades, quant tuning, and utilization tracking are real on-call load. If the team cannot carry it, cloud is the safer default.

If questions 1-3 do not force a direction, default to cloud and re-evaluate when utilization data exists. The most expensive choice is oscillating between the two without committing to either.

## Model Router Minimum Bar

- Per-task routing table with explicit allowed models.
- Structured-output capability recorded per model.
- Fallback chain that preserves privacy and permission constraints.
- Token/cost budget per run and per role.
- Observability that logs model, tokens, retries, verifier result, and fallback reason.
- Eval suite run before changing a route.

### Minimum Acceptable Schema for a Routing Decision

A route entry is not "use Sonnet for coding." It is a record so the decision is auditable and refreshable:

```
task_class:    agentic_coding
allowed:       [value-coder, frontier-coder]      # ordered escalation ladder
verifier:      {type: tests, suite: billing-proration}
escalate_if:   tests_fail OR patch_lint_fail OR retries >= 2
budget:        {max_input_tokens: 60_000, max_output_tokens: 8_000, max_usd_per_run: 0.40}
privacy:       no_pii_egress, region: eu-west
last_eval:     2026-07-10, pass_rate: 0.91 on value tier, 0.97 on frontier tier
```

If you cannot fill `verifier`, `escalate_if`, and `last_eval`, you do not have a route — you have a guess.

## Reference Router

| Load | When |
|---|---|
| `references/task-model-matrix-cloud.md` | Comparing current cloud model tiers, prices, context windows, and task fit. |
| `references/bedrock-model-matrix.md` | Routing on Amazon Bedrock specifically: Claude/non-Claude catalog, IDs, endpoints, the direct-API feature gaps, inference profiles, and model lifecycle/EOL. |
| `references/task-model-matrix-local.md` | Selecting open-weight models by VRAM tier, quantization, and local tool-calling risk. |
| `references/routing-architecture.md` | Designing routers, escalation ladders, fallback chains, and per-role model pinning. |
| `references/cost-tracking.md` | Tracking token spend, quota exhaustion, budgets, and cost regressions across providers. |

### How to Use the References Together

The four references answer different questions and are read in a different order depending on the job:

| Job | Read order | Why |
|---|---|---|
| "I am picking a model for a new task" | Cloud matrix → Local matrix → Routing → Cost | Pick the model first, then the route, then the budget. |
| "My bill spiked" | Cost tracking → Routing → Cloud matrix | Find the cause, then the route that caused it, then the price behind it. |
| "I am building a router from scratch" | Routing → both matrices → Cost | Architecture first, then populate allowed models, then budgets. |
| "I am moving a workload local" | Local matrix → Routing → Cost | Size the model, then the route, then the cost comparison. |
| "A provider deprecated my model" | Cloud matrix → Routing → Cost | Find the replacement, update the route, re-check the budget. |

The references are designed to be **read independently** — each defines its terms. But the routing and cost references assume you have a current matrix (cloud or local) to populate the `allowed:` lists with real model IDs.

## Pitfalls

1. **Using leaderboards as a substitute for evals.** Leaderboards are broad priors, not proof for your task. Build task evals in the `agent-evals` skill and route based on those results. *Concrete fix:* keep a frozen 50-200 case eval set per task class; any route change must beat the incumbent by a margin you pre-declared (e.g., +3 points pass rate) before it ships.
2. **Trusting a stale matrix.** Prices and model IDs move monthly. Check the `Last verified` banner before high-stakes decisions. *Concrete fix:* add a CI check that fails if the matrix file's `Last verified` month is older than your refresh SLA (e.g., 45 days).
3. **Paying frontier prices for mechanical work.** Classification, extraction, format conversion, and simple summarization should run on budget/value models with validators. *Concrete fix:* any route whose verifier is a JSON schema or regex should be on a budget tier; flag frontier-tier calls that produce < 200 output tokens for review.
4. **Deploying local tool use unmeasured.** Local models can look good in chat and fail structured tool calls. Run a tool-call eval before making one an agent controller. *Concrete fix:* require a tool-call exactness score (arguments match expected schema and values) above a threshold, e.g., ≥ 0.95 on a 50-case set, before a local model is allowed as a planner.
5. **Silent fallback to a weaker policy tier.** A fallback model must satisfy the same privacy, tool, schema, and data-residency constraints as the primary. *Concrete fix:* tag every model with a capability + policy tuple `(privacy, schema_strict, region, tool_support)` and reject any fallback whose tuple is not ≥ the primary's on every dimension.
6. **Forgetting output-token cost.** Verbose agents can spend more on output than input. Cap output, compress intermediate results, and avoid reflective loops. *Concrete fix:* set `max_output_tokens` per role; alert when a role's median output exceeds 2x its p50 from the last 7 days.
7. **Escalating on "the prompt looks hard."** Difficulty is not a failure signal. *Concrete fix:* escalation must be triggered by a named verifier outcome (test fail, schema invalid, low calibrated confidence, reviewer disagreement), never by the model's own length or reasoning style.
8. **Single-family reviewer echo.** A reviewer from the same family as the builder inherits its blind spots. *Concrete fix:* when risk is high, force the reviewer to a different provider/family and log disagreements as a review artifact.
