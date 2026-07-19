---
name: multi-agent-orchestration
description: "Designing systems of multiple agents: orchestrator-worker decomposition, delegation, Claude Code subagents, multi-agent routing, review panels, and agent-to-agent protocol choices. Use when splitting work across planner/worker/reviewer roles, spawning subagents, building routing rules, or deciding whether A2A/framework handoffs are appropriate. Does not cover single-agent requirements design (see agent-design), durable-execution mechanics (see deterministic-agents), or eval methodology (see agent-evals)."
---

# Multi-Agent Orchestration

Multi-agent systems buy parallelism, specialization, isolation, and independent review. They cost tokens, latency, coordination complexity, and verification burden. Use them only when the benefit is explicit.

The core tradeoff is always the same: every agent you add multiplies cost and verification work, and only pays off when it brings real parallelism, real isolation, or real independent review. A second agent that shares the parent's tools, context, and authority is overhead, not orchestration. This skill is about making that trade deliberately — when to split, how to delegate safely, how to route without leaking, and when an interop protocol is or is not ready.

## When to Use

- A mission has multiple phases with different skills or risk profiles.
- You need independent review or adversarial verification.
- Work can run in parallel without sharing fragile state.
- A subagent can isolate context-heavy or untrusted material.
- Multiple users, workspaces, roles, or tool policies require routing boundaries.
- You are evaluating A2A or framework-native agent handoffs.

**Don't use for:** a single coherent agent design (`agent-design` skill), crash-safe execution (`deterministic-agents` skill), model routing detail (`model-selection` skill), or eval design (`agent-evals` skill).

## Orchestration Shapes

| Shape | Use when | Main risk |
|---|---|---|
| Single agent + skills | Task fits one context and one authority | Overbuilding if you add agents. |
| Single agent + subagents | Parallel/context-heavy subtasks | Starved subagents or unverified reports. |
| Orchestrator-worker | Multi-phase mission with specialist roles | Coordinator becomes bottleneck. |
| Pipeline | Fixed sequence with clear artifacts | Too rigid for exploratory tasks. |
| Review panel | High-risk output needs independent critique | Cost and false positives. |
| Event-driven agents | External events trigger specialized handlers | Harder state/retry semantics. |

## Worked Flow: Decompose → Dispatch → Verify → Synthesize

A canonical orchestrator-worker mission moves through four phases. Each phase emits an artifact the next phase depends on; the orchestrator never trusts a worker's self-report.

| Phase | Orchestrator does | Worker returns | Proof |
|---|---|---|---|
| 1. Decompose | Split mission into proof-bearing phases; assign one owner each | — | Phase list with owners + contracts |
| 2. Dispatch | Hand each worker inputs, constraints, tool policy, and budget | Runs in isolation | Acknowledged start + bounded output |
| 3. Verify | Read the artifact, run tests, reproduce evidence | `diff` / `tests` / `evidence` / `report` / `decision` | One proof artifact per phase |
| 4. Synthesize | Carry forward artifacts, not summaries; resolve conflicts | — | Final state recorded on the board |

**Concrete sketch (pseudocode, illustrative).** Mission: "Add feature X behind a flag, with tests and a security review."

```
Phase 1 (decompose): owner=lead  -> phases=[impl, test, review]
Phase 2 (dispatch):  impl   -> worker-A (write tools, repo branch)
                    test   -> worker-B (read-only, run harness)
                    review -> worker-C (read-only, no network)
Phase 3 (verify):   impl returns diff; test returns pass/fail counts;
                    review returns cited findings + severity
Phase 4 (synthesize): lead applies convergent fixes, records final
                      decision on board, advances the gate
```

If a phase has no artifact, the mission is not ready to dispatch — re-decompose until each phase has a proof contract.

## Delegation Heuristic

Delegate when the task has a specialist role, produces a verifiable artifact, benefits from isolation, or would overload the main context. Do it inline when it is a short question, a tiny edit, or a few tool calls with no independent artifact.

| Delegate when... | Do it inline when... |
|---|---|
| Distinct skill, risk profile, or tool policy | A few tool calls answer it |
| Produces a diff, test run, report, or decision | A tiny edit or single lookup |
| Untrusted or context-heavy material | No independent artifact is produced |
| Long-running or parallel-safe | Coordination overhead exceeds the work |

Delegation overhead is real: each spawn costs a prompt, a verification step, and state tracking. If the inline path is two tool calls and the delegated path is a spawn plus verification, inline wins. Full gate, state, and failure-mode rules live in `references/orchestrator-worker.md`.

## Proof Contract

Every delegated task needs one of: `diff`, `tests`, `evidence`, `report`, or `decision`. The parent verifies before acting. For the full proof-contract rules, see the `deterministic-agents` skill (`proof-contracts` reference).

## Subagent Minimum Bar

- Spawn prompt includes context, task, inputs, output format, constraints, and verification.
- Tool policy is narrower than the parent unless there is a reason.
- Timeout, budget, and stop condition are explicit.
- Output is written to a file or returned in a bounded format.
- Parent checks the artifact instead of trusting self-report.

### Spawn-Prompt Anatomy (template)

```
[Context] You are a {{role}} spawned by the lead agent for mission {{mission}}.
The lead needs {{why this matters}}. You do NOT inherit the parent conversation.

[Task] {{bounded, independently executable statement}}

[Inputs] Files: {{list}}. Branch: {{name}}. Read-only paths: {{list}}.

[Output] Write {{artifact}} to {{path}} and return a {{N}}-line manifest.
Do not paste full file contents into the chat.

[Constraints] Do not modify {{forbidden}}. Stop after {{max_turns}} turns or on {{condition}}.

[Verification] Completion is proven by: {{diff | tests | evidence | report | decision}}.
The parent reads the artifact; "done" alone is not accepted.
```

The ambient parent context (open conversation, private reasoning, local assumptions) usually does **not** transfer into the subagent — the spawn prompt is the entire briefing. Full role, cost, and tool-policy rules live in `references/subagent-design.md`.

## Review Panels

High-risk output needs independent critique. A review panel deploys two or
more agents to evaluate the same output independently, then collates. The
pattern: the orchestrator produces a draft → N reviewers examine it in
parallel (each read-only, each with a different specialty or threat-model
lens) → the orchestrator reads all findings and decides.

**When to use review panels:**
- A single-agent review is insufficient (the reviewer has the same blind
  spots as the author).
- The output has compliance, legal, or safety implications.
- You need adversarial verification — what does a hostile reviewer catch
  that a friendly one would miss?
- The cost of a false positive (rejecting something good) is acceptable
  weighed against the cost of a false negative (shipping something bad).

**Panel composition:**
| Reviewer | Specialty | Provides |
|---|---|---|
| Peer reviewer | Same domain | "Is this technically correct?" |
| Security auditor | Threat-model lens | "What can an attacker do with this?" |
| Compliance reviewer | Regulatory lens | "Does this violate any policy?" |
| Adversarial reviewer | "How would I break this?" | Jailbreak and edge-case probing |

**Consensus vs collation:**
- **Collation** (recommended): The orchestrator reads all findings and
  decides. "Reviewer A found X, Reviewer B found Y; I'm not shipping
  until X is fixed; Y is acceptable risk." Each reviewer is a tool the
  orchestrator consults.
- **Consensus** (limited utility): All reviewers must agree before the
  output ships. Consensus amplifies false positives (one overcautious
  reviewer blocks everything) and adds latency (N agents in series wait
  on each other). Use consensus only when the cost of a false negative
  is catastrophic (safety-critical systems) and combine it with a bypass
  path for the operator.

Full panel patterns, thresholds, and the `review-panels.md` reference
cover composition, evidence, and verdict mechanics.

## Routing Rules

Route by task, risk, data boundary, user/team, channel, and model need. Document precedence. Keep credentials, workspaces, and memory isolated when agents have different authorities.

### Precedence (typical order)

1. Exact task override (explicit pin)
2. Risk boundary (read-only vs destructive)
3. Data / workspace boundary (regulated dataset, repo scope)
4. User / team boundary
5. Channel / surface
6. Model need (cheap vs frontier)
7. Default agent

When two rules match at the same tier, the most specific or first-configured wins — and that rule must be visible in the routing config, not implicit. Worked conflict-resolution and isolation patterns live in `references/multi-agent-routing.md`.

## Orchestrator Failure Modes (quick map)

| Symptom | Root cause | Reference |
|---|---|---|
| Worker says "done" with no artifact | Missing proof contract | `orchestrator-worker.md`, `subagent-design.md` |
| Mission state lost after restart | No persisted board/state file | `orchestrator-worker.md` (State) |
| Coordinator becomes bottleneck | Orchestrator doing worker jobs | `orchestrator-worker.md` (Delegate or Do It Inline) |
| Five weak subagents, worse result | Unbounded fan-out | `subagent-design.md` (Scope and Cost) |
| Reviewers converge on a wrong answer | Identical prompts/models/blind spots | `review-panels.md` (Panel Shapes) |
| Cross-tenant or cross-repo leak | Shared tools/credentials/memory | `multi-agent-routing.md` (Isolation) |

## Reference Router

| Load | When |
|---|---|
| `references/orchestrator-worker.md` | Decomposing missions, assigning workers, requiring proof contracts, and handling gates/state. |
| `references/subagent-design.md` | Designing Claude Code subagents and spawn prompts with realistic inheritance/cost assumptions. |
| `references/multi-agent-routing.md` | Routing tasks among roles/agents while preserving workspace, memory, and tool isolation. |
| `references/review-panels.md` | Running independent reviewers/judges and consolidating convergent vs unique findings. |
| `references/agent-protocols.md` | Surveying A2A, MCP's boundary, framework handoffs, and shared-state vs message-passing models. |

## Pitfalls

1. **Delegating work a skill would cover.** If reusable instructions or a deterministic script solve it, a subagent is pure overhead.
2. **Trusting self-reported success.** A subagent saying "done" is not evidence. Read the diff, tests, logs, or report.
3. **Starving subagents of context.** The spawn prompt carries the task. Ambient parent assumptions usually do not transfer.
4. **Unbounded fan-out.** Five weak subagents can cost more and produce worse work than one focused agent. Cap concurrency.
5. **Copying tool policy across roles.** A reviewer, implementer, and deployer have different risk profiles.
6. **No persisted state for long missions.** If restart loses the board, the orchestration design is incomplete.
7. **Letting a leaf spawn workers.** If the architecture says an agent is a leaf, giving it spawn authority breaks the authority boundary and creates unbounded fan-out.
8. **Sequencing reviewers.** A second reviewer that sees the first's findings anchors on them and stops being independent.
