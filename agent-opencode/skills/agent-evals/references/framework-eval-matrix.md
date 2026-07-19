# Framework Eval Matrix

Each framework has different trajectory shape, different observability
hooks, and different eval-tool integrations. This reference maps each
of the 13 harnesses to the eval patterns that work natively, and shows
how to capture the trajectory the `agent-evals` doctrine asserts on.

For the eval taxonomy (governance / capability / behavioral /
regression) and the golden-suite doctrine, see this skill's `SKILL.md`
and `eval-taxonomy.md`. This file is the per-framework implementation
layer.

## The Trajectory Capture Problem

Every eval asserts on a trajectory — the ordered sequence of model
calls, tool calls, and tool results within a run. Each framework
captures trajectory differently:

| Framework | Where the trajectory lives | How to extract it |
|---|---|---|
| Claude Agent SDK | `--output-format json` | Parse the JSON run record |
| OpenAI Agents SDK | `RunResult.raw_responses`, `tool_calls` | Inspect attributes |
| Copilot SDK | Session event stream | Subscribe to `session.events()` |
| Google ADK | `RunResult.events` | Iterate events |
| Microsoft Agent Framework (MAF) | AgentRuntime conversation log | Query the runtime |
| LangGraph | `State` snapshot at every node | LangSmith trace OR checkpointer replay |
| CrewAI | `CrewOutput.token_usage`, `TaskOutput` chain | CrewAI's OTel export |
| LlamaIndex | `callback_manager` events | LlamaIndex tracing / OTel |
| Pydantic AI | `RunResult.all_messages()` | Inspect the message list |
| smolagents | `agent.logs` | Direct list inspection |
| Vercel AI SDK | `result.steps` | Iterate `steps[].toolCalls` |
| Mastra | `agent.run()` returns observations | Inspect observations |
| Custom loop | Your span emitter | Your format |

If your eval asserts on trajectory, you must wire the framework's
extraction path before the suite can run.

## Per-Framework Eval Patterns

### Claude Agent SDK

```python
# Capture
result = await agent.run(prompt="...", output_format="json")
trajectory = json.loads(result)

# Assert
assert any(call["tool"] == "search_tickets" for call in trajectory["tool_calls"])
assert not any(call["tool"] == "deploy" for call in trajectory["tool_calls"])
```

Pair with: Anthropic's trace processor for OTel; Langfuse for hosted eval.

### OpenAI Agents SDK

```python
result = await Runner.run(agent, prompt)
tool_calls = [c for c in result.raw_responses if c.tool_calls]
trajectory = [{"tool": c.name, "args": c.arguments} for c in tool_calls]

assert any(t["tool"] == "search_tickets" for t in trajectory)
```

Pair with: Langfuse or LangSmith for trajectory dashboards.

### Copilot SDK

```typescript
const session = await copilot.sessions.create({...});
const events = [];
for await (const event of session.events()) events.push(event);

const toolCalls = events.filter(e => e.type === 'tool_call');
assert(toolCalls.some(t => t.tool === 'searchTickets'));
```

Pair with: GitHub's audit log + OTel for span export.

### LangGraph

```python
# Replay from checkpointer for replay-as-fixture
config = {"configurable": {"thread_id": run_id}}
state_history = list(graph.get_state_history(config))
trajectory = [s.values for s in state_history]

# Or via LangSmith
from langsmith import Client
client = Client()
runs = client.list_runs(project_name="my-agent", execution_order=1)
```

LangSmith is the canonical LangGraph eval platform. Replay from the
checkpointer is the deterministic-fixture path.

### CrewAI

```python
result = crew.kickoff()
# CrewOutput has token usage and the task chain
trajectory = [
    {"task": t.description, "output": str(t.output), "agent": t.agent.role}
    for t in crew.tasks
]
# Tool-level trajectory requires OTel export
```

Pair with: CrewAI's built-in OTel; Langfuse for hosted eval.

### Pydantic AI

```python
result = await agent.run("...", usage_limits=UsageLimits())
# Full message history
messages = result.all_messages()
tool_calls = [m for m in messages if m.kind == "response" and m.tool_calls]
```

Pair with: Logfire (same vendor) for trajectory dashboards.

### smolagents

```python
result = agent.run("...")
# agent.logs has every step including the Python the agent wrote
trajectory = [
    {"step": i, "code": log.code, "result": log.result}
    for i, log in enumerate(agent.logs)
]
```

The trajectory includes the *code the model generated*, not just tool
calls — evals must account for arbitrary Python execution.

### Vercel AI SDK

```typescript
const result = await generateText({...});
const trajectory = result.steps.map(step => ({
  toolCalls: step.toolCalls,
  text: step.text,
}));
```

Pair with: Vercel AI SDK's `experimental_telemetry` for OTel; Langfuse
for hosted eval.

### Custom Loop

```python
# Your span emitter already has the trajectory
trajectory = [
    span for span in span_buffer
    if span["session_id"] == session_id
    and span["run_id"] == run_id
]
```

The custom loop is the easiest to eval — you emit exactly the spans you
want to assert on.

## Eval Platform Integration Matrix

| Platform | Frameworks with native support | Best for |
|---|---|---|
| **LangSmith** | LangChain, LangGraph | LangChain ecosystem agents |
| **Langfuse** | OpenAI Agents SDK, Vercel AI SDK, LangChain, CrewAI, custom | Open-source; self-hostable; broad framework support |
| **Phoenix (Arize)** | LangChain, LlamaIndex, OpenAI, custom | Open-source observability + eval; self-hostable |
| **Braintrust** | OpenAI, Anthropic, custom | Hosted eval with prompt-optimization loop |
| **Logfire** | Pydantic AI, LangChain, OpenAI | Pydantic-native; hosted |
| **Vertex AI Eval** | Google ADK, Gemini | Google Cloud shops |
| **Azure AI Evaluation** | MAF, Azure OpenAI | Azure shops |
| **Inspect (AI Safety)** | OpenAI, Anthropic, custom | Open-source; security/safety evals |
| **promptfoo** | All (CLI-driven) | Local-first red-team and YAML-driven evals |
| **DeepEval** | LangChain, OpenAI, custom | Open-source; pytest-style assertions |
| **RAGAS** | LlamaIndex, LangChain, custom | RAG-specific metrics |

Pick by ecosystem fit. Langfuse and Phoenix are the safest default for
multi-framework shops — both work with most harnesses via OTel.

## Per-Framework Trajectory Assertion Patterns

### "must_call_tool" assertion

```python
# Claude Agent SDK
assert any(tc["name"] == "search_tickets" for tc in trajectory["tool_calls"])

# LangGraph (via LangSmith)
from langsmith import expect
expect.contains(run, {"name": "search_tickets"})

# Pydantic AI
assert any(m.tool_calls and any(tc.name == "search_tickets" for tc in m.tool_calls)
           for m in result.all_messages())

# Custom loop
assert any(span["tool"] == "search_tickets" for span in trajectory if span["type"] == "tool_call")
```

### "must_not_execute" assertion

```python
# All frameworks: the destructive tool's name must not appear in executed tools
EXECUTED = extract_executed_tool_names(trajectory)
assert "deploy" not in EXECUTED
assert "delete_user" not in EXECUTED
```

### "must_request_approval" assertion

For HITL agents, the trajectory must show a pause before the destructive
tool. Framework-specific:

| Framework | Signal |
|---|---|
| Claude Agent SDK | `permissionDecision: "ask"` in trajectory |
| LangGraph | `interrupt_before` fired; resume timestamp recorded |
| CrewAI | `human_input=True` triggered; verdict recorded |
| Custom loop | Pending-approval span in trajectory |

## LLM-as-Judge Integration

Most frameworks can pipe their trajectory into a judge model:

```python
# Universal pattern (works with any framework's trajectory)
from openai import OpenAI
judge = OpenAI()

verdict = judge.chat.completions.create(
    model="gpt-5.6",
    messages=[
        {"role": "system", "content": "You judge agent trajectories..."},
        {"role": "user", "content": json.dumps({
            "task": case["prompt"],
            "trajectory": trajectory,
            "rubric": case["expected_behavior"],
        })},
    ],
    response_format={"type": "json_object"},
)
```

The judge evaluates against the rubric in the eval case. Framework-
agnostic; works with any of the 13 harnesses.

## Eval Sandbox Per-Framework

For governance evals that test destructive operations:

| Framework | How to sandbox the eval run |
|---|---|
| Claude Agent SDK | `permission_mode: "default"` + `disallowed_tools: ["Bash"]` |
| OpenAI Agents SDK | Only register safe tools; the framework has no sandbox |
| LangGraph | Conditional edges route dangerous tools to a stub node |
| smolagents | Docker container with no network; read-only mounts |
| Custom loop | Safety floor plugin blocks; record the block as the assertion |

For frameworks without native sandboxing, run the eval inside a Docker
container with no secrets, no network egress, and read-only mounts.

## Replay-as-Fixture Support

| Framework | Replay support |
|---|---|
| Claude Agent SDK | Replay via recorded `--output-format json` |
| LangGraph | Checkpointer replay (the gold standard) |
| MAF | Conversation replay via runtime host |
| Custom loop | Span replay if you recorded spans |
| OpenAI Agents SDK | No native replay; you record responses and substitute |
| Pydantic AI | `message_history` parameter for replay |
| Others | Generally no replay; use recorded responses as fixtures |

LangGraph's checkpointer is the most mature replay mechanism in the
framework landscape. If replay-as-fixture is critical to your eval
strategy, that weighs toward LangGraph.

## Framework-Specific Eval Pitfalls

1. **Trajectory not captured.** The framework ran the agent; the eval
   cannot inspect what happened. Fix: wire trajectory extraction
   before writing the first eval case.
2. **Asserting on text when trajectory matters.** The agent gave the
   right answer but called the wrong tools. Fix: governance and
   capability evals assert on trajectory, not just output.
3. **Eval platform lock-in.** Eval code is written for LangSmith; you
   switch to Langfuse; everything rewrites. Fix: keep eval cases as
   framework-agnostic JSONL; the runner adapts to the platform.
4. **No sandbox for governance evals.** The eval tests "agent refuses
   to delete production data" but runs against the production DB.
   Fix: container with no production access; record the refusal.
5. **LLM judge without calibration.** Judge drift over time; evals
   flake. Fix: re-calibrate the judge against human labels monthly.
6. **Replay not deterministic.** Same prompt, different trajectory;
   eval flakes. Fix: pin model IDs; record temperature=0; substitute
   recorded responses for full determinism.

## See Also

- `eval-taxonomy.md` — the four-category eval taxonomy.
- `golden-suites.md` — the golden-suite doctrine.
- `eval-ci-wiring.md` — wiring evals into CI.
- `../../framework-selection/references/framework-build-matrix.md` —
  the build counterpart (how to scaffold each framework).
- `../../agent-deployment/references/framework-deploy-matrix.md` — the
  deploy counterpart.
- `../../agent-safety/references/framework-safety-matrix.md` — per-
  framework tool policy and hooks.
