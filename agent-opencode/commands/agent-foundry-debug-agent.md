---
description: Debug a live-agent behavior surprise — diagnose from transcript, trace, audit log, and layer map before changing anything.
agent: build
---

Debug the agent at `$ARGUMENTS`. Diagnose the behavior surprise BEFORE
changing anything; a 3 AM prompt edit is rarely attributed, rarely
eval-gated, and frequently the root cause of the next incident.

Load `agent-deployment` (especially `operating-live-agents.md`) and
`agent-harness` (especially `error-recovery.md`,
`harness-observability.md`). Process:

1. **Freeze the run.** Pin the failing session ID and the exact code
   version. Do not iterate in the live environment — capture the
   failing state and reproduce in staging.

2. **Reconstruct the trajectory.** Pull:
   - The session transcript (from the session store).
   - The trace (from OTel / Langfuse / Phoenix / LangSmith).
   - The audit log rows for that session (from safety-audit.log).
   - Any user-facing reports (issue, ticket, complaint).

3. **Layer-map the failure.** An agent has 6 layers; the failure is in
   exactly one (or a chain across two). Identify it:

   | Layer | Symptom if it's the bug |
   |---|---|
   | Provider | 4xx/5xx spikes; refusals; model-card drift |
   | Harness | Loop stuck; compaction lost context; tool dispatch errored |
   | Tools | Tool returned wrong/malformed data; tool timed out |
   | Prompt | Instructions ambiguous; behavior off-spec |
   | Memory / RAG | Stale chunk surfaced; wrong entity retrieved |
   | Permission / safety | Blocked a legitimate call OR allowed a bad one |

4. **Reproduce.** Re-run the exact session with the exact model +
   code + config + tools + memory state. Use the eval suite to
   produce a deterministic reproduction.

5. **Form hypothesis, write a regression eval case.** Before fixing,
   write the eval case that captures the bug. The case is named after
   the bug (`regression-issue-42`). It must fail before the fix and
   pass after.

6. **Fix in staging.** Apply the smallest change that resolves the
   hypothesis. Run the eval suite. If green, run smoke-test. If
   green, prepare a release via `/agent-foundry-ship-check`.

7. **Never ship from debug.** Debug produces a candidate fix;
   ship-check is the gate. A debug session that ends with "I'll just
   push this through" is how regressions compound.

Report: the layer the failure lived in, the hypothesis, the regression
case, the fix, and whether the candidate is ready for ship-check.