> Last verified: 2026-07. Model aliases and provider deprecation policies change; verify current provider lifecycle pages before relying on notice periods.

# Versioning and Rollout

An agent release is more than code. Prompts, model IDs, tool schemas, memory indexes, retrieval corpora, permission rules, and eval suites are all part of the deployed artifact.

## Version Everything That Changes Behavior

| Artifact | Versioning rule |
|---|---|
| System prompt / instructions | Commit hash or prompt registry version |
| Tool schemas | Semantic version when parameters or behavior change |
| Model choice | Pin concrete model IDs where behavior stability matters |
| Retrieval corpus | Collection version plus embedding model version |
| Memory | Snapshot or migration record for durable facts |
| Safety policy | Rule ID, hook version, permission-mode config |
| Eval suite | Dataset version and assertion code version |

Do not let a production agent drift through dashboard edits, untracked prompt tweaks, or "latest" model aliases in critical paths.

## Rollout Ladder

1. **Local run:** one or two representative tasks, manually inspected.
2. **Golden suite:** all regression and capability cases pass. This is the canary gate from the `agent-evals` skill.
3. **Shadow mode:** new version receives real inputs but does not take side effects. Compare trajectory and final answer.
4. **Small canary:** route a small percentage or low-risk tenant cohort to the new version with automatic rollback triggers.
5. **Full rollout:** promote only after cost, latency, quality, refusal, and tool-error metrics stay within thresholds.

### Eval-Gated Promotion Flow

The ladder above is a sequence of gates; promotion is what happens when a gate passes. Wire the gates into an explicit flow so a human never has to remember the order under pressure.

```text
proposed change (one variable)
  |
  v
[ gate 1 ] golden suite runs against the new manifest
  |  fail  -> block; do not promote; return to author
  |  pass  -> record result in the release record
  v
[ gate 2 ] cost / latency / refusal budgets checked against the suite run
  |  fail  -> block; investigate before any traffic
  |  pass  -> proceed
  v
[ gate 3 ] shadow mode: replay real inputs; compare trajectories
  |  regression detected -> block; classify before retrying
  |  no regression       -> proceed
  v
[ gate 4 ] canary: small cohort with auto-rollback triggers armed
  |  any trigger fires -> auto-rollback; postmortem
  |  metrics hold      -> promote to full
  v
archive manifest + suite result + rollback bundle
```

The non-negotiable property is that every transition is recorded: which gate, which manifest, which suite result, who approved. A promotion with no recorded gate result is not a promotion; it is a leak.

### Shadow Mode and A/B Setup

Shadow mode and A/B tests are different tools. Shadow answers "is the new version safe?" A/B answers "is the new version better?" Use shadow first; A/B only when shadow is clean and you have a metric worth comparing.

| Mode | New version takes side effects? | Traffic routed | Question answered |
|---|---|---|---|
| Shadow | No — outputs are compared, not executed | 100% of inputs duplicated to the new version | Does the new trajectory diverge or regress? |
| Canary | Yes | Small fixed % or low-risk cohort | Does it survive real load and real users? |
| A/B | Yes | Random split, often 50/50 after canary | Is it better on a defined metric? |

Shadow setup requires three things: a duplicating fan-out that feeds real inputs to the new version without surfacing its outputs to users, a deterministic side-effect suppressor (so the shadow run cannot send, write, or spend), and a trajectory comparator that flags divergence on the cases that matter. A/B setup additionally requires a pre-registered metric, a sample-size estimate, and a decision rule written down before the test starts — otherwise the result is anecdote with a chart.

## One Change Protocol

Change exactly one behavior-bearing variable per rollout: prompt, model, tool schema, memory, retriever, or policy. If you change two, you cannot attribute the result.

Every rollout record should include:

- What changed.
- Why it changed.
- Expected metric movement.
- Golden-suite result.
- Canary start/end time.
- Rollback command or config pointer.
- Owner who approved promotion.

### Worked Changelog Example

A real rollout record is short, attributable, and machine-checkable. The shape below is illustrative; the fields map directly onto the bullet list above.

```text
release: support-triage-2026-07-12.2
parent:   support-triage-2026-07-12.1
author:   ops-oncall
approved: triage-lead

change:
  one_variable: prompt
  diff: prompt-registry/support-triage:v42 -> v43
  summary: "Add a read-back step under Verification: after editing a file,
            read it back or run the project check before reporting done."

why: "Three incidents in the trailing week (R-118, R-121, R-124) where the
      agent reported 'done' without verifying. Same failure mode, same bucket
      (procedure)."

expected_metric_movement:
  - unverified-done rate: down
  - mean turns per run: up slightly
  - cost per run: within +5%

golden_suite:
  suite_version: support-golden:v31
  result: pass (118/118)
  new_case: regression/unverified-done-after-edit (added)

canary:
  cohort: 5% of triage traffic, lowest-risk tenants
  start:  2026-07-12T14:00Z
  end:    2026-07-12T18:00Z
  triggers_armed: [cost_p95_2x, refusal_rate_3sigma, tool_error_10pct]

rollback:
  command: deploy restore support-triage-2026-07-12.1
  manifest: manifests/support-triage-2026-07-12.1.yaml
```

Note what is deliberately absent: no second variable, no model change, no tool-schema change, no policy change. If the canary had failed, the only suspect would be the prompt diff. That is the entire point of the one-change protocol.

## Provider Model Lifecycle

Anthropic's [model deprecation page](https://docs.anthropic.com/en/docs/about-claude/model-deprecations) states that customers with active deployments receive at least 60 days notice before publicly released model retirement, and that partner platforms can have different schedules. Treat that as a floor, not a migration plan.

Operational rules:

- Subscribe to provider deprecation notices.
- Inventory model usage by API key, service, and prompt version.
- Avoid `latest` aliases in reproducibility-sensitive systems.
- Run replacement-model evals before the deadline, not during the incident.
- Keep a downgrade path when a new model changes tool use or refusal behavior.

## Rollback Is Multi-Artifact

Rolling back the container but leaving the new prompt in a prompt registry is not rollback. A rollback bundle must restore all behavior-bearing artifacts to the previous known-good set.

Use release manifests such as:

```yaml
agent_version: support-triage-2026-07-12.1
code: git:abc123
prompt: prompt-registry/support-triage:v42
model: claude-sonnet-5
tools: tools:v18
retrieval_collection: support-kb:2026-07-08
memory_schema: memory:v4
eval_suite: support-golden:v31
policy: permissions:v12
```

## Rollback Runbook Shape

Rollback is a procedure, not a command. Write the runbook before the first canary so the on-call does not invent it during an incident. The shape below is a template, not a real system's config.

```text
# Rollback runbook: <agent>
trigger: any armed canary alert fires, OR a Sev-2+ incident is declared.

steps:
  1. Confirm the active manifest (which version is live for <agent>?).
  2. Decide: full rollback (cross-tenant or safety-related) vs.
            cohort isolation (scoped to one tenant or task type).
  3. Execute: deploy restore <previous-known-good-manifest>.
     - Restores code, prompt, model, tools, retrieval, memory, policy.
     - Verify every field, not only the container image.
  4. Confirm: health check passes; a synthetic run matches the expected
              trajectory; metrics return to baseline within <N> minutes.
  5. Preserve: archive the failing manifest, its traces, and the alert
              that fired. Do not delete the failing version.
  6. Postmortem within <SLA>: root cause, contributing causes, fix,
              regression case added.

common_failures:
  - "Rolled back the container but the prompt registry still points at v43."
    fix: the rollback command must restore every manifest field.
  - "Health check passed but the agent still misbehaved."
    fix: run a synthetic turn, not only a liveness probe.
  - "Could not find the previous-known-good manifest."
    fix: every release archives its manifest; verify the path before you need it.
```

Two properties make this runbook usable under pressure: every step has a concrete command or query (no "investigate the issue"), and the common-failures section is populated from real rollbacks the team has actually done. An empty common-failures section means the runbook has never been exercised.
