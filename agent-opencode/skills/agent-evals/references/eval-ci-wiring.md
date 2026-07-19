# Running Evals in CI

Designing an eval and *running* it in CI are two different engineering problems. The `references/eval-taxonomy.md` and `references/golden-suites.md` files own what a good case is; this file owns what happens when that case runs on every push and PR — where nondeterminism, cost, secrets, and gating policy decide whether the suite is a trusted merge gate or a flaky tax everyone learns to ignore. A perfectly designed suite wired into CI badly is worse than no suite: it trains the team to click "re-run" until green.

The governing rule: **CI must be able to tell a real regression from noise, and it must cost less than the thing it protects.** Everything below serves those two constraints.

## The CI Eval Pyramid

Not every eval belongs on every push. Order cases by cost and determinism, and run the cheap deterministic tiers always, the expensive model-judged tiers rarely and under a budget.

| Tier | What it checks | Determinism | Cost | Runs |
|---|---|---|---|---|
| 1. Structural | File layout, schema shape, config↔code wiring, contract inventory | Fully deterministic | Free (no model) | Every push, always-on, blocks merge |
| 2. LLM-free assertions | Recorded-trajectory replay, `must_call_tool`/`must_not_execute` against a fixed transcript, output-schema validation | Fully deterministic | Free (replay, no live model) | Every push, blocks merge |
| 3. Model-judged (deterministic-gated) | Governance refusals, tool-arg correctness on a *live* model with a hard pass/fail rubric | Nondeterministic; mitigated | Metered (input+output tokens) | PR smoke subset; full on release branch |
| 4. Model-judged (subjective) | Helpfulness, tone, rubric fit via calibrated LLM judge | Nondeterministic; noisy | Highest (judge tokens on top of run tokens) | Nightly / candidate-change only |

The pyramid mirrors the classic test pyramid, but the cost axis is steeper: tier 1 is free, tier 4 can cost dollars per case. **Push as much coverage down the pyramid as possible.** A governance refusal you can assert against a recorded transcript (tier 2) should never be paid for as a live judged call (tier 3). Move a case up only when the lower tier genuinely cannot express the check — subjective quality is the only thing that truly needs tier 4.

## Handling LLM Nondeterminism in CI

Live model calls (tiers 3-4) are not reproducible the way a unit test is. The same case can pass at 11:00 and fail at 11:05 with no code change. CI must absorb that variance *without* absorbing real regressions along with it.

### Pin what the provider lets you pin

| Lever | Effect | Caveat |
|---|---|---|
| `temperature: 0` | Removes most sampling variance | Not zero variance — kernels, batching, and model updates still drift output |
| Seed (where supported) | Reproducible sampling for a fixed model version | A silent model-version bump invalidates the seed; pin the version too |
| Pinned model version/snapshot | Removes provider-side model drift | Requires a deliberate bump + re-baseline when the snapshot retires |
| Fixed prompt + fixtures | Removes input drift | The eval prompt must be the *deployed* prompt path, not a copy that rots |

Pinning reduces variance; it does not eliminate it. Design the gate to tolerate the residue.

### Retry-with-quorum, never silent retry

A flaky *judge* call (the model that scores, or a governance case near a decision boundary) can be retried — but only as an explicit quorum, logged, with a rule that fails closed:

- Run the judged case `N` times (e.g. 3). Require a **quorum** (e.g. 2 of 3 agree on pass) to call it a pass. A split decision is a *fail*, not a coin-flip re-run.
- Log every attempt and the quorum outcome. The CI log must show "2/3 pass → PASS", never a silent second attempt that overwrites the first.
- **Governance cases fail closed:** any single "executed the destructive action" result fails the case regardless of quorum. You do not get to average away a safety breach.

The anti-pattern is `retry_until_green` — re-running a failing case until it happens to pass, then reporting green. That masks exactly the regression the suite exists to catch. A retry that changes the verdict without being recorded is a lie told to the merge button.

### Quarantine lanes for known-flaky cases

When a case is genuinely flaky (near a judge decision boundary, timing-sensitive, dependent on an unstable fixture), quarantine it — do not delete it and do not leave it silently failing the gate:

- Move it to a `quarantine` lane that **runs but does not block merge**, exactly the `quarantine` state in `references/eval-taxonomy.md`'s case lifecycle.
- Every quarantined case carries an **owner and a deadline**, like an open bug. It reports in nightly output so it stays visible.
- A quarantine lane is a hospital, not a graveyard. Sweep it on a cadence: fix the flake and return the case to the blocking gate, or delete it deliberately with a reason. A case that has sat in quarantine for two months is protecting nothing.

## Judge-Call Cost Budgets Per CI Run

Tiers 3-4 spend real money on every run. Without a per-run cap, a fan-out bug or a retry storm turns one PR into a four-figure bill. Wire the same discipline the `model-selection` skill applies to production runs — see that skill's `references/cost-tracking.md` — into the CI job itself.

| Control | Setting | Behavior on breach |
|---|---|---|
| Per-run hard token cap | `max_tokens_per_ci_run` | Abort the eval job, mark it failed (not passed), surface the cap in the log |
| Per-run hard dollar cap | `max_usd_per_ci_run` | Same — a job that would exceed budget fails loudly, never silently truncates coverage |
| Per-case timeout | `timeout_seconds` (from the case) | Kill the case, record a failure artifact, do not hang the runner |
| Quorum multiplier awareness | `N × case_count × avg_tokens` | Budget must account for retry-with-quorum fan-out, or the cap trips on normal runs |

The cap must **fail the job**, not silently drop cases to fit the budget. A run that quietly evaluated 40 of 60 cases because it ran out of budget and then reported green is a false pass — the 20 unrun cases are exactly where the regression hides.

### Sampling strategy: match run scope to branch stakes

| Trigger | Scope | Rationale |
|---|---|---|
| PR push | Tier 1-2 full + tier 3 **smoke subset** (governance + one case per write-capable tool) | Fast, cheap, cost-bounded; catches the breaks that must never merge |
| Merge to release branch | Tier 1-3 **full suite** | The release is the gate the doctrine cares about; pay for full coverage here |
| Nightly scheduled | Tier 1-4 **full sweep**, including subjective judged cases | Catches drift that no single PR triggered; not on the merge path, so latency is free |
| Manual dispatch | Any tier, operator-chosen | Re-baselining, model-swap canaries, incident investigation |

Choose the smoke subset deliberately: every governance case, one capability case per write-capable or brittle tool, and any regression case for an incident that recurred. The smoke subset is not "the first 10 cases" — it is the cases whose failure must block a merge even under a tight PR budget.

## Fixture and Cassette Caching

Structural and LLM-free tiers get their determinism from **replay**: a recorded model response (a "cassette") played back instead of a live call. This is the mechanism that makes tier 2 free and hermetic. It is also a loaded gun.

| Replay is valid when | Replay lies when |
|---|---|
| Testing the assertion/scorer logic itself (does `must_call_tool` fire on this recorded trajectory?) | You changed the prompt or model — the cassette is the *old* behavior, so a green replay proves nothing about the new agent |
| Regressing a known past failure whose transcript already exists | The tool schema changed — the recorded tool call no longer matches the live surface |
| Making CI fast, hermetic, and cost-free for behavior that is already frozen | The fixture drifted from production data and the recorded response no longer reflects reality |

The rule: **replay proves the recorded trajectory still passes your assertions; it can never tell you how a changed agent would respond.** This is the `transcript-replay vs live simulation` split from `references/golden-suites.md`, applied to CI. The correct pattern is to live-run on prompt/model/tool changes (tier 3), archive the resulting transcripts, and replay them as fast deterministic regressions (tier 2) on every subsequent push — re-recording deliberately whenever the surface under test changes. A cassette that outlives the behavior it recorded is a green light wired to nothing.

## Gating Strategy

Not every tier blocks merge. Map each eval category to a gate action so the merge button means something precise.

| Eval category | Tier | Gate action | Why |
|---|---|---|---|
| Governance (refusal, approval, destructive-op) | 2-3 | **Block merge** | Safety-critical, fails closed; a governance regression must never reach main |
| Capability — write-capable tools | 2-3 (smoke) | **Block merge** | A broken write path is a production incident waiting to ship |
| Regression cases | 2 | **Block merge** | The incident already happened once; re-shipping it is unacceptable |
| Output-schema / structural contract | 1-2 | **Block merge** | Downstream code depends on the shape; free to check, so always check |
| Capability — read-only / low-risk | 3 | **Warn** on PR, **block** on release | Cost-bounded on PRs; full enforcement where it matters |
| Subjective quality (judge-scored) | 4 | **Nightly-only, warn** | Noisy; gate on a pre-declared delta, never a single-run number |

A "warn" gate posts a status but does not block; a "block" gate fails the required check. The failure mode to avoid is treating every tier as blocking — that makes the noisy tier 4 flakiness block merges, and the team responds by disabling the whole suite. Gate hard on the deterministic, fail-closed tiers; gate soft on the subjective ones.

## Secrets and Keys Hygiene in CI Eval Runs

A CI eval run holds a live provider API key — often with real spend authority. Treat the eval job as a privileged surface:

1. **Scoped keys, not the org root key.** Use a CI-specific key with its own budget cap (belt-and-suspenders with the per-run dollar cap) and the narrowest model/route allowlist the suite needs.
2. **Secrets from the CI secret store, never the repo.** No key in a fixture, a cassette, a committed `.env`, or a workflow file. The secret-scan job in this repo's own CI (`gitleaks` over the working tree) exists precisely to catch this class of leak.
3. **Redact model I/O in CI logs.** A judged case echoes prompts and responses; a governance case may include a synthetic secret as bait. Scrub before the transcript hits the Actions log — the same redaction discipline the `agent-deployment` skill's observability reference applies to production spans.
4. **Fork PRs do not get secrets.** A pull request from a fork must not receive the eval key, or an attacker exfiltrates it by editing the eval prompt. Run tiers 1-2 (no key needed) on fork PRs; defer tier 3-4 to a maintainer-triggered run after review.
5. **Rotate on exposure, and assume exposure on any log leak.** A key that appeared in a public Actions log is burned, cap or no cap.

## Cost Attribution of CI Eval Spend

CI eval spend is real spend and belongs in the same ledger as production, tagged so it does not masquerade as product usage. Wire it through the model of the `model-selection` skill's `references/cost-tracking.md`: tag every CI judged call with `budget_owner = ci`, the branch, the PR number, and the tier. Then the monthly review (see that file's *Cost governance* section) can answer "what did the eval suite itself cost, and is it earning that spend?" — the pitfall of an eval suite that costs more than the feature it guards is only visible if CI spend is attributed, not buried in a shared total.

## Worked Example: This Repository's Own CI

This marketplace dogfoods a golden-contract gate at **tier 1 — fully deterministic, zero LLM cost** — on its own plugins. It is a smaller surface than a full agent trajectory suite (structural contracts, not model behavior), but the CI shape is identical, and it is a complete working reference for tiers 1-2.

### The runner: `scripts/run-plugin-evals.py`

Each plugin may pin an integration contract at `plugins/<name>/evals/golden/plugin-contract.json`. The runner (stdlib only, no model, no network) loads each contract and runs five deterministic check families against the plugin on disk:

- **`check_skills`** — every listed skill has a `SKILL.md`; with `skills_complete`, the listed set must *equal* the on-disk set (a closed-world inventory — an unlisted extra skill and a missing one both fail).
- **`check_command_routing`** — with `routing_complete` (default), every `commands/*.md` must have a contract entry, and each command file must still contain the ``loads``/``delegates_to``/``mentions`` strings the contract pins (routing drift = fail).
- **`check_trigger_vocabulary`** — a skill's frontmatter `description` must still carry its trigger terms and its `must_defer` sibling references, so it does not silently stop activating.
- **`check_subagents`** — a contracted read-only subagent must declare a `tools:` line and must not hold `Write`/`Edit`/`MultiEdit`/`NotebookEdit`/`Bash` (least-privilege), and must not gain a forbidden tool.
- **`check_safety_floor`** — actually *executes* each plugin's PreToolUse hook scripts against `never_run_smoke` and `routine_smoke` events, asserting the floor still denies what must never run and does not false-positive on routine operations.

Any violation appends to `failures`, prints a diagnosis, and exits non-zero. The doctrine's "fix the plugin or edit the contract deliberately, never both silently" is the exit code.

### The gate: `.github/workflows/validate.yml`

The `self-evals` job runs `python3 scripts/run-plugin-evals.py` on every push and PR. A contract violation fails the required check and blocks merge — doctrine #1 (no change ships without its golden suite passing) made executable. The same workflow runs the structural validator, the skills-catalog freshness check, the safety-hook floor tests (a second, unit-test view of the same hooks the eval runner smoke-tests), a `gitleaks` secret scan of the working tree, and a syntax sweep. Every one of these is tier 1: deterministic, free, always-on, blocking.

**Why this is a real gate and not theater:** the checks are closed-world (the `skills_complete`/`routing_complete` flags fail on *additions* the contract did not authorize, not just deletions), they execute the actual safety hooks rather than trusting their presence, and they cost nothing per run — so there is no budget pressure to sample or skip. It runs the full suite on every push because it can afford to.

### What the next tier up would add — and cost

The repo gate stops at structural contracts because its "agents" are skills and hooks, not live model trajectories. A product agent suite adds tiers 3-4 on top of this exact skeleton:

- **Tier 3 (model-judged, gated):** replace "does the contract file pin `must_call_tool`?" with "does the *live agent*, given the case prompt, actually call the tool and refuse the destructive one?" This needs a provider key, a per-run budget cap, `temperature: 0` + a pinned model snapshot, and retry-with-quorum on the boundary cases. Rough order of magnitude: a 40-case PR smoke subset at a value-tier model, a few thousand tokens per case, lands in the low tens of cents per run — cheap enough to gate every PR. **> Last verified: 2026-07 — token prices move; recompute against the current `model-selection` `references/task-model-matrix-cloud.md` before quoting a figure.**
- **Tier 4 (subjective, nightly):** add a calibrated LLM judge scoring helpfulness/rubric-fit over the full suite, with a panel for high-impact subjective calls. This multiplies token cost (run tokens + judge tokens, times the panel size) and is why it lives on the nightly sweep, gated on a pre-declared delta, never on the PR merge path.

The migration is additive: keep the free deterministic tiers exactly as they are (they never stop earning their keep), and layer the metered tiers on top with their own budget and gating policy. Start where this repo starts — a stable case input, machine-readable assertions, and CI failure on regression — then add cost only when a check genuinely needs a live model to express it.

## Pitfalls

1. **Silent retry masking a regression.** Re-running a failing judged case until it passes, then reporting green, hides the exact break the suite exists to catch. *Fix:* retry only as a logged quorum (2-of-3), treat a split as a fail, and fail governance cases closed on any single breach.
2. **Judge drift between CI and prod.** The CI judge model/version silently diverges from the one scoring production, so CI passes cases prod would fail (or vice versa). *Fix:* pin the judge model+version, run the same judge config path in CI and prod, and re-baseline deliberately when either moves.
3. **An eval suite that costs more than the feature.** Unbounded judged cases on every push can out-spend the product they protect. *Fix:* per-run token/dollar caps that fail the job, push coverage down the pyramid, sample tier 3 on PRs, and attribute CI spend (`budget_owner = ci`) so the cost is visible in the monthly review.
4. **The flaky-quarantine graveyard.** Cases dumped into quarantine to make CI green, then never fixed, quietly erode coverage. *Fix:* every quarantined case gets an owner and a deadline, reports in nightly output, and is swept on a cadence — fixed back into the gate or deleted with a reason.
5. **PR-smoke passing while nightly reds are ignored.** The full nightly sweep goes red for weeks, but because it does not block merges, nobody looks — and a real regression ships. *Fix:* route nightly failures to the owning team as a paging alert, not a dashboard nobody reads; a red nightly is an open incident with an owner, not decoration.
6. **A cassette that outlived its behavior.** Replaying a recorded response after the prompt, model, or tool schema changed makes CI green while proving nothing about the new agent. *Fix:* replay only frozen behavior; live-run and re-record whenever the surface under test changes; treat a stale cassette like a stale mock.
7. **The cap that silently drops cases.** A per-run budget that truncates coverage to fit and then reports green turns the safety net into a false pass. *Fix:* the cap fails the job loudly; a run that could not afford full coverage is a failed run, not a passed one.
8. **The eval prompt path that rots away from prod.** CI evaluates a copied prompt/config that has drifted from what deployment actually runs, so a green suite guards a fiction. *Fix:* run evals from the same config path used in deployment (the `agent-evals` doctrine), and add a check that the eval entrypoint imports the shipped prompt, not a fixture copy.
