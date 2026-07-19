# Framework Build Matrix

The agent-design workflow produces a framework-agnostic design artifact
(`.foundry/design.md` with Tools, Authority, Failure modes, State, and
Verification sections). The build step translates that design into a
concrete implementation in a chosen framework.

This reference shows how each of the 13 harness frameworks implements
the design artifacts. Use it during `/agent-foundry-build-agent` to
scaffold the right shape for the framework the design names.

For framework *selection*, see `SKILL.md`. For framework *deployment*,
see `../../agent-deployment/references/framework-deploy-matrix.md`. This
file is the bridge: design → runnable code in framework X.

## The Design-to-Framework Translation

Every design artifact has these sections. Each framework has a native
shape for each.

| Design section | What the framework provides |
|---|---|
| Tools table | Tool decorators / schemas / function registrations |
| Authority table | Permission rules / hooks / guardrails |
| State spec | Memory / checkpoint / context objects |
| Failure modes | Retry policies / error handlers / fallback chains |
| Verification | Eval hooks / trace inspection / assertions |

The build step's job is one mapping per row. The sections below show
each framework's mapping.

## Per-Framework Build Patterns

### Claude Agent SDK

| Design section | Claude Agent SDK primitive |
|---|---|
| Tools | `@tool` decorator; tool schemas auto-derived from type hints |
| Authority | `permission_mode` (`acceptEdits`, `plan`, `default`, `bypassPermissions`); `allowed_tools` / `disallowed_tools` |
| State | `ClaudeAgent` instance; sessions resumable by `session_id` |
| Failure modes | `max_turns`; SDK-level retry on provider errors; `try/except` around `agent.run()` |
| Verification | `--output-format json` for trajectory capture; OTel export |

```python
from claude_agent_sdk import ClaudeAgent, ClaudeAgentOptions, tool

@tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

agent = ClaudeAgent(
    options=ClaudeAgentOptions(
        model="claude-sonnet-5",
        permission_mode="acceptEdits",
        allowed_tools=["search_tickets", "Read", "Grep"],
        max_turns=15,
    ),
)
result = await agent.run(prompt="...", session_id="...")
```

### OpenAI Agents SDK

| Design section | OpenAI Agents SDK primitive |
|---|---|
| Tools | `@function_tool` decorator; handoffs via `Agent(handoffs=[...])` |
| Authority | Manual: filter tools per agent; use handoffs to gate specialists |
| State | `Runner.run()` returns `RunResult`; local context only — sessions are your job |
| Failure modes | `max_turns` per agent; SDK raises `MaxTurnsExceeded`; you wrap with retry |
| Verification | `RunResult` includes `raw_responses`, `tool_calls`; pair with Langfuse |

```python
from agents import Agent, Runner, function_tool

@function_tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

triage = Agent(
    name="triage",
    model="gpt-5.6-terra",
    tools=[search_tickets],
    handoffs=[specialist],
)
result = await Runner.run(triage, "Find open P1 tickets")
```

### Copilot SDK

| Design section | Copilot SDK primitive |
|---|---|
| Tools | Custom tools registered via `client.tools.register()`; MCP servers via config |
| Authority | Hooks: `pre-tool-use`, `post-tool-use`; agent-level allowed-tools |
| State | Cloud sessions managed by Mission Control; resume by session URL |
| Failure modes | SDK retries on transient; session limits cap runaway |
| Verification | Event stream from `client.session.events()`; OTel export |

```typescript
import { Copilot } from '@github/copilot-sdk';

const copilot = new Copilot({ auth: { type: 'github-app', ... } });
const session = await copilot.sessions.create({ agent: 'my-agent' });
await copilot.tools.register('search_tickets', { ... });
session.on('event', (e) => console.log(e));
await session.prompt('Find open P1 tickets');
```

### Google ADK

| Design section | Google ADK primitive |
|---|---|
| Tools | `FunctionTool` class or `@tool` decorator; `Toolset` for grouped registration |
| Authority | Manual: per-agent tool list; vertex AI safety settings |
| State | `Session` service (in-memory, Postgres, or Vertex AI sessions) |
| Failure modes | `max_turns`; ADK runtime handles retries |
| Verification | Vertex AI traces; `RunResult` includes `events` |

```python
from google.adk import Agent, FunctionTool

@FunctionTool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

agent = Agent(
    name="triage",
    model="gemini-3.1-pro",
    tools=[search_tickets],
    instruction="You triage support tickets...",
)
```

### Microsoft Agent Framework (MAF)

| Design section | MAF primitive |
|---|---|
| Tools | `@agent_tool` decorator; `AgentRuntime` registers tools per agent |
| Authority | `AgentRuntime` host enforces per-agent tool list; conversations have policies |
| State | `AgentRuntime` state; conversations resume by `conversation_id` |
| Failure modes | `max_conversation_turns`; runtime handles retries |
| Verification | Azure Monitor / Application Insights native |

```python
from microsoft.agents import Agent, agent_tool, AgentRuntime

@agent_tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

triage = Agent(name="triage", model="gpt-5.6", tools=[search_tickets])
runtime = AgentRuntime()
runtime.register(triage)
```

### LangGraph

| Design section | LangGraph primitive |
|---|---|
| Tools | `ToolNode` or `@tool` decorator; bind via `llm.bind_tools([...])` |
| Authority | Per-node conditional edges; `interrupt_before` for HITL gates |
| State | TypedDict state flows through graph; checkpointer persists |
| Failure modes | Conditional edges for retry paths; `recursion_limit` on the graph |
| Verification | LangSmith native; `State` snapshot at every node for trajectory |

```python
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.tools import tool
from typing import TypedDict, Literal

@tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

class State(TypedDict):
    query: str
    results: list[dict]
    needs_review: bool

def triage(state: State) -> State:
    results = search_tickets.invoke({"query": state["query"]})
    return {"results": results, "needs_review": any(r["priority"] == "P1" for r in results)}

builder = StateGraph(State)
builder.add_node("triage", triage)
builder.add_node("review", review_node)
builder.add_edge(START, "triage")
builder.add_conditional_edges("triage", lambda s: "review" if s["needs_review"] else END)

graph = builder.compile(
    checkpointer=PostgresSaver(...),
    interrupt_before=["review"],
)
```

### CrewAI

| Design section | CrewAI primitive |
|---|---|
| Tools | `@tool` decorator; tools attached to `Agent` instances |
| Authority | `Agent.allow_delegation`; `Task.tools` filter per task |
| State | `Crew` shares context; `Flow` provides step state |
| Failure modes | `Task.max_iter`; `Crew` raises on max |
| Verification | CrewAI's OTel export; `usage_metrics` on CrewOutput |

```python
from crewai import Agent, Task, Crew, tool

@tool("Search Tickets")
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    return [...]

triage_agent = Agent(
    role="Ticket Triager",
    goal="Find and classify open support tickets",
    tools=[search_tickets],
    max_iter=10,
)
task = Task(
    description="Find open P1 tickets",
    agent=triage_agent,
    expected_output="A list of P1 tickets with severity and assignee",
)
crew = Crew(agents=[triage_agent], tasks=[task])
result = crew.kickoff()
```

### LlamaIndex

| Design section | LlamaIndex primitive |
|---|---|
| Tools | `FunctionTool` wrapper; `QueryEngineTool` for RAG-backed tools |
| Authority | Per-agent tool list; `AgentWorkflow` enforces per-agent tools |
| State | `Context` object passed between agents; durable with `Context(redis_client)` |
| Failure modes | `max_iterations` per agent; workflow step caps |
| Verification | LlamaIndex tracing; OTel via `callback_manager` |

```python
from llama_index.core.agent import FunctionAgent
from llama_index.core.tools import FunctionTool

def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    return [...]

tool = FunctionTool.from_defaults(fn=search_tickets)
agent = FunctionAgent(
    tools=[tool],
    llm=llm,
    system_prompt="You triage support tickets...",
    max_iterations=15,
)
result = await agent.run("Find open P1 tickets")
```

### Pydantic AI

| Design section | Pydantic AI primitive |
|---|---|
| Tools | `@agent.tool` decorator; typed args + return; dependencies via `Deps` |
| Authority | Per-agent tool registration; typed dependencies enforce boundaries |
| State | `RunContext[Deps]`; sessions via `session_id` + external store |
| Failure modes | `UsageLimits(requests=..., total_tokens=...)` |
| Verification | Logfire native; Pydantic validation is the first-line check |

```python
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

@dataclass
class Deps:
    db: Database

agent = Agent("openai:gpt-5.6", deps_type=Deps, system_prompt="...")

@agent.tool
async def search_tickets(ctx: RunContext[Deps], query: str) -> list[dict]:
    """Search the ticket system."""
    return await ctx.deps.db.search(query)

result = await agent.run("Find open P1 tickets", deps=Deps(db), usage_limits=UsageLimits(requests=15))
```

### smolagents

| Design section | smolagents primitive |
|---|---|
| Tools | `Tool` subclass; agent writes Python to call them |
| Authority | `authorized_imports`; sandbox limits; `max_steps` |
| State | Single-run; no built-in session store |
| Failure modes | `max_steps`; Python execution errors caught and surfaced |
| Verification | `agent.write_memory_to_files()`; `agent.logs` for trajectory |

```python
from smolagents import Tool, CodeAgent, LiteLLMModel

class SearchTickets(Tool):
    name = "search_tickets"
    description = "Search the ticket system."
    inputs = {"query": {"type": "string", "description": "The search query"}}
    output_type = "array"

    def forward(self, query: str) -> list[dict]:
        return [...]

agent = CodeAgent(
    tools=[SearchTickets()],
    model=LiteLLMModel(model_id="openai/glm-4.7", api_base="...", api_key=...),
    max_steps=10,
    authorized_imports=["json"],  # narrow!
)
result = agent.run("Find open P1 tickets")
```

### Vercel AI SDK

| Design section | Vercel AI SDK primitive |
|---|---|
| Tools | `tool({ description, parameters, execute })`; passed to `streamText({ tools })` |
| Authority | Manual: per-call tool filter; harness-level checks |
| State | Manual: `messages` array managed by your code |
| Failure modes | `maxSteps` on `streamText` / `generateText` |
| Verification | OTel via `experimental_telemetry`; `toUIMessageStream` for UI |

```typescript
import { generateText, tool } from 'ai';
import { z } from 'zod';

const result = await generateText({
  model: openai('gpt-5.6'),
  maxSteps: 15,
  tools: {
    searchTickets: tool({
      description: 'Search the ticket system.',
      parameters: z.object({ query: z.string() }),
      execute: async ({ query }) => db.search(query),
    }),
  },
  messages: [{ role: 'user', content: 'Find open P1 tickets' }],
});
```

### Mastra

| Design section | Mastra primitive |
|---|---|
| Tools | `createTool({ id, description, execute })`; registered on agent |
| Authority | Per-agent tool list; workflow step gating |
| State | `MastraMemory` for cross-run; workflow `State` for in-run |
| Failure modes | `maxSteps` per agent; workflow step caps |
| Verification | OTel; Mastra's own dashboard |

```typescript
import { Mastra } from '@mastra/core';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const searchTickets = createTool({
  id: 'search-tickets',
  description: 'Search the ticket system.',
  inputSchema: z.object({ query: z.string() }),
  execute: async ({ context }) => db.search(context.query),
});

const agent = new Agent({
  name: 'triage',
  instructions: 'You triage support tickets.',
  model: openai('gpt-5.6'),
  tools: { searchTickets },
  maxSteps: 15,
});
```

### Custom Provider-SDK Loop (custom loop)

| Design section | Custom loop primitive |
|---|---|
| Tools | Plain Python/TS functions; JSON Schema for the model |
| Authority | Your code; check before dispatch |
| State | Your dataclass / context object |
| Failure modes | Your retry/circuit-breaker |
| Verification | Your span emitter |

```python
TOOLS = {
    "search_tickets": {
        "description": "Search the ticket system.",
        "schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "fn": lambda query: db.search(query),
    }
}

async def run_agent(prompt, max_steps=15):
    messages = [{"role": "user", "content": prompt}]
    for step in range(max_steps):
        response = await client.chat.completions.create(
            model="glm-4.7",
            messages=messages,
            tools=[{"type": "function", "function": t} for t in TOOLS.values()],
        )
        # ... dispatch tool calls, append results, check stop conditions
```

## Mapping Common Design Patterns

### HITL Gate

| Framework | How to implement an approval gate |
|---|---|
| Claude Agent SDK | `permission_mode: "default"` + `PreToolUse` hook |
| OpenAI Agents SDK | Hand off to a `human_approval` agent; resume on verdict |
| Copilot SDK | `pre-tool-use` hook; agent pauses |
| LangGraph | `interrupt_before=["approve"]`; resume via `update_state` |
| CrewAI | `human_input=True` on the task |
| MAF | `UserProxyAgent` in the conversation |
| Custom loop | Pre-dispatch check; await async verdict |

### Read-Only Specialist

| Framework | How to enforce read-only |
|---|---|
| Claude Agent SDK | `allowed_tools=["Read", "Grep", "Glob"]` |
| OpenAI Agents SDK | Only register read tools on the agent |
| LangGraph | Conditional edge skips write tools |
| CrewAI | `Task.tools` filtered to read-only |
| Pydantic AI | Type system: `Deps` only exposes read methods |
| Custom loop | Tool registry filtered; safety floor blocks writes |

### Cost-Capped Run

| Framework | How to cap cost |
|---|---|
| Claude Agent SDK | `max_turns` + provider billing alerts |
| OpenAI Agents SDK | Wrap `Runner.run()` with token counter |
| LangGraph | `recursion_limit` + checkpointer to resume |
| Pydantic AI | `UsageLimits(total_tokens=...)` |
| Custom loop | Per-step budget check; abort on overrun |

## Per-Framework Scaffolds

For each framework, the build step should copy the matching starter scaffold
from `framework-selection/assets/` (when present) and adapt it. Current
starters ship for: Claude Agent SDK (Python + TS), LangGraph.

For frameworks without a starter asset, copy the per-framework code block
above into `src/agent.py` (or `src/agent.ts`) and adapt the system prompt,
tool list, and authority gates from `design.md`.

## Common Build Pitfalls (Across Frameworks)

1. **Tools wider than the design.** The framework makes it easy to add
   tools; the design said two; you ship ten. Fix: register only the
   tools named in the design's Tools table.
2. **No HITL gate on destructive tools.** The framework supports it but
   you skipped the wiring. Fix: every destructive tool goes through a
   pre-tool interrupt or conditional edge.
3. **Default model alias in production.** `model="gpt-5.6"` instead of
   the pinned version. Fix: pin full model IDs in the built agent;
   treat the version as a release artifact.
4. **In-process session state.** Works in dev; dies on restart. Fix:
   wire the framework's external session store before the first
   production deploy.
5. **No step cap.** "The model knows when to stop" — until it doesn't.
   Fix: `max_steps` / `max_turns` / `max_iter` on every agent.
6. **Tool schemas drift from the spec.** The design said `search(query:
   str)`; the built tool takes `search(q: str)`. Fix: lock tool names
   and argument names in the eval suite; CI fails on drift.

## See Also

- `../../agent-deployment/references/framework-deploy-matrix.md` — per-
  framework Docker recipes (the deploy counterpart to this build
  reference).
- `../../agent-evals/references/framework-eval-matrix.md` — per-framework
  eval patterns and trajectory capture.
- `../../agent-safety/references/framework-safety-matrix.md` — per-
  framework tool policy, hooks, and permission enforcement.
- `../../agent-harness/references/harness-comparison.md` — the
  framework-by-framework coverage matrix for the 9 harness concerns.
- `framework-landscape.md` — the framework comparison and churn log.
