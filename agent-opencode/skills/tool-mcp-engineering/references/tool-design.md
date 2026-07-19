# Tool Design

Tools are the model's action interface. The model sees a name, description, parameters, and return content; design for that interface, not for your implementation internals.

The model never sees your code, your database, or your internal routing — only the tool's name, its description, the parameter schema, and whatever the tool returns. Every confusion the model exhibits is a confusion in that contract. Fix the contract, not the model: if it calls the wrong tool, the name or description misled it; if it passes bad args, the schema is unclear; if it mishandles the result, the return format buried the actionable part.

## Capability Paths

| Need | Surface |
|---|---|
| Existing command with instructions | Skill that teaches CLI usage. |
| Small deterministic logic | Skill backed by a script. |
| Existing third-party integration | Connect an existing MCP server. |
| Cross-client typed capability | Build an MCP server. |
| Marketplace bundle of skills/commands/hooks/assets | Full plugin. |

## Principles

1. **Name for user intent.** `find_customer` beats `run_sql_query_against_postgres`.
2. **Keep parameters flat and typed.** Avoid deeply nested objects and ambiguous unions.
3. **Descriptions are instructions.** Parameter descriptions should constrain format, defaults, and exclusions.
4. **Return model-readable next steps.** Do not dump raw JSON when the agent needs a summary and follow-up ID.
5. **Make errors explicit.** Return auth, validation, rate-limit, and retryability details in text the model can act on.
6. **Side effects must be idempotent.** Use idempotency keys, natural PUT semantics, or clear duplicate reporting.
7. **One tool, one task-level job.** Do not expose one generic mode-switching megatool unless the task really is generic probing.

## Before / After: Naming

Bad names describe the implementation; the model cannot tell when to use them.

| Bad (implementation-shaped) | Good (intent-shaped) | Why |
|---|---|---|
| `run_sql_query_against_postgres` | `find_customer` | Model knows the goal, not your DB |
| `execute_post_v2_users_endpoint` | `create_user` | Task-level, not route-level |
| `do_thing` | `reset_password` | Specific intent, searchable |
| `gateway_dispatcher` | `send_invoice_email` | Names the action and the artifact |

## Before / After: Parameters

Flat, typed, documented beats nested blobs.

Bad (nested, ambiguous):

```json
{
  "options": { "filter": { "type": "customer", "value": "?" }, "opts": ["?"] }
}
```

Good (flat, typed, bounded):

```json
{
  "customer_id": { "type": "string", "description": "Customer identifier, e.g. \"cus_123\"" },
  "status": { "type": "string", "enum": ["open", "closed"], "default": "open" },
  "limit": { "type": "integer", "minimum": 1, "maximum": 100, "default": 25 }
}
```

The model fills flat, described fields reliably. Nested optional blobs force it to guess structure, which is exactly where hallucinated arguments appear.

## Return Format Example

Bad: raw API body with 200 fields.

Good: "Created ticket ABC-123. Status: open. Use `get_ticket` with id `ABC-123` to check progress."

The good return does three things: states the outcome, gives a stable ID, and points at the next useful tool. That last part — the next-action hint — is what keeps a multi-step workflow moving without the model re-deriving the state machine each call.

## Error Format Example

Bad: `{"error": "fail"}` or a bare HTTP status with no body.

Good:

```
create_ticket failed.
reason: rate_limited
status: 429
retryable: true
retry_after_seconds: 30
hint: wait and retry with the same idempotency_key; duplicate creates are safe.
```

The good error tells the model three things it can act on: *what* went wrong (rate-limited), *whether* to retry (yes), and *how* (wait, reuse the idempotency key). Without retryability and idempotency guidance, the model either gives up or retries blindly and creates duplicates.

## Side-Effect Guard

Every write/delete/send/publish tool should have preview or dry-run behavior and clear confirmation gates. Tool policy belongs in `agent-safety`, but tool design must make safe operation possible.

The design responsibility splits cleanly: the *tool* must offer a preview/dry-run path and idempotency so safe operation is possible; the *policy* layer (sandbox, permissions, human approval) decides whether the tool may actually fire. A tool that cannot be operated safely is a tool policy cannot fully fix — so design the safe path first, then gate it. Concretely: a destructive tool should accept a `dry_run` flag (or be split into `preview_*` and `apply_*` tools), accept an idempotency key, and return a classified preview the policy layer can show before the apply.

### Idempotency in practice

An idempotent write is one the model can retry safely. Three patterns cover almost every case:

| Pattern | How it works | Example |
|---|---|---|
| Idempotency key | Caller passes a key; server de-dupes retries with the same key | `create_invoice(idempotency_key=..., ...)` |
| Natural PUT semantics | Identify the resource uniquely; repeated calls converge to the same state | `put_user(user_id=..., email=...)` |
| Duplicate reporting | Server detects a repeat and returns the existing artifact with `already_existed: true` | `create_ticket` returns the prior ticket instead of a second one |

Without one of these, a retried write creates duplicates and the model cannot tell whether the first call landed — which is exactly the failure that erodes trust in the tool surface.


