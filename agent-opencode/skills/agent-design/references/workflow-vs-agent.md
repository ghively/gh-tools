# Workflow vs Agent — The Deterministic-First Decision Tree

> Last verified: 2026-07. The definitions are stable; what goes stale is the product examples and the exact framing in Anthropic's guidance — re-check [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) if citing it verbatim.

The most consequential design decision in this pillar: **who owns control flow — your code, or the model?**

- **Workflow:** LLMs and tools orchestrated through *predefined code paths*. Code decides what happens next; the LLM fills in steps.
- **Agent:** the LLM *dynamically directs its own process and tool usage*, deciding at runtime what to do next.

(Definitions from Anthropic's [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents).) Anthropic's core guidance, verbatim in spirit: find the simplest solution possible, and only increase complexity when needed — for many applications, *optimizing single LLM calls with retrieval and in-context examples is usually enough*. Agents trade latency, cost, and variance for better performance on genuinely open-ended tasks. Their consistently reported finding: the most reliable production implementations were simple, composable patterns — not framework-heavy autonomous stacks.

**The deterministic-first rule:** every workload starts as a candidate script. It has to *earn* each step up the ladder by failing a concrete test below. The burden of proof is always on the more agentic option.

## The escalation ladder

```
1. Script                    code only — no LLM anywhere
2. Workflow                  code control flow + LLM inside steps is NOT yet needed,
                             but structure is multi-step (pipelines, ETL, cron jobs)
3. Workflow with LLM steps   code decides the path; LLM classifies / drafts /
                             extracts / summarizes at fixed points
4. Agent                     LLM decides the path; code enforces budgets and gates
5. Multi-agent               multiple LLM deciders coordinating
```

Each rung is roughly an order of magnitude more expensive to run, debug, and trust than the one below it. Never enter the ladder above the lowest rung that passes the tests below — and design so you can fall back a rung, not just climb.

### Rung tests — climb only on a "no"

**Stay at 1 (script)** unless: some step requires judgment over natural language, unstructured data, or fuzzy criteria that you cannot express as code. Parsing JSON, renaming files, calling APIs on a schedule, diffing states — none of this needs a model. An LLM in a pipeline that regex could handle is a reliability downgrade.

**Stay at 2-3 (workflow / workflow with LLM steps)** unless: you *cannot enumerate the steps in advance*. Ask literally: "can I draw this as a flowchart with a fixed set of boxes?" If yes — even with branches, retries, and LLM calls inside boxes — it's a workflow. The five workflow building blocks (from Anthropic, all rung-3):

| Building block | What it does | Use when |
|---|---|---|
| **Prompt chaining** | Sequential LLM calls, each consuming the previous output; add programmatic checks between steps | Task decomposes cleanly into fixed subtasks (draft → critique-gate → translate) |
| **Routing** | Classifier directs input to a specialized handler | Distinct input categories needing different treatment (support ticket types) |
| **Parallelization** | Independent subtasks run simultaneously (sectioning), or the same task runs N times (voting) | Independent sections; or multiple samples raise confidence (safety votes, code review passes) |
| **Orchestrator-workers** | An LLM decomposes dynamically, delegates, synthesizes | Subtasks can't be predefined — the boundary rung; this is where workflow shades into agent |
| **Evaluator-optimizer** | Generator + critic loop against clear criteria, capped | Iteration measurably improves output and a rubric exists |

Building and hardening rungs 1-3 is the `deterministic-agents` skill.

**Stay at 3, don't go to 4 (agent)** unless ALL of these are true:
- [ ] The number and order of steps is genuinely unpredictable — you can't hardcode the path
- [ ] The environment gives **checkable feedback** the model can react to (test results, tool errors, fetched pages) — an agent without feedback is a random walk
- [ ] You can define **success programmatically** (tests pass, ticket resolved, report meets schema) — otherwise you can't eval it (see `agent-evals`)
- [ ] The blast radius of a wrong autonomous decision is bounded — sandboxing, approval gates, and budgets exist (see `agent-safety`)
- [ ] You've accepted the latency/cost/variance tax, and stakeholders have too
- [ ] A rung-3 prototype actually failed — you tried the workflow and watched it be insufficient, rather than assumed it

**Stay at 4, don't go to 5 (multi-agent)** unless: a single agent demonstrably hits a wall — context overflow from workloads that genuinely fan out, need for isolation between trust domains, or parallelism with runtime-determined decomposition. "The task is big" is not a reason; big tasks with static decomposition are rung-3 parallelization. Multi-agent runtime mechanics: `multi-agent-orchestration` skill.

## The decision tree, flattened

```
Can code alone do it reliably?
├─ yes → SCRIPT (rung 1-2). Done.
└─ no → Does judgment occur only at fixed, known points?
    ├─ yes → WORKFLOW WITH LLM STEPS (rung 3).
    │        Pick chaining / routing / parallelization / evaluator blocks.
    └─ no → Can you predict the steps but not their content?
        ├─ yes → planner-executor or graph state machine —
        │        still mostly rung 3 with agentic nodes.
        └─ no (steps themselves unpredictable) →
            Is there checkable feedback + programmatic success + bounded blast radius?
            ├─ no → STOP. Re-scope the task until there is,
            │       or keep a human in the loop at rung 3.
            └─ yes → AGENT (rung 4).
                     One context window not enough, or trust domains differ?
                     ├─ no → single agent.
                     └─ yes → MULTI-AGENT (rung 5), smallest topology that works.
```

## Concrete checklist before you write "agent" in a design doc

1. **Flowchart test:** tried to draw the fixed flowchart and genuinely failed.
2. **Feedback test:** named the signal the model observes after each action (test output, API response, page content).
3. **Success test:** wrote the programmatic success condition down.
4. **Budget test:** set max steps, max tokens/cost per run, and wall-clock timeout.
5. **Blast-radius test:** listed the worst action the agent can take autonomously and confirmed it's survivable (Stage 5 decision matrix in `agent-design-workflow.md`).
6. **Fallback test:** defined what happens when the agent fails — degrade to the rung-3 path or escalate to a human, never silent retry-forever.
7. **Prototype test:** a raw tool-call loop (a few dozen lines against the model API) was tried before any framework was installed.

Fewer than 7 checks? You're building a workflow that thinks it's an agent. That's fine — build the workflow.

## Lessons that keep re-proving this

- **Deterministic parts made deterministic are the reliability you get to keep.** Every step moved from model-decided to code-decided is a step that never hallucinates, never drifts with a model upgrade, and costs nothing to re-run.
- **Hybrid is the production norm.** Real systems are workflows at the top level (code owns the pipeline, budgets, retries, delivery) with agent loops embedded where open-endedness is real (the "fix the failing test" node inside a CI workflow). Design the deterministic shell first, then carve out agentic holes.
- **Agents "succeed" by redefining success.** A loosely-specified agent that fails for weeks will eventually learn to swallow the error and report success. Pin success conditions in code, not in the prompt.
- **The demo-to-production gap is the control-flow gap.** An agent demos better; a workflow ships better. Variance that's charming in a demo is a pager alert in production.
- **Frameworks last.** Per Anthropic: start with LLM APIs directly — many patterns are a few lines of code; frameworks obscure the prompts and responses underneath and "incorrect assumptions about what's under the hood are a common source of error." Framework choice is Stage 7 of the design process, after the ladder rung is chosen.

## When the agent rung is right, commit properly

Deterministic-first is not agent-never. When a task truly is open-ended — a coding agent resolving an issue end-to-end, deep research across unknown sources, computer-use across arbitrary UIs — a rung-3 workflow will be a ceiling, not a floor: you'll encode assumptions the task keeps violating. At that point build the agent deliberately: strong model, consolidated tool surface, explicit budgets, sandbox, evals from day one. Half-hearted agents (agent control flow + workflow-grade guardrails missing) are the worst of both rungs.

## See also

- `agent-patterns.md` — the shapes available at rungs 3-5
- `agent-design-workflow.md` — where this classification happens (Stage 2)
- the `deterministic-agents` skill — building rungs 1-3 well
- the `multi-agent-orchestration` skill — rung 5 mechanics
