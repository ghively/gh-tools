# Self-Improvement Loop

Self-improvement is a production loop, not a vibe. The deployed agent learns only when observations become regression tests, fixes, and curated knowledge.

## Loop

```text
observe production behavior
  -> capture failures and near misses
  -> classify the failure mode
  -> add or update a regression eval
  -> make one fix
  -> verify with evals and trace evidence
  -> deploy through canary
  -> consolidate durable lessons
```

## Capture

Every meaningful production surprise should create an issue or incident record with:

- Trace/session ID.
- User-visible symptom.
- Expected behavior.
- Actual tool trajectory.
- Bucket from `agent-design/references/failure-modes.md`.
- Severity and recurrence risk.

Near misses count. A hook blocking a dangerous command, a cost ceiling preventing a runaway loop, or a user correcting a wrong assumption are all learning signals.

### Capture Template

The capture record is the input to everything downstream. A vague capture ("agent was weird on Tuesday") produces a vague fix. Use a consistent shape so the record can be classified without re-reading the trace.

```text
capture: <incident or issue ID>
date: <timestamp>
trace_ids: [R-NNN, ...]
symptom: <one sentence the user would write>
expected: <one sentence of what should have happened>
actual_trajectory: <the tool calls / decisions that happened, summarized>
bucket: <failure-modes bucket, or "unclassified">
severity: <low / medium / high>
recurrence_risk: <one-off / repeated / systemic>
near_miss: <yes / no>   # hook block, cost cap, user correction, etc.
```

Two fields deserve emphasis. `recurrence_risk` decides whether this becomes a regression case now or later: a systemic risk earns a case immediately, a one-off may not. `near_miss` ensures that a hook or cost cap doing its job still becomes a learning signal rather than a silent non-event.

## Classify

Classification is the bridge between a captured incident and a fix. A capture that is not classified cannot be converted into an eval case, because the eval must assert on the specific behavior that went wrong.

| If the failure is... | Classify as... | The eval asserts on... |
|---|---|---|
| Wrong voice, stance, or refusal posture | Persona | Tone/stance markers in the output |
| Skipped procedure or verification | Procedure | Presence of the expected verification step in the trajectory |
| Missing, stale, or un-retrieved fact | Memory / context | The fact being present and used in the response |
| Wrong or missing tool call | Tool preference | The correct tool being called with correct arguments |
| Right tool, blocked | Policy | The action completing under the adjusted policy |
| Live config does not match intent | Config drift | Behavior matching the reconciled manifest |
| Bad judgment despite correct inputs | Runtime / model | Output quality against a rubric |

When a failure does not fit any row, mark it `unclassified` and surface it at the next consolidation pass. Forcing a misfit into a bucket produces a fix that does not address the real cause.

## Convert Failures Into Evals

The `agent-evals` skill owns eval construction, but the deployment loop owns the rule: every fixed production bug gets a regression case before the fix is considered complete.

For each failure:

1. Write the smallest prompt or event that reproduces it.
2. Add assertions on trajectory, not just final answer, when tool behavior mattered.
3. Name the case after the failure.
4. Run it against current production to confirm it fails.
5. Fix one thing.
6. Run the suite again and store the result in the release record.

## Worked Sequence

The loop is easiest to see end to end. The example below follows one production failure from observation to consolidated lesson. Names and IDs are illustrative.

| Stage | Action | Artifact produced |
|---|---|---|
| 1. Capture | On-call notices the triage agent marked three tickets resolved without verifying the fix was deployed. Files an incident record. | Incident `I-224`, linked to traces R-118, R-121, R-124 |
| 2. Classify | Read the three traces. All three skip the deploy-status call between edit and report. Same symptom, same bucket. | Bucket: procedure (from `tweaking-live-agents.md`); root cause: missing verification rule |
| 3. Eval case | Write the smallest repro: a turn where the agent edits a file and is asked to confirm. Assert a deploy-status (or equivalent verification) call before the "resolved" message. Name it `regression/unverified-resolved`. | New case in the golden suite; confirmed to fail on current production |
| 4. Fix | Add one rule to the operating-rules file: "confirm a fix is live before marking resolved." Exactly one change; persona, model, tools, memory, and policy untouched. | `rules/support-triage:v12 -> v13` |
| 5. Verify | Run `regression/unverified-resolved` (now passes) and the rest of the golden suite (still passes). Canary the change; metrics hold. | Suite result `support-golden:v32, 119/119`; canary record archived |
| 6. Consolidate | At the monthly consolidation pass, confirm no other prompt sentence covers this; the rule stays in operating rules (not memory, not persona). Link the rule to `I-224` and the regression case. | Lesson recorded: "verification rules belong in the operating-rules file, with a regression case per rule." |

The discipline that makes this a loop rather than a list of fixes: stage 3 (eval case) happens before stage 4 (fix), and stage 6 (consolidate) is scheduled, not improvised. Skip stage 3 and the bug will recur silently; skip stage 6 and the team will accumulate five narrow prompt sentences for what was one procedural rule.

## Consolidate Lessons

Agents accumulate lessons in several places: prompts, skills, memory, tool descriptions, runbooks, and eval datasets. Schedule a recurring consolidation pass to prevent fragmentation.

During consolidation:

- Merge duplicate lessons.
- Remove stale workaround notes after the underlying system changes.
- Promote repeated one-off prompt fixes into a skill or operating rule.
- Demote noisy session facts out of durable memory.
- Link each durable lesson to the eval or incident that justifies it.

### Consolidation Schedule

Consolidation is not "when someone gets around to it." It is a scheduled pass, because unscheduled consolidation never happens and lessons fragment across prompts, memory, runbooks, and chat threads.

| Cadence | Scope | Owner | Output |
|---|---|---|---|
| Weekly (15 min) | Triage new incidents and near misses from the operating journal; confirm each has a capture record and a bucket. | On-call | Updated journal; open eval-case tasks |
| Monthly (60-90 min) | Review every fix shipped since the last pass. Merge duplicates, retire stale workarounds, promote repeated prompt sentences into skills or rules, demote noisy memory facts. | Agent owner | Consolidated lesson log; one PR per promotion/demotion |
| Quarterly (half-day) | Re-read the whole persona, operating rules, and memory seed as a single document. Look for contradictions, drift from the original job sentence, and lessons that belong in design rather than the prompt. | Agent owner + a reviewer who did not write the originals | Architecture or design flags; possible migration triggers |

The monthly pass is where most consolidation value lands. The weekly triage keeps the journal honest; the quarterly read catches the slow drift that no single month reveals. A team that only does the weekly triage will accumulate lessons faster than it consolidates them, which is the same as not consolidating.

## Anti-Patterns

- Capturing only happy-path wins and ignoring failures. Fix: treat near misses and hook blocks as captures too; the operating journal is for surprises, not bragging.
- Writing lessons into memory without a trigger that will retrieve them. Fix: every durable fact needs a retrieval trigger; otherwise it is inert text that costs tokens and changes nothing.
- Fixing the same bug class with one more prompt sentence every week. Fix: three repeats of the same bucket is a consolidation trigger — promote it to an operating rule or a skill.
- Letting production traces reveal problems that never reach the golden suite. Fix: no fix ships without its regression case; the case is part of "done," not a follow-up task.
- Optimizing the prompt based on anecdotes without checking aggregate metrics. Fix: every claimed improvement must show movement on a dashboard metric or a suite, not a cherry-picked transcript.
- Closing incidents without a capture record. Fix: an incident with no capture record cannot become a regression case; the loop dies at stage 1.
