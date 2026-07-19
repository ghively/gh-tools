# Harness-Level Caching

The harness sits between the user and the provider, which makes it the
natural caching layer. A well-designed harness caches at three levels:
prompt prefix, tool results, and full responses. Each has different
semantics, invalidation rules, and cost profiles.

## The Cache Hierarchy

| Layer | What it caches | Hit rate | Invalidation |
|---|---|---|---|
| **Prompt-prefix cache** | The stable system + instructions + tools prefix | High (provider-managed) | Prefix change |
| **Tool-result cache** | Tool outputs for identical arguments | Medium | Tool's data changes |
| **Response cache** | Full model responses for identical contexts | Low (rarely exact repeats) | Context change |

Provider-managed prompt caching (Anthropic, OpenAI, Gemini) is the
biggest win and requires only prefix stability from the harness.
Tool-result and response caches are harness-managed and require explicit
design.

## Prompt-Prefix Cache

The provider discounts input tokens that hit a cached prefix. The
harness must:

- Keep the prefix stable: system prompt, instructions, tool schemas
  frozen for the session.
- Sort tool schemas deterministically. Schema order changes bust the
  cache.
- Place variable content (the conversation history) after the stable
  prefix.
- Use explicit cache breakpoints (Anthropic) where supported.

Provider specifics:

| Provider | Mechanism | Threshold | Discount |
|---|---|---|---|
| Anthropic | Automatic (5-min) or explicit breakpoints (1-hour) | ≥ 1024 tokens | ~90% off input price |
| OpenAI | Automatic | ≥ 1024 tokens | ~50% off input price |
| Gemini | Explicit context cache | Varies | Configurable |

See `prompt-context-engineering/references/long-horizon-context.md`
for the prompting-side details.

The harness's role is to preserve prefix stability. The provider does
the actual caching.

## Tool-Result Cache

When a tool is called with the same arguments twice, the harness can
return the cached result instead of re-executing. This is safe for:

- **Read-only tools** (search, get, list): no side effects.
- **Deterministic tools**: same args → same result.

Unsafe for:

- **Side-effecting tools** (write, deploy, send): never cache.
- **Time-sensitive tools** (current time, latest news): cache with a
  short TTL.
- **Non-deterministic tools** (LLM-backed subtools): cache only if the
  randomness is acceptable.

```python
cache_key = hash(tool_name, args, session_id)
if cache_key in tool_result_cache:
    cached = tool_result_cache[cache_key]
    if not cached.is_expired():
        span_emit(tool_call, cached, cache_hit=True)
        return cached.result

result = await dispatch_tool(tool_name, args)
tool_result_cache[cache_key] = CachedResult(
    result=result,
    expires_at=now() + tool.ttl,
)
return result
```

### Cache-Invalidation Signals

The harness invalidates the tool-result cache when:

- The tool's underlying data changes (a webhook, a file edit, a
  database write).
- The session's permissions change (a previously-allowed path may now
  return a different result).
- The tool itself signals invalidation (a tool can declare "my results
  are stale after X").

The hardest of these is detecting data changes. The harness typically
relies on TTLs (accept some staleness) or explicit invalidation hooks
(the tool calls a `cache.invalidate` API).

## Response Cache

For identical contexts and model configurations, the harness can return
the cached model response. This is rare in production (contexts rarely
repeat exactly) but useful for:

- **Eval runs** that replay the same trajectory.
- **Test fixtures** that must produce identical output.
- **Demo sessions** that should not burn tokens.

The response cache is keyed on the hash of the full context + model +
config. Any change invalidates.

```python
context_hash = hash(
    system_prompt,
    json.dumps(messages, sort_keys=True),
    json.dumps(tool_schemas, sort_keys=True),
    model_id,
    temperature,
    max_tokens,
)
if context_hash in response_cache:
    return response_cache[context_hash]

response = await call_model(...)
response_cache[context_hash] = response
```

Response caching must be **opt-in** for production agents (identical
contexts are usually a bug, not a feature).

## Cache Span Emission

Every cache hit emits a span:

```json
{
  "type": "cache_hit",
  "layer": "tool_result",
  "key_hash": "abc123",
  "saved_latency_ms": 850,
  "saved_cost_usd": 0.002
}
```

This makes the cache's value visible to the operator.

## Cache vs Memory

Caching is not memory. Memory (the `memory-rag` skill) is the agent's
durable knowledge store, written explicitly via tool calls. Caching is
the harness's transparent optimization for repeated work. The agent
does not know about the cache; it knows about memory.

## Pitfalls

1. **Caching side-effecting tools.** The harness caches a `deploy`
   result; the second call returns the cached success without
   deploying. Fix: never cache side-effecting tools.
2. **Prefix instability.** The harness reorders tool schemas every
   turn; cache misses every time. Fix: deterministic sort.
3. **Stale tool results.** The cache returns yesterday's search
   results. Fix: TTL per tool; explicit invalidation hooks.
4. **Response cache in production.** Identical contexts mask bugs (the
   agent should have varied its approach). Fix: opt-in only.
5. **No cache-hit spans.** The harness saves 30% on cost; nobody knows.
   Fix: emit a span for every hit.
6. **Cache that grows unbounded.** The cache fills memory. Fix:
   bounded LRU with TTL.
