> Last verified: 2026-07. Claude API SSE event names, fine-grained tool streaming, and Agent SDK input/output modes change across releases; re-check the streaming docs (platform.claude.com/docs/en/build-with-claude/streaming) and code.claude.com/docs/en/agent-sdk before wiring transport code.

# Streaming and Progressive UX

A production agent that answers in 40 seconds with a blank screen feels broken; the same agent streaming its progress feels fast. Streaming is a deployment concern, not a model feature: the model emits tokens and tool calls, and your serving layer decides what the user sees, when, and how to keep the connection alive through long silent tool phases. This reference covers streaming agent output to users **without** giving up the structured-output guarantees that make the agent verifiable.

## Why Agents Differ From Chat Streaming

Streaming a chat completion is a solved problem: pipe token deltas to the browser. Agents break that model in four ways, and each one is a UX decision the serving layer must make.

| Agent property | Why chat-streaming assumptions fail |
|---|---|
| Tool-call interleaving | Output is not one text stream; it is text, then a tool call, then a silent wait, then more text. Naive "print every delta" renders half-formed tool JSON to the user. |
| Long silent tool phases | A retrieval, browser step, or subagent can run 30s+ with zero model tokens. A token-only stream looks hung; the connection may time out before the next token. |
| Multi-step progress | The user cares about *which step* ("searching", "writing the file") more than which token. Step boundaries are the useful signal, and they live in the event structure, not the text. |
| Structured final artifact | The deliverable is often JSON/a file/a decision, not prose. Streaming raw JSON tokens invites mid-parse rendering and breaks the schema guarantee consumers depend on. |

The governing rule: **stream human-readable progress; deliver machine-consumed results atomically at completion.** Progress text is for the person watching; the structured artifact is for the code downstream, and it must arrive whole.

## Transport Decision Table

Pick the transport from the run's shape, not from what the frontend already uses. All four carry the same event envelope (below); they differ in duplex, reconnect, and infra cost.

| Transport | Reach for it when... | Duplex | Reconnect / replay | Watchouts |
|---|---|---|---|---|
| SSE (Server-Sent Events) | One-way server→client token/progress stream over a single HTTP response; the default for agent output | No (server→client only) | Built-in via `Last-Event-ID` + event `id:` — you must implement the replay buffer | Proxies/load balancers buffer; disable response buffering. Browser caps ~6 SSE connections per host on HTTP/1.1 |
| WebSocket | The user interrupts, approves, or steers mid-run (barge-in, approval pauses, live tool confirmation) | Yes | None built-in — you design resume tokens and replay yourself | Heavier infra (sticky sessions, ping/pong keepalive); overkill for pure output streaming |
| Polling (`GET /runs/{id}/events?after=<cursor>`) | Serverless/stateless clients, mobile on flaky networks, or when a run outlives any single connection | No (client pulls) | Trivial — the cursor *is* the resume token; the event log is the source of truth | Latency = poll interval; chatty. Use long-poll or back off when idle |
| Chunked HTTP (raw `Transfer-Encoding: chunked`) | A CLI or server-to-server consumer that wants a byte stream without SSE framing | No | None | No event typing; you re-invent framing. Prefer SSE unless the consumer can't parse SSE |

Decision procedure: **duplex need first** — if the user acts mid-run, WebSocket. **Then run duration vs. connection lifetime** — if the run can outlive a connection (minutes-long, mobile), polling over a durable event log. **Otherwise SSE**, the default for streamed output. Chunked HTTP only for consumers that can't parse SSE. These combine: a webhook-triggered long run commonly writes to a durable event log that a browser tails over SSE and a mobile client polls — same events, three readers. See `packaging-serving.md` for the shape combinations this rides on.

## The Progressive-Disclosure UX Ladder

Each rung adds fidelity and cost. Climb only as far as the product needs; every rung above spinner is engineering you maintain.

| Rung | What the user sees | Cost | When it's enough |
|---|---|---|---|
| 1. Spinner / indeterminate | "Working…" | Trivial | Sub-2s runs where progress detail adds nothing |
| 2. Step announcements | "Searching docs" → "Drafting reply" | Low — emit a typed event at each step boundary | Most tool-using agents; the highest value-per-effort rung |
| 3. Streamed tokens | The reply appears word by word | Medium — token deltas over SSE | Long prose replies; chat surfaces |
| 4. Streamed tool progress | "Reading 3 of 12 files", heartbeats during long calls | Medium-high — tools must emit progress events | Long silent tool phases that would otherwise read as hung |
| 5. Interactive intermediate artifacts | A draft/plan/diff the user can inspect or approve mid-run | High — needs duplex transport + approval protocol | High-stakes actions; human-in-the-loop pauses |

Skipping rung 2 is the most common mistake: teams jump to token streaming (rung 3) and still show a dead screen during the tool phase that actually dominates wall-clock time. Announce steps first; stream tokens second. Rung 5 is where streaming meets approval gates — see the human-in-the-loop cross-ref below.

## Streaming With Structured Output

The tension: users want to watch; consumers need a schema-valid artifact. Three patterns resolve it, in order of preference.

**1. Stream progress text, deliver the JSON at completion (default).** The model streams a human-readable narration ("Looking up the account… found it… drafting the summary"); the structured artifact is emitted as a single terminal event once complete and validated. The user never sees raw JSON; the consumer never sees a partial object. This is the right default because it keeps the schema guarantee from `deterministic-agents` (structured-outputs) fully intact — the artifact is validated before it leaves the process.

**2. Partial-JSON streaming — and its parsing hazards.** Some UIs want to render fields as they generate (a form filling in live). Streaming the JSON tokens works only with a *tolerant incremental parser* that accepts prefixes of a valid document; a standard `json.loads`/`JSON.parse` on a partial buffer throws on every delta until the last. Hazards, all real production incidents:
   - A partial string field renders a half-word, then a control character mid-escape.
   - The consumer reads the object before the closing brace and acts on a missing required field.
   - Constrained decoding guarantees the *final* document matches the schema; it guarantees **nothing about intermediate byte states**. Never let code branch on a partially-streamed object.
   The rule: partial-JSON streaming is a *rendering* technique for a trusted human viewer, never a data path for code. Anything a program consumes waits for the validated terminal artifact.

**3. Event-envelope pattern (the wire contract).** Wrap everything in a typed event so text, structure, and control signals never get confused on the wire. A minimal vocabulary:

```json
{"type": "status",      "step": "retrieval", "detail": "searching knowledge base"}
{"type": "delta",       "text": "Here is what I found"}
{"type": "tool_start",  "tool": "kb_search", "id": "call_1"}
{"type": "tool_result", "id": "call_1", "ok": true, "summary": "3 documents"}
{"type": "final",       "artifact": { /* the schema-valid object, whole */ }}
```

The consumer switches on `type`: render `delta` text, show `status`/`tool_start` as progress, and treat `final.artifact` as the only authoritative result. `delta` is display-only; `final` is load-bearing. This envelope is transport-agnostic — the same JSON lines flow over SSE `data:` frames, WebSocket messages, or a polled event array — which is what lets one event log feed three readers.

## Claude API Streaming Mechanics

Verified against the Claude API streaming docs (2026-07). Set `stream: true` (or use the SDK stream helper) and the Messages API returns Server-Sent Events. The event sequence for one message:

| SSE event | Carries | Use |
|---|---|---|
| `message_start` | Message metadata (id, model, role) | Open your render buffer |
| `content_block_start` | A new block begins (`text`, `tool_use`, `thinking`) | Branch rendering by block type |
| `content_block_delta` | Incremental content: `text_delta`, `input_json_delta` (tool args), `thinking_delta` | Append to the block; **do not** render `input_json_delta` as user text |
| `content_block_stop` | Block complete | Finalize that block |
| `message_delta` | Top-level updates: `stop_reason`, cumulative `usage` | Read the stop reason and token count |
| `message_stop` | Message complete | Close the stream |

Load-bearing details:
- **`input_json_delta` is partial tool-call JSON**, streamed token by token. It is not valid JSON until `content_block_stop`. Accumulate it; parse once. This is the API-level instance of the partial-JSON hazard above.
- **Thinking blocks** stream as `thinking_delta`. On current models (Fable 5, Opus 4.8/4.7, Sonnet 5) `thinking.display` defaults to `"omitted"` — the blocks arrive with empty text, so a UI that streams reasoning shows a long pause before output. Set `thinking: {type: "adaptive", display: "summarized"}` to stream a readable summary. (Confirm via the claude-api skill / model docs before relying on model-specific defaults.)
- **Fine-grained tool streaming** is not a beta header on current SDKs: set `eager_input_streaming: true` on the tool definition and use the regular stream, so tool arguments stream as they generate rather than arriving whole.
- **Stream any large `max_tokens` request.** The SDKs raise (or silently time out) on non-streaming requests above ~16K output — an idle connection drops before a minutes-long turn finishes. Streaming keeps the connection warm; use `get_final_message()` / `finalMessage()` to collect the whole response when you don't need per-token handling.
- **`pause_turn`** appears as a `stop_reason` when a server-side tool loop hits its iteration cap. Re-send the assistant turn to resume; surface it to the user as "still working", not "done".

## Agent SDK Streaming Modes

Verified against code.claude.com/docs/en/agent-sdk (2026-07). The Claude Agent SDK has two input modes; the distinction matters for interactive vs. one-shot deployments.

- **Streaming input mode (default, recommended).** You pass an async generator of user-message objects as `prompt`. In TypeScript, `query({ prompt: generateMessages(), options })` where the generator yields `SDKUserMessage` objects. In Python, construct `ClaudeSDKClient(options)`, call `await client.query(message_generator())`, then iterate `client.receive_response()`. This mode enables mid-session image uploads, queued messages, real-time interruption, and persistent context — the substrate for rungs 4–5 of the UX ladder. A generator exception is handled quietly (TS surfaces a generic abort message; Python stalls without raising), so validate inside the generator before yielding.
- **Single message input.** `query({ prompt: "...", options: { maxTurns: 1 } })` (TS) / `query(prompt="...", options=ClaudeAgentOptions(...))` (Python) for one-shot, stateless calls — the right shape for a Lambda. It does **not** support image attachments, queued messages, or interruption. Continue a prior run with `continue: true` / `continue_conversation=True`.
- **Output stream.** Both modes yield a message stream you iterate; a `result` message with subtype `success` (TS) / a `ResultMessage` (Python) carries the final result. Match your event envelope's `final` event to that terminal message.

Pick streaming input when the deployment is interactive or long-running; single message when it's a stateless one-shot. This maps directly onto the deployment shapes in `packaging-serving.md`.

## Backpressure and Reconnection

A stream that can't survive a dropped connection is a demo, not a deployment. Two problems: the fast producer outrunning a slow consumer (backpressure), and the connection dropping mid-run (reconnection).

- **Event IDs and resume tokens.** Every event gets a monotonic `id`. SSE clients send `Last-Event-ID` on reconnect; polling clients pass the cursor as `?after=<id>`. Either way the server replays events after that id. The resume token is just the last id the client acknowledged.
- **Replay-on-reconnect requires a durable event log.** SSE's built-in reconnect replays only what the server still buffers. For runs that must survive a real disconnect, write every event to a durable log (the session store from `packaging-serving.md`) and replay from it. This is the same log that lets a polling client and an SSE client read the same run — reconnection and multi-reader are the same mechanism.
- **Backpressure.** If the client can't keep up, don't buffer unboundedly in server memory (the OOM path). Bound the buffer and either drop coalescible `status`/heartbeat events (never `delta` or `final`) or apply flow control. Token deltas and the final artifact are load-bearing; intermediate progress pings are not — shed those first.
- **Idempotent replay.** Because a client can reconnect and re-receive events it already processed, the consumer must dedupe on event id. This is the streaming face of the idempotency discipline in `deterministic-agents` (idempotency-and-replay): at-least-once delivery is guaranteed, so make event handling safe to repeat.

## Progress UX for Long Tool Calls

The failure mode that most makes an agent feel broken is the silent tool phase. Defenses:

- **Heartbeats.** During a long tool call emit periodic `status`/heartbeat events (e.g. every few seconds) so the connection stays warm and the UI shows liveness. SSE comment-lines (`: keepalive`) also prevent proxy idle-timeout without polluting the event stream.
- **Tool-progress events.** A tool that can report progress ("file 3 of 12") should emit `tool_result`-style partial events, not stay silent until done. This is rung 4 of the ladder.
- **Timeout signaling.** Every tool call has a deadline (see the loop-discipline bounds in the deployment SKILL). When it trips, emit an explicit `status` event ("this is taking longer than expected") rather than letting the stream hang to the wall-clock limit. A visible slow is far better than an invisible stall.
- **Mask the wait, honestly.** An acknowledgment before a slow call ("checking that now") is good UX; a fake progress bar that doesn't track real work is a lie that erodes trust the first time it stalls at 90%.

## Cross-References

- `deterministic-agents` (structured-outputs) — the schema guarantee this reference streams *around*; never stream a partial object into a code path.
- `deterministic-agents` (idempotency-and-replay) — replay-on-reconnect delivers events at-least-once; dedupe on event id.
- `agent-design` (human-in-the-loop) — rung 5 of the ladder is an approval pause mid-stream; the interactive-artifact and duplex-transport machinery here is what makes those pauses possible.
- `agent-design` (voice-multimodal-agents) — its "streaming everywhere" doctrine is this reference applied to a latency-fatal surface: on voice, every rung of the ladder is mandatory, not optional.
- `packaging-serving.md` (this pillar) — the deployment shapes, session store, and shape combinations these streams ride on.
- `observability.md` (this pillar) — stream events double as trace spans; emit trace/session IDs on every event.

## Pitfalls

1. **Rendering raw tool-call JSON to the user.** Symptom: half-formed `{"query": "bil` flashes on screen mid-generation. Cause: piping `content_block_delta` / `input_json_delta` straight to the UI. Fix: branch on block type; render only `text` deltas, accumulate tool-arg deltas silently, and show tool activity as a typed `tool_start` status instead.

2. **Parsing a partially-streamed object.** Symptom: intermittent parse errors, or code acting on an object missing required fields. Cause: `json.loads`/`JSON.parse` on a buffer before `content_block_stop`, or a consumer reading `final` before it arrives. Fix: use a tolerant incremental parser for *display only*; gate all code paths on the validated terminal artifact.

3. **Silent long tool phase read as hung.** Symptom: users refresh or abandon during a 30s retrieval that emits no tokens; the connection times out at a proxy. Fix: emit heartbeats and step-announcement events (rungs 2 and 4); add SSE keepalive comments to defeat proxy idle-timeouts.

4. **No resume token, so a dropped connection loses the run.** Symptom: a mobile client that reconnects sees a fresh empty stream and the minutes-long run is unreachable. Cause: streaming from ephemeral memory with no durable event log. Fix: assign monotonic event ids, persist every event to a durable log, and replay from `Last-Event-ID` / cursor on reconnect.

5. **Unbounded server-side buffering under backpressure.** Symptom: server memory climbs and OOMs when a slow client falls behind a fast run. Cause: queuing every event in memory with no bound. Fix: bound the buffer; shed coalescible `status`/heartbeat events first; never drop `delta` or `final`.

6. **Streaming into a structured-output guarantee and breaking it.** Symptom: the schema-valid artifact that downstream code depends on arrives in pieces, and a consumer occasionally reads a malformed intermediate state. Cause: treating the streamed token feed as the data contract. Fix: keep two channels — progress text for humans, one atomic validated artifact for code (the event-envelope `final`).

7. **Non-idempotent event handling on reconnect.** Symptom: a duplicate side effect (double toast, double increment, replayed action) after a reconnect replays already-seen events. Cause: at-least-once delivery with no dedupe. Fix: dedupe on event id; make handlers safe to run twice (see idempotency-and-replay).

8. **Thinking-stream shows a dead screen.** Symptom: a UI that streams model reasoning shows a long pause before any text. Cause: `thinking.display` defaults to `"omitted"` on current models, so `thinking_delta` blocks stream empty. Fix: set `display: "summarized"` when you surface reasoning, or announce a "thinking" step so the pause reads as progress, not a stall.
