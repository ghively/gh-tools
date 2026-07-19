> Last verified: 2026-07. LangChain/LangGraph imports, checkpointer packages, and prebuilt-agent helpers have changed recently; verify against current docs before copying into production.

# LangGraph Quickstart — Prebuilt Loop and Hand-Built Graph

LangGraph is the low-level orchestration runtime for explicit state, branches, checkpointing, streaming, and human-in-the-loop control. In current docs, the high-level prebuilt agent path is `langchain.agents.create_agent`; use hand-built `StateGraph` when the graph shape matters.

Primary docs: [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents) and [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview).

A runnable starter lives in this skill's `assets/langgraph-starter/` — a
triage → interrupt-for-approval → act graph with checkpointing, showing the
two features you pick LangGraph for (explicit state machine, durable
human-in-the-loop).

## Install

```bash
pip install -U langchain langgraph
```

Add provider packages as needed, for example `langchain-openai`, `langchain-anthropic`, or `langchain-ollama`.

## Minimal Prebuilt Tool-Calling Agent

```python
from langchain.agents import create_agent
from langchain.tools import tool

@tool
def get_status(service: str) -> str:
    """Return the current status for a named service."""
    return f"{service}: ok"

agent = create_agent(
    model="openai:gpt-5.5",
    tools=[get_status],
    system_prompt="You are a concise operations assistant.",
)

result = agent.invoke({"messages": [{"role": "user", "content": "Check billing"}]})
print(result["messages"][-1].content)
```

For local models, current docs support provider strings such as `ollama:<model>` in the high-level agent API. Local tool calling is more fragile than cloud tool calling; read `local-model-pitfalls.md` before committing to it.

```python
agent = create_agent(model="ollama:qwen3", tools=[get_status])
```

## Add Conversation Persistence

The prebuilt agent accepts a checkpointer. Current docs show `InMemorySaver` from `langgraph.checkpoint.memory` and a `thread_id` in config.

```python
from langchain.agents import create_agent
from langchain_core.utils.uuid import uuid7
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="anthropic:claude-sonnet-4-6",
    tools=[get_status],
    checkpointer=InMemorySaver(),
)

config = {"configurable": {"thread_id": str(uuid7())}}
agent.invoke({"messages": [{"role": "user", "content": "Remember service billing."}]}, config=config)
agent.invoke({"messages": [{"role": "user", "content": "What service did I mention?"}]}, config=config)
```

Use memory checkpointers for demos only. Production persistence belongs in a durable store and must be paired with idempotent side effects; see `deterministic-agents`.

## Hand-Built StateGraph

Use `StateGraph` when you need explicit nodes and edges, not just a generic loop.

```python
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

class TicketState(TypedDict):
    text: str
    route: Literal["refund", "technical", "other"]
    answer: str

def classify(state: TicketState):
    text = state["text"].lower()
    if "refund" in text:
        return {"route": "refund"}
    if "error" in text or "bug" in text:
        return {"route": "technical"}
    return {"route": "other"}

def refund(state: TicketState):
    return {"answer": "I routed this to the refund workflow."}

def technical(state: TicketState):
    return {"answer": "I routed this to technical support."}

def other(state: TicketState):
    return {"answer": "I routed this to general support."}

def choose(state: TicketState):
    return state["route"]

graph = StateGraph(TicketState)
graph.add_node("classify", classify)
graph.add_node("refund", refund)
graph.add_node("technical", technical)
graph.add_node("other", other)
graph.add_edge(START, "classify")
graph.add_conditional_edges("classify", choose)
graph.add_edge("refund", END)
graph.add_edge("technical", END)
graph.add_edge("other", END)
app = graph.compile()

print(app.invoke({"text": "I need a refund", "route": "other", "answer": ""}))
```

## Human-in-the-Loop Shape

Use interrupts around actions where the model may propose but must not execute alone.

```python
from langgraph.types import interrupt

def approve_refund(state: TicketState):
    decision = interrupt({
        "question": "Approve refund?",
        "ticket": state["text"],
    })
    if decision == "approve":
        return {"answer": "Refund approved by human."}
    return {"answer": "Refund not approved."}
```

Exact resume mechanics vary by checkpointer and deployment environment; verify the current interrupt docs before shipping.

## When LangGraph Is the Right Pick

| Need | Use LangGraph? |
|---|---|
| One simple tool-calling loop | Usually use `create_agent` first |
| Explicit branches/retries/checkpoints | Yes |
| Human approval mid-run | Yes |
| Durable long-running workflow | Yes, if paired with durable checkpointer and idempotent tools |
| Role-based multi-agent demo | Maybe CrewAI is faster |
| Document/RAG-heavy app | Maybe LlamaIndex is faster |

## Pitfalls

1. **Using deprecated helpers from old tutorials.** Fix: verify current imports; current docs lead with `langchain.agents.create_agent` for prebuilt agents.
2. **Treating checkpointing as exactly-once execution.** Fix: pair with idempotency keys and effect journals.
3. **Building every branch as an LLM node.** Fix: deterministic classification and routing should be code when possible.
4. **Using local models without measuring tool-call reliability.** Fix: run a tool-call eval suite and read `local-model-pitfalls.md`.
