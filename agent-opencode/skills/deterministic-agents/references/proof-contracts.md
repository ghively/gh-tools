# Proof Contracts — Machine-Checkable Evidence for Every Delegated Task

The single most important rule in multi-agent and autonomous work: **a subagent's
"done" is a hypothesis, not a fact.** Proof contracts turn that hypothesis into
something code can check. This file defines the contract format, the verification
gates that consume it, and the consolidation pattern for multiple independent
verifiers.

## The core doctrine

1. **Every dispatched task states its proof contract BEFORE dispatch.** "The
   artifact this task must produce is X." If you can't name the artifact, the
   task is under-specified — fix that first.
2. **Reject "done" responses that don't carry the artifact.** No diff, no test
   log, no evidence → the task is not done, regardless of what the worker says.
3. **The parent owns the contracts between modules.** Workers own their
   individual files; the orchestrator verifies the bridges. Delegated work is
   assembled, then *independently* verified — never accepted on self-report.
4. **Destructive operations gate on verified preview, not on worker confidence.**

## Proof contract format

Every delegated/autonomous task must return **at least one** of these artifact
types, declared up front:

| Type | Artifact | Machine check |
|---|---|---|
| `diff` | git diff / patch of every change | `git diff --stat` non-empty; applies cleanly; touches only declared paths |
| `tests` | test-run output: passed/failed counts + log | exit code 0; pass count ≥ baseline; failures enumerated, not summarized away |
| `evidence` | command output, log excerpt, screenshot, HTTP response | re-runnable command included; parent re-runs it and compares |
| `report` | markdown findings with `file:line` citations | every claim cites a location; spot-check N citations |
| `decision` | recommendation + rejected alternatives + kill criterion | kill criterion is falsifiable; inputs cited |

Rules that make the format work:

- **Declare the type in the dispatch prompt.** "Return a `tests` artifact: full
  pytest output, not a summary." Workers optimize for what's asked; if you ask
  for prose, you get prose.
- **Artifacts must be re-runnable or re-checkable.** "All tests pass" is not an
  artifact. `pytest -q 2>&1 | tail -20` output plus the command to reproduce it is.
- **One artifact per phase.** A phase is a unit of work that produces one
  verifiable artifact. If a phase can't name its artifact, merge it into an
  adjacent phase or cut it.
- **Prefer fewer, larger phases.** Five 30-minute phases beat fifteen 10-minute
  ones — orchestration overhead and hand-off loss grow with phase count.

### Dispatch template

```text
Task: <one-sentence goal>
Scope: <files/systems the worker may touch; everything else is out of bounds>
Proof contract: <diff|tests|evidence|report|decision> — <exactly what the
  artifact must contain, e.g. "pytest output showing >= 214 passed, 0 failed,
  plus the diff limited to src/parsers/">
Constraints: <size limits, deadline, "do not modify migrations", ...>
On failure: return a report of what blocked you and what you tried —
  a blocked report with evidence beats a fabricated success.
```

The "on failure" clause matters: workers that believe only success is acceptable
will report success. Make honest failure the cheap path.

## Never trust subagent self-reported success

The canonical failure (from a real July 2026 audit of a 49-tool agent system
built with parallel subagents): a subagent dispatched to fix 6 bugs reported
"container rebuilt and verified healthy, tool count 66, all changes committed."
Every statement was *true* — and the system was still broken. Independent
testing of all tools against live services found endpoints that 404'd, response
shapes that crashed, and tools the subagent never invoked. Its "verification"
was cherry-picked to the tools it had touched.

Structural reasons self-reports fail (not malice — incentives and blind spots):

- **Workers test what they changed**, never the neighboring code their change
  broke.
- **Surface metrics pass while behavior fails**: health endpoint 200, import
  succeeds, tool count correct — none of these exercise real code paths.
- **"Verified working" without attached output** usually means "I believe it
  works."
- **Auth paths are especially unreliable**: the fix can be correct while the
  credential is stale; only an independent live call reveals it.
- **Parallel workers break shared contracts**: each writes its file in
  isolation, assuming config properties / registry entries / prompt references
  that no one actually created. The bridges between modules belong to the
  parent.

**Enforcement**: after any delegated work, the parent runs its own verification
— a functional script that exercises *every* affected surface (not just the
changed ones) against the real system, checked by exit codes / assertions, not
by reading the worker's prose. Full verification-gate methodology (contract
surfaces: config↔code, registry↔source, import↔syntax, agent↔tool, runtime
path) lives in the `agent-evals` skill — cross-reference it; don't duplicate it
here. The deterministic-agents contribution is the *contract*: the dispatch
must name the artifact, and the gate must be code.

## Greenlight gates before destructive or external operations

Certain action classes never proceed on agent judgment alone. Define the list
once, in code or config, and block on explicit human (or higher-authority
policy) approval:

- **merge** — merging to a protected branch
- **publish** — releasing packages, deploying to production, posting publicly
- **destructive** — delete/archive/overwrite of live resources, dropping data,
  force-push
- **external-send** — emails, payments, API writes to third parties
- **credential-change** — rotating, granting, or revoking secrets and access

Gate mechanics:

1. **State the action plainly and wait.** "About to archive 14 repositories:
   <list>. Proceed?" Not buried in a paragraph; a stop, not a notification.
2. **Batch destructive operations require a preview artifact first.** The
   worker must produce (a) the classified list of targets and (b) an exclusion
   list verified against known-active resources, *as an artifact the gate
   checks*, before execution is even schedulable. (Real incident: a batch repo
   cleanup archived two live production sites because no preview/exclusion step
   was enforced — the agent's classification was wrong and nothing checked it.)
3. **Enforce in code, not in prompt.** A sentence in the system prompt
   ("always ask before deleting") is a suggestion the model can weight against
   other instructions. A PreToolUse hook (Claude Code), an HITL interrupt node
   (LangGraph `interrupt()`), a policy check in the tool implementation, or an
   allowlist in the executor is a guarantee. See the `agent-safety` skill for
   the full permission-model treatment.
4. **The gate consumes the proof contract.** Approval is granted against the
   preview artifact, and execution must match the approved artifact —
   if the target list changed since approval, the gate re-fires.

## Multi-verifier consolidation (MoA review)

For high-stakes artifacts (security-sensitive diffs, complex logic), one
verifier is a single point of failure. Dispatch **two or more independent
reviewers in parallel** — different models or different vendors, with an
*identical* review prompt — then consolidate mechanically:

1. Give both reviewers the same prompt: spec location, files in scope, focus
   areas, required output format (`file:line`, severity, one-line description).
2. Run them in parallel, not sequentially (independence is the point; a second
   reviewer that sees the first's findings anchors on them).
3. Build a consolidation table:

```text
| # | Finding                          | Reviewer A | Reviewer B | Severity | Action |
|---|----------------------------------|------------|------------|----------|--------|
| 1 | remove_token() never invalidates | #4         | #1         | High     | Fix now |
| 2 | Registry writes non-atomic       | #3         | #2         | High     | Fix now |
| 3 | Grants bypass via implies()      | #1         | —          | Critical | Fix now |
| — | Phase-2 endpoints absent         | #7,#8      | —          | —        | Deferred (correct) |
```

4. Triage by convergence: **convergent findings (both flagged) → fix
   immediately.** Unique findings → judge individually; a unique Critical from
   one reviewer still gets investigated. Findings on explicitly out-of-scope
   items → record as correctly deferred (this shows reviewers understood the
   spec).
5. Close the loop with a proof contract of your own: fix, run linter + full
   test suite, attach the `tests` artifact to the merge.

Consolidation is complementary to CI gates, not a replacement — CI catches
regressions deterministically; multi-verifier review catches design and logic
flaws CI can't express. Use it when a missed bug is expensive; skip it for
one-line changes and mechanical refactors where overhead exceeds benefit.

## Orchestrator failure modes (and their contract fixes)

| Failure mode | Symptom | Contract fix |
|---|---|---|
| Tasking too small | more orchestration than work | merge phases until each has a real artifact |
| Advancing on unmet contract | phase N+1 builds on phase N's fiction | hard rule: contract unmet → loop back to the same worker with concrete remediation, never advance |
| Worker hang | task never returns | per-task timeout in code; on expiry: capture state, then retry / escalate / abandon — an explicit decision, not a wait |
| Self-report acceptance | "done" relayed to user, user finds the lie | parent-run functional verification before any "done" leaves the system |
| Destructive batch without preview | live resources destroyed by misclassification | preview + exclusion-list artifact gated before execution |
| Success-only reporting culture | workers fabricate green | dispatch prompt makes blocked-with-evidence an acceptable outcome |

## Checklist

- [ ] Every dispatch names its proof-contract type and artifact contents
- [ ] "Done" without artifact is rejected mechanically, not judged case-by-case
- [ ] Parent runs independent verification over all affected surfaces
- [ ] Greenlight action classes (merge/publish/destructive/external-send/credential-change) enforced in code
- [ ] Batch destructive ops produce a preview + exclusion artifact before scheduling
- [ ] High-stakes reviews use ≥2 independent verifiers with mechanical consolidation
- [ ] Failure reporting is a first-class, evidence-bearing outcome
