# Review Panels

A review panel runs multiple independent reviewers or judges, then consolidates convergent and unique findings. The value is diversity of failure detection, not redundant agreement theater.

## When It Is Worth It

Use a panel for security-sensitive changes, complex logic, high-cost decisions, adversarial claims, or work where a single reviewer has known blind spots. Do not use it for trivial edits, pure formatting, or time-critical hotfixes where normal tests are enough.

### Cost Math

A panel of N reviewers costs roughly N full passes plus a consolidation pass. Before spinning one up, compare against the single-reviewer baseline:

```
panel_cost   ≈ N × (input_tokens + review_tokens) + consolidation
single_cost  ≈ 1 × (input_tokens + review_tokens)

worth_it_when: expected_cost_of_missed_bug  >  (panel_cost − single_cost)
```

A two-reviewer panel over a small diff is cheap insurance for a security-sensitive change. A five-reviewer panel over a 30k-token diff for a cosmetic refactor is waste. The decision is economic, not aesthetic: multiply fan-out by per-reviewer cost, and only pay it where the downside of a missed defect is larger than the markup.

## Pattern

1. Give each reviewer the same source material and scope.
2. Keep reviewers independent; do not let the second see the first's findings.
3. Ask for file:line or source-cited findings with severity.
4. Consolidate into convergent, unique, false-positive, and out-of-scope groups.
5. Fix convergent high-severity findings first.
6. Verify every accepted finding with tests, reproduction, or source evidence.

### Worked Walkthrough

Running a panel over a security-sensitive PR, step by step:

1. **Brief.** Hand every reviewer the identical diff plus the relevant source files. Each gets the same scope statement ("authorization and input handling only") and the same output contract ("cited file:line findings, severity per finding").
2. **Run independently.** Reviewer A (security lens) and Reviewer B (correctness lens) run in parallel, neither sees the other's output. A skeptic reviewer may be added for claims that need adversarial pressure.
3. **Collect artifacts.** Each reviewer writes findings to its own file (`review-a.md`, `review-b.md`) with citations. Prose-only or "looks fine" reports are rejected and re-requested with the citation requirement restated.
4. **Consolidate.** The consolidator builds the table, groups findings into convergent / unique / false-positive / out-of-scope, and assigns an action per row.
5. **Act + verify.** Convergent high-severity findings are fixed first; each fix gets a test or reproduction. Unique findings are reproduced before fixing; false-positives are recorded with a one-line reason so the noise does not recur.

The non-obvious step is #2: independence is what makes convergence meaningful. If Reviewer B sees A's findings, B will anchor on them, converge becomes agreement theater, and the diversity you paid for disappears.

## Panel Shapes

| Shape | Use |
|---|---|
| Two independent code reviewers | Complex PRs and bug-prone patches. |
| Diverse lenses | Security, correctness, UX, performance, maintainability. |
| Skeptic panel | Claims that need adversarial verification. |
| Judge panel | Subjective outputs where one LLM judge is too noisy. |

The value of a panel is **diversity of failure detection**, not redundant agreement. Two reviewers with the same prompt, same model, and same context will find the same bugs and miss the same bugs — that is agreement theater. To get real diversity: vary the lens (security vs correctness vs perf), vary the prompt framing, and keep reviewers independent so no reviewer sees another's output before filing.

### Reviewer Briefing Contract

Every reviewer on a panel receives the same briefing, regardless of lens:

| Element | Why it must be identical |
|---|---|
| Source material (diff/files) | Different inputs make findings incomparable |
| Scope statement | A reviewer told to look at "security" vs one told "correctness" must still share the same change boundary |
| Output contract | Cited file:line + severity, so consolidation is mechanical |
| Independence guarantee | No reviewer sees another's findings before filing |

What *differs* between reviewers is the lens (security / correctness / performance / UX) and, optionally, the prompt framing — that is where diversity comes from. Keep the inputs and output contract identical; vary only the lens. If you vary the inputs too, you are running separate reviews, not a panel, and convergence stops meaning anything.

## Consensus Thresholds

Convergence is a priority signal, not proof. Unique findings can be critical. A panel verdict is trustworthy when reviewers had enough context, used independent reasoning, cited evidence, and the consolidator verified the claims.

A practical thresholding scheme:

| Convergence | Severity floor | Default action |
|---|---|---|
| ≥2 reviewers, cited evidence | any | Fix (or explicitly accept the risk) |
| 1 reviewer, cited + reproduced | high | Fix after reproduction confirms |
| 1 reviewer, no reproduction | medium | Investigate; do not auto-fix |
| ≥2 reviewers, no citations | — | Treat as a lead, not a verdict; ask for evidence |

Note that "≥2 reviewers agree" without citations is weaker than "1 reviewer with a reproduced failing test." Convergence raises priority; evidence decides the fix. Unique findings from a well-briefed reviewer often beat a chorus of uncited agreement.

## Consolidation Table

| Finding | Reviewer A | Reviewer B | Severity | Action |
|---|---|---|---|---|
| Missing authorization check | #2 | #1 | High | Fix now |
| Slow query on large table | - | #4 | Medium | Reproduce, then decide |
| Future feature absent | #6 | - | Out of scope | Defer |

The consolidation step is where panels earn their cost. Group findings into four buckets — **convergent** (multiple reviewers, fix first), **unique** (one reviewer, verify independently), **false-positive** (reproduction fails, discard with reason), and **out-of-scope** (real but not this change, defer to a tracker). Every accepted finding gets a test, a reproduction, or a source citation before it is acted on; every rejected finding gets a one-line reason so the decision is auditable.

## Pitfalls

- Sequential reviews where later reviewers anchor on earlier output.
- Treating all panel comments as equally true.
- No consolidation table.
- No tests after fixes.
- Reviewers with identical prompts, models, and blind spots.
- Fixing only convergent findings and dropping unique ones that a single reviewer caught but happened to be critical.
- Filing false-positives silently instead of recording why they were rejected, so the same noise recurs next review.
