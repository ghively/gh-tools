# Structured Outputs — Schema-Constrained Model Output Across Providers

> Last verified: 2026-07. Provider API parameter names and constrained-decoding backends churn fast — re-check the provider docs linked below before writing new integration code.

Free-text parsing of model output is a **bug class**: the model will eventually add a preamble, wrap the answer in markdown, rephrase your sentinel label, or emit smart quotes, and your regex breaks in production at 2am. Every serious provider and local inference stack now supports *constrained decoding* — the sampler literally cannot emit a token that violates your schema. Use it for anything code consumes.

## Two mechanisms, use both

1. **Constrained decoding** (provider-enforced): guarantees *syntactic* validity — output parses and matches the schema shape. Cannot guarantee the *content* is right.
2. **Validation + bounded repair** (client-enforced, Pydantic/zod): catches *semantic* invalidity — nonexistent IDs, business-rule violations, constraints the provider's schema subset can't express (min/max, regex patterns, cross-field rules).

Constrained decoding without validation trusts shape as meaning. Validation without constrained decoding wastes retries on malformed JSON the sampler could have prevented. Layer them.

## Provider matrix (July 2026)

| | Request shape | SDK helper | Guarantees | Notes |
|---|---|---|---|---|
| **Anthropic** | `output_config: {format: {type: "json_schema", schema: ...}}` on `messages.create` | `client.messages.parse(..., output_format=PydanticModel)` → `response.parsed_output`; TS: `zodOutputFormat(schema)` | Schema-conformant text block (except on `refusal` stop reason) | Old top-level `output_format` param is deprecated — use `output_config.format`. Assistant prefill is **removed** on current models (400) — structured outputs is the replacement. First request per schema pays a compile cost; 24h schema cache after |
| **Anthropic (tools)** | `strict: true` top-level on the tool definition | — | `tool_use.input` validates exactly against `input_schema` | Requires `additionalProperties: false` + `required` on the schema. Not compatible with programmatic tool calling |
| **OpenAI** | `response_format: {type: "json_schema", json_schema: {..., strict: true}}` (Chat Completions) / `text.format` (Responses API) | `client.responses.parse(...)` / `.beta.chat.completions.parse(...)` with Pydantic/Zod | Grammar-enforced conformance when `strict: true` | `{type: "json_object"}` (JSON mode) is legacy — valid JSON, no schema. Check the `refusal` field before reading parsed output. All fields must be `required`; express optionality as `"type": ["string", "null"]` |
| **Ollama** (local) | `format: <JSON schema object>` on `/api/chat` or `/api/generate` | Python: `format=Model.model_json_schema()`; JS: `format: zodToJsonSchema(schema)` | Grammar-constrained sampling against the schema | `format: "json"` (bare JSON mode) also exists — prefer the full schema. Pair with low temperature for extraction tasks |
| **vLLM** (local/served) | `structured_outputs` / `guided_json`, `guided_choice`, `guided_regex`, `guided_grammar` via the OpenAI-compatible server or `SamplingParams` | Works with any OpenAI-compatible client | Token masking — invalid tokens are unsampleable | Backend choice matters: **xgrammar** (default, JIT-compiled pushdown automata, fastest for most schemas), **outlines** (FSM-based; amortizes well when one complex schema is reused across thousands of requests), **lm-format-enforcer** (fallback). Also exposed by SGLang, TGI, llama.cpp (GBNF grammars) |

Primary docs: [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/).

### Anthropic specifics worth knowing

- **Schema subset:** supported — basic types, `enum`, `const`, `anyOf`/`allOf`, `$ref`, `additionalProperties: false` (required on every object), string formats (`date-time`, `email`, `uuid`, ...). **Not** supported — recursive schemas, numeric constraints (`minimum`/`maximum`), string length constraints. The Python/TS SDKs strip unsupported constraints from the wire schema and validate them client-side — which is exactly the two-layer model above, done for you.
- **Failure modes to handle:** `stop_reason: "refusal"` → output may not match schema, check before parsing. `stop_reason: "max_tokens"` → truncated JSON, raise `max_tokens` rather than retrying blind.
- Incompatible with citations (400).

### OpenAI specifics worth knowing

- `strict: true` is the production default; treat refusals as first-class (`message.refusal` populated instead of `content`).
- Same flat-subset restrictions (no `minLength`, all properties required, `additionalProperties: false`); the SDK `parse()` helpers translate Pydantic/Zod for you.
- Structured outputs also applies to function calling: `strict: true` inside each tool definition.

## Enum-constrained decisions

The single highest-leverage structured-outputs trick for agents: **when the model is making a decision your code branches on, constrain the answer to the branch set.**

```python
class RouteDecision(BaseModel):
    reasoning: str                    # let the model think BEFORE it commits
    route: Literal["billing", "technical", "account", "escalate_human"]
    confidence: Literal["high", "medium", "low"]
```

- The `route` field cannot be misspelled, hedged ("probably billing?"), or out-of-vocabulary — the sampler masks everything except the four literals.
- Put the `reasoning` field **before** the decision field: field order is generation order, so the model reasons before committing. A bare enum with no reasoning field measurably degrades decision quality on hard cases — you've forced an instant answer.
- `confidence: "low"` + code-side threshold = a clean escalation valve (route to a bigger model or a human) without letting the model freeform its way out.
- On vLLM, the degenerate case is even cheaper: `guided_choice=["billing", "technical", "account", "escalate_human"]` — one field, few tokens, near-zero parse risk.

This pattern is what makes the router pattern in `explicit-control-flow.md` deterministic: model picks from an enumerable set, code does the dispatch.

## The validation + bounded repair loop

Constrained decoding handles syntax. This loop handles semantics:

```python
from pydantic import BaseModel, ValidationError

MAX_REPAIRS = 2

def extract(client, prompt: str) -> Invoice:
    messages = [{"role": "user", "content": prompt}]
    last_error = None
    for attempt in range(1 + MAX_REPAIRS):
        resp = client.messages.parse(
            model=MODEL, max_tokens=2048,
            messages=messages, output_format=Invoice,   # constrained decoding layer
        )
        try:
            invoice = resp.parsed_output
            validate_business_rules(invoice)              # semantic layer:
            return invoice                                 #   IDs exist, dates sane, totals add up
        except (ValidationError, BusinessRuleError) as e:
            if str(e) == last_error:
                raise RepairStalled(e)                    # same error twice = no progress, stop
            last_error = str(e)
            messages += [
                {"role": "assistant", "content": resp.content},
                {"role": "user", "content":
                    f"Your output failed validation:\n{e}\n"
                    "Fix ONLY the named problems. Change nothing else."},
            ]
    raise ExtractionFailed(last_error)                    # escalate: bigger model, human, or DLQ
```

Rules that make this loop deterministic rather than a slot machine:

1. **Bound it.** 1–2 repairs. If two feedback rounds don't fix it, the third won't either — escalate.
2. **Feed back the *specific* error**, not "try again." Pydantic/zod error messages are written for exactly this.
3. **Detect stalls.** Identical error twice means the model can't or won't fix it; retrying burns money.
4. **Have a terminal path.** Escalation to a stronger model, a human queue, or a dead-letter record. Silent retry-forever is an unbounded loop with extra steps.
5. **Log every repair.** Repair rate per schema is your early-warning metric — a rising rate means the schema or prompt drifted from the task.

zod equivalent: `schema.safeParse(json)` → feed `result.error.issues` back; identical structure.

## Schema evolution

Schemas are API contracts between the model, your code, and often a queue of stored outputs. Evolve them like contracts:

- **Additive-optional is safe.** New fields must be optional-with-default (or nullable, on OpenAI strict mode) so old stored outputs still parse and old prompts still validate.
- **Renames and semantic changes are versioned.** `InvoiceV2`, not an in-place mutation. Carry a `schema_version` literal field in the output itself so consumers and stored records are self-describing.
- **Tolerant reader, strict writer.** Generation uses `additionalProperties: false` (providers require it); *consumers* of stored outputs should ignore unknown fields so you can roll schema versions forward without a flag day.
- **Migrate, don't branch.** When V2 lands, backfill or lazily upgrade stored V1 records with a pure function `v1_to_v2()`. Two live read paths forever is how pipelines rot.
- **Every schema change is an eval run.** Adding a field changes the generation task — a "harmless" new required field can tank quality on the old fields. Re-run the extraction eval set (see the `agent-evals` skill) before shipping.
- **Watch the compile cache.** Providers cache compiled schemas (Anthropic: ~24h) keyed on exact schema bytes; a schema that changes per-request (dynamic descriptions, injected enums that vary) pays compile latency every call. Keep schemas static; put per-request variation in the prompt.

## Pitfalls

1. **Over-constraining kills quality.** A 40-field schema with everything required forces the model to fill fields it has no evidence for — it will confabulate. Make genuinely-optional data optional/nullable, and give the model an explicit `"unknown"` enum member or null rather than forcing a guess.
2. **Decision field before reasoning field.** Generation order = field order. Decision-first schemas get you unreasoned answers with post-hoc rationalization.
3. **Parsing the text block when a `parse()` helper exists.** `json.loads(response.content[0].text)` works until a refusal or truncation; the SDK helpers handle those states.
4. **Assuming JSON mode = structured outputs.** `json_object` (OpenAI) / `format: "json"` (Ollama) guarantee parseable JSON, not *your* JSON. Legacy; don't reach for them in new code.
5. **Dynamic schemas defeating the grammar cache.** See schema evolution above — static schema, dynamic prompt.
6. **Schemas that are too narrow for the task.** A schema that enforces one correct answer but the question is ambiguous forces the model to guess. Fix: add an `"uncertain"` variant; this is a real signal, not noise.

## Function-Calling vs `response_format`

When the agent needs a structured artifact, you choose between two channels:

| Channel | How it works | When to use | Cost |
|---|---|---|---|
| **Function-calling (`tools`)** | The model emits a `tool_use` block; the harness dispatches a tool | The structure feeds into a downstream tool or side effect (deploy, search, insert). Only one producer per turn (the model). | 1 tool round-trip per structured output |
| **`response_format` / `structured_outputs`** | The model emits the structure inline as part of its response text (JSON inside `content`). No tool dispatch | The structure is the deliverable — a classification, an extraction, a routing decision. No tool call needed. | 0 round-trips (inline); cheaper |

**Decision rule:** if the structured output does not trigger a side effect,
use `response_format` — it's cheaper and faster. If the output triggers a
tool (the model says "deploy X" and the harness dispatches the deploy
tool), use function-calling — the tool output enters the conversation and
the model can respond to it.

**Crossover cases:** the model needs both reasoning and a structured output.
Options:

1. **Native thinking mode + structured output.** Anthropic's `thinking`
   blocks appear before the structured output. Reasoning tokens are not in
   the structure. Best of both worlds if the provider supports it.
2. **Separate calls.** First call: `response_format` for the reasoning
   text. Second call: `tools` for the side effect. Two calls, higher
   latency, but the reasoning is inspectable.
3. **Tag-based.** `<thinking>...</thinking><output>...</output>` in a
   single text response. Parse the tags. Works across all providers;
   fragile if the tag syntax leaks into the content.

**Structured outputs via grammars** (Guidance, Outlines, xgrammar, LMQL):
these guarantee the exact format at the token level, not just validation
post-hoc. Best for constrained-decoding use cases (form filling, codegen
with syntax guarantees). These libraries sit between the harness and the
provider, intercepting logit selection.

## Streaming + Structured Outputs

Structured outputs are typically delivered atomically (the full JSON
arrives when the model finishes generating). Streaming changes this:

**Partial JSON.** The harness can parse incomplete JSON as the model
generates it, showing the structure filling in field-by-field. This is
for UI feedback only — never dispatch a tool call or validate a schema
against partial output.

**Provider support:**
- Anthropic: `tool_use` fields stream incrementally via `input_json_delta`
  events. Structured outputs via `content_block_delta` for `text` blocks
  containing JSON. Parse partial JSON at the client.
- OpenAI: `response_format` with `stream: true` → partial JSON chunks.
  Function-calling tool arguments stream incrementally.
- Gemini: Structured output streaming via `GenerateContentResponse`.

**Refusal interactions:** a streaming structured output can begin and then
hit a refusal mid-stream. The partial output is invalid. The harness must
detect the refusal (via `stop_reason` or a special refusal event) and
discard the partial output, not attempt to validate it.

**Truncation interactions:** a `max_tokens` truncation mid-structure
produces invalid JSON. The harness detects the truncation (`stop_reason:
max_tokens`) and retries with higher `max_tokens` or summarizes.

## Replay Mechanics

A deterministic agent records every model call and tool call so it can be
replayed. The replay event log records:

```json
{"step": 0, "type": "model_call", "input": {"messages": [...], "tools": [...]}, "output": {"content": [...], "stop_reason": "tool_use", "usage": {...}}}
{"step": 1, "type": "tool_call", "tool": "search", "args": {"query": "..."}, "output": {"results": [...]}, "duration_ms": 120}
{"step": 2, "type": "model_call", "input": {...}, "output": {...}}
```

**Replay modes:**
1. **Post-hoc debugging:** Replay the exact trajectory to understand what
   the agent did and why.
2. **Replay-as-fixture:** Replay the model calls with recorded responses
   substituted (the harness never actually calls the model). This is the
   eval fixture — deterministic replay for CI.
3. **Counterfactual replay:** Change one tool result and replay to see
   what the agent *would have* done. Useful for "what if the search had
   returned different results?"
4. **Durable-execution replay:** Resume a durable run from the journal.
   See `durable-execution.md`.

**What to record per call:**
- Model call: `messages` (all context), `tools` (schemas), `model_id`,
  `temperature`, `response` (full), `stop_reason`, `usage`, `latency_ms`,
  `timestamp`.
- Tool call: `tool` name, `args`, `result`, `duration_ms`, `timestamp`,
  `idempotency_key`.

**Timestamp handling during replay:** For replay-as-fixture, substitute
the recorded timestamp (not `datetime.now()`). This keeps the replay
byte-identical to the original run and prevents timestamp-dependent
test flakiness.

## Concurrency Control for Agent State

When multiple sessions or replicas share the same durable state (e.g.,
the same `thread_id` in LangGraph), the harness must prevent concurrent
modification:

| Pattern | How | When |
|---|---|---|
| **Optimistic concurrency** | Write with a version/etag; on conflict, re-read and re-apply | Low-contention workloads |
| **Pessimistic locking** | Acquire a lock (Redis `SETNX`, Postgres `SELECT ... FOR UPDATE`) before modifying state | High-contention or critical-path writes |
| **Single-writer** | Only one replica writes to a given state key (Restate Virtual Objects pattern) | The simplest correct answer |
| **Last-writer-wins with merge** | Write the full new state; merge conflicts at read time with a conflict-resolution function | Append-only state (e.g., chat history) |

The simplest correct default is **single-writer**: each `session_id` or
`thread_id` routes to exactly one replica. The session store or LB pins
the ID to the replica. If the replica dies, another replica picks up
from the durable store.

**Replay + concurrency**: when replaying records and a concurrent write
occurred between the original run and the replay, the replay must either
fail (detect the version difference and abort) or be marked as a replay
(not a new write) in the audit log.
6. **Enum sets that grow without review.** A 60-member routing enum is a classification task the model will do badly; past ~10–15 branches, use hierarchical routing (coarse enum → per-branch fine enum) instead.
