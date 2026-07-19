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
6. **Enum sets that grow without review.** A 60-member routing enum is a classification task the model will do badly; past ~10–15 branches, use hierarchical routing (coarse enum → per-branch fine enum) instead.
