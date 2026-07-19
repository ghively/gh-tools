# Harness-Level Observability

The harness is the observation point for the agent's runtime behavior.
It emits spans for every model call, every tool call, every compaction,
every error, every interrupt. Without these spans, operating a live
agent is guesswork.

This reference covers what the harness emits. For the broader
observability doctrine (dashboards, alerts, retention), see
`agent-deployment/references/observability.md`.

## The Span Taxonomy

Every harness operation emits a span:

| Span type | When emitted | Key fields |
|---|---|---|
| `model_call` | Each call to the provider | model, tokens_in, tokens_out, cache_hit, latency, cost, stop_reason |
| `tool_call` | Each tool dispatch | tool, args, result_size, latency, status |
| `compaction` | Each context compaction | trigger, size_before, size_after, turns_affected |
| `interrupt` | Each HITL pause | tool, args, verdict, user_id |
| `error` | Each error recovery | stage, error_type, message, retry, surfaced_to_model |
| `stream_event` | Stream lifecycle | type (start/interrupt/resume/end), bytes |
| `session_event` | Session lifecycle | type (create/resume/fork/end), session_id |

Each span has a timestamp, a session ID, a run ID (within the session),
and a step number (within the run). Together these reconstruct the full
trajectory.

## The GenAI Semantic Conventions

The OpenTelemetry GenAI semantic conventions (formerly
`semantic-conventions/trace/gen-ai`, now in the dedicated
`semantic-conventions-genai` repository) define standard span
attributes:

- `gen_ai.system`: provider name (`anthropic`, `openai`, `bedrock`)
- `gen_ai.request.model`: model ID
- `gen_ai.usage.input_tokens`: input token count
- `gen_ai.usage.output_tokens`: output token count
- `gen_ai.usage.cache_read_input_tokens`: cache hit tokens
- `gen_ai.usage.cache_write_input_tokens`: cache write tokens

The harness should emit these attributes on every `model_call` span so
that OTel-compatible backends (Langfuse, LangSmith, Phoenix, Honeycomb)
can render standard dashboards.

## Tool-Call Span Detail

```json
{
  "type": "tool_call",
  "session_id": "ses_abc",
  "run_id": "run_001",
  "step": 4,
  "tool": "deploy",
  "args": {"service": "api", "env": "staging"},
  "result_size": 142,
  "latency_ms": 1850,
  "status": "ok",
  "permission_verdict": "approved",
  "interrupt_duration_ms": 4500
}
```

The `permission_verdict` and `interrupt_duration_ms` fields are
harness-specific (not in the GenAI spec) but essential for operating
an agent with HITL interrupts.

## Cost Tracking at the Harness Layer

The harness is where per-run cost is computed. For each `model_call`
span:

```
run_cost = Σ (
  (input_tokens - cache_read_tokens) × input_price
  + cache_read_tokens × cache_read_price
  + cache_write_tokens × cache_write_price
  + output_tokens × output_price
)
```

The harness accumulates this across all model calls in a run and emits
a `run_cost` span at run end. See `model-selection/references/cost-tracking.md`
for the cost-tracking doctrine.

## Trace Export

The harness exports traces via:

| Exporter | Use case |
|---|---|
| OTLP (HTTP/gRPC) | Standard; works with any OTel collector |
| Langfuse / LangSmith SDK | Direct integration with eval platforms |
| stdout / file | Dev; debugging |
| Webhook | Custom; real-time alerting |

The harness should support multiple exporters simultaneously (e.g.,
OTLP to the production collector + stdout for dev).

## Trajectory Capture

A trajectory is the ordered sequence of spans within a run. It is the
eval harness's input: the eval asserts on the trajectory, not just the
final text.

```python
trajectory = [
    {"step": 0, "type": "model_call", "stop_reason": "tool_use"},
    {"step": 1, "type": "tool_call", "tool": "search", "status": "ok"},
    {"step": 2, "type": "model_call", "stop_reason": "tool_use"},
    {"step": 3, "type": "tool_call", "tool": "deploy", "status": "ok",
     "permission_verdict": "approved"},
    {"step": 4, "type": "model_call", "stop_reason": "end_turn"},
]
```

The harness must emit every span; gaps in the trajectory make evals
unverifiable. See the `agent-evals` skill for how evals assert on
trajectories.

## Redaction

Spans contain tool arguments and results, which may contain PII or
secrets. The harness must:

- Register a redaction layer with the span emitter.
- Redact known-secret patterns (env vars named `*_KEY`, `*_TOKEN`).
- Redact PII per the organization's policy.
- Never redact the `tool` name, `status`, `latency`, or `cost` fields
  — those are operational signals.

See `agent-safety` for the redaction doctrine.

## Pitfalls

1. **No spans for model calls.** Only tool calls are spanned; cost and
   latency of the model itself are invisible. Fix: emit a span for
   every model call.
2. **Gaps in the trajectory.** Compaction and interrupt spans are
   missing; the eval harness cannot reconstruct what happened. Fix:
   emit spans for every harness operation.
3. **Secrets in spans.** The tool arguments include an API key; the
   span is exported to the collector; the key leaks. Fix: redaction
   layer before export.
4. **No cache metrics.** The span records input/output tokens but not
   cache hit/miss; cost optimization is invisible. Fix: emit
   `cache_read_input_tokens` and `cache_write_input_tokens`.
5. **Stdout only in production.** Spans go to stdout; nobody reads
   them. Fix: OTLP export to a real collector.
6. **Trajectory without step numbers.** Spans have timestamps but no
   step ordinal; reconstructing order is fragile. Fix: emit `step`
   as an explicit integer.
