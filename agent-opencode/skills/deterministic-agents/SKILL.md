---
name: deterministic-agents
description: "Making agent systems predictable, reproducible, and verifiable: structured outputs and schema-constrained decoding, explicit code-owned control flow, idempotent side effects, durable execution (Temporal/Inngest/Restate/LangGraph/Cloudflare/Step Functions), proof contracts for delegated work, and systematic workflow optimization. Use when an agent behaves differently run-to-run, retries cause duplicate side effects, free-text parsing breaks, or you need crash-safe long-running agent workflows. Does not cover when to choose a workflow vs an agent (see agent-design), framework selection (see framework-selection), or eval methodology (see agent-evals)."
---

# Deterministic Agents

LLMs are probabilistic; production systems must not be. This skill is the engineering discipline for squeezing nondeterminism out of agent systems until only the parts that *benefit* from model judgment remain probabilistic — and even those are constrained, bounded, and verified.

## When to Use

- An agent produces different results on identical inputs and you need to know why (and whether it matters).
- You're parsing model output with regex/string-splitting and it breaks weekly.
- Retries or crashes cause duplicate emails, duplicate tickets, double-charged API calls.
- An agent loop occasionally runs forever, or "reflects" itself into a spiral.
- A long-running agent dies mid-task and loses all progress.
- Sub-agents report "done" and you later discover nothing was done.
- An agent workflow works but costs too much or takes too long, and you want to optimize it without breaking it.

**Don't use for:** deciding whether a task should be a workflow or an agent at all (`agent-design` skill), picking LangGraph vs CrewAI vs the Claude Agent SDK (`framework-selection` skill), or building eval suites to measure quality (`agent-evals` skill — though determinism is what makes evals repeatable).

## The Determinism Doctrine

Four laws. Every reference file in this skill is an elaboration of one of them.

1. **The LLM decides as little as possible.** Every decision delegated to the model is a decision that can go differently next run. Model judgment is for the parts that genuinely need language understanding — classification of messy input, synthesis, code generation. Routing, sequencing, retry policy, and termination belong in code.
2. **Code owns the control flow.** The loop, the branch, the stop condition — these live in your program, not in the model's "judgment about whether to continue." An agent that decides its own termination will sometimes decide wrong.
3. **Every side effect is idempotent.** Agent actions run in an at-least-once world: retries, crashes, and replays are guaranteed at scale. Any tool that writes, sends, or charges must be safe to execute twice.
4. **Every claim is verified.** A model saying "tests pass" is a token sequence, not a test run. Success is established by machine-checkable evidence — exit codes, diffs, HTTP responses — never by self-report.

## Determinism Levers

Each lever, what class of failure it eliminates, and what it costs you.

| Lever | What it fixes | Cost |
|---|---|---|
| Schema-constrained output (JSON schema / grammar decoding) | Malformed output, parse failures, invented fields | Schema authoring; slight quality hit if schema fights the task; first-request compile latency |
| Enum-constrained decisions (`enum` / `guided_choice`) | Unparseable or out-of-vocabulary routing decisions | Must enumerate branches up front |
| Validation + bounded repair loop (Pydantic/zod) | Semantically invalid output that passes syntax | Extra calls on failure; needs an escalation path |
| Code-owned control flow (state machine / typed graph) | Runaway loops, skipped steps, order-dependent bugs | Upfront design; less "emergent" flexibility |
| Frozen plan (plan-then-execute) | Mid-run scope drift, plan mutation under pressure | Replanning requires an explicit, gated step |
| Hard stops (max iterations + token budget + wall clock) | Infinite loops, cost blowups | Legitimate long tasks need generous limits + resume |
| Idempotency keys + effect journal | Duplicate side effects on retry | Key plumbing in every effectful tool |
| Dry-run / plan-apply split | Destructive mistakes | Two-phase execution; preview can go stale |
| Durable execution (journal + replay) | Lost progress on crash; unsafe manual retries | Runtime dependency; workflow-code determinism rules |
| Proof contracts on delegated work | Fabricated or mistaken "done" reports | Verification step per task; slower handoffs |
| Result caching (exact-match) | Variance *and* cost on repeated identical calls | Staleness management; cache keying discipline |
| Pinned model versions/snapshots | Silent behavior drift when provider updates an alias | You must schedule migrations deliberately |
| Deterministic context assembly (sorted keys, stable ordering, no timestamps) | Run-to-run drift from context noise; cache misses | Discipline in prompt-building code |
| `temperature=0` / seeds | Reduces sampling variance only | **Does not give reproducibility** — see pitfalls #4; removed entirely on the newest Anthropic models |

**Order of application:** structure the output first (cheapest, biggest win), then take control flow into code, then make effects idempotent, then add durability, then verify claims, then optimize. That ordering is roughly the reference router below.

## The Minimum Bar for Production

Non-negotiables — an agent system that violates these is not "flexible," it's broken:

- **No free-text parsing of model decisions.** Anything code branches on comes out of a schema-constrained field or a tool call, never regex over prose.
- **No unbounded loops.** Every loop has an iteration cap AND a token/cost budget AND a wall-clock limit. Whichever trips first wins.
- **No side-effecting tool without an idempotency story.** Key, journal check, or natural idempotency (PUT-semantics) — pick one, document it in the tool.
- **No destructive action without a gate.** Delete/merge/publish/send-external/credential-change go through preview + explicit approval (human or a verifier with authority).
- **No accepting "done" without an artifact.** Diff, test output, log excerpt, HTTP response — something a program can check.

## Reference Router

| Load | When |
|---|---|
| `references/structured-outputs.md` | Getting schema-guaranteed JSON out of Anthropic / OpenAI / Ollama / vLLM; enum-constrained routing; validation+retry loops; evolving schemas without breaking consumers |
| `references/explicit-control-flow.md` | Choosing between LLM-as-function, prompt chains, routers, plan-then-execute, state machines (LangGraph StateGraph), bounded loops — what each buys and costs |
| `references/idempotency-and-replay.md` | Retries duplicating side effects; idempotency keys; effect journals; transactional outbox; dry-run modes; replayable logs; what temperature=0 and seeds actually guarantee; caching as a determinism tool |
| `references/durable-execution.md` | Crash-safe long-running agents; July-2026 comparison of Temporal, Inngest AgentKit, Restate, LangGraph checkpointers/Platform, Cloudflare Workflows/Durable Objects, AWS Step Functions; decision table by need |
| `references/proof-contracts.md` | Delegating work to sub-agents/workers; the diff/tests/evidence/report/decision contract; greenlight gates before destructive ops; multi-reviewer consolidation; never trusting self-reports |
| `references/workflow-optimization.md` | Systematic cost/latency/variance reduction: measure first, collapse steps into code, parallelize, cache (prompt + result), batch, right-size models, cut context |

## Pitfalls

1. **Reflection loops without stop conditions.** "Critique your answer and improve it" with no bound converges slowly, oscillates, or degrades — models will find fault forever if asked. Bound repair loops (2–3 iterations), require each iteration to fix a *named* defect from a validator, and exit on no-progress (same error twice = escalate, don't retry).
2. **Parsing free text is a bug class, not a bug.** Every `re.search(r"ANSWER:\s*(.*)", ...)` over model prose is a latent production incident. The model *will* eventually rephrase, add markdown, or translate the label. Constrained decoding exists on every major provider and local stack in 2026 — use it (`references/structured-outputs.md`).
3. **Non-idempotent retries.** The retry that saves you from a transient 500 is the same retry that sends the customer two emails. If a tool has side effects and no idempotency key, your reliability mechanism is a duplication mechanism (`references/idempotency-and-replay.md`).
4. **Assuming `temperature=0` = reproducible.** Greedy decoding still varies across runs on hosted APIs: floating-point non-associativity plus dynamic batching means your request's logits change depending on what other requests were in the batch; MoE routing and silent infra changes add more drift. It's variance *reduction*, not reproducibility — and the newest Anthropic models (Fable 5, Opus 4.7/4.8, Sonnet 5) reject `temperature` outright, so architecture, not sampling params, must carry your determinism. Bit-exact replay exists only for self-hosted inference with batch-invariant kernels, at real throughput cost.
5. **Hidden nondeterminism from context ordering.** Unsorted `dict`/`set` iteration when building prompts, retrieval results ordered by nondeterministic score ties, `datetime.now()` in system prompts, parallel tool results appended in completion order — each makes "identical" runs see different prompts. Different prompt bytes = different behavior *and* broken prompt caches. Sort keys, stabilize ordering, timestamp at the edges only.
6. **Trusting self-reported success.** "I've updated the config and restarted the service" is a plausible-sounding sentence the model generates whether or not it happened. Verify externally: read the file back, curl the endpoint, count the tests (`references/proof-contracts.md`).
7. **Letting the model own retry policy.** "If the tool fails, try again" in a prompt yields anywhere from zero to twelve retries with improvised arguments. Retry with backoff is five lines of code with exactly the semantics you wrote.
8. **Unpinned model aliases in reproducibility-sensitive paths.** `gpt-4o` / `claude-sonnet-latest`-style aliases move underneath you. Pin snapshots where behavior stability matters; treat model upgrades as deployments with eval runs (see the `agent-evals` skill), not as ambient drift.
9. **Validating syntax but not semantics.** Schema-valid JSON can still contain a `user_id` that doesn't exist or a date in the wrong decade. Constrained decoding guarantees shape; business-rule validation (and the bounded repair loop) guarantees meaning.
10. **Checkpointing ≠ durability.** Saving state after each step protects against losing *data*, not against duplicate execution, concurrent resumes of the same run, or partial side effects between checkpoints. Know which guarantee your stack actually provides (`references/durable-execution.md`).
