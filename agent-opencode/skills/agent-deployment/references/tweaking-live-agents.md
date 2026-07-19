<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->

# Tweaking Live Agents

Tweaking is a surgical workflow. The goal is to fix one observed behavior without destabilizing the rest of the agent.

## Diagnostic Gate

Never edit first. Work in this order:

1. Reproduce the issue or locate the original run.
2. Narrow it to one bucket.
3. Confirm the specific fix.
4. Make exactly one change under version control.
5. Re-run the original case and the relevant golden tests.

### Narrowing to One Bucket

Step 2 is where most tweaks go wrong. Use the same top-down discipline as the layer-narrowing procedure in `operating-live-agents.md`: walk the buckets in order and stop at the first one the evidence confirms.

| Question | If yes, bucket is... |
|---|---|
| Is the wrong *voice or stance* on display, with the right actions? | Persona |
| Did it have the right facts and tools, but skip a procedure or verification? | Procedure |
| Did it lack a fact, cite a stale fact, or fail to retrieve? | Memory |
| Did it have the right intent but pick the wrong tool (or no tool)? | Tool preference |
| Did it pick the right tool but get blocked? | Policy blocking |
| Does the live config not match what the team thinks shipped? | Config drift |

If two answers are "yes," you have two bugs. Sequence them; do not bundle. The order usually matters: fix config drift first (so you are tweaking the agent you actually have), then memory, then policy, then tool preference, then procedure, then persona. Earlier buckets contaminate the reading of later ones.

## Six Buckets

| Symptom | Bucket | Typical fix |
|---|---|---|
| Tone, verbosity, stance are wrong | Persona | Edit system prompt or output style |
| Skips verification or reports too early | Procedure | Tighten operating rules and examples |
| Forgets durable facts or uses stale facts | Memory | Fix write/read/curation policy; update memory |
| Chooses wrong tool or no tool | Tool preference | Improve tool descriptions or operating rules |
| Blocked from expected action | Policy blocking | Adjust permission, hook, sandbox, or approval path |
| Behavior differs from deployed intent | Config drift | Reconcile release manifest, settings, prompt registry, model ID |

### Worked Example per Bucket

Each bucket has a characteristic symptom, a confirming piece of evidence, and a one-change fix. Use these as templates, not as the only way each bucket presents.

**Persona.** Symptom: the agent apologizes excessively and hedges every answer. Evidence: the transcript shows three apology opens in five turns; tone is off-stance versus the system prompt. Fix: edit the system prompt's voice section only. Do not also rewrite procedure. Regression case: `regression/over-apologetic-tone`.

**Procedure.** Symptom: the agent reports "done" without verifying. Evidence: the trace shows no verification tool call between the edit and the report. Fix: add one rule under Verification in the operating-rules file. Regression case: `regression/unverified-done`.

**Memory.** Symptom: the agent forgets the user's timezone and asks again every session. Evidence: the memory store has no timezone entry, or the entry exists but is not in the loaded context for the session. Fix: either write the fact with the right retrieval trigger, or fix the curation rule that pruned it. Do not "fix" this by restating the timezone in the prompt. Regression case: `regression/forgotten-timezone`.

**Tool preference.** Symptom: the agent searches the web when it should query the internal knowledge base. Evidence: the trace shows a web-search call where a `kb.lookup` call was available and correct. Fix: improve the `kb.lookup` description and add a preference rule ("for internal policy questions, prefer kb.lookup over web search"). Regression case: `regression/wrong-source-for-policy`.

**Policy blocking.** Symptom: the agent cannot run a build command it needs to verify a change. Evidence: the policy log shows the shell tool blocked on the build command with rule `shell.deny.unscoped`. Fix: scope an approval path for the build command in the project workspace, or adjust the rule to allow it in the approved directory. If the fix expands authority, treat it as a deployment and re-run security review. Regression case: `regression/blocked-required-build`.

**Config drift.** Symptom: production behavior no longer matches what the team thinks shipped. Evidence: the live model ID is `claude-sonnet-5-20260620` but the manifest says `claude-sonnet-5`; an alias moved; the prompt registry points at v44 while the manifest says v42. Fix: reconcile the release manifest, settings, prompt registry, and model ID to one known-good set; re-deploy from source control. This is the only bucket whose fix is "make reality match the manifest," not "edit the agent." Regression case: the manifest-reconciliation diff itself.

The shared discipline across all six: the fix is exactly one change in one bucket, evidenced by one trace, verified by one regression case. If a "fix" touches two buckets, it is two fixes and must be sequenced.

## One-Change Patch Pattern

Good tweak:

- "In prompt v42, add one rule under Verification: after editing a file, read it back or run the project check before reporting done."
- Then run the failing case and one regression case.

Bad tweak:

- "Rewrite the whole system prompt, switch models, loosen permissions, and add a new memory rule."
- If behavior improves, you still do not know why.

### Tweak Record Template

A tweak is a small release; record it like one. The shape below mirrors the rollout record in `versioning-rollout.md`, scoped to a single bucket.

```text
tweak: support-triage-2026-07-12.3
parent: support-triage-2026-07-12.2
bucket: procedure
symptom: "Agent reported 'done' without verifying the fix was live (run R-124)."
evidence: "trace R-124, span s_42: no deploy-status call between edit and report."
change:
  one_variable: operating-rules
  diff: rules/support-triage:v12 -> v13
  summary: "Add Verification rule: confirm a fix is live before marking resolved."
regression_case: regression/unverified-resolved (added; fails on v12, passes on v13)
golden_suite: support-golden:v31 -> v32, pass (119/119)
rollback: restore rules/support-triage:v12 and suite v31
```

If any field above is blank or "TBD," the tweak is not ready to ship. The regression case is mandatory: a tweak with no regression case is a tweak that cannot be verified and will silently regress later.

## Version Control Rules

- Agent config, prompts, tool schemas, eval cases, and memory migrations belong in a reviewable change record.
- Do not patch live dashboard text without exporting it back to source control.
- Name regression cases after the bug they prevent.
- If a tweak changes authority, treat it as a deployment and re-run security review.

## Stop Conditions

Stop tweaking and re-open design when:

- More than two buckets are implicated.
- The same bucket recurs after multiple targeted fixes.
- The fix requires expanding tool authority or network reach.
- The prompt is accumulating narrow rules that would be clearer as a skill, tool contract, or code-owned workflow.

### When a Tweak Becomes a Release

Some tweaks are not tweaks. Escalate from the tweaking workflow to the full release workflow in `versioning-rollout.md` when any of these is true:

| Signal | Why it is not a tweak |
|---|---|
| The change expands authority, network reach, or data access | Security review is required; treat as a deployment |
| The change swaps the model or aliases | Affects every behavior; needs the full golden suite, not a regression case |
| The change touches memory schema or retrieval corpus version | Affects every run that loads memory or retrieval; needs migration and rollback plan |
| More than one bucket must change to fix the symptom | That is two releases, sequenced, not one tweak |
| The same bucket has been tweaked three times this month | The design is asking too much of one layer; re-open design |

The rule of thumb: if the change can be described as "one sentence in one file, verified by one new regression case," it is a tweak. Anything larger is a release and earns the full gate.
