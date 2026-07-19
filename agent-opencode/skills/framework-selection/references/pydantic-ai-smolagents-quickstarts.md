> Last verified: 2026-07. Pydantic AI (`pydantic-ai`) and smolagents (`smolagents`) both evolve quickly — verify against [ai.pydantic.dev](https://ai.pydantic.dev/) and [huggingface.co/docs/smolagents](https://huggingface.co/docs/smolagents).

# Pydantic AI & smolagents Quickstarts

Two distinctive Python-native frameworks. Pydantic AI optimizes for type safety and dependency injection. smolagents is HF's code-as-action framework — the agent writes Python instead of calling tools.

## Pydantic AI

### When to Pick

- Type safety is the priority (typed tool args + structured outputs).
- You want dependency injection to enforce least-privilege by construction.
- You're already in the Pydantic ecosystem (FastAPI, etc.).

### Adoption Level

Level 1-2 (harness helper + typed deps).

### Minimal Example

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic import BaseModel

class Ticket(BaseModel):
    id: str
    priority: str
    summary: str

@dataclass
class Deps:
    db: Database  # your typed dependency

agent = Agent(
    "openai:gpt-5.6",
    deps_type=Deps,
    output_type=list[Ticket],
    system_prompt="You triage support tickets...",
)

@agent.tool
async def search_tickets(ctx: RunContext[Deps], query: str) -> list[dict]:
    """Search the ticket system."""
    return await ctx.deps.db.search(query)

result = await agent.run(
    "Find open P1 tickets",
    deps=Deps(db=Database(...)),
    usage_limits=UsageLimits(requests=15),
)
tickets = result.output  # type: list[Ticket] — validated
```

### Type-Safety as a Safety Boundary

`Deps` is the safety boundary. If `ReadOnlyDeps` doesn't expose a write method, the agent literally cannot call one:

```python
@dataclass
class ReadOnlyDeps:
    db: ReadOnlyDatabase  # no write methods exposed

@agent.tool
async def search(ctx: RunContext[ReadOnlyDeps], query: str) -> list[dict]:
    return await ctx.deps.db.search(query)
# Agent has no path to db.write — ReadOnlyDeps doesn't expose it
```

### ZAI Wiring

```python
from pydantic_ai.models.openai import OpenAIModel
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
model = OpenAIModel("glm-4.7", openai_client=client)
agent = Agent(model, ...)
```

### Pitfalls

1. **Untyped deps.** Using `dict` for `Deps` loses the safety boundary. Fix: dataclass or Pydantic model.
2. **`output_type=str` by default.** Lose the structured-output guarantee. Fix: declare the output type.
3. **No native HITL.** Fix: raise an exception in a tool to pause.

## smolagents

### When to Pick

- Code-as-action: the agent writes Python to combine tools, loops over data, etc.
- Data analysis, ETL, research — tasks where the agent benefits from writing real code.
- You can sandbox aggressively.

### Adoption Level

Level 2 (code-action loop).

### Minimal Example

```python
from smolagents import CodeAgent, LiteLLMModel, Tool

class SearchTickets(Tool):
    name = "search_tickets"
    description = "Search the ticket system."
    inputs = {"query": {"type": "string", "description": "The search query"}}
    output_type = "array"

    def forward(self, query: str) -> list[dict]:
        return [...]

agent = CodeAgent(
    tools=[SearchTickets()],
    model=LiteLLMModel(model_id="openai/glm-4.7", api_base="https://open.bigmodel.cn/api/paas/v4/", api_key=os.environ["ZAI_API_KEY"]),
    max_steps=10,
    authorized_imports=["json"],  # narrowest possible
)

result = agent.run("Find open P1 tickets and group by assignee")
```

### The Code-Execution Risk

smolagents writes and executes Python in your process. Sandbox mandatory:

```bash
docker run --network=none --read-only \
  --security-opt=no-new-privileges --cap-drop=ALL \
  -v ./workspace:/workspace:ro \
  smolagents-agent:latest
```

### ZAI Wiring

```python
from smolagents import LiteLLMModel
model = LiteLLMModel(
    model_id="openai/glm-4.7",
    api_base="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
```

### Pitfalls

1. **No sandbox.** The agent writes arbitrary Python; you trust it. Fix: Docker with no network, read-only mounts, no capabilities.
2. **`authorized_imports=["*"]`.** The agent can import anything. Fix: whitelist exactly the modules it needs.
3. **No session persistence.** Single-run by default. Fix: external session store.
4. **`agent.logs` is the trajectory.** Capture before the process exits.

## See Also

- `framework-build-matrix.md` — design → Pydantic AI / smolagents translation.
- `../../agent-evals/references/framework-eval-matrix.md` — trajectory capture.
- `../../agent-safety/references/framework-safety-matrix.md` — safety primitives (smolagents section is critical).
- `../../agent-deployment/references/framework-deploy-matrix.md` — Dockerfile.
