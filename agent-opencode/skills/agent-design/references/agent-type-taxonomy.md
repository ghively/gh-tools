> Last verified: 2026-07. Agent product categories and flagship examples change quickly; re-check vendor docs and public product pages before treating this taxonomy as market-complete.

# Agent Type Taxonomy — Production Shapes in 2026

Agent design starts by naming the kind of system you are building. The same ReAct loop can appear as a coding CLI, a customer support bot, or a scheduled background worker, but each type has different latency, safety, cost, and UX constraints.

## Quick Matrix

| Agent type | Defining traits | Canonical examples | Best-fit patterns |
|---|---|---|---|
| Coding copilot / CLI agent | Reads and edits code, runs tests, uses shell/filesystem tools, works in a project workspace | Claude Code, Claude Agent SDK apps, OpenAI Codex-style CLIs, IDE agents | ReAct, tool-use, orchestrator-worker, graph state machine for gated changes |
| Autonomous background worker | Runs from queues, schedules, webhooks, or tickets; may operate without a human in the loop | Triage bots, report generators, inbox processors, ops remediators | Workflow first, planner-executor, graph state machine, memory-augmented |
| Deep-research agent | Searches, reads, verifies, synthesizes, cites; long horizon and source-heavy | Research mode products, analyst agents, due-diligence agents | Orchestrator-worker, reflection/evaluator, memory-augmented |
| Computer-use / browser agent | Operates GUIs or browsers where APIs are unavailable; observes pixels/DOM and acts | Browser-use agents, desktop automation agents, RPA-with-LLM systems | ReAct, tool-use, graph state machine with human gates |
| Voice agent | Real-time speech turn-taking with low latency and interruption handling | Phone support agents, meeting assistants, voice concierges | Tool-use, workflow router, ReAct only for open-ended turns |
| Embedded deterministic pipeline | LLM steps inside an otherwise coded process; product feature, not chatbot | Extraction/classification workflows, review gates, document processors | Workflow, structured outputs, evaluator-optimizer |
| Customer-facing chat agent | Handles users directly, often with retrieval and account tools | Support chat, sales assistant, product help bot | Router + ReAct specialists, retrieval, evaluator gates |
| Multi-agent fleet | Multiple specialized agents coordinate through delegation or shared state | Code-review panels, research swarms, enterprise automation fleets | Orchestrator-worker, review panel, graph state machine |

## Coding Copilots and CLI Agents

**Defining traits:** broad workspace authority, iterative tool use, long task horizons, and a high need for external verification. These agents do not just answer; they inspect files, edit, run commands, and report evidence.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Approval gates for destructive commands, scoped filesystem access, deterministic hooks for never-run operations |
| Latency | Users tolerate multi-minute work if progress is visible and final proof is strong |
| Cost | Use subagents selectively; cache stable project context; right-size model for search vs edit vs review |
| Correctness | No self-reported success; require diffs, test output, command exit codes |

**Pattern fit:** ReAct for exploratory coding, tool-use for file/search/shell operations, orchestrator-worker for parallel investigation, graph state machines for release workflows with approvals.

## Autonomous Background Workers

**Defining traits:** triggered by events rather than conversation. They often run unattended, so failure policy matters more than personality.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Prefer read-only or draft-only operation; escalate irreversible actions |
| Latency | Queue latency matters less than reliability; batch where possible |
| Cost | High volume demands cheap default models and deterministic code for mechanical steps |
| Correctness | Idempotency keys and durable execution are mandatory for side effects |

**Pattern fit:** deterministic workflow first, with LLM functions for classification/summarization. Use graph state machines when the worker needs retries, checkpoints, or human approval.

## Deep-Research Agents

**Defining traits:** search/read/synthesize loops, source diversity, citation requirements, and long context pressure.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Treat fetched text as data, not instructions; source verification pass required |
| Latency | Long runtimes are acceptable only with staged progress and resumable notes |
| Cost | Parallel search is expensive; cap fan-out and summarize aggressively |
| Correctness | Require source-grounded claims and a final contradiction check |

**Pattern fit:** orchestrator-worker for independent source exploration, evaluator-optimizer for claim checking, memory-augmented notes for long runs.

## Computer-Use and Browser Agents

**Defining traits:** operate through fragile interfaces instead of stable APIs. They observe UI state, click/type/navigate, and must recover from layout drift.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Never allow unapproved purchase, send, delete, or credential-change actions |
| Latency | Visual perception and step-by-step UI actions are slow |
| Cost | Avoid UI automation when an API, MCP server, or CLI exists |
| Correctness | Add state assertions after every critical UI action |

**Pattern fit:** ReAct over browser/computer tools, with graph-state checkpoints around login, selection, preview, and apply stages.

## Voice Agents

**Defining traits:** speech input/output, real-time interruption, partial utterances, and strict turn latency.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Confirm before account changes, external sends, purchases, or private data disclosure |
| Latency | Tool calls and long reasoning must be hidden behind short acknowledgements or deferred follow-up |
| Cost | Streaming speech plus LLM calls can multiply spend; route simple intents to deterministic handlers |
| Correctness | Repeat critical details back before acting |

**Pattern fit:** deterministic intent router first, tool-use for known tasks, ReAct only for open-ended conversations.

## Embedded Deterministic Pipelines

**Defining traits:** the user may not perceive an "agent" at all. The LLM is a bounded step inside product code.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Keep control flow in code; schemas and validators around model output |
| Latency | Usually synchronous product latency; budget per step |
| Cost | Optimize prompts, cache stable prefixes, batch offline jobs |
| Correctness | Golden evals and regression cases are easier here than in open-ended agents |

**Pattern fit:** structured outputs, evaluator-optimizer when quality criteria are explicit, graph state machine if the pipeline is long-running.

## Customer-Facing Chat Agents

**Defining traits:** direct user interaction, support/sales/product workflows, retrieval, account lookups, and brand-risk constraints.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Strong injection defense, tool policy by account scope, escalation for sensitive actions |
| Latency | Users expect fast first response; defer slow research |
| Cost | High volume requires routing to cheapest capable model |
| Correctness | Retrieval freshness and source attribution matter more than cleverness |

**Pattern fit:** router workflow plus ReAct specialists, retrieval-augmented generation, evaluator gates before externally visible actions.

## Multi-Agent Fleets

**Defining traits:** multiple roles, separate contexts, delegated work, shared state or message passing, and synthesis.

**Design constraints:**

| Constraint | Design implication |
|---|---|
| Safety | Per-agent tool policy; do not copy one permissive policy everywhere |
| Latency | Parallelism helps wall-clock but increases total token spend |
| Cost | Fan-out must be capped and justified by independence of subtasks |
| Correctness | Require proof contracts; verify worker outputs before synthesis |

**Pattern fit:** orchestrator-worker for decomposition, review panels for independent judgment, graph state machines for persistent coordination.

## Selection Rules

1. If the process has fixed steps, design a workflow or embedded deterministic pipeline before calling it an agent.
2. If a human is waiting synchronously, latency and progress UX are design requirements, not implementation details.
3. If the agent can affect external state, design the approval and idempotency story before tool schemas.
4. If the task needs many sources or much context, decide whether to compress, retrieve, or split into subagents before the first run.
5. If the system has multiple agents, name why each role needs separate context, tools, or authority.

## Sources

- LangChain agents documentation: https://docs.langchain.com/oss/python/langchain/agents
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- Anthropic context-window and effective-agent guidance: https://docs.anthropic.com/en/docs/build-with-claude/context-windows
- LlamaIndex agent workflow docs: https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/
