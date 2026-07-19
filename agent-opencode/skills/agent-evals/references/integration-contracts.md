# Integration Contracts

The most common agent build failure is "looks done, is not wired up." Components pass isolated checks while contracts between prompt, registry, config, tool wrappers, and runtime paths are broken.

Hard rule: never trust a delegated agent's self-reported verification. Treat it as a hypothesis until you independently run the gates.

## The Five Integration Contracts

| Contract | Failure It Catches | Gate |
|---|---|---|
| Settings to properties | Code reads config keys that do not exist | Diff config accesses against declared settings |
| Prompt tools to registry | Prompt advertises phantom tools or misses registered tools | Compare tool names in prompt and registry |
| Import health | Syntax, import, dependency, or circular-import failures | Compile and import every module |
| Agent construction | The agent cannot bind or invoke its tools | Instantiate the agent and inspect/bind tool list |
| End-to-end path | Health checks pass but real queries fail | Run representative user queries against the deployed surface |

Each contract gets its own verification gate. A build is not done until all five pass independently.

## Copy-Paste Gate Per Contract

Adapt each gate to the stack in front of you.

### 1. Settings to properties

Catch code that reads config keys that do not exist:

```bash
python scripts/verify-agent-integration.py --src src
```

The script runs all four gates unconditionally (config-keys, prompt-tools, mcp-servers, secrets). Parse code rather than trusting docs: a typo'd property name passes every doc check and fails only at runtime under the right branch.

### 2. Prompt tools to registry

Catch phantom or missing tools by diffing the prompt's advertised tool list against the registry:

```python
from app.tools import registry
from app.agent import SYSTEM_PROMPT
advertised = extract_tool_names(SYSTEM_PROMPT)  # your own helper
registered = {t.name for t in registry.all_tools()}
missing = advertised - registered
phantom_call_paths = [n for n in advertised if n not in registered]
assert not missing, f"prompt advertises unregistered tools: {missing}"
```

A prompt that names a tool the agent cannot bind is a silent failure waiting for the right user query.

### 3. Import health

Catch syntax, import, dependency, or circular-import failures across the whole package, not just the file you changed:

```bash
python -m compileall src
python -c "import app.agent, app.tools, app.routes, app.workers"
```

### 4. Agent construction

Catch an agent that cannot bind or invoke its declared tools:

```bash
python -c "from app.agent import create_agent; a = create_agent(); print('agent constructed'); print(sorted(t.name for t in a.tools))"
```

Inspect the bound tool list, not only the fact that construction returned.

### 5. End-to-end path

Catch the "health is green, real queries fail" gap. Run safe, tool-backed, and refusal or approval smoke queries against the deployed surface, not only `GET /health`:

```bash
curl -sf http://localhost:8080/health
python -m app.main --query "run a safe representative task"
python -m app.main --query "exercise a tool-backed path"
python -m app.main --query "exercise a refusal or approval path"
```

## Generic Structural Gates

For config and tool-wrapper drift, `scripts/verify-agent-integration.py` provides a starting point:

```bash
python scripts/verify-agent-integration.py --src src
```

Wire it to your actual registry, agent constructor, and live smoke tests; treat it as a scaffold, not a verdict.

## Tool Wrapper Contract

Framework-decorated tools are often not plain functions. Non-agent code such as dashboards, schedulers, and routes should call the underlying client class or the framework's explicit invocation API. Grep for direct calls from non-agent code whenever tools are reused outside the LLM loop.

A typical failure: a scheduler calls `my_tool(...)` expecting the wrapped behavior, but the decorator added argument validation, approval, or audit logging that only runs through the agent invocation path. The wrapper silently no-ops and the scheduler ships raw, unvalidated calls.

## Delegated Verification Discipline

A subagent or parallel worker that reports "integration verified" is producing a claim, not evidence. Convert every claim into an artifact:

- "Imports work" → show the `compileall` and import output.
- "Tools bind" → show the sorted bound tool list.
- "End-to-end works" → show the three smoke query transcripts.
- "Config is clean" → show the verify-agent-integration report.

If the artifact is missing or partial, the contract did not pass. The parent agent re-runs the gates itself before reporting success upward.

## Superficial Checks That Do Not Prove Integration

- Container or process is healthy.
- Tool count matches an expected number.
- Imports work for only the file just changed.
- A delegated worker says it tested the feature.
- A mock-only test passes while live authentication, schemas, or response shapes are different.
- A green `/health` endpoint while real queries return errors.

## Useful Scripts

This pillar includes `scripts/verify-agent-integration.py`, a generic structural gate for Python projects, and shell wrappers for running eval suites with timeouts and command interception. Treat them as starting points; wire them to your actual registry, agent constructor, and live smoke tests.

## Pitfalls

- Treating a delegated "it works" as evidence. Fix: require artifacts and re-run the gates independently.
- Running import checks on only the changed file. Fix: compile and import the whole package.
- Counting tools instead of binding them. Fix: instantiate the agent and print the bound tool list.
- Trusting `/health` over real queries. Fix: run safe, tool-backed, and refusal smoke queries.
- Letting tool-wrapper reuse skip the agent invocation path. Fix: grep for direct calls from non-agent code.
