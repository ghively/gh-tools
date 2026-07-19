# Design: <agent name>

Status: draft
Designed with: /agent-foundry:design-agent

## Job

This agent's job is to <do what> for <whom> on <what surface>.

## Users & surface

Who talks to it, through what interface, with what expectations of latency
and tone. Auth story if the surface is shared.

## Threat model

Who sends input, which inputs are untrusted (fetched pages, file contents,
webhook payloads, other agents), and the worst outcome we accept vs the
worst outcome we must make impossible.

## Task split

| Operation | Class (deterministic / bounded-reasoning / open-ended) | Owner (code / model) |
|---|---|---|
| <operation> | <class> | <owner> |

## Pattern

<chosen architecture> because <rationale>. Ladder rungs rejected below it:
<script / workflow / workflow+LLM steps> — rejected because <reason>.

## Tools

| Tool | Purpose | read/write | Sensitivity |
|---|---|---|---|
| <tool> | <task-level purpose> | <read/write> | <none / external-send / spend / destructive / credential> |

## Authority

| Action class | Autonomy |
|---|---|
| <search/read> | autonomous |
| <draft content> | autonomous / report-after |
| <send / spend / delete / deploy> | escalate-before |
| <never-do operations> | never (deterministic floor, not prompt text) |

## State

What persists (memory, files, DB rows), where it lives, and how it is pruned.
"Nothing persists" is a valid answer — say it explicitly.

## Failure modes

| Mode | Response | User-visible signal |
|---|---|---|
| <tool fails> | <retry policy / alternate / escalate> | <what the user sees> |
| <context overflow> | <compaction / refusal> | <signal> |
| <injected instructions in fetched content> | <content-channel discipline> | <logged where> |

## Verification

Smoke-test additions beyond the Standard 8 (the canonical list lives in
the `agent-design` SKILL.md and the `.foundry/smoke.md` template); the proof contract (what
evidence means "done"); eval seeds (governance cases come from the Failure
modes + Authority tables above).

## Framework, model, deployment

Chosen LAST. Framework: <choice> because <rationale>. Model tier per role:
<main / fan-out / judge>. Deployment shape: <CLI / service / worker /
webhook / scheduled / embedded>.
