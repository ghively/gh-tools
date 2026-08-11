---
name: agent-design
description: "Designing an agent system before writing code: scope, task analysis, architecture patterns, tool surface, decision boundaries, failure modes, and the point where framework choice finally becomes appropriate. Use when a user asks to build, plan, redesign, decompose, or critique an agent. Does not cover framework/implementation choice (see framework-selection), multi-agent runtime mechanics (see multi-agent-orchestration), or deployment (see agent-deployment)."
---

# Agent Design

Agent design is the pre-code discipline. The mistake this skill prevents is skipping straight to a framework, tool list, or model before you know what job the agent owns, which decisions it may make, and what can go wrong.

## When to Use

- A user says "build an agent for..." or asks for an agent architecture.
- A system is bloated, unsafe, too expensive, or too vague and needs redesign.
- You need to decide whether the workload is a workflow, agent, or multi-agent system.
- You need to define an agent's tool surface and authority boundaries.
- You need to critique a proposed agent design before implementation.

**Don't use for:** choosing LangGraph vs CrewAI vs an SDK (`framework-selection` skill), designing inter-agent protocols or fleets (`multi-agent-orchestration` skill), production packaging and rollout (`agent-deployment` skill), the agent runtime loop itself (`agent-harness` skill), or deep prompt/context mechanics (`prompt-context-engineering` skill).

## The Design Doctrine

1. **Never skip to stage 7.** Framework choice is the result of design, not the first design decision.
2. **Start with the job sentence.** "This agent's job is to ___ for ___ on ___." If that sentence is mushy, the agent will be mushy.
3. **Separate deterministic work from agentic work.** Fixed steps belong in code; LLM judgment belongs only where language understanding or open-ended planning is required.
4. **Authority is architecture.** Read-only, draft-only, and full-operator agents are different systems even if their prompts look similar.
5. **Failure modes are requirements.** If you cannot say what happens when a tool fails, context overflows, or fetched content attacks the prompt, the design is incomplete.

## The Mandatory 7-Stage Process

| Stage | Establish | Output |
|---|---|---|
| 1. Scope | What the agent owns, what it does not, who it serves, and where it runs | One-paragraph scope statement |
| 2. Task Analysis | Which operations are deterministic, bounded-reasoning, or open-ended | Task catalog with reasoning classification |
| 3. Architecture Pattern | ReAct, workflow, planner-executor, graph, orchestrator-worker, memory-augmented | Pattern choice with rationale |
| 4. Tool Surface | Data sources and actions, consolidated into task-level tools | Tool catalog with read/write/sensitivity labels |
| 5. Decision Boundaries | What is autonomous, report-after, or escalate-before | Authority matrix |
| 6. Failure Modes | What breaks and how the agent responds | Failure catalog |
| 7. Framework | Only now pick framework/runtime/deployment shape | Framework choice grounded in stages 1-6 |

If the user asks "what framework should I use?" before stages 1-6 are clear, answer with the missing design questions first.

## Workflow vs Agent Triage

| Workload shape | Build as | Why |
|---|---|---|
| Fixed steps, checkable output | Deterministic workflow or script | Cheaper, testable, repeatable |
| Fixed flow with LLM judgment at known points | Workflow with LLM calls | Code owns control flow; model handles bounded judgment |
| Steps unknown until runtime | Agent loop | Model must decide next action dynamically |
| Many independent unknown subtasks | Orchestrator-worker | Separate contexts and parallel work earn their overhead |
| Long-running process with gates/retries | Graph state machine | Explicit state, checkpoints, human interrupts |

Default to the least agentic system that solves the job.

## Pattern Quick Table

| Pattern | Use when | Avoid when |
|---|---|---|
| ReAct | Steps are unpredictable but fit in one context | The process is static or needs exact ordering |
| Tool-use/function-calling | The model needs capabilities with typed inputs | The tool names mirror API endpoints instead of user tasks |
| Planner-executor | A plan can be made up front and executed cheaply | The world changes every step and replanning is constant |
| Evaluator-optimizer | Quality criteria are explicit and iteration improves results | There is no objective pass condition |
| Orchestrator-worker | Subtasks are independent or too large for one context | A for-loop or single skill would suffice |
| Graph state machine | You need branches, retries, HITL, checkpoints | A simple prompt chain is enough |
| Memory-augmented | Useful facts must persist across sessions | Memory would become stale task progress |

## Tool Surface Rules

- One tool per task-level operation, not one tool per API endpoint.
- Label each tool as read-only, write, destructive, external-send, credential-affecting, or spend-affecting.
- Define error behavior before implementation: retry, alternate path, escalate, or fail closed.
- Side-effecting tools need idempotency and approval policy; see `deterministic-agents` and `agent-safety`.

## Requirements Elicitation Map

Do not interrogate the user with every question at once. Cover these dimensions conversationally, then write down the answers that affect architecture.

| Dimension | Ask | Design impact |
|---|---|---|
| User and surface | Who talks to it, and through what interface? | Auth, latency, tone, session model |
| Workload | What jobs must it complete repeatedly? | Task catalog and pattern choice |
| Inputs | What files, APIs, messages, or documents does it read? | Retrieval, context, injection risk |
| Outputs | What artifacts or actions does it produce? | Output contracts and verification |
| Authority | What may it change, send, buy, delete, or deploy? | Tool policy and approval gates |
| Freshness | Which facts must be current? | Research discipline, live lookups, cache TTLs |
| Success | How will we know it worked? | Evals, proof contracts, smoke tests |

If a user cannot answer a dimension, design the safest narrow default and mark the assumption.

## Architecture Completeness Review

Before implementation, the design should answer these questions in writing:

| Question | Incomplete answer smell |
|---|---|
| What exact job does the agent own? | "Help with everything" |
| Which steps are deterministic? | Every step says "LLM decides" |
| What tool calls can change external state? | Tools are listed without read/write labels |
| What can go wrong? | Only model hallucination is mentioned |
| How does it recover? | "The agent retries" with no bound or policy |
| What evidence proves success? | "It says it is done" |
| Which facts can go stale? | No live-check or verification plan |
| Where does state live? | "In the conversation" |

## Agent Type Fit

| If the user is building | Design emphasis |
|---|---|
| Coding/CLI agent | Workspace scope, shell/file authority, proof by tests/diffs |
| Background worker | Idempotency, queue semantics, durable state, alerts — `agent-deployment` skill, scheduled-event-driven reference |
| Deep research agent | Source quality, citation discipline, context isolation |
| Browser/computer-use agent | UI state assertions, approval before irreversible actions — `computer-use-browser-agents.md` |
| Voice agent | Latency, interruption handling, confirmation of critical facts — `voice-multimodal-agents.md` |
| Customer chat agent | Injection defense, retrieval freshness, escalation paths |
| Multi-agent fleet | Delegation contracts, per-agent tool policy, fan-out limits |

Load `agent-type-taxonomy.md` when these constraints materially change the design. When the starting point is an existing Claude Code plugin, the `opencode-authoring` skill's plugin-capability-audit reference derives the target agent type from the plugin's components before this design process begins.

## Minimal Design Artifact

A small but complete design artifact should contain:

```text
Job: This agent's job is to ___ for ___ on ___.
Users/surface: Who uses it and where.
Task split: deterministic / bounded reasoning / open-ended.
Pattern: chosen architecture and why.
Tools: name, purpose, read/write/sensitivity.
Authority: autonomous / report-after / escalate-before.
State: what persists, where, and how it is pruned.
Failure modes: mode, response, user-visible signal.
Verification: smoke tests, proof contract, eval seeds.
Framework: chosen only after the above.
```

If this artifact feels too heavy, the proposed agent is probably underspecified, not "simple."

## Smoke-Test Sequence

Run the first working version through a narrow smoke test before adding capabilities:

This is the **canonical Standard 8** smoke sequence. The contract in
`references/design-artifact-contract.md`, the template at
`assets/foundry-template/smoke.md`, and the `/agent-foundry-smoke-test`
command all reference this list. "Smoke-test additions beyond the
Standard 8" in `design.md` means additions beyond **this** list.

1. **Reachability:** can the user invoke it on the intended surface?
2. **Context inspection:** does it know only the intended rules and memory?
3. **Tool inventory:** does it report the expected tools and authority?
4. **Read path:** can it perform a harmless read/query task?
5. **Write path:** can it draft or apply a low-risk change with verification?
6. **Escalation path:** does it ask before a high-impact action?
7. **Failure path:** does it handle a tool error without looping or fabricating success?
8. **Persistence path:** if memory/state exists, does it survive a session restart?

Do not add more tools until this sequence passes.

## Decision Boundary Matrix

| Action class | Default autonomy | Escalate before |
|---|---|---|
| Search/read/query | Autonomous if scoped | Reading sensitive data outside declared scope |
| Draft unsent content | Autonomous | Legal, medical, financial, or high-brand-risk content |
| Modify local workspace | Autonomous only in approved project scope | Broad rewrites, deletes, permission changes |
| Send externally | Report/draft by default | Any irreversible send or publication |
| Spend money/deploy/delete | Never autonomous by default | Always, unless a written policy says otherwise |

## Reference Router

| Load | When |
|---|---|
| `references/agent-design-workflow.md` | Walking the full seven-stage design process and build sequence |
| `references/agent-patterns.md` | Choosing ReAct, tool-use, planner-executor, evaluator, orchestrator, graph, or memory patterns |
| `references/failure-modes.md` | Building the failure catalog and designing responses |
| `references/requirements-elicitation.md` | Interviewing the user and resolving vague scope |
| `references/system-architecture.md` | Reviewing system shape and architecture completeness |
| `references/design-artifact-contract.md` | Reading/writing `.foundry/` pipeline state — design.md format, status semantics, state.json |
| `references/computer-use-browser-agents.md` | The workload acts through a browser/desktop UI instead of an API |
| `references/human-in-the-loop.md` | Designing approval gates, draft-confirm flows, interrupts, and escalation mechanics |
| `references/voice-multimodal-agents.md` | The surface is spoken audio, or image/document inputs shape the design |
| `references/workflow-vs-agent.md` | Deciding whether an agent is needed at all |
| `references/agent-type-taxonomy.md` | Mapping the design to production agent categories and constraints |
| `references/research-discipline.md` | Knowing when to fetch current docs instead of relying on memory |
| `references/domain-patterns.md` | Worked patterns for three common agent domains — customer-support, RPA, deep-research — covering tool surface, authority floor, eval emphasis, framework fit, and pitfalls |

## Pitfalls

1. **Designing for a framework before requirements are clear.** Fix: force stages 1-6 first, then run `framework-selection` against the resulting requirements.
2. **Skipping threat modeling.** Fix: build the decision-boundary matrix and mark every tool's authority before implementation.
3. **Building one giant agent for a fleet workload.** Fix: split only when subtasks need isolated context, distinct tools, or parallel independent work; otherwise keep one agent.
4. **Building an agent when a deterministic workflow would do.** Fix: classify every task; fixed control flow belongs in code.
5. **Vague persona standing in for architecture.** Fix: persona is voice; architecture is scope, tools, authority, state, and failure behavior.
6. **Memory as a dumping ground.** Fix: store durable facts only; task state belongs in explicit workflow state or working files.
7. **Ignoring current-doc research.** Fix: verify volatile framework/model/API facts before they become build decisions.
8. **No first-week restraint.** Fix: ship one surface and one narrow capability, observe behavior, then expand deliberately.
