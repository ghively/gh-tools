# Agent Framework Landscape — July 2026

> Last verified: 2026-07. Version numbers and GA/deprecation status are the fastest-rotting
> facts here — check PyPI/npm and each project's changelog before quoting a version.

Every framework below is a variation on one loop: an LLM sees state, decides an action
(tool call, hand-off, answer, stop), the action executes, the result feeds back as new
state. Frameworks differ in **how explicit that loop is** (graph you control vs.
abstraction you configure) and **what ships in the box** (tools, sessions, sandboxes,
optimizers). Prototype a raw tool-call loop first; adopt a framework when its abstraction
earns its cost (Anthropic's "Building Effective Agents" finding: the most reliable
implementations were simple prompt chains, not framework-heavy stacks).

## The landscape table

| Framework | Orchestration model + maturity (2026-07) | Local/open-model story |
|---|---|---|
| **LangGraph** (`langgraph` 1.2.x) | Explicit graph: nodes/edges + typed state; checkpointing + HITL interrupts. MIT; 1.0 GA Oct 2025, stable 1.x line. **`langgraph.prebuilt.create_react_agent` is deprecated** — the prebuilt path is now `langchain.agents.create_agent` (`langchain` v1, adds middleware: retries, HITL, PII, subagents), which compiles to a LangGraph graph | `ChatOllama` (`langchain-ollama`) or `ChatOpenAI(base_url=...)` at any OpenAI-compatible endpoint |
| **LlamaIndex** (`llama-index` 0.14.x) | Event-driven async Workflows (standalone `llama-index-workflows` pkg since "Workflows 1.0"); prebuilt `FunctionAgent`/`ReActAgent`/`CodeActAgent` + `AgentWorkflow` multi-agent handoffs sharing a `Context`. MIT. 0.13 removed the legacy `AgentRunner` classes | `llama-index-llms-ollama`, or `OpenAILike` at any compatible endpoint |
| **CrewAI** (`crewai` 1.15.x) | Role-based **Crews** (autonomous delegation) + **Flows** (`@start`/`@listen`/`@router` event-driven control); a Crew embeds in a Flow step. Docs now lead with Flows + declarative JSONC crew configs as the production pattern; classic `Agent`/`Task`/`Crew` Python API remains current. MIT; Python >=3.10,<3.14 | `LLM(model="ollama/<name>", base_url=...)` — LiteLLM-style provider prefixes |
| **Microsoft Agent Framework** (`agent-framework` 1.10.x py / `Microsoft.Agents.AI` 1.13.x .NET) | Unified successor **merging AutoGen + Semantic Kernel**: ChatAgents + graph-based Workflows, native MCP + A2A. MIT; **GA 1.0 April 2026**; AutoGen & SK in maintenance mode; community fork **AG2** continues independently | OpenAI-compatible chat client with custom `base_url` (Ollama, vLLM, Foundry Local) |
| **OpenAI Agents SDK** (`openai-agents` 0.18.x py / `@openai/agents` 0.13.x TS) | Lightweight loop: `Agent` + `Runner`, **handoffs** (agent-to-agent delegation), **guardrails** (parallel validators), sessions, tracing, realtime/voice. Successor to the archived Swarm experiment. MIT; still pre-1.0 | Good despite the name: custom `AsyncOpenAI(base_url=...)` client, `openai-agents[litellm]`, or the any-llm extra — 100+ providers incl. Ollama |
| **Pydantic AI** (`pydantic-ai` 2.x) | Single type-safe `Agent` with typed `output_type`, decorated tools, dependency injection — "FastAPI feeling for GenAI." v2 (June 2026) adds **capabilities** (bundled instructions+tools+hooks) and a harness layer; first-class **durable execution** (Temporal/DBOS/Prefect/Restate). MIT | Model-agnostic core (OpenAI/Anthropic/Google); Ollama via `OpenAIChatModel` + custom provider `base_url` |
| **smolagents** (HF, `smolagents` 1.26.x) | Minimalist (~1k LOC core). Flagship **CodeAgent**: the agent writes Python code as its actions instead of JSON tool calls; `ToolCallingAgent` for the classic shape; sandboxing via local executor, E2B, Modal, Docker, or Pyodide/WASM (`executor_type=`). Apache-2.0 | Best-in-class: `TransformersModel` (in-process), `InferenceClientModel`, `LiteLLMModel`, OpenAI-compatible — local is a first-class citizen |
| **Google ADK** (`google-adk` 2.4.x) | Code-first `LlmAgent` + deterministic workflow agents (`Sequential`/`Parallel`/`Loop`); **2.0 (May 2026, breaking)** adds a graph Workflow Runtime (fan-out/fan-in, retries, HITL) and a Task API; A2A protocol for cross-agent interop. Apache-2.0; Python/Go/Java/TS | Gemini-first; other/local models via the `LiteLlm` wrapper (Ollama, vLLM) or LangChain4j (Java) |
| **Claude Agent SDK** (`claude-agent-sdk` 0.2.x py / `@anthropic-ai/claude-agent-sdk` 0.3.x TS) | The **Claude Code harness as a library**: managed loop + built-in tools (Read/Write/Edit/Bash/Glob/Grep/Web), MCP, hooks, subagents, sessions/resume/fork, permission system. You host it; it spawns the bundled CLI as a subprocess. See `claude-agent-sdk.md` | **None** — Claude models only (first-party API, Bedrock, Vertex, Foundry) |
| **DSPy** (`dspy` 3.2.x) | Not an orchestrator — a *programming model*: typed `Signature`s + `Module`s (`Predict`, `ChainOfThought`, `dspy.ReAct`) compiled by **optimizers** (MIPROv2, GEPA, BootstrapFewShot) against a metric instead of hand-written prompts. MIT | `dspy.LM` rides LiteLLM: `ollama_chat/<model>` or any OpenAI-compatible `api_base` |
| **NVIDIA NeMo Agent Toolkit** (`nvidia-nat` 1.8.x, CLI `nat`) | Framework-**agnostic** wrapper: treats LangGraph/CrewAI/LlamaIndex/Semantic Kernel agents as composable function calls, adding profiling, eval, observability, and an MCP front end. NOT an orchestration runtime. Apache-2.0; renamed AgentIQ → AIQ Toolkit → NeMo Agent Toolkit (old package names are transitional shims) | Docs cover NIM/vLLM/OpenAI-compatible; Ollama works via `_type: openai` at its `/v1` endpoint (wire-compatible, not NVIDIA-tested) |

## Decision table (need → framework)

| Your dominant need | Reach for |
|---|---|
| Full branching/retry/HITL control over the loop; resumable graphs | **LangGraph** (hand-built `StateGraph`) |
| Standard tool-calling agent in the LangChain ecosystem, minimal code | **`langchain.agents.create_agent`** (LangGraph under the hood) |
| Agent over your document/RAG stack; event-driven steps | **LlamaIndex** (`FunctionAgent` / Workflows) |
| Quick role-based multi-agent demo | **CrewAI Crews** |
| Precise step sequencing with occasional autonomous pockets | **CrewAI Flows** (or LangGraph) |
| Migrating off AutoGen or Semantic Kernel; .NET shop; Azure-native | **Microsoft Agent Framework** |
| OpenAI-ecosystem app wanting handoffs + guardrails with near-zero framework weight | **OpenAI Agents SDK** |
| Type-safe structured outputs, DI, testability; durable execution via Temporal | **Pydantic AI** |
| Agent whose actions are code (data wrangling, computation-heavy); strongest local-model support; minimal core you can read in an afternoon | **smolagents** (CodeAgent) |
| Gemini/GCP-native, A2A interop, Java or Go teams | **Google ADK** |
| Coding/filesystem/shell agent on Claude; batteries-included harness with permissions, sessions, subagents | **Claude Agent SDK** (see `claude-agent-sdk.md`) |
| Prompts tuned by data against a metric, not by hand | **DSPy** (see `dspy-msaf-nemo-quickstarts.md`) |
| Profiling/eval/observability over an existing multi-framework stack | **NeMo Agent Toolkit** (wraps, doesn't replace) |
| A 50-line script with one model and three tools | **No framework** — a raw tool-call loop over the provider SDK |

Second-order tiebreakers when two rows fit:

- **Local-model requirement** disqualifies the Claude Agent SDK and penalizes Google ADK
  (wrapper-only); smolagents > LangGraph > everything else for local-first work — and read
  `local-model-pitfalls.md` before committing to any of them.
- **Team's existing stack** beats marginal feature differences: LangChain shop → LangGraph;
  .NET → MS-AF; Pydantic-heavy FastAPI codebase → Pydantic AI; GCP → ADK.
- **Pre-1.0 risk**: OpenAI Agents SDK and Claude Agent SDK are still 0.x — expect breaking
  changes per minor version; pin versions and read changelogs on upgrade.
- **Determinism requirements** (exactly-once side effects, workflow-grade retries) point to
  Pydantic AI + Temporal or moving the control flow out of the agent entirely — see the
  `deterministic-agents` skill.

## Churn log — what changed recently (why your memory may be stale)

- `langgraph.prebuilt.create_react_agent` **deprecated** in LangGraph 1.0 (removal planned
  for 2.0); `langchain.agents.create_agent` is the replacement. `MemorySaver` is now an
  alias of `InMemorySaver`; SQLite/Postgres checkpointers live in separate packages.
- **Microsoft**: `microsoft/autogen` and Semantic Kernel are maintenance-mode; Microsoft
  Agent Framework 1.0 GA'd April 2026 and is the target for new work. AG2 is an
  unaffiliated community fork of AutoGen — three different things, one word ("AutoGen").
- **LlamaIndex 0.13** deleted the legacy `AgentRunner`; Workflows were extracted to a
  standalone package; Query Pipelines deprecated.
- **Pydantic AI** went 1.0 GA Sept 2025 and **2.0 stable June 2026** (capabilities, leaner
  core with provider extras).
- **Google ADK 2.0** (May 2026) is a breaking release: new agent API, event model, session
  schema.
- **NVIDIA**: AgentIQ → AIQ Toolkit → **NeMo Agent Toolkit** (`nvidia-nat`); same API,
  three names in two years — old tutorials reference dead package names.
- **OpenAI**: Swarm (experimental) archived → **Agents SDK** is the production successor.
- **Anthropic**: "Claude Code SDK" renamed → **Claude Agent SDK**; `ClaudeCodeOptions` →
  `ClaudeAgentOptions`; default system prompt and filesystem-settings loading removed.

The meta-lesson: framework knowledge has a ~6-month half-life. Skills and docs you write
should pin versions and record verification dates; agents you build should not hard-depend
on prebuilt helpers that a framework has already marked deprecated.

## Reading the table honestly

- **Overlap is huge.** Every row can build a ReAct-style tool-calling agent. The
  differentiators are the second features: state graphs (LangGraph), data connectors
  (LlamaIndex), role ergonomics (CrewAI), typed outputs (Pydantic AI), code-as-action
  (smolagents), built-in computer-use tools (Claude Agent SDK), optimizers (DSPy).
- **Framework choice is stage 7, not stage 1.** Design the agent first (scope, task
  decomposition, pattern, tool surface, decision boundaries, failure modes — see the
  `agent-design` skill), then run this table against the requirements.
- **You can mix.** NeMo-AT profiles across frameworks; MCP tools are portable across
  most of these; DSPy-optimized prompts can be pasted into any framework's system prompt.

Primary sources: LangGraph — https://docs.langchain.com/oss/python/langgraph/overview ;
LlamaIndex agents — https://developers.llamaindex.ai/python/framework/understanding/agent/ ;
CrewAI — https://docs.crewai.com ; MS Agent Framework —
https://learn.microsoft.com/en-us/agent-framework/overview/ ; OpenAI Agents SDK —
https://openai.github.io/openai-agents-python/ ; Pydantic AI — https://ai.pydantic.dev ;
smolagents — https://huggingface.co/docs/smolagents ; Google ADK —
https://google.github.io/adk-docs/ ; Claude Agent SDK —
https://docs.claude.com/en/api/agent-sdk/overview ; DSPy — https://dspy.ai ; NeMo-AT —
https://docs.nvidia.com/nemo/agent-toolkit/latest/ ; Anthropic "Building Effective
Agents" — https://www.anthropic.com/research/building-effective-agents .
