# Agent-OpenCode Skill Catalog

Auto-generated index of all skills in the agent-opencode package.

13 skills in 13 pillars.

| Skill | Description |
|---|---|
| `agent-deployment` | Deploying agents to production and operating them there: packaging, serving, session persistence, observability, versioning, rollout, live-agent tuning, and closed-loop improvement. |
| `agent-design` | Designing an agent system before writing code: scope, task analysis, architecture patterns, tool surface, decision boundaries, failure modes, and the point where framework choice finally becomes appro. |
| `agent-evals` | Evaluate and verify agent systems with golden task suites, JSONL eval cases, integration gates, regression tests, trajectory scoring, and eval tooling. |
| `agent-harness` | The agent runtime loop itself — the harness that wraps the model: tool-call dispatch and parallelism, context-window management during a run (compaction, eviction, summarization), session lifecycle (c. |
| `agent-safety` | Agent safety and security hardening: secure agent systems with threat models, least-agency tool policy, sandbox tiers, guardrails, deterministic hooks, MCP/plugin audit practices, and third-party code. |
| `deterministic-agents` | Making agent systems predictable, reproducible, and verifiable: structured outputs and schema-constrained decoding, explicit code-owned control flow, idempotent side effects, durable execution (Tempor. |
| `framework-selection` | Choosing and getting productive in an agent framework or SDK: raw tool-call loops, LangGraph/LangChain, CrewAI, LlamaIndex, Microsoft Agent Framework, Claude Agent SDK, DSPy, Pydantic AI, smolagents, . |
| `memory-rag` | Designing retrieval-augmented generation and agent memory systems: chunking, embeddings, vector and hybrid retrieval, reranking, RAG evaluation, memory backends, and agentic retrieval loops. |
| `model-selection` | Choosing and routing models per task: cloud model matrices, local/open-weight model fit, router architecture, fallback chains, and cost tracking across providers. |
| `multi-agent-orchestration` | Designing systems of multiple agents: orchestrator-worker decomposition, delegation, Claude Code subagents, multi-agent routing, review panels, and agent-to-agent protocol choices. |
| `opencode-authoring` | Authoring OpenCode skills, commands, subagents, permissions, plugins, and MCP registrations, plus porting extensions from other hosts (Claude Code, Cursor, Windsurf) into OpenCode. |
| `prompt-context-engineering` | Engineering what goes into the model: prompts, system prompts, context-window management, long-horizon context, prompt optimization, DSPy optimization, and prompt-injection defense. |
| `tool-mcp-engineering` | Giving agents new capabilities: tool design, choosing skill/script/CLI/MCP/plugin surfaces, MCP server authoring and debugging, and adapting HTTP APIs into MCP servers. |

## Per-Skill Reference Counts

| Skill | Reference files |
|---|---|
| `agent-deployment` | 13 |
| `agent-design` | 13 |
| `agent-evals` | 6 |
| `agent-harness` | 12 |
| `agent-safety` | 9 |
| `deterministic-agents` | 6 |
| `framework-selection` | 12 |
| `memory-rag` | 4 |
| `model-selection` | 5 |
| `multi-agent-orchestration` | 5 |
| `opencode-authoring` | 14 |
| `prompt-context-engineering` | 5 |
| `tool-mcp-engineering` | 5 |

## Commands (Workflow Entry Points)

| Command | What it does |
|---|---|
| `/agent-foundry-build-agent` | Build an agent only from an approved .foundry/design.md, including tools, authority enforcement, evals, and a pinned baseline. |
| `/agent-foundry-cost-audit` | Audit agent token spend and propose routing, caching, context, retry, and model changes with estimated savings. |
| `/agent-foundry-debug-agent` | Debug a live-agent behavior surprise — diagnose from transcript, trace, audit log, and layer map before changing anything. |
| `/agent-foundry-design-agent` | Conduct a seven-stage agent design interview and write an approved .foundry/design.md before implementation. |
| `/agent-foundry-extend-agent` | Extend a deployed agent — add a tool, skill, or behavior; re-run evals and smoke before re-releasing. |
| `/agent-foundry-migrate-agent` | Migrate an agent from one framework to another — freeze behavior with evals, port one path at a time, re-run after each. |
| `/agent-foundry-new-agent` | Run the complete agent-foundry lifecycle from approved design through build, evals, smoke test, security audit, and release gate. |
| `/agent-foundry-new-eval-suite` | Build a golden governance, capability, behavioral, and regression eval suite for an agent. |
| `/agent-foundry-new-mcp-server` | Design and scaffold an MCP server after checking whether an existing server or CLI is simpler. |
| `/agent-foundry-new-skill` | Author an OpenCode skill with trigger-focused frontmatter, concise procedures, linked references, and quality checks. |
| `/agent-foundry-new-subagent` | Author a least-privilege OpenCode subagent with explicit mode, permissions, prompt defense, and output contract. |
| `/agent-foundry-operate-agent` | Operate a deployed agent — verify health, review the audit trail, surface anomalies, decide on tweaks vs incidents. |
| `/agent-foundry-pick-model` | Recommend cloud or local models for a task or agent role using current matrices, routing tiers, cost, privacy, and verification tasks. |
| `/agent-foundry-red-team` | Red-team an agent — adversarial test campaign across jailbreak, injection, privilege-escalation, and exfiltration vectors. Produces regression eval ca |
| `/agent-foundry-refresh-matrices` | Re-verify stale model matrices and framework surveys against live sources and update only verified Last verified banners. |
| `/agent-foundry-review-agent` | Review an existing agent codebase against the seven-stage design doctrine and failure-mode catalog without modifying it. |
| `/agent-foundry-rollback-agent` | Roll back a deployed agent — restore code, prompt, model, tool, memory, and config to the last known-good manifest; verify. |
| `/agent-foundry-security-audit-agent` | Audit an agent project or third-party extension for threats, secret exposure, permissions, injection paths, and unsafe dependencies. |
| `/agent-foundry-ship-check` | Re-verify design approval, build, evals, smoke, audit, safety floor, and operations, then return SHIP or DO-NOT-SHIP. |
| `/agent-foundry-smoke-test` | Run the eight-step live smoke sequence for a built agent and record evidence in .foundry/smoke.md. |