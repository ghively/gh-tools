# Streaming and Progressive Output

A harness that buffers the full response before emitting anything has
failed at UX. Users perceive a multi-second pause as broken. The
harness's job is to stream tokens, tool-call decisions, and tool
results as they happen, within the constraints of structured-output
guarantees.

This reference covers the harness layer of streaming. For the
UX-progressive-disclosure ladder and the provider API mechanics, see
`agent-deployment/references/streaming-and-progressive-ux.md`.

## What to Stream

| Layer | Stream? | How |
|---|---|---|
| Model tokens (visible text) | Yes | Token-by-token from the provider |
| Model reasoning (thinking) | Optional | Stream if the user opted in; never by default |
| Tool-call decisions | Yes | As soon as the model emits the call |
| Tool-call arguments | Yes | As they stream from the model |
| Tool execution progress | Yes | Long-running tools emit progress events |
| Tool results | On completion | After the tool returns; cannot stream a unit of work that must complete |
| Errors | Yes | As soon as the harness detects |

The harness streams everything it can. The exceptions are tool results
(a tool call is atomic — it either returned or it did not) and
structured outputs that must be complete before they are valid.

## Stream Plumbing

```
Provider ──token──► Harness ──token──► UI
                       │
                       ├─tool_call──► Tool dispatcher ──progress──► UI
                       │                  │
                       │                  └─result──► Harness ──► Context
                       │
                       └─error──► Error handler ──► UI + Context
```

The harness is the fan-out point: it consumes the provider stream and
emits multiple downstream streams (tokens to UI, tool calls to
dispatcher, errors to handler). Backpressure on any downstream must
not block the others.

## Backpressure

When the UI cannot keep up (slow terminal, slow network), the harness
must:

- Never block the provider stream — buffering unbounded tokens is a
  memory leak.
- Apply backpressure to the UI (drop intermediate tokens, keep the
  latest).
- Continue capturing tool calls and errors regardless of UI
  backpressure.

A common pattern: the UI subscribes to a throttled token stream (every
16 ms for 60 fps); the harness captures the full stream for the
transcript regardless.

## Partial JSON for Structured Outputs

When the model emits a structured output (JSON schema, tool input),
the harness can stream it as partial JSON:

```python
# Partial JSON parsing
def parse_partial_json(text):
    # Best-effort parse; close braces/brackets if missing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try closing
        for closer in ['}', '"]', ']', '}}', '"]']:
            try:
                return json.loads(text + closer)
            except json.JSONDecodeError:
                continue
        return None
```

This lets the UI show the structure filling in as the model types.
Library support: `partial-json-parser` (JS), `jsonschema`-aware partial
parsers.

Rules:

- Partial JSON is for UI feedback only; never dispatch a tool on a
  partial parse.
- The harness dispatches the tool only after the model emits the full
  call (`stop_reason: tool_use`).

## Tool-Call Streaming

When the model emits multiple tool calls in one turn, the harness can:

- **Stream the decisions** as the model makes them (the user sees
  "calling tool X" before the tool returns).
- **Dispatch in parallel** if the calls are independent.
- **Stream tool progress** for long-running tools (a search tool
  returns partial results; a deploy tool emits stage events).

## Stream Interruption

See `error-recovery.md` for the recovery path when the stream drops.
The streaming-specific rule: never show the user a partial response
and then a different full response without acknowledging the rewind.

## The Stream Boundary

The harness streams to:

- The **primary UI** (user-facing).
- The **observability system** (spans, traces).
- The **transcript** (durable session storage).

These are three different streams with different consumers. The
harness emits all three; each has its own backpressure and durability
rules.

## Pitfalls

1. **Buffering the full response.** First-token latency in seconds.
   Fix: stream from the first token.
2. **No backpressure on the UI.** Slow terminal → unbounded buffer →
   OOM. Fix: throttle the UI stream; keep the full stream for the
   transcript.
3. **Dispatching on partial JSON.** A tool call dispatched before the
   model finished emitting it; the arguments are truncated. Fix:
   dispatch only after `stop_reason: tool_use`.
4. **Stream rewind without acknowledgment.** The connection drops; the
   harness retries; the user sees a different continuation. Fix:
   acknowledge the rewind; show the user what changed.
5. **No streaming for errors.** The harness waits until the full error
   is formatted before emitting. Fix: emit the error type immediately;
   fill in details as they arrive.
6. **One stream for everything.** The UI blocks because the
   observability system is slow. Fix: separate streams with separate
   backpressure.
