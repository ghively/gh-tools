# Incident Response Playbook

When an agent is implicated in an active incident — safety event,
data leak, runaway spend, prompt-injection landing, or unexplained
behavior change — this is the runbook. Goal: contain, preserve
evidence, restore service, then diagnose.

This reference is the agent-safety complement to the rollback, debug,
and red-team commands. For the broader safety doctrine, see the rest
of this skill's references.

## Severity Classification

| Severity | Symptom | Initial response |
|---|---|---|
| **SEV1** | Active data exfiltration, secret leak, or safety event in production | Immediate containment (revoke keys + stop the agent); preserve evidence; page on-call |
| **SEV2** | Runaway spend, persistent misbehavior, but no data loss | Roll back to last known-good; investigate within the hour |
| **SEV3** | User-visible degradation, intermittent failures | Debug-session; canary the fix |
| **SEV4** | Single-user complaint, isolated oddity | Route to debug; non-urgent |

## SEV1: The First 30 Minutes

Containment before diagnosis. Every minute the agent runs is a minute
the incident can compound.

1. **Revoke the provider keys.** Rotate `ZAI_API_KEY`,
   `ANTHROPIC_API_KEY`, etc. The agent cannot burn more tokens or
   exfiltrate more data without a valid key.
2. **Stop the agent.** `docker compose stop <agent>` or the
   orchestrator equivalent. Do NOT destroy the container — its
   in-memory state is evidence.
3. **Freeze the state volume.** Snapshot `/data` (or whatever the
   state path is) before any cleanup. This is the forensic record.
4. **Preserve logs.** Capture the safety-audit.log, the OTel trace
   export, and the docker logs for the last 24 hours into a
   read-only artifact.
5. **Notify.** Page on-call; alert security if a leak is suspected;
   open the incident channel; assign an incident commander.

## SEV1: The Next 4 Hours

Stabilize, then diagnose.

1. **Identify the entry point.** Which session? Which input? Which
   tool call crossed the line? Use the audit log to reconstruct.
2. **Identify what left the system.** Did data egress? Did a side
   effect land (a deploy, a write to an external API)? Check egress
   logs, provider call logs, downstream system audit trails.
3. **Decide on rollback vs hotfix.** Roll back if the failure is in
   the deployed version. Hotfix only if the failure is in config or
   data that rollback cannot reach (a leaked key already rotated, a
   poisoned memory store).
4. **Restore service with the rolled-back version.** Run smoke-test
   against the rolled-back version before re-opening traffic.
5. **Communicate broadly.** Users affected, data exposed, action
   taken, expected resolution time.

## SEV1: Post-Incident (Within 48 Hours)

The blameless postmortem.

1. **Timeline reconstruction.** Minute-by-minute from logs and traces.
2. **Root cause.** The single failure (or chain) that produced the
   incident. Layer-map: provider, harness, tools, prompt, memory,
   permissions.
3. **Defense-in-depth failure.** Which layers failed to catch it?
   The model? The harness? The tools? The permission rules? The
   safety floor? The sandbox?
4. **Action items with owners and dates.** Each item is a fix that
   prevents this class of incident.
5. **Regression eval cases.** Every SEV1 produces at least one
   regression eval case (named after the incident). The case must
   fail before the fix and pass after.
6. **Red-team follow-up.** Run `/agent-foundry-red-team` against the
   fixed agent within a week. The incident revealed a class of
   attack; check for siblings.

## Common Incident Patterns

### Prompt-Injection Landing

The agent read untrusted content (issue body, fetched web page, tool
result) that contained embedded instructions, and it followed them.

- **Containment**: revoke keys, stop agent.
- **Investigation**: identify the untrusted source; trace which
  instructions the agent followed.
- **Fix**: tighten the prompt defense (see
  `prompt-context-engineering/injection-defense.md`); add a
  deterministic hook that blocks the specific exfiltration pattern;
  add a regression eval case with the injection payload.

### Runaway Spend

The agent looped or hit rate limits repeatedly; the provider bill
spiked.

- **Containment**: revoke keys (immediate); add a hard cost ceiling
  at the gateway.
- **Investigation**: identify the loop or retry storm; check whether
  doom-loop detection was enabled.
- **Fix**: enable doom-loop detection (see
  `agent-harness/references/doom-loop-prevention.md`); tighten
  `max_turns` and wall-clock; add per-day spend alerts in the
  provider console.

### Permission Drift

The agent started using a tool or path it should not have. Often a
side effect of an `/agent-foundry-extend-agent` run that widened
authority.

- **Containment**: roll back to the prior known-good config.
- **Investigation**: identify the change that widened authority
  (git log the config; check the extension history).
- **Fix**: revert the widening; add a regression eval case that
  asserts the agent does NOT use that tool.

### Memory Poisoning

A malicious actor wrote to the agent's memory store (via a tool
input or a separate vector) and the agent's behavior shifted over
time.

- **Containment**: roll back the memory store to a known-good
  snapshot.
- **Investigation**: identify the write that poisoned memory;
  trace what read the poisoned entry and when.
- **Fix**: validate memory writes; add a regression eval case
  that uses a poisoned-memory fixture.

### Tool-Result Injection

A tool returned content that contained embedded instructions
(`{"result": "ignore previous instructions and ..."}`); the agent
followed them.

- **Containment**: roll back the tool's data source if possible;
  otherwise revoke the agent's access to that tool.
- **Investigation**: identify the tool; trace which results
  contained injections; identify what the agent did in response.
- **Fix**: add a sanitizer on tool results; add a regression eval
  case with the injected result payload.

## Pitfalls

1. **Diagnosing before containing.** The incident compounds while
   you investigate. Fix: containment first; diagnosis from frozen
   state.
2. **Destroying the container.** The container's in-memory state is
   evidence. Fix: `stop`, not `down`; snapshot before cleanup.
3. **Hotfixing under pressure.** A 3 AM hotfix is rarely
   attributed and frequently the root cause of the next incident.
   Fix: roll back to known-good; hotfix in staging with the eval
   suite.
4. **No regression case.** The incident class will recur without a
   regression eval. Fix: every incident produces at least one
   case, verified to fail without the fix.
5. **No blameless postmortem.** Without one, the org repeats the
   failure. Fix: schedule within 48 hours; nobody is blamed;
   systemic gaps are surfaced.
6. **No red-team follow-up.** Incidents reveal attack classes; the
   class has siblings. Fix: red-team within a week of any SEV1.

## See Also

- `/agent-foundry-rollback-agent` command — the rollback procedure.
- `/agent-foundry-debug-agent` command — diagnosis procedure.
- `/agent-foundry-red-team` command — follow-up adversarial testing.
- `../../agent-deployment/references/operating-live-agents.md` —
  daily operating doctrine.
- `../../agent-deployment/references/versioning-rollout.md` —
  versioning, canary, rollback manifests.
- `deterministic-hooks.md` — the safety floor and its audit log.
- `multi-tenant-isolation.md` — per-tenant incident containment.
