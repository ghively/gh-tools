#!/usr/bin/env python3
"""Minimal LangGraph agent: triage -> (interrupt for approval) -> act.

The shape to keep: state as a typed dict, LLM judgment confined to named
nodes, the approval gate as a real interrupt (checkpointed, resumable), and
the action node executing only what was drafted and approved.
"""
import argparse
import sys
import uuid
from typing import Literal, TypedDict

from langchain_anthropic import ChatAnthropic
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

llm = ChatAnthropic(model="anthropic:claude-sonnet-4-6")


class State(TypedDict, total=False):
    request: str
    draft_action: str      # what the agent proposes to do
    needs_approval: bool
    approved: bool
    result: str


def triage(state: State) -> State:
    """LLM step: classify the request and draft the concrete action."""
    msg = llm.invoke(
        "You triage requests for an operations agent. For the request below, "
        "draft the ONE concrete action you would take (imperative, specific), "
        "then on a new line write RISKY if the action is destructive, "
        "external-facing, or spends money, else SAFE.\n\n"
        f"Request: {state['request']}"
    )
    text = msg.content if isinstance(msg.content, str) else str(msg.content)
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return {
        "draft_action": "\n".join(lines[:-1]) or text,
        "needs_approval": lines[-1].strip().upper().startswith("RISKY"),
    }


def route(state: State) -> Literal["approve", "act"]:
    return "approve" if state["needs_approval"] else "act"


def approve(state: State) -> State:
    # The graph interrupts BEFORE this node (interrupt_before below). By the
    # time this body runs, a human has resumed the thread with a verdict
    # injected via update_state. Fail closed if somehow absent.
    if not state.get("approved"):
        return {"result": "DECLINED — action not taken."}
    return {}


def act(state: State) -> State:
    if state.get("result"):          # declined path fell through
        return {}
    # Replace with the real side effect. Execute ONLY the drafted action.
    return {"result": f"EXECUTED: {state['draft_action']}"}


builder = StateGraph(State)
builder.add_node("triage", triage)
builder.add_node("approve", approve)
builder.add_node("act", act)
builder.add_edge(START, "triage")
builder.add_conditional_edges("triage", route)
builder.add_edge("approve", "act")
builder.add_edge("act", END)

# InMemorySaver = demo only; use a SQLite/Postgres checkpointer for real resume.
# (MemorySaver still exists as a deprecated alias — prefer InMemorySaver.)
graph = builder.compile(checkpointer=InMemorySaver(), interrupt_before=["approve"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("request", nargs="?", help="the ask")
    ap.add_argument("--resume", metavar="THREAD_ID")
    ap.add_argument("--approve", action="store_true")
    args = ap.parse_args()

    if args.resume:
        config = {"configurable": {"thread_id": args.resume}}
        graph.update_state(config, {"approved": args.approve})
        state = graph.invoke(None, config)  # None = continue from checkpoint
        print(state["result"])
        return

    if not args.request:
        ap.error("give a request, or --resume <thread-id>")
    thread_id = uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.invoke({"request": args.request}, config)

    if state.get("result"):          # SAFE path ran straight through
        print(state["result"])
        return
    # Interrupted: print the 30-second approval payload and exit.
    print("APPROVAL NEEDED")
    print(f"  action:       {state['draft_action']}")
    print(f"  blast radius: judge from the action above — it will run verbatim")
    print(f"  on decline:   nothing executes; thread ends")
    print(f"resume: python src/graph.py --resume {thread_id} --approve   (or without --approve to decline)")
    sys.exit(0)


if __name__ == "__main__":
    main()
