> Last verified: 2026-07. Usage APIs, billing exports, and gateway budget controls change often; verify provider and observability docs before treating numbers as authoritative.

# Cost Tracking

Model routing without cost tracking is wishful budgeting. Track spend at the same granularity you route: task, user, agent role, model, provider, prompt version, and tool phase.

## Cost Tracking as a Reliability Concern

Cost is not just a finance line item; it is a leading indicator of agent health. The same patterns that waste tokens — unbounded retries, reflective loops, context flooding, escalating on scary-looking prompts — also degrade latency, reliability, and user experience. A cost spike is usually a behavior bug in disguise. Treat the cost dashboard as a reliability signal, owned by engineering, not just a monthly invoice forwarded by finance.

## What to Capture

| Field | Why |
|---|---|
| Provider/model/model version | Prices and behavior differ by exact model. |
| Input/output/cache tokens | Output tokens usually dominate cost. |
| Tool phase or agent role | Identifies over-expensive planner/reviewer/retriever loops. |
| Request ID and run ID | Lets traces join to invoices and eval failures. |
| Retry/fallback count | Retries can double cost invisibly. |
| Budget owner | Team/project/user chargeback. |

### Capturing Cost Without Drowning in Telemetry

The six fields above are the minimum. Resist the urge to log every header — most of the value comes from joining three things: **what was spent** (tokens × price), **what it was for** (run ID + role + task class), and **whether it worked** (verifier result). If your schema cannot answer "how much did failed billing-extraction runs cost last week, per model?" you are missing one of those three joins.

| Anti-pattern | Why it hurts | Fix |
|---|---|---|
| Logging only totals | Cannot attribute a spike to a role or prompt version | Log per-call with role + run ID + prompt version. |
| No verifier result on the span | Cannot tell cheap-and-correct from cheap-and-wrong | Add `verifier_pass: bool` to every span. |
| Ignoring cache tokens | Cache reads cost a fraction of cache misses; effective input price varies wildly | Log `cache_read`, `cache_write`, `cache_miss` separately. |
| No retry/fallback reason | A "doubled cost" looks like a price change | Log `retry_reason` / `fallback_reason` per span. |
| Per-user attribution missing | Cannot charge back or set per-user budgets | Add `budget_owner` at span write time. |

## Control Layers

1. Provider-native usage dashboards and billing exports.
2. Gateway budgets and per-key limits, such as LiteLLM budget controls.
3. Observability platforms such as Langfuse or LangSmith where traces include model spans.
4. Application-level hard caps: max iterations, max tokens, max dollars per run.

Layers should be **additive**, not substitutive: the provider dashboard tells you what you spent, the gateway enforces limits before the spend happens, the observability platform explains *why* a span cost what it did, and the application hard cap is the last line that protects a runaway run. If you rely only on the provider dashboard, you find out about budget blowouts in next month's invoice.

### Sample Budget-Alert Setup

A defensible budget config has at least three thresholds, each wired to an action — not just a notification:

| Layer | Threshold | Action |
|---|---|---|
| Per-run hard cap | `max_usd_per_run = 0.50` | Abort run, mark task failed, log trigger. |
| Per-key soft limit | `daily_usd = 50` (per agent role) | Page on-call; new requests for that role queue, not fail. |
| Per-project monthly budget | `monthly_usd = 2000` | Block new runs; allow in-flight to finish; open a ticket to review routes. |
| Burst guard | `tokens_per_minute > 3 × p50` for a role | Throttle that role's concurrency for 5 minutes; surface in cost dashboard. |

Wire the alert to the **budget owner** (team or project), not a shared channel — a `#cost-alerts` room that nobody reads is the same as no alert. Keep a tested fallback for the per-key soft-limit case (degraded service should not become total outage).

## Exhaustion Detection

Rate-limit and quota exhaustion are reliability incidents. Poll provider usage where available, alert before monthly budget or per-minute limits are hit, and keep a tested fallback chain for degraded service. Do not discover quota exhaustion from user-facing 429s.

### Concrete Signals to Poll

| Signal | Source | What it tells you |
|---|---|---|
| `remaining_tokens` / `rate_limit_remaining` headers | Provider response headers | Per-minute headroom; cheap to log. |
| Org monthly spend vs. quota | Provider usage API | Distance to the monthly cap. |
| 429 with `retry_after` | Provider error | Already too late — treat as incident, not telemetry. |
| p99 latency uptick on a provider | Observability platform | Often precedes throttling; canary signal. |
| Cache-read ratio | Provider usage API | A dropping cache ratio raises effective input cost without raising call count. |

Poll at a cadence faster than your soft-limit window (e.g., every 60s for per-minute limits, every 5 min for daily budgets).

## Cost Review Cadence

Weekly for fast-moving prototypes; daily for high-volume production. Sort by total spend, spend per successful task, and spend per failed task. A high spend-per-failure usually means a loop, bad retrieval, or an overpowered default model.

### Review Sort Orders (Use All Three)

| Sort | Reveals |
|---|---|
| Total spend | Who the big spenders are (often one role or one prompt version). |
| Spend per successful task | Efficiency — which tasks are cheap-to-done vs. expensive-to-done. |
| Spend per failed task | Where waste concentrates — failures cost more than successes. |
| Spend per verifier-pass | The true unit economics of the route, including retries. |
| Spend per user / per project | Chargeback fairness and budget-owner accountability. |

The single most revealing number is usually **spend per failed task**. A healthy route has low spend-per-failure (failures are caught early and cheaply). A route where failures cost more than successes is one where retries, escalations, or context flooding are running unbounded.

### Cost-Regression Postmortem Shape

When a route change or prompt revision spikes spend, the postmortem should answer four questions with numbers, not narrative:

1. **What changed?** Commit/route/prompt version before and after, with timestamp.
2. **By how much?** Spend per successful task before vs. after (median and p95), plus pass-rate change. A cost regression that also raised pass rate may be intentional; one that raised cost *and* lowered pass rate is a bug.
3. **Where did the tokens go?** Breakdown by role/phase: input, output, cache-read, cache-write, retries. A 3x output-token jump with no behavior change usually means a reflective loop was added or a `max_output_tokens` cap was removed.
4. **What is the rollback?** The route entry's `last_eval` field should let you revert in one change. If you cannot roll back in under five minutes, the route was not versioned properly.

A worked example shape: *"PR #482 swapped the coding route from value-tier to frontier-tier 'for quality'. Spend per successful task rose from $0.04 to $0.31 (+675%); pass rate rose from 0.91 to 0.92 (+1 point). Rolled back; the 1-point gain was within eval noise. Action: re-propose with a tighter verifier and a budget cap before re-trying."*

## Common Fixes

| Symptom | Fix |
|---|---|
| Frontier model used for extraction | Move extraction to schema + budget model. |
| Review panel too expensive | Use panel only for high-risk changes; sample otherwise. |
| Long-context bills spike | Add retrieval, compression, or context pruning. |
| Retry storms | Move retry policy into code with bounded attempts. |
| Fallback doubles cost | Verify before escalating; do not retry with same failing input blindly. |
| Output tokens dominate | Cap `max_output_tokens` per role; forbid reflective "let me think again" loops in the prompt. |
| Cache-read ratio drops | Re-order prompt so the stable prefix is first; avoid per-request dynamic prefixes that bust the cache. |
| Eval cost itself is high | Sample the eval set for routine route checks; run the full set only on candidate changes. |

### Fix Application Order

When several symptoms appear at once, fix in this order — earlier fixes often eliminate later symptoms for free:

1. **Cap retries and output tokens.** Bounded attempts and `max_output_tokens` kill retry storms and output bloat in one change.
2. **Move mechanical work to budget tier + schema.** Removes the largest single source of frontier-tier overspend.
3. **Stabilize the prompt prefix.** Restores cache-read ratio and cuts effective input cost without a route change.
4. **Add retrieval / context pruning.** Targets long-context bills specifically.
5. **Sample the review panel.** Reduces reviewer cost without removing the safety check.
6. **Re-run the eval on sampled set.** Confirms the fixes did not regress pass rate before declaring victory.

A common mistake is to chase the symptom with the biggest dollar number first. The biggest number is usually *output* cost on the frontier tier, whose root cause is *unbounded retries*, whose root cause is *no verifier on a mechanical task*. Fix the verifier and the upstream symptoms disappear.

## Cost Governance

Per-run tracking tells you what a run cost; governance decides who pays for it, who may approve more of it, and when an agent stops earning its spend. Governance is the layer that turns a cost dashboard from an engineering curiosity into an accountable budget with owners and kill switches. It sits on top of everything above — you cannot govern spend you are not attributing.

### Chargeback and Showback

Once spend is attributed (the `budget_owner` field from *What to Capture*), you can either **charge it back** (bill the owning team/tenant real money) or **show it back** (report each owner's share without an internal transfer). Showback is the common starting point; chargeback creates the incentive that actually changes behavior. Both require the same thing: every model call tagged to a payer before it happens, not reconstructed from an invoice after.

| Tagging layer | How it tags | Strength | Watch out |
|---|---|---|---|
| Application layer | The agent attaches `tenant`, `team`, `agent_id`, `task_class` to each span at call time | Finest granularity; ties spend to run + verifier result | Only as reliable as the code path; an untagged call is unattributed spend |
| Gateway layer | A proxy (e.g. LiteLLM) enforces per-key budgets and tags by API key → team | Enforced before spend, not just observed | Key-to-owner mapping must stay current or attribution rots |
| Provider-native | Cloud billing tags / cost-allocation dimensions | Survives into the invoice; audit-grade | Coarsest; often per-account, not per-agent |

On **Bedrock**, application inference profiles are the native tagging mechanism: wrap a model in an application inference profile and its usage carries cost-allocation tags into AWS billing, so per-team/per-agent chargeback rides the existing IAM/billing plumbing instead of a bolt-on ledger. See the `bedrock-model-matrix` reference for inference-profile mechanics and the regional-endpoint cost lever. The general rule across layers: **tag at the finest layer you control and reconcile upward** — application tags for engineering review, gateway keys for enforcement, provider tags for the finance-grade number.

### Budget Approval Workflows

An autonomous agent spends money without a human in the loop on each call, so the budget ladder *is* the human in the loop. Escalate through three rungs, each with a named owner and an action, not just a notification:

| Rung | Trigger | Action | Owner |
|---|---|---|---|
| Soft alert | Spend > 70% of the period budget, or burn-rate implies early exhaustion | Notify the budget owner; runs continue | Owning team lead |
| Hard cap | Spend hits 100% of the allocated budget | New runs blocked (in-flight finish); degrade to a cheaper route if one is defined | Owning team + platform |
| Human approval | A request to *raise* the cap, or a one-off run above the per-run ceiling | Explicit sign-off before more budget unlocks | Budget-accountable manager |

The unresolved question every autonomous-agent deployment must answer: **who owns the budget for an agent that runs unattended?** An agent with no named budget owner is an agent whose overspend nobody is accountable for — the same failure mode as an alert wired to a channel nobody reads. Name the owner before the agent ships, not after the first surprise invoice. The owner holds both the raise-the-cap authority and the kill authority below.

### Cost-Anomaly-to-Incident Wiring

A spend spike is a reliability signal (see *Cost Tracking as a Reliability Concern*), so wire anomaly detection on the spend curve into the same incident path as any other production alert — do not wait for the monthly review to notice.

1. **Detect.** Alert on burn-rate anomalies, not just absolute thresholds: spend velocity > N× the trailing baseline for a role/tenant, a cost-per-successful-task step change, or a cache-read ratio collapse (effective input price spiking with no call-count change).
2. **Respond automatically where safe.** Auto-pause a runaway role, or degrade it to a cheaper model — but only through a fallback that preserves every privacy, schema, tool, and residency constraint the primary held. This is the same capability-monotonic rule as the fallback chains in the `routing-architecture` reference; a cost-driven degrade that silently drops a policy constraint is a governance violation, not a cost saving. Fail closed for external-send / money-moving / write actions: those must not run on a degraded tier just to stay under budget.
3. **Escalate to a human.** A budget anomaly that auto-paused a production agent is an incident with an owner, routed through the `agent-deployment` skill's observability alerting (the "cost per run or per tenant exceeds budget" alert), not a line item discovered next month.

The anti-pattern is an anomaly detector that only emails: by the time someone reads it, the runaway loop has spent the budget. Detection without an automated first response is telemetry, not governance.

### Governance Review Cadence

Beyond the daily/weekly *Cost Review Cadence* above (which finds waste *within* a route), hold a slower **monthly per-agent review** that asks the harder question: is this agent worth what it costs?

| Review input | Question it answers |
|---|---|
| Monthly spend per agent | What did this agent actually cost to run? |
| Value delivered (tasks closed, tickets deflected, revenue influenced) | What did it produce that a human or a cheaper path would not? |
| Spend per verifier-pass, trended | Are the unit economics improving, flat, or degrading month over month? |
| Trend vs. prior months | Is cost growing faster than value? |

Declare **kill criteria before the agent ships**, so retiring it is a pre-agreed threshold rather than a political fight later. An agent that costs more than the value it delivers for two consecutive review periods, with no credible fix in flight, gets degraded to a cheaper tier, scoped down, or shut off. "We already built it" is a sunk cost, not a reason to keep paying its monthly bill. The review's job is to make that decision on numbers — spend against value — not on attachment.

### Cost-Governance Pitfalls

1. **Showback with no owner.** A per-team cost report that names no accountable owner changes nothing. *Fix:* every agent and tenant has a named budget owner before it ships; the owner holds both raise-cap and kill authority.
2. **Untagged spend.** Any call that reaches the provider without an owner tag is unattributable and silently socializes cost across everyone. *Fix:* tag at the finest layer you control (app span, gateway key, or Bedrock application inference profile) and reject or flag untagged routes.
3. **Anomaly alert with no automated response.** An emailed spike alert arrives after the budget is already spent. *Fix:* wire detection to an automatic pause or capability-monotonic degrade, then page a human; the email is the third step, not the only one.
4. **Cost-driven degrade that drops a constraint.** Falling back to a cheaper model to save money, and losing a privacy/schema/residency guarantee in the process, trades a cost problem for a compliance incident. *Fix:* every degrade path is capability-monotonic (`routing-architecture` fallback rules); money-moving and write actions fail closed rather than degrade.
5. **No kill criteria.** An agent that never earns its spend keeps running because nobody agreed in advance when to stop it. *Fix:* pre-declare kill thresholds (cost-vs-value for N periods) at ship time and enforce them in the monthly governance review.
