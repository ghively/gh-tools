> Last verified: 2026-07. Router products and gateway features change quickly; verify LiteLLM, OpenRouter, and provider gateway docs before relying on a specific capability.

# Routing Architecture

The doctrine: classify the task, route to the cheapest capable model, and escalate only on verified failure. Routing by vibes burns budget and hides quality regressions.

## Router Shape

```
request
  -> classify task, risk, latency, modality, context size
  -> choose cheapest capable model for that class
  -> run with structured outputs / validators
  -> if verifier fails, escalate one rung
  -> log cost, latency, model, prompt version, verifier result
```

### Concrete Router Config Snippet

A route table is data, not code. Keep it in a versioned file so changes are reviewable and revertible:

```yaml
routes:
  - task_class: extraction_pii_redact
    allowed: [budget-extract]              # single rung; no escalation needed
    verifier: { type: json_schema, schema: pii_redact_v2 }
    budget:  { max_usd_per_run: 0.02, max_output_tokens: 1000 }
    privacy: { pii: redact_before_egress, region: eu-west }

  - task_class: coding_patch
    allowed: [value-coder, frontier-coder]  # ordered escalation ladder
    verifier: { type: tests, suite: unit+lint }
    escalate_if: tests_fail OR retries >= 2
    budget:  { max_usd_per_run: 0.40, max_output_tokens: 8000 }

  - task_class: external_send_money
    allowed: [frontier-reason]              # high-risk: single strong tier
    verifier: { type: reviewer_panel, min_agreement: 2, families: 2 }
    budget:  { max_usd_per_run: 1.00 }
    require_human_approve: true
```

Rules this snippet encodes without stating them in prose:

- **The allowed list is ordered** — first entry is the default; later entries are escalation rungs.
- **Every route has a verifier** — no verifier means no escalation signal, which means no ladder.
- **Budgets are per-run, not per-call** — a 12-step agent that costs $0.40 total is fine; one step that costs $0.40 is not.
- **High-risk routes are short and gated** — money movement gets one strong tier plus a human, not a cheap-to-expensive ladder.

## Classification Inputs

| Signal | Why it matters |
|---|---|
| Task type | Extraction, coding, reasoning, RAG, vision, writing need different models. |
| Risk | Writes, money movement, security, and external sends deserve stronger models and gates. |
| Schema strictness | Some models are cheaper but fail structured output more often. |
| Context size | Long-context models are costly; retrieval may be cheaper. |
| Latency target | Interactive chat and overnight analysis should not share defaults. |
| Privacy/residency | Local or region-bound routes may be mandatory. |

## Escalation Ladder

1. Budget model handles mechanical work.
2. Value model handles default agent steps.
3. Frontier model handles ambiguous judgment, complex code, or failed verification.
4. Human or deterministic workflow handles actions a model should not decide.

Escalate only when a validator catches a real failure: invalid JSON, failing tests, insufficient citations, low confidence from a calibrated classifier, or reviewer disagreement. Do not escalate because the prompt looks hard.

### Escalation Triggers (Concrete)

| Verifier type | Trigger condition | Action |
|---|---|---|
| JSON schema | Parse fails OR required field missing OR enum value invalid | Re-run same tier once with stricter instruction; if still fails, escalate one rung. |
| Test suite | Any test fails OR patch does not apply | Same-tier retry up to `retries >= 2`; then escalate. |
| Citation/faithfulness | Answer has a claim with no supporting chunk, OR faithfulness score < threshold (e.g., 0.9) | Re-run with "cite or refuse"; escalate if second attempt still unsupported. |
| Calibrated confidence | Model-reported confidence < threshold (e.g., 0.6) on a calibrated classifier | Escalate directly — low confidence is itself the signal. |
| Reviewer panel | Disagreement between reviewers, OR agreement but below quorum | Escalate to a third family or to a human. |
| Deterministic check | Lint/typecheck/format/regex fails | Same-tier retry once; escalate on second failure. |

The threshold column is the part teams skip. "Escalate when confidence is low" is not a route; "escalate when calibrated confidence < 0.6" is.

## Per-Role Pinning

Multi-agent systems should pin by role, not by project. A planner may need a stronger reasoning model; a scraper may need a cheap model or no model; a reviewer may need a different family from the builder to reduce correlated mistakes. See the `multi-agent-orchestration` skill for delegation patterns.

### Per-Role Pinning Table

| Role | Typical tier | Family constraint | Why |
|---|---|---|---|
| Router/classifier | Budget | Any | Highest call volume; schema-validated. |
| Retriever/RAG answerer | Value | Any | Quality matters; failures catchable by faithfulness check. |
| Planner | Value reasoning | Any | Decomposition quality drives downstream cost. |
| Worker/coder | Value coding | Any | Most steps; escalate per doctrine. |
| Reviewer/auditor | Value or frontier | **Different family from builder** | Reduces correlated mistakes. |
| Summarizer | Budget | Any | Mechanical, length-capped. |
| Final-answer/external-send | Frontier | Any, plus human gate | Irreversible actions. |

### Anti-Patterns in Per-Role Pinning

- **Same model reviews its own output.** A builder and reviewer from the same family share blind spots. Pin the reviewer to a different family when risk justifies the cost.
- **Planner under-powered, workers over-powered.** A weak planner produces a bad plan that no amount of frontier worker compute can rescue. Spend on the planner first.
- **Every role on the frontier tier "to be safe."** This is the most expensive way to get the same pass rate you would get from a ladder. Safety comes from verifiers, not from tier inflation.
- **Pinning by project name.** Projects end; roles persist. Pin to the role's capability requirement and let projects inherit.

## Gateway Options

| Option | Use when | Watch out |
|---|---|---|
| LiteLLM proxy | You need unified provider config, budgets, retries, fallbacks | Budget and fallback behavior must be tested under outage. |
| OpenRouter routing | You want broad provider/model access and marketplace-style routing | Provider variance; pin when reproducibility matters. |
| Provider-native gateway | You are standardized on one provider/cloud | Lower portability; feature surface differs by cloud. For Amazon Bedrock, the model catalog, endpoints, and the features it lacks vs the direct API are in the `model-selection` skill's `references/bedrock-model-matrix.md`. |
| Custom router | You have eval-backed task classes and strict policy | You own observability, cost accounting, and failover. |

## Failure Handling

Keep fallback chains short. A broken primary provider should fail over by task class, not randomly. Never silently swap to a model with weaker privacy, tool, or structured-output guarantees. Log the fallback so eval failures can be explained later.

### Fallback Chain Rules

1. **Length.** Two or three rungs is plenty. A six-rung chain is a sign you are hiding a quality problem with retries.
2. **Capability monotonicity.** Each fallback must satisfy every constraint the primary did: privacy tier, schema strictness, tool support, data residency, modality. A cheaper fallback that drops a constraint is a policy violation, not a fallback.
3. **Failure correlation.** Two models from the same provider share outage windows and quota pools. Prefer a different provider for the first fallback rung.
4. **Observable.** Every fallback must log: trigger, from-model, to-model, reason (429 / 5xx / timeout / verifier-fail), and whether the user saw degraded behavior.
5. **Tested.** Inject provider outages in staging and confirm the chain actually fires. An untested fallback is a wish.

### Decision: Fail Open vs. Fail Closed

| Situation | Choose | Why |
|---|---|---|
| Read-only summary, best-effort | Fail open (degraded answer, flag it) | User experience matters more than perfection. |
| Extraction feeding a deterministic pipeline | Fail closed (queue, retry later) | Bad extraction poisons downstream state. |
| External send / money / write | Fail closed, always | Irreversible actions must not run on a degraded tier. |
| Tool that mutates shared state | Fail closed | A half-applied tool call is worse than no call. |
