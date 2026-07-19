# The Agent Loop

The loop is the harness's heartbeat. Every harness implements some shape
of the six-step cycle below. The differences between harnesses are almost
entirely in how they handle the edge cases at each step.

## The Six Steps in Depth

### 1. Assemble Context

Before each model call, the harness assembles the context window:

```
[System prompt]
[Instructions / AGENTS.md rules]
[Tool schemas]
[Conversation history]      ← the part that grows
[Injected memory / RAG]     ← optional, per-turn
[Current user message]
```

The harness's job here is **context engineering**: select what fits,
compress what does not, keep the prefix stable for prompt caching. See
`context-management.md` for the compaction doctrine and
`prompt-context-engineering` skill for the prompting side.

Key harness responsibilities at this step:

- Enforce a **token budget** below the model's context window (leave room
  for the response and for tool results that arrive mid-turn).
- Keep the **prefix stable** so the prompt cache hits.
- **Sort tool schemas deterministically** — schema order changes bust
  the cache.
- Inject **session metadata** (session ID, turn number, user identity)
  in a fixed position.

### 2. Call the Model

The harness sends the assembled context to the model and receives:

- Streaming tokens (the visible reasoning / answer).
- Tool-call requests (parsed from the stream as they arrive).
- Stop reason (`end_turn`, `tool_use`, `max_tokens`, `stop_sequence`).

The harness decides:

- **Stream or buffer.** Always stream for user-facing output. Buffer
  only when the consumer cannot handle partial results.
- **Capture intermediate state.** Tool calls emitted mid-stream must be
  captured even if the stream is interrupted before `end_turn`.
- **Respect the stop reason.** `tool_use` means "I want to call a tool";
  `max_tokens` means "I ran out of output budget"; `end_turn` means "I'm
  done."

```python
# Pseudocode for the model-call step
stream = client.messages.stream(
    model=model_id,
    system=system_prompt,
    messages=assembled_messages,
    tools=tool_schemas,
    max_tokens=output_budget,
)

text_chunks, tool_calls = [], []
with stream as response:
    for event in response:
        if event.type == "content_block_delta":
            text_chunks.append(event.delta.text)
            emit_to_user(event.delta.text)        # stream to UI
        elif event.type == "tool_use":
            tool_calls.append(event)

stop_reason = response.stop_reason
```

### 3. Decide What to Do

The harness routes based on what the model returned:

| Model output | Harness action |
|---|---|
| Text only, `stop_reason: end_turn` | Return to user; end turn |
| One or more tool calls, `stop_reason: tool_use` | Dispatch tools (step 4) |
| Empty response or refusal | Recovery path (see `error-recovery.md`) |
| `stop_reason: max_tokens` | Continue with "please continue" or truncate the turn |

The decision is the harness's, not the model's. The model proposes; the
harness dispatches.

### 4. Execute Tool Calls

Tool execution is where most harness bugs live. The harness must:

- **Enforce permission** before dispatch. Destructive tools require a
  pre-tool interrupt (see `hitl-interrupts.md`).
- **Bound duration.** Every tool call has a timeout. A hung tool does
  not hang the agent.
- **Capture output.** Tool input, output, duration, and exit status
  become a span for observability.
- **Handle parallelism.** Independent tool calls run in parallel;
  dependent calls run sequentially. The harness decides, not the model.
- **Sanitize.** Tool output that will re-enter the model context is
  untrusted data; apply size limits and redaction.

```python
# Dispatch with parallelism + timeout + permission
async def dispatch(tool_calls, context):
    independent = classify_independent(tool_calls)
    results = await asyncio.gather(*[
        run_one(call, context, timeout=30)
        for call in independent
    ])
    return results

async def run_one(call, context, timeout):
    if requires_permission(call):
        await ask_user(call)             # HITL interrupt
    try:
        result = await tool_registry[call.name](
            *call.args,
            timeout=timeout,
            **context,
        )
        span_emit(call, result, status="ok")
        return result
    except ToolTimeout:
        span_emit(call, None, status="timeout")
        return {"error": "tool timed out"}
    except Exception as e:
        span_emit(call, None, status="error", error=str(e))
        return {"error": str(e)}
```

### 5. Append Results to Context

Tool results are appended to the conversation history. The harness must:

- **Truncate large outputs.** A tool that returns 50 KB of JSON will
  blow the context window. Truncate, summarize, or page.
- **Check the budget.** After appending, if the context is over the
  pre-compaction threshold, compact before the next model call.
- **Maintain cache stability.** Append to the end; do not rewrite
  earlier turns.

### 6. Check Stop Conditions

Before looping back to step 1, the harness checks:

| Condition | Action |
|---|---|
| Step cap reached | Stop; surface "step cap hit" |
| Wall-clock budget exhausted | Stop; surface "timeout" |
| Token/cost budget exhausted | Stop; surface "budget hit" |
| Doom-loop detector triggered | Stop; surface "loop detected" |
| User interrupt received | Stop; hand back to user |
| Model returned `end_turn` | Stop naturally |

The step cap is the **hard floor**. No harness should ever loop without
one, regardless of what the model says.

## Stop-Condition Defaults

| Condition | Dev default | Production default |
|---|---|---|
| Step cap | 50 turns | 10–25 turns (task-dependent) |
| Wall clock | 10 minutes | 2–5 minutes |
| Token budget | Unlimited | Per-task ceiling |
| Doom-loop detector | Off | On (hash last 5 tool-call signatures) |

## Worked Example: A Minimal Loop

```python
import asyncio
from dataclasses import dataclass

@dataclass
class HarnessConfig:
    max_steps: int = 25
    max_wall_clock_s: int = 300
    token_budget: int | None = None
    tool_timeout_s: int = 30

async def run_agent(
    client, model_id, system, messages, tools, config, user_input
):
    messages = [*messages, {"role": "user", "content": user_input}]
    start = time.monotonic()

    for step in range(config.max_steps):
        if time.monotonic() - start > config.max_wall_clock_s:
            return "wall clock budget hit"

        # 1. Assemble context (compaction check elided)
        # 2. Call the model
        response = await client.messages.create(
            model=model_id,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )

        # 3. Decide
        text_parts, tool_calls = parse_response(response)
        if text_parts:
            emit_to_user(text_parts)

        if not tool_calls:
            return text_parts              # natural stop

        # 4. Execute tools
        tool_results = await asyncio.gather(*[
            dispatch_tool(tc, config.tool_timeout_s)
            for tc in tool_calls
        ])

        # 5. Append results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # 6. Doom-loop check
        if is_doom_loop(messages, window=5):
            return "doom loop detected"

    return "step cap hit"
```

This is the shape every harness implements. The production version adds
compaction, streaming, observability, HITL interrupts, durable
checkpointing, and error recovery — each the subject of its own reference
file here.

## Pitfalls Specific to the Loop

1. **Checking stop conditions only at the top of the loop.** A tool
   call that takes 5 minutes burns the wall-clock budget while the
   harness waits. Fix: check stop conditions after each tool call too.
2. **Trusting `end_turn`.** Some models emit `end_turn` and then more
   text in the next call. Fix: the harness stops on `end_turn` but
   the user can always send a follow-up.
3. **Appending tool results as a single user message.** Some providers
   require tool results as separate messages per tool call. Fix: match
   the provider's expected shape exactly.
4. **No span emission on the model call itself.** The model call is a
   span too (tokens, latency, cost, cache hit/miss). Fix: emit a span
   for every model call, not just tool calls.
5. **Re-dispatching on retry without re-asking the model.** A tool
   fails; the harness retries the tool. The model does not know the
   first attempt happened. Fix: append both attempts to context so the
   model can adjust.
