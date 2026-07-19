> Last verified: 2026-07. The OpenAI Agents SDK (Swarm's production successor) churns fast — verify imports against [current docs](https://github.com/openai/openai-agents-python) before copying.

# OpenAI Agents SDK Quickstart

The OpenAI Agents SDK is the production successor to Swarm. Its signature primitive is the **handoff**: an agent can hand the conversation to another agent mid-turn, with the receiving agent inheriting history. Tools are `@function_tool` decorated functions.

## When to Pick

- Multi-specialist agents where handoffs are the natural shape (triage → specialist).
- OpenAI-first shops that want first-party SDK support.
- You need a thin harness on top of the OpenAI provider SDK.

## Adoption Level

Level 1-2 (harness helper + handoff composition). Not a graph framework.

## Current Mechanics

- Package: `openai-agents` (Python) and `@openai/agents` (Node).
- Imports verified: `from agents import Agent, Runner, function_tool, handoff`.
- Handoffs are first-class: `Agent(handoffs=[other_agent])`.
- Tracing via the SDK's `trace_processor`; pair with Langfuse or LangSmith.

## Minimal Example

```python
from agents import Agent, Runner, function_tool
import asyncio

@function_tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system for matching tickets."""
    # implementation
    return [...]

triage = Agent(
    name="triage",
    model="gpt-5.6-terra",
    instructions="You triage support tickets...",
    tools=[search_tickets],
)

async def main():
    result = await Runner.run(triage, "Find open P1 tickets")
    print(result.final_output)

asyncio.run(main())
```

## Handoffs

```python
from agents import handoff

specialist = Agent(name="specialist", model="gpt-5.6-terra", instructions="...")
triage = Agent(
    name="triage",
    model="gpt-5.6-terra",
    handoffs=[handoff(specialist)],
)
```

## Tooling Notes

- Sessions: the SDK is stateless across runs. Pair with a session store for durable conversations.
- Observability: OTel export via the SDK's `VoiceEngine` / trace processors.
- Structured outputs: pair with Pydantic for typed tool args and structured agent output.

## ZAI Wiring

OpenAI-compatible — set `base_url` on the model:

```python
from agents.models.openai_provider import OpenAIProvider
zai = OpenAIProvider(base_url="https://open.bigmodel.cn/api/paas/v4/", api_key=os.environ["ZAI_API_KEY"])
triage = Agent(name="triage", model=zai.get_model("glm-4.7"), ...)
```

See `../../agent-deployment/references/zai-provider-config.md` for the full ZAI reference.

## Migration Notes

- From Swarm: the `Agent` and `handoff` shapes carry over; `Routine` is replaced by direct agent definition.
- From LangChain's `create_agent`: handoffs are not chain composition; they're runtime delegation.

## Pitfalls

1. **No built-in session store.** Conversations die with the process. Fix: pair with Postgres.
2. **`max_turns` per agent.** Cross-agent loops are not bounded. Fix: set `max_turns` on every agent in a handoff chain.
3. **Handoffs hide tool transitions.** The receiving agent's tools are not the sender's. Fix: explicit tool overlap or pass context.
4. **Tracing is opt-in.** Without `tracing_enabled`, no trajectory. Fix: enable in `Runner.run_config`.

## See Also

- `framework-build-matrix.md` — design → OpenAI Agents SDK translation.
- `../../agent-evals/references/framework-eval-matrix.md` — trajectory capture for this SDK.
- `../../agent-safety/references/framework-safety-matrix.md` — safety primitives.
- `../../agent-deployment/references/framework-deploy-matrix.md` — Dockerfile for this SDK.
