# Idempotency & Replay — Safe Retries, Effect Journals, and What "Deterministic" Really Means

> Last verified: 2026-07. Provider sampling-parameter behavior (which params exist, seed semantics) and batch-invariant inference support change frequently; the idempotency patterns themselves are evergreen.

Agent systems live in an **at-least-once world**. SDKs auto-retry 5xx/429s, durable-execution runtimes re-run failed steps, orchestrators re-dispatch crashed workers, and humans click "run again." If any tool in your agent's belt sends, writes, charges, or deletes, then *your reliability machinery is a duplication machinery* — unless every effect is idempotent.

## At-least-once vs exactly-once for agent actions

- **At-most-once** (fire, never retry): loses work on any transient failure. Almost never what you want.
- **At-least-once** (retry until acknowledged): the default everywhere — and it *will* duplicate effects.
- **Exactly-once delivery** does not exist in distributed systems. What exists is **exactly-once *processing***: at-least-once delivery + idempotent effects. That equation is the whole game.

Classify every tool at design time:

| Class | Examples | Retry policy |
|---|---|---|
| Pure / read-only | search, fetch, grep, compute | Retry freely; cache freely |
| Naturally idempotent | `PUT /config`, "set status = closed", upsert-by-key | Retry freely — same call twice = same end state |
| Effectful, dedupable | send email, create ticket, POST payment, publish message | Retry **only** with an idempotency key |
| Effectful, destructive | delete, merge, revoke, mass-update | Idempotency key **and** a gate (see `proof-contracts.md`) |

The tool schema should say which class it is — a one-line `"Idempotent: safe to retry"` / `"Side-effecting: requires idempotency_key"` in the description keeps both the model and the next engineer honest.

## Idempotency keys for side-effect tools

The Stripe-popularized pattern, applied to agent tools:

1. Caller supplies a unique key per *logical operation* (not per attempt).
2. Receiver records the key with the result of the first execution.
3. Same key again → return the recorded result, execute nothing.

**Where the key comes from matters.** Never let the model invent it — the model that retries a "failed" call will happily invent a *fresh* key, defeating the whole mechanism. Derive it deterministically in code from run identity + step identity:

```python
def tool_send_email(to: str, body: str, *, ctx: RunContext):
    key = f"{ctx.run_id}:{ctx.step_id}:send_email:{sha256(f'{to}|{body}')}"
    return email_api.send(to=to, body=body, idempotency_key=key)
```

- Same run + same step + same payload → same key → duplicate suppressed, whether the retry came from the SDK, the workflow engine, or a human.
- A *legitimately new* attempt (new run, changed payload) gets a new key and executes.
- If the downstream API supports idempotency keys (Stripe, most payment/messaging APIs), pass yours through. If it doesn't, implement the dedup on your side of the tool: **effect journal**.

## The effect journal

A dedup table your tool layer consults before executing anything effectful:

```sql
CREATE TABLE effect_journal (
  idempotency_key TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  args_hash TEXT NOT NULL,
  status TEXT NOT NULL,          -- 'in_progress' | 'succeeded' | 'failed'
  result JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

Execution protocol: `INSERT ... ON CONFLICT DO NOTHING` with `status='in_progress'` → if the insert won, execute the effect and update to `succeeded` with the result; if it lost, read the row — return the stored result if `succeeded`, wait/fail if `in_progress` (a concurrent attempt holds it; add a lease timeout for crashed holders).

The journal doubles as your **audit log of everything the agent actually did** — which is precisely the evidence layer `proof-contracts.md` builds on, and the record you diff against when a run is disputed.

## Transactional outbox for agent-triggered writes

When one agent step must update your database **and** notify the outside world (webhook, queue message, email), doing them as two separate calls means a crash between them leaves them inconsistent — forever, in whichever order you chose.

The outbox pattern: in **one local transaction**, write the domain change *and* an `outbox` row describing the external effect. A separate relay process reads the outbox and performs the external delivery (at-least-once — so the delivery itself carries an idempotency key, closing the loop).

```
BEGIN;
  UPDATE orders SET status='refunded' WHERE id=$1;
  INSERT INTO outbox(id, kind, payload) VALUES ($key, 'send_refund_email', $payload);
COMMIT;                      -- both or neither, atomically
-- relay: SELECT ... FROM outbox WHERE delivered_at IS NULL → deliver(idempotency_key=id) → mark
```

For agents this means: the *tool* writes intent transactionally; *infrastructure* performs the external effect. The model can crash, retry, or be replayed at any point without producing a state where the DB says refunded but no email ever goes out (or two do).

## Dry-run modes and the plan/apply split

Every destructive or bulk tool should take `dry_run: bool` and return **exactly what it would do** — the resolved target list, the diff, the count — without doing it. Then structure the flow as plan → gate → apply (Terraform semantics):

1. Agent calls tool with `dry_run=true` → gets a manifest of intended effects.
2. Manifest is validated by code (counts within bounds? protected resources excluded?) and/or approved by a human — see the greenlight gates in `proof-contracts.md`.
3. Apply executes **the manifest**, not a re-derivation — re-deriving at apply time means the thing approved and the thing executed can differ. Stamp the manifest with a hash; apply refuses a stale hash if the world changed in between.

This converts "the model decided to delete things" into "the model *proposed* deletions; code and/or a human authorized this exact list."

## Replayable event logs

Record every LLM call and tool call — full request (model, params, messages), full response, timing, token usage — keyed by `run_id`/`step_id`. This is table stakes for determinism work because it enables:

- **Post-hoc debugging** of "why did run 4182 email the wrong customer" by inspecting exactly what the model saw and said — not by trying to reproduce it (you often can't; see below).
- **Replay-as-fixture:** re-execute the pipeline with recorded LLM responses substituted for live calls. Your control flow, parsing, validation, and effect logic become deterministically testable, offline, free. This is how you regression-test an agent *harness* independently of the model.
- **Counterfactual replay:** re-run recorded inputs against a new model/prompt version and diff the outputs — the input side of an eval run (see the `agent-evals` skill).
- **Durable-execution replay:** journaling runtimes (Temporal/Restate/etc.) do exactly this internally; the recorded step result is what makes crash-recovery skip completed LLM calls instead of re-charging you for them (`durable-execution.md`).

Redact secrets at write time; logs of prompts are logs of whatever was in the prompts.

## Seeds, temperature=0, and the real limits

What sampling controls actually buy you, precisely:

- **`temperature=0` (greedy decoding) reduces variance; it does not give reproducibility.** On hosted APIs the dominant cause is not "hidden randomness" but *floating-point non-associativity meeting dynamic batching*: your request's matmuls/reductions get tiled differently depending on which other requests share the batch, the last-bit logit drift occasionally flips a near-tie, and one flipped token cascades into a different completion. MoE models add expert-routing sensitivity on top.
- **Seeds are best-effort.** OpenAI's `seed` parameter + `system_fingerprint` explicitly promise only "mostly consistent, same backend config" — the fingerprint changes when infra does. Anthropic's newest models (Fable 5, Opus 4.7/4.8, Sonnet 5) **removed `temperature`/`top_p`/`top_k` entirely** (400 if sent) — a clear signal: don't build determinism on sampling params.
- **Bit-exact reproducibility exists only where you control inference:** batch-invariant kernels (pioneered by Thinking Machines' "Defeating Nondeterminism" work, since shipping in [vLLM](https://docs.vllm.ai/) and SGLang as batch-invariant options) give bit-identical outputs across runs — at a real throughput cost (tens of percent). Reserve it for cases that justify it: eval reproducibility, audit/compliance replay, debugging heisenbugs.
- **Model aliases drift.** `*-latest` aliases and even "stable" endpoints get silent infra updates. Pin dated snapshots where behavior stability matters, and treat model bumps as deployments with eval gates.

**Design consequence:** never build correctness on "the model will say the same thing next time." Build it on schemas (output can't be malformed), code-owned flow (order can't vary), idempotency (repeats can't hurt), and recorded logs (the past is inspectable). Sampling determinism is a nice-to-have on top, not a foundation.

## Caching as a determinism AND cost tool

Two different caches, often confused:

| | Provider prompt cache | Result cache (yours) |
|---|---|---|
| What's cached | Attention KV state of a prompt *prefix* | Final output of a full call |
| Effect on output | **None** — generation still runs, still varies | Total: identical input → byte-identical output |
| Wins | ~90% input-cost reduction + latency on the cached span | 100% of cost/latency on hits; variance → zero |
| Governed by | Prefix stability (see `workflow-optimization.md`) | Your key: `hash(model_snapshot, params, canonical_prompt, schema_version)` |

The result cache is the underrated determinism lever: for pure calls (classify/extract/score — pattern 1 in `explicit-control-flow.md`), an exact-match cache makes the *system* deterministic on repeated inputs even though the model isn't — the first answer becomes the pinned answer. Include the model snapshot and schema version in the key so upgrades naturally invalidate; give entries a TTL matched to how fast the task's ground truth drifts; log the hit rate (it's also your duplicate-work detector).

## Pitfalls

1. **Model-invented idempotency keys.** The retrying model invents a fresh key and the dedup does nothing. Keys are derived in code from run/step identity — the model never sees them.
2. **Key per attempt instead of per operation.** Same bug, your fault instead of the model's: putting `attempt_number` or a timestamp into the key derivation.
3. **Retrying a timeout as if it failed.** A timed-out effectful call may have *succeeded* downstream. Without a key/journal, "retry on timeout" is the classic double-send. With one, it's safe — that's the point.
4. **Journal write after effect execution.** Crash between effect and journal = replay re-executes. Reserve the key (`in_progress`) *before* executing; that's why the protocol above is insert-first.
5. **Dry-run and apply that re-derive independently.** The approved preview and the executed action must be the same artifact (manifest + hash), or the gate certifies nothing.
6. **`temperature=0` in the compliance doc.** Writing "outputs are deterministic (temperature=0)" in a design review is a false claim on hosted inference; auditors and incident reviews will eventually notice. Say "variance-minimized, fully logged, replayable" — and make it true with the event log.
7. **Caching effectful calls.** Result caches are for pure calls only. A cached "success" for `send_email` means the second logical send silently never happens — that's the effect *journal*'s job, which looks similar but has opposite semantics (suppress re-execution of the *same* operation, not reuse across operations).
