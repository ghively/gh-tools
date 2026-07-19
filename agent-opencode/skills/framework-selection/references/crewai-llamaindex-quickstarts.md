> Last verified: 2026-07. CrewAI and LlamaIndex project layouts, Flow APIs, and agent imports move quickly; verify generated scaffold files before editing them.

# CrewAI and LlamaIndex Quickstarts

Use this when LangGraph is not the most ergonomic first pick. CrewAI is strongest when role/task/crew vocabulary matches the user's mental model. LlamaIndex is strongest when the agent sits close to documents, indexes, query engines, or event-driven workflows.

## CrewAI: Flow Owning State, Crew Doing Work

Current CrewAI docs lead with **Flows** for production structure: the Flow owns state and execution order; agents work inside a crew step.

```bash
crewai create flow latest-ai-flow
cd latest_ai_flow
```

Minimal Flow shape:

```python
from pydantic import BaseModel
from crewai.flow import Flow, listen, start

class ResearchState(BaseModel):
    topic: str = "AI Agents"
    report: str = ""

class ResearchFlow(Flow[ResearchState]):
    @start()
    def prepare_topic(self):
        self.state.topic = "AI Agents"

    @listen(prepare_topic)
    def run_research(self):
        # Call a crew loaded from JSONC or built in Python.
        self.state.report = "crew result"

def kickoff():
    ResearchFlow().kickoff()
```

Minimal JSONC crew shape from current docs:

```jsonc
{
  "name": "Research Crew",
  "agents": ["researcher"],
  "tasks": [
    {
      "name": "research_task",
      "description": "Research {topic} and write a concise report.",
      "expected_output": "A markdown report with key findings and implications.",
      "agent": "researcher",
      "output_file": "output/report.md",
      "markdown": true
    }
  ],
  "process": "sequential",
  "verbose": true
}
```

Pick CrewAI when:

- Stakeholders naturally describe the system as roles and tasks.
- You need a quick multi-agent demo or role-based prototype.
- A Flow with a few crew steps is clearer than a lower-level graph.
- You value declarative crew config and generated project structure.

Avoid CrewAI when:

- You need precise low-level control over every state transition.
- You are building mostly deterministic code with one LLM call.
- Role-play abstractions obscure tool policy and verification.

Primary docs: https://docs.crewai.com/en/quickstart

## LlamaIndex: AgentWorkflow Near Data and Tools

LlamaIndex's `FunctionAgent` and `AgentWorkflow` are good fits when the agent is part of a retrieval/document application or when LlamaIndex tools/query engines already exist.

```bash
pip install llama-index
```

Minimal `FunctionAgent`:

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI

async def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

agent = FunctionAgent(
    tools=[multiply],
    llm=OpenAI(model="gpt-4o-mini"),
    system_prompt="Use tools for arithmetic.",
)

response = await agent.run(user_msg="What is 6 * 7?")
print(response)
```

Wrap in `AgentWorkflow` for orchestration:

```python
from llama_index.core.agent.workflow import AgentWorkflow

workflow = AgentWorkflow(agents=[agent])
response = await workflow.run(user_msg="What is 6 * 7?")
```

Maintain state with `Context`:

```python
from llama_index.core.workflow import Context

ctx = Context(agent)
await agent.run(user_msg="My project is Atlas.", ctx=ctx)
await agent.run(user_msg="What project did I mention?", ctx=ctx)
```

Pick LlamaIndex when:

- The agent needs query engines, indexes, document tools, or RAG-native components.
- You need event streaming around agent/tool events.
- You want serializable workflow context for stateful document agents.
- You are already using LlamaIndex for ingestion/retrieval.

Avoid LlamaIndex when:

- The work is not data/RAG-heavy and a simpler provider SDK loop suffices.
- You need the clearest possible low-level graph semantics; use LangGraph.
- You are using it only because "agent" appears in the docs.

Primary docs: https://docs.llamaindex.ai/en/stable/examples/agent/agent_workflow_basic/

## CrewAI vs LlamaIndex vs LangGraph

| Need | Best first pick |
|---|---|
| Explicit graph, retries, checkpoints, HITL | LangGraph |
| Role/task crew prototype | CrewAI |
| Production Flow around role-based crew work | CrewAI Flow |
| Agent over RAG/query engines | LlamaIndex |
| Serializable context in a document workflow | LlamaIndex |
| One model + three tools | No framework or provider SDK |

## Pitfalls

1. **Letting generated scaffold dictate architecture.** Fix: run `agent-design` first; edit scaffold to match design.
2. **Using roles to hide missing tool policy.** Fix: every CrewAI agent still needs explicit authority boundaries.
3. **Using LlamaIndex as a generic agent runtime when no data stack exists.** Fix: pick simpler abstractions unless retrieval is central.
4. **Forgetting async boundaries.** Fix: LlamaIndex agent examples are async; wire runtime accordingly.
