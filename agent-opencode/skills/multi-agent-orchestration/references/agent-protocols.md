> Last verified: 2026-07. Agent interoperability protocols are moving quickly; verify A2A, framework, and SDK docs before claiming production support.

# Agent Protocols and Interop

MCP standardizes how an agent reaches tools, resources, and prompts. For MCP details, see the `tool-mcp-engineering` skill. Agent-to-agent interop is less mature and should be described carefully.

The boundary matters for design: MCP answers "how does *one* agent reach a capability?" while A2A and framework handoffs answer "how do *two* agents cooperate?" A common mistake is reaching for A2A when the real need is just a new MCP tool — if the question is "give my agent a capability," that is MCP; if the question is "let my agent hand a task to a different agent," that is the interop layer this reference covers.

## A2A Status

Google announced Agent2Agent (A2A) in 2025 as an open protocol for agents to discover capabilities, exchange messages, manage tasks, and return artifacts over common web standards. By July 2026 the project is under the `a2aproject` organization, describes JSON-RPC 2.0 over HTTP(S), agent cards, streaming/SSE, push notifications, rich parts, and SDKs. The repository shows a 1.0.x release line, but real production adoption still depends on framework and vendor integrations.

Primary sources: [Google announcement](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/) and [A2A repository](https://github.com/a2aproject/A2A).

### Agent Card (conceptual sketch)

A2A discovery centers on an **agent card** served at a well-known URL: it advertises who the agent is, what it can do, and how to reach it. Based on what the project describes, a card conceptually carries:

- **identity** — name, description, version
- **endpoint** — URL where the agent receives JSON-RPC 2.0 requests
- **capabilities** — which optional transports the agent supports (e.g. streaming/SSE, push notifications)
- **skills** — the tasks the agent advertises it can perform
- **authentication** — how callers must authenticate

```
// Conceptual sketch only — field names evolve with the spec.
// Verify against the A2A repository before implementing.
{
  "name": "travel-booker",
  "description": "Books flights and hotels",
  "version": "1.0.x",
  "endpoint": "https://agent.example.com/a2a",
  "capabilities": { "streaming": true, "pushNotifications": true },
  "skills": [ { "name": "book_flight", "description": "..." } ],
  "authentication": { /* scheme per spec */ }
}
```

Treat the card as a discovery artifact, not a security boundary: a skill advertisement is a claim, and a caller should still scope what it sends to a remote agent the same way it scopes any untrusted endpoint.

### Discovery and task lifecycle (conceptual)

At the protocol level, the flow A2A describes is conceptually: a caller fetches a remote agent's card, sends a JSON-RPC 2.0 task request to the advertised endpoint, and the two sides exchange messages until the task completes and returns an artifact. Streaming/SSE and push notifications are the mechanisms for long-running tasks where the caller should not hold a blocking connection. This is a sketch of the shape the project describes, not a frozen contract — confirm method names, task states, and notification events against the repository before implementing.

| Concept | What it is for |
|---|---|
| Agent card | Discovery: who the agent is and how to reach it |
| Task request | Start a unit of work with the remote agent |
| Message exchange | Back-and-forth needed to complete the task |
| Streaming / push | Progress and completion for long-running tasks |
| Artifact | The deliverable returned when the task finishes |

## Framework Handoffs

| Mechanism | Model | Production posture |
|---|---|---|
| OpenAI Agents SDK handoffs | Agent transfers control to another agent/tool with state | Useful inside OpenAI stack; verify API surface and tracing. |
| CrewAI | `Agent.allow_delegation` + `Agent.delegation` — agents delegate tasks to other agents in a Crew; sequential or hierarchical process types; the Crew shares context across agents. Flows (event-driven stateful ordering) are the production shape — a Crew embeds inside a Flow step | Evaluate delegation semantics; CrewAI delegation is asymmetric (A→B ≠ B→A); Flow state is per-step, not durable by default |
| LangGraph handoff/Command patterns | Graph node returns control updates and next destination | Strong for explicit, durable orchestration in code. |
| Microsoft Agent Framework (MAF) | Enterprise multi-agent abstractions and integrations | Evaluate current SDK maturity and cloud coupling. AutoGen (predecessor) still widely deployed — `GroupChat` + `ConversableAgent` primitives map to MAF's runtime host |
| A2A | Cross-vendor remote agent task protocol | Promising interop standard; verify per implementation. |
| MCP | Tool/resource/prompt transport | Production-ready for tools; not an agent conversation protocol by itself. |

Each handoff style implies a different authority model. In-SDK handoffs (OpenAI Agents SDK, LangGraph) keep control inside one process you own — the state, tracing, and failure handling are yours to design, and the "handoff" is really a node transition. MCP is narrower: it hands an agent *capabilities* (tools/resources/prompts), not conversational control, so it composes cleanly underneath any of the above rather than replacing them. A2A is the only row aimed at cross-vendor remote agents, which is why its posture is "promising but verify per implementation" rather than "ship it today."

### LangGraph: `Command(goto=...)`

In LangGraph a handoff is a node returning a `Command` that carries both the state update and the next destination — control flow lives *in the node*, not in graph edges. Verify field names against the LangGraph docs before shipping (the API is stable but moving).

```python
from langgraph.types import Command
from typing import Literal

def triage_agent(state) -> Command[Literal["billing_agent", "refund_agent"]]:
    decision = classify(state)  # your routing logic
    return Command(
        goto=decision,                       # next node = the agent to hand to
        update={"messages": state["messages"]},  # state carried across the handoff
    )
```

When the target agent lives in a *parent* graph (the handing-off agent is a subgraph), add `graph=Command.PARENT` so LangGraph routes outside the current subgraph:

```python
return Command(goto="sales_agent", update={...}, graph=Command.PARENT)
```

Wrapped as a handoff *tool*, the same `Command` is returned from the tool and must include the triggering `AIMessage` plus a `ToolMessage` in `update["messages"]` to keep the tool-call pairing valid — otherwise the next model call sees an orphaned tool call.

### OpenAI Agents SDK: `handoff()`

The OpenAI Agents SDK (Python package `openai-agents`, imported as `agents`) models a handoff as a tool the SDK auto-generates. List target agents directly, or wrap with `handoff()` for overrides and callbacks:

```python
from agents import Agent, handoff

billing_agent = Agent(name="Billing agent")
refund_agent = Agent(name="Refund agent")

triage_agent = Agent(
    name="Triage agent",
    handoffs=[billing_agent, handoff(refund_agent, on_handoff=log_refund)],
)
```

`handoff()` accepts `tool_name_override`, `tool_description_override`, `on_handoff` (a callback), `input_type` (schema for handoff arguments), `input_filter` (trim what the next agent sees), and `is_enabled`. Control transfers fully to the target agent, which inherits the prior conversation history. Verify the parameter surface against the current SDK docs before relying on any single option.

Both snippets share the property that makes in-SDK handoffs production-safe today: **you own both ends and the whole thing runs in one process you control** — which is exactly the boundary the honest assessment below draws between "commit" and "watch."

## Coordination Models

| Model | Use when | Tradeoff |
|---|---|---|
| Shared state | Agents need a common board, queue, or memory | Concurrency and contamination risks. |
| Message passing | Agents are isolated services | More protocol overhead, clearer boundaries. |
| Orchestrator-mediated | One controller routes and verifies | Bottleneck, but easiest to govern. |
| Peer-to-peer | Agents negotiate directly | Hardest to debug and secure. |

Choosing between them is mostly a governance question. If you need a clear audit trail and a single approval boundary, orchestrator-mediated wins despite the bottleneck. If agents are independently owned services from different teams, message passing keeps boundaries explicit at the cost of protocol work. Shared state is tempting because it feels simple, but concurrency bugs and cross-contamination are exactly the failures that are hardest to reproduce. Peer-to-peer is reserved for cases where no party is willing to be the controller, and you accept that debugging will be painful.

### Choosing a coordination model

| If you need... | Pick... |
|---|---|
| One approval boundary, one audit trail | Orchestrator-mediated |
| Agents owned by different teams/services | Message passing |
| A shared task board many agents read/write | Shared state (with provenance) |
| No central controller and you accept hard debugging | Peer-to-peer |

These compose. A common production shape is orchestrator-mediated *with* a shared state board (the orchestrator owns the board; workers read/write records with provenance). Pure peer-to-peer with no shared state is the hardest to operate and should be a deliberate choice, not an accident.

## Honest Assessment

Production-ready today: explicit orchestrator-worker code, LangGraph-style graphs, MCP tools, and framework-native handoffs where you control both ends. Emerging: cross-vendor A2A ecosystems and fully dynamic agent discovery. Treat open-ended agent marketplaces as untrusted code until audited.

A useful way to frame the choice: the rows you fully control (your orchestrator code, your LangGraph graph, your MCP tools, your in-stack handoffs) are where you should build durable behavior today. The cross-vendor rows (A2A, dynamic discovery, open agent marketplaces) are where you should prototype, track the spec, and avoid making hard production commitments until framework and vendor integrations catch up. The boundary between "use it" and "watch it" is exactly the boundary between "I control both ends" and "I am calling a remote agent I did not build."

### When to commit vs wait

| Situation | Posture |
|---|---|
| Both ends are your code | Commit: use orchestrator code, LangGraph, or in-SDK handoffs |
| You need a tool/capability for one agent | Commit: build/connect an MCP server |
| You must coordinate agents from different vendors | Prototype A2A; do not freeze your API on it yet |
| You want to discover unknown remote agents | Wait: dynamic discovery is still emerging |
| You are offered an open agent marketplace | Treat as untrusted code until audited |

The risk of committing early to an emerging protocol is not just churn — it is that you may build authority and isolation assumptions around a contract that changes, then ship a security boundary that no longer matches the spec. Track these rows, prototype against them, but keep your durable authority logic in the layers you control.


