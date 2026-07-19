> Last verified: 2026-07. Google ADK is fast-moving; verify against [google.github.io/adk-docs](https://google.github.io/adk-docs/).

# Google ADK Quickstart

Google's Agent Development Kit — Vertex-AI-blessed for Gemini, with first-class tool registration, `Session` state, and Vertex AI trace integration.

## When to Pick

- Gemini-first agents.
- You're on Google Cloud and want Workload Identity auth (no static keys).
- You need deep Vertex AI integration (model garden, indexes, grounding).

## Adoption Level

Level 2-3 (harness helper + session state). Less graph-shape than LangGraph.

## Current Mechanics

- Package: `google-adk` (Python).
- Imports verified: `from google.adk import Agent, FunctionTool, Runner, Session`.
- Sessions: `Session` service supports in-memory, Postgres, or Vertex AI sessions (durable).
- Tools: `@FunctionTool` decorator or `Toolset` for grouped registration.
- Auth: Workload Identity on GKE/GCE; `GOOGLE_APPLICATION_CREDENTIALS` for portable deploys.

## Minimal Example

```python
from google.adk import Agent, FunctionTool, Runner
import asyncio

@FunctionTool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system for matching tickets."""
    return [...]

agent = Agent(
    name="triage",
    model="gemini-3.1-pro",
    tools=[search_tickets],
    instruction="You triage support tickets...",
)

async def main():
    runner = Runner(agent=agent)
    result = await runner.run_async("Find open P1 tickets")
    print(result.text)

asyncio.run(main())
```

## Sessions (Durable)

```python
from google.adk.sessions import VertexSessionService

session_service = VertexSessionService(
    project="my-project",
    location="us-central1",
)
# Sessions persist across process restarts
```

## Multi-Agent

```python
specialist = Agent(name="specialist", model="gemini-3.1-pro", ...)
triage = Agent(
    name="triage",
    model="gemini-3.1-pro",
    sub_agents=[specialist],
)
```

## ZAI Wiring

ADK supports OpenAI-compatible backends via custom model wrappers. For ZAI:

```python
from google.adk.models.openai_compatible import OpenAICompatibleModel
zai_model = OpenAICompatibleModel(
    model="glm-4.7",
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
agent = Agent(name="triage", model=zai_model, ...)
```

## Pitfalls

1. **Static service-account key in the image.** Fix: Workload Identity on GKE; no key in the image.
2. **No native pre-tool hook.** Fix: wrap tool functions; ADK does not intercept.
3. **Vertex AI session pricing.** Durable sessions bill per session per hour. Fix: in-memory for dev; Vertex for prod.
4. **Model ID dialect.** Gemini models on Vertex vs direct API have different names. Fix: pin the exact ID.

## See Also

- `framework-build-matrix.md` — design → Google ADK translation.
- `../../agent-evals/references/framework-eval-matrix.md` — trajectory capture for ADK.
- `../../agent-safety/references/framework-safety-matrix.md` — safety primitives.
- `../../agent-deployment/references/framework-deploy-matrix.md` — Dockerfile for ADK.
