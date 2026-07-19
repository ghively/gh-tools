> Last verified: 2026-07. DSPy optimizer names, Microsoft Agent Framework package maturity, and NeMo Agent Toolkit component names are volatile; check current docs before pinning versions.

# DSPy, Microsoft Agent Framework, and NeMo Agent Toolkit

These are not interchangeable "agent frameworks." DSPy is an authoring and optimization model for LLM programs. Microsoft Agent Framework is a general agent/workflow SDK and successor path for AutoGen/Semantic Kernel teams. NeMo Agent Toolkit is a framework-agnostic wrapper for profiling, evaluation, observability, and serving workflows.

## DSPy as Agent Authoring

DSPy is best when you want typed tasks and metric-driven prompt/program optimization rather than hand-tuned prompts.

```bash
pip install -U dspy
```

Minimal typed extraction:

```python
import dspy

dspy.configure(lm=dspy.LM("openai/gpt-5.4-mini"))

class Triage(dspy.Signature):
    """Route a support ticket."""
    ticket: str = dspy.InputField()
    urgency: str = dspy.OutputField(desc="low, medium, or high")
    team: str = dspy.OutputField()

triage = dspy.Predict(Triage)
print(triage(ticket="Refund request for duplicate charge."))
```

Minimal ReAct module with tools:

```python
def search(query: str) -> list[str]:
    """Search the knowledge base."""
    return ["result 1", "result 2"]

agent = dspy.ReAct("question -> answer", tools=[search])
print(agent(question="What policy covers refunds?"))
```

Use DSPy when:

- You can define a metric and examples.
- Prompt quality matters enough to optimize systematically.
- You want signatures/modules that can move across models.
- You are building RAG, extraction, classification, or agent steps that need measurable improvement.

Do not use DSPy as a replacement for durable orchestration, permission policy, or deployment. Deep prompt optimization guidance lives in `prompt-context-engineering/references/dspy-optimization.md`.

Primary docs: https://dspy.ai

## Microsoft Agent Framework Migration Notes

Microsoft Agent Framework combines AutoGen-style agent abstractions with Semantic Kernel enterprise features and graph-based workflows. Current docs describe Agents, a batteries-included Harness, and Workflows with checkpointing and human-in-the-loop support.

Minimal Python shape:

```bash
pip install agent-framework
```

```python
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint="https://your-foundry-service.services.ai.azure.com/api/projects/your-project",
    model="gpt-5.4-mini",
    credential=AzureCliCredential(),
)

agent = client.as_agent(
    name="HelloAgent",
    instructions="You are a friendly assistant. Keep your answers brief.",
)

result = await agent.run("What is the largest city in France?")
print(result)
```

Migration guidance:

| If you used | Treat Agent Framework as |
|---|---|
| AutoGen for simple multi-agent chats | The official Microsoft successor path, but redesign instead of line-by-line porting |
| Semantic Kernel filters/plugins | A familiar enterprise feature base with newer agent/workflow abstractions |
| AG2 community fork | A separate ecosystem; do not assume compatibility |
| LangGraph | Not a mandatory migration; compare graph/workflow needs honestly |

Use Microsoft Agent Framework when:

- Your team is in .NET, Python, or Go and wants Microsoft-supported agent/workflow primitives.
- You are migrating from AutoGen or Semantic Kernel.
- You need Azure/Foundry integration, typed workflows, middleware, or enterprise telemetry.

Primary docs: https://learn.microsoft.com/en-us/agent-framework/overview/

## NeMo Agent Toolkit as a Wrapper, Not Your Core Runtime

NeMo Agent Toolkit wraps and improves agent workflows across frameworks. Current docs include workflow configuration, framework integrations, MCP/A2A front ends, evaluation, profiling, optimization, and observability.

Use it when:

- You already have LangGraph, CrewAI, LlamaIndex, or another workflow and need profiling/evaluation/observability around it.
- You want to expose workflows through MCP or A2A surfaces.
- You need systematic performance profiling and sizing guidance.
- You operate a multi-framework stack and want a common wrapper layer.

Do not use it when:

- You have not chosen or built the underlying workflow yet.
- You need a simple one-agent prototype.
- You expect it to replace framework design decisions.

Primary docs: https://docs.nvidia.com/nemo/agent-toolkit/latest/

## Decision Table

| Need | Pick |
|---|---|
| Optimize prompts/programs against a metric | DSPy |
| Add ReAct to a typed LLM program | DSPy |
| Migrate Microsoft AutoGen/Semantic Kernel work | Microsoft Agent Framework |
| Build typed enterprise workflows in Microsoft stack | Microsoft Agent Framework |
| Profile/evaluate/serve an existing workflow | NeMo Agent Toolkit |
| Choose a general open graph runtime | LangGraph |

## Pitfalls

1. **Calling DSPy an orchestrator.** Fix: use it for modules, signatures, and optimization; put runtime control elsewhere if needed.
2. **Confusing AutoGen, AG2, and Microsoft Agent Framework.** Fix: treat them as related but distinct; verify migration docs.
3. **Assuming NeMo Agent Toolkit replaces your framework.** Fix: wrap a designed workflow; do not skip framework selection.
4. **Optimizing without a metric.** Fix: if you cannot score examples, DSPy optimization is premature.
