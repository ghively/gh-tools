> Last verified: 2026-07. Agent telemetry schemas and observability vendor capabilities change quickly; re-check OpenTelemetry and vendor docs before building dashboards.

# Agent Observability

Agent observability answers five questions: what did the agent see, what did it decide, what did it call, what did it cost, and where did it fail. Traditional request logs are not enough because the interesting behavior lives inside the trajectory.

## Current State

- OpenTelemetry's old GenAI semantic-convention page now points to the dedicated [semantic-conventions-genai repository](https://github.com/open-telemetry/semantic-conventions-genai), so treat GenAI span names and attributes as active spec surface rather than frozen infrastructure.
- The [Claude Agent SDK observability docs](https://code.claude.com/docs/en/agent-sdk/observability.md) export metrics, log events, and beta traces through OTLP. Traces include interaction, LLM request, tool, and hook spans; content is not exported by default.
- Platforms such as [Langfuse](https://langfuse.com/docs), [LangSmith](https://docs.smith.langchain.com/observability), and [Braintrust](https://braintrust.dev/docs/guides/traces) combine tracing with evaluation, prompt/version management, or failure analysis. Use them when they reduce operational work; keep your instrumentation portable through OTEL where possible.

## What to Instrument

| Signal | Minimum fields |
|---|---|
| Model step | model ID, prompt version, input/output token counts, cost, latency, stop reason, retry count |
| Tool call | tool name, arguments after redaction, result status, latency, error class, side-effect ID |
| Retrieval | query, retriever version, document IDs, scores, source collection, latency |
| Agent loop | turn count, step count, loop detector state, max-turn stop, wall-clock duration |
| User feedback | rating, correction text, target span/run, user/tenant ID |
| Safety gate | permission prompt, denial reason, hook decision, policy rule ID |

### Per-Step Instrumentation in Practice

The minimum fields above are not aspirational; each one answers a specific production question. Use this mapping to defend the instrumentation against "we can add that later."

| Field | The question it answers when missing | Where it usually lives |
|---|---|---|
| Input/output token counts | "Why did this run cost 4x the median?" | Span attributes on the model-call span |
| Per-step cost | "Which tenant or task type is burning the budget?" | Derived from tokens x price; attribute on the run |
| Per-step latency | "Is the slowdown the model, a tool, or retrieval?" | Span duration, decomposed by span kind |
| Stop reason | "Did it stop because it was done, hit max turns, or refuse?" | Span attribute; one of the most under-logged fields |
| Tool-call success rate | "Is this integration degrading, or is the agent misusing it?" | Group tool spans by name and compute error rate |
| Retry count | "Are we papering over a flaky dependency?" | Counter on model and tool spans |
| Trajectory capture | "Can I replay this exact run to diagnose it?" | Linked spans per turn with parent/child relationships |
| Side-effect ID | "Which external action did this span cause, and can I reverse it?" | Idempotency key or external-system reference attached to the tool span |

Trajectory capture deserves its own decision. The interesting behavior lives inside the sequence of turns, not in any single span. Capture spans with stable parent/child links so a run can be reconstructed end to end. The OpenTelemetry GenAI conventions cover span names and attributes for LLM and tool calls; map your agent's spans onto those names so dashboards and vendor tooling line up.

Capture full trajectories for debugging, but decide deliberately where prompt text and tool outputs may be stored. Many teams need two tiers: structural telemetry everywhere, content telemetry only in approved environments with retention controls.

## Alerts That Matter

- Cost per run or per tenant exceeds budget.
- Step count or wall-clock duration exceeds the expected envelope.
- Repeated tool-call failures spike for a specific integration.
- Refusal rate changes materially after a model or policy update.
- Retrieval returns low scores or empty context for common intents.
- Permission denials rise, indicating either policy drift or attempted misuse.
- Loop detector finds repeated thoughts, repeated tool calls, or no-progress retries.

A cost-per-run or per-tenant budget alert is not just a dashboard signal — wire it into the spend-anomaly incident path in the `model-selection` skill's `references/cost-tracking.md` *Cost governance* section (auto-pause or capability-monotonic degrade, then page the budget owner).

### Agent-Specific Alert Signals and Thresholds

Traditional service alerts (error rate, latency p99) miss most agent failure modes. Add agent-specific signals, and set thresholds from a baseline rather than guessing.

| Signal | What it catches | Suggested starting threshold | Window |
|---|---|---|---|
| Loop detector fires | Repeated thoughts, repeated tool calls, no-progress retries | Any non-zero rate above baseline; page if >1% of runs | Per run; aggregate hourly |
| Cost per run | Token runaway, fan-out explosion, silent model upgrade | p95 cost > 2x the trailing 7-day median | Rolling hourly |
| Cost per tenant | A single tenant burning disproportionate budget | Tenant share > N% of daily spend (set N by plan) | Daily |
| Tool-error rate (per tool) | A specific integration degrading or the agent misusing it | Error rate > 10% for a tool that was < 2% | Rolling 15 min |
| Refusal rate | Prompt-injection surge, model behavior shift, policy drift | Shift > 3 sigma from the trailing 14-day baseline | Rolling hourly |
| Retrieval emptiness | Knowledge base gaps, embedding drift, broken connectors | Empty or below-threshold results > 5% of retrieval calls | Rolling hourly |
| Permission-denial rate | Policy drift or attempted misuse | Denial rate > 2x the trailing 7-day baseline | Rolling daily |
| Max-turn stops | Agent not converging; task too hard or tools failing | Stop-due-to-limit rate > 5% of runs | Rolling daily |
| Wall-clock timeout | Stuck tool, hung browser, deadlock | Timeout rate > 1% of runs | Rolling hourly |

Treat every threshold above as a starting point to calibrate against your own baseline, not a universal constant. The first week of traffic establishes the baseline; the second week is when thresholds become trustworthy. A threshold that pages on day one before you have a baseline is a threshold set by guessing.

## Log Hygiene

1. Redact secrets and credentials before traces leave the process.
2. Hash or tokenize user identifiers unless the observability backend is approved for direct identifiers.
3. Keep raw prompts and tool outputs off by default; enable only for a scoped incident or eval dataset capture.
4. Put retention on high-risk trace classes, especially browser sessions, shell output, user files, and customer support messages.
5. Store enough provenance to reconstruct the run: code version, prompt version, model version, tool schema version, memory collection version.

### Redaction Example

Redaction must happen before content leaves the process, not in the backend. The shape below is illustrative pseudocode, not a library contract; the point is the order: classify, scrub, then emit.

```text
# Pseudocode shape for a redaction hook on every exported span.

def redact_before_export(span):
    # 1. Secret patterns: API keys, bearer tokens, connection strings.
    for pattern in SECRET_PATTERNS:
        span.attributes = scrub(span.attributes, pattern)

    # 2. Direct identifiers: email, phone, account numbers, user IDs.
    #    Hash unless the backend is approved for direct identifiers.
    for field in IDENTIFIER_FIELDS:
        span.attributes[field] = hash_or_tokenize(span.attributes[field])

    # 3. Free-text fields: prompt text, tool arguments, tool results.
    #    Off by default; enable only in approved environments.
    if not env_allows_content(span.env):
        span.drop_fields(CONTENT_FIELDS)

    # 4. Provenance: never redact. These are required to reconstruct the run.
    keep(span.attributes["code.version"])
    keep(span.attributes["prompt.version"])
    keep(span.attributes["model.id"])
    keep(span.attributes["tools.version"])

    return span
```

Two failure modes to watch for: redacting the provenance fields (which makes the trace useless for diagnosis) and forgetting the tool-result field (which leaks whatever the tool returned — often exactly the sensitive content you meant to scrub). Test the hook with a synthetic span that contains a fake key, a fake email, and a fake tool result before trusting it in production.

## Practical Dashboard

Start with one dashboard per production agent:

- Volume: runs, users, tasks by type.
- Quality: eval pass rate, user feedback, escalation rate.
- Reliability: error rate by tool, retry count, timeout count.
- Latency: end-to-end duration, model latency, tool latency.
- Cost: tokens and spend by model, tenant, task type.
- Safety: denials, approvals, sandbox violations, hook blocks.

If you cannot answer "which prompt/model/tool version caused this behavior?" from the trace, your deployment is not observable yet.
