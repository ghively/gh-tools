# Mid-Turn Error Recovery

The harness's quality shows in how it handles failures mid-turn. A tool
times out, a model returns a refusal, a rate limit hits mid-stream, a
tool produces malformed output. Each has a distinct recovery path.

This reference covers the failure modes and the harness's response. The
unifying doctrine: **transient failures retry with backoff; permanent
failures surface; destructive operations never auto-retry.**

## Failure Taxonomy

| Failure | Source | Transient? | Recovery |
|---|---|---|---|
| Rate limit (429) | Provider | Yes | Exponential backoff with jitter |
| Server error (5xx) | Provider | Yes | Exponential backoff |
| Request too large (413) | Context overflow | No | Compact and retry |
| Bad request (400) | Bug in harness | No | Surface; do not retry |
| Authentication (401/403) | Config | No | Surface; do not retry |
| Content refusal | Model policy | Sometimes | Rephrase or surface |
| Tool timeout | Tool | Sometimes | Retry once, then surface |
| Tool error (exception) | Tool | No | Append error to context; let model adjust |
| Tool malformed output | Tool | No | Validate; append error to context |
| Stream interruption | Network | Yes | Reconnect with last token |
| Process crash | Harness/OS | N/A | Resume from last checkpoint |

## Provider Error Recovery

### Rate Limits (429)

The harness retries with exponential backoff and jitter:

```python
async def call_with_backoff(fn, max_retries=5):
    for attempt in range(max_retries):
        try:
            return await fn()
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(wait)
```

Rules:

- Honor the `Retry-After` header if the provider sends one.
- Add jitter to avoid thundering herds.
- Circuit-break after N retries; surface persistent failures.
- Emit a span for every retry so the operator sees the backoff.

### Server Errors (5xx)

Same backoff doctrine as 429. Distinguish 5xx (server's fault, retry)
from 4xx (client's fault, do not retry unless you fixed the client).

### Request Too Large (413)

The context overflowed the provider's limit. Recovery:

1. Compact the context (see `context-management.md`).
2. Retry the request.

Do not retry without compaction — the same request will fail the same
way.

### Authentication Errors (401/403)

Never retry. Surface to the operator; the credentials need rotation or
the config needs fixing.

## Model Refusal Recovery

When the model refuses to answer (content policy, safety filter):

1. **Check the refusal reason.** Providers return a structured reason.
2. **If the refusal is a false positive** (the request was legitimate),
   the harness can retry with a rephrased system prompt or a different
   model.
3. **If the refusal is legitimate**, surface it to the user; do not
   bypass.

Never auto-rephrase to evade a safety filter the user deployed
deliberately. The harness's job is to surface the refusal, not to
work around it.

## Tool Error Recovery

### Tool Timeout

A tool call exceeds its timeout. Recovery:

1. Cancel the tool call.
2. Append a timeout error to the context as the tool result.
3. Let the model decide whether to retry, adjust, or give up.

```python
try:
    result = await asyncio.wait_for(
        tool_registry[call.name](**call.args),
        timeout=30,
    )
except asyncio.TimeoutError:
    result = {"error": "tool call timed out after 30s",
              "tool": call.name, "args": call.args}
# Always append — the model must see the timeout to adjust
messages.append_tool_result(call.id, result)
```

Rules:

- Never auto-retry a timed-out tool without letting the model see the
  timeout first. The model may decide the tool is the wrong approach.
- If the model retries the same tool and it times out again, the
  harness's doom-loop detector should catch it (see
  `doom-loop-prevention.md`).

### Tool Exception

A tool raises an exception. Recovery:

1. Catch the exception.
2. Format it as a structured error result.
3. Append to context.
4. Let the model adjust.

The model seeing the error is the recovery. Hiding the error from the
model prevents it from adjusting.

### Tool Malformed Output

A tool returns output that does not match its declared schema. Recovery:

1. Validate against the schema.
2. If invalid, format a validation error and append to context.
3. Let the model decide (retry, different tool, give up).

This is the same doctrine as tool exceptions: surface the error to the
model.

## Stream Interruption

The streaming connection drops mid-response. Recovery:

1. Record the last token received.
2. Reconnect with the provider's continuation mechanism (e.g.,
   `stream_id` + last token).
3. If the provider does not support continuation, restart the request
   with the same context and discard the partial response.

Rules:

- Never show the user a partial response and then a different full
  response without acknowledging the rewind.
- Emit a span noting the stream interruption.

## Process Crash

The harness process dies mid-run. Recovery at restart:

1. Load sessions with `status: active` from the durable store.
2. For each, check whether the interrupted run had side-effecting tool
   calls in flight.
3. For each in-flight tool call, check whether the side effect landed
   (idempotency check).
4. Either resume from the last completed turn or surface the
   interruption to the user.

This is the hardest recovery path and must be tested with chaos
testing, not just clean-shutdown testing.

## The Never-Retry List

Some operations must never be auto-retried:

- Destructive tool calls (`delete`, `deploy`, `send`, `transfer`).
- Operations with external side effects that are not idempotent.
- Operations that already returned a success (the harness just did not
  record it).

For these, the harness surfaces the uncertainty to the user:
"Operation may have completed; verify before retrying."

## Error Spans

Every error emits a span:

```json
{
  "type": "error",
  "stage": "tool_dispatch",
  "tool": "deploy",
  "error_type": "timeout",
  "message": "exceeded 30s budget",
  "retry": false,
  "surfaced_to_model": true
}
```

The `surfaced_to_model` field tells the operator whether the model saw
the error and has a chance to adjust.

## Pitfalls

1. **Silent retry of a destructive operation.** The tool was dispatched;
   the network dropped; the harness retries; the operation lands twice.
   Fix: destructive operations are never auto-retried.
2. **Hiding errors from the model.** The harness catches a tool
   exception and returns an empty result; the model cannot adjust.
   Fix: always append the error to context.
3. **Retry without backoff.** A 429 triggers an immediate retry; the
   provider rate-limits again. Fix: exponential backoff with jitter.
4. **Retry without a circuit breaker.** The harness retries forever.
   Fix: cap retries at N; surface persistent failures.
5. **Crash recovery that re-executes.** The crash happened after a
   side effect; the recovery retries it. Fix: idempotency check before
   retry.
6. **Refusal bypass.** The harness treats a safety refusal as an error
   and retries with a rephrased prompt. Fix: refusals are surfaced,
   not bypassed.
