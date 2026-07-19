<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->

# Operating Live Agents

Operating is what you do when the deployed shape is basically right but the behavior needs evidence-driven diagnosis. Do not jump straight to prompt edits.

## Evidence Sources

| Evidence | Answers |
|---|---|
| Session transcript | What did the agent see and say? |
| Tool-call trace | What did it actually call, with what inputs, and what happened? |
| Runtime logs | Did the process crash, retry, or hit dependency errors? |
| Telemetry dashboard | Is this isolated or systemic? |
| Memory/retrieval state | Did the agent have the fact, fail to retrieve it, or retrieve stale context? |
| Policy/audit logs | Was a permission, hook, sandbox, or network rule the blocker? |

The transcript is the ground truth for behavior. The trace is the ground truth for execution. User reports are important, but verify them against both before changing anything.

### How to Read a Transcript for Diagnosis

Reading a transcript well is the core operating skill. Read in this order, not top-to-bottom:

1. **The user's actual input** — stripped of your assumptions about what they meant.
2. **What context was loaded** — persona, operating rules, retrieved facts, memory. Was the right information present at all?
3. **The first model turn** — before any tool call. Did the agent understand the request, or did it misunderstand before acting?
4. **Each tool call's arguments and result** — did it call the right tool with the right inputs, and did the result match what it claimed?
5. **The final response** — does it match what the tools actually returned, or did the agent narrate a success that the trace contradicts?

The most common diagnostic finding is a mismatch between step 4 (what the tools returned) and step 5 (what the agent claimed). That mismatch is the bug; everything else is context for why it happened.

## Diagnose a Behavior Surprise

1. **Reproduce or locate the run.** Get the session ID, trace ID, request ID, or timestamp. If none exists, create a fresh reproduction.
2. **Read the exact turn.** User prompt, loaded context, model output, tool calls, tool results, and final response.
3. **Narrow to a layer.** Do not "improve the prompt" until you know which layer failed.
4. **Show evidence.** Name the run and the line/span that proves the diagnosis.
5. **Change one thing.** Prompt, tool schema, memory, policy, or model, not all at once.
6. **Verify with the same case.** The evidence that exposed the problem should prove the fix.

## Layer Map

| Layer | Controls | Failure signs |
|---|---|---|
| Persona/system prompt | Role, tone, refusal posture | Off voice, wrong stance, over-apology |
| Operating rules | Procedures, verification, reporting | Skipped checks, claimed done without proof |
| Context and memory | Facts and prior decisions | Forgot fact, cited stale fact, ignored retrieval |
| Tool policy | What actions are permitted | Expected tool blocked, unsafe tool allowed |
| Sandbox/network | What is physically reachable | File/network permission errors |
| Runtime/model | Raw reasoning and provider behavior | Bad judgment despite correct context and tools |

## Layer-Narrowing Decision Procedure

The layer map names the candidates; the procedure decides between them. Walk it top-down and stop at the first layer that explains the evidence. Do not skip ahead to "rewrite the prompt."

| Step | Question | If yes... | If no... |
|---|---|---|---|
| 1 | Does the transcript show the wrong *voice*, *stance*, or *refusal posture*? | Layer: persona. Edit the system prompt only. | Continue. |
| 2 | Did the agent have the right context but skip a procedure, a verification step, or a report? | Layer: operating rules. Tighten the rules file. | Continue. |
| 3 | Did the agent lack a fact, cite a stale fact, or ignore what retrieval returned? | Layer: context/memory. Fix the write/read/curation path. | Continue. |
| 4 | Did the agent want the right action but call the wrong tool, or no tool? | Layer: tool preference. Improve descriptions or rules. | Continue. |
| 5 | Did the agent call the right tool but get blocked? | Layer: tool policy. Adjust permission, hook, sandbox, or approval path. | Continue. |
| 6 | Did everything above look correct, and the judgment was still bad? | Layer: runtime/model. Pin a different model, or treat as a design limit. | Re-read the transcript; you missed something. |

The discipline is the ordering. Most operators jump to step 1 or step 6 because both feel productive. Step 1 (rewrite the persona) rarely fixes a procedure problem; step 6 (blame the model) is the last resort, not the first, and only credible after steps 1-5 are cleared with evidence.

### Worked Example

Symptom: a triage agent closed three tickets as "resolved" without verifying the fix was deployed.

Walking the procedure against the trace for run R-124:

| Step | Evidence in the trace | Verdict |
|---|---|---|
| 1 Persona | Tone and stance match the system prompt; no over-apology, no wrong refusal. | Not persona. |
| 2 Operating rules | The agent's "report done" step has no verification substep; the rules file says "report the result" but not "confirm the change is live." | **Hit.** Layer is operating rules. |
| 3 Context/memory | The deployment-status fact was in memory and was retrieved correctly. | Not context. |
| 4 Tool preference | The agent had and used the deploy-status tool on other runs; it was available here too. | Not tool preference. |
| 5 Tool policy | No tool was blocked. | Not policy. |
| 6 Runtime/model | Not reached. | — |

Diagnosis: operating rules, not persona and not model. Fix: add one rule under Verification ("after reporting a fix, confirm it is live before marking resolved"). Add the regression case `regression/unverified-resolved` before the fix ships. Verify by replaying R-124 and confirming the agent now calls the deploy-status tool before resolving.

The trap this procedure prevents: rewriting the persona or swapping the model for what was, in fact, a missing one-line operating rule.

## Triage: Investigate, Tune, or Migrate

Not every surprise is a tweak. Before reaching for a fix, classify the response:

| Signal from the evidence | Response | Where it lives |
|---|---|---|
| One layer, one run, reproducible | **Tune** — targeted one-change fix | `tweaking-live-agents.md` |
| Pattern across runs, same layer | **Investigate then tune** — confirm the bucket, then fix once for all | this file + `tweaking-live-agents.md` |
| Multiple layers implicated at once | **Investigate** — do not patch; find the common cause | this file |
| Authority, trust boundary, or scope must change | **Migrate** — re-architect, do not tune | Migration Triggers below |
| Same bucket recurs after multiple fixes | **Migrate** — the design is asking too much of one layer | Migration Triggers below |

The costly mistake is tuning when the evidence actually calls for migration: the team ships five narrow prompt edits for what was always one authority-boundary change.

## Migration Triggers

Re-architect rather than tune when:

- A read-only agent now needs write authority.
- One agent has grown two workloads with different trust boundaries.
- Context-heavy work repeatedly crowds out the main conversation.
- Premium models are used for mechanical work that workers could handle.
- Policy changes are becoming broad enough to change the agent's fundamental authority.

Tune when the issue maps cleanly to one layer and a targeted fix can be tested.

## Weekly Operating Checklist

1. Review failed runs, high-cost runs, and unusually long runs.
2. Check tool-error and permission-denial trends.
3. Sample one successful run for qualitative drift.
4. Verify scheduled jobs or event handlers actually fired.
5. Review new memories or knowledge updates for stale, duplicate, or unsafe content.
6. Confirm model deprecation notices and provider status have not changed your risk.

### From Checklist to Pattern Detection

The weekly checklist's real output is not "we checked." It is a small set of recurring patterns that, once seen, become the input to the self-improvement loop. Keep a lightweight operating journal: one line per surprising run, tagged with the layer from the layer map. After a few weeks the journal reveals the bucket that deserves a fix, an eval case, or a design change — instead of reacting to incidents one at a time.

A journal that never produces a consolidation candidate means either the agent is perfect (unlikely) or the checklist is not being done honestly. The `self-improvement-loop.md` reference owns what happens next.
