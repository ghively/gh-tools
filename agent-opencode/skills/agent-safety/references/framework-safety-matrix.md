# Framework Safety Matrix

Each framework has different mechanisms for tool policy, permission
enforcement, hooks, and sandboxing. This reference maps each of the 13
harnesses to the safety primitives it provides — and the gaps the
agent-foundry safety floor fills.

For the safety doctrine (OWASP agentic threats, sandboxing tiers,
guardrails, deterministic hooks, tool policy, multi-tenant isolation),
see this skill's `SKILL.md` and the other references. This file is the
per-framework enforcement layer.

## The Safety Layering

Defense in depth across four layers:

1. **Provider safety** (model-side): refusals, content filters, prompt
   injection defenses. Apply via the model and provider config.
2. **Framework safety** (harness-side): tool policy, permission rules,
   hooks. Apply via the framework's native primitives (this reference).
3. **Deterministic safety floor** (code-enforced): the never-run
   primitives block regardless of model or framework. Apply via the
   agent-foundry safety plugin or OpenCode permission rules.
4. **Sandbox** (OS/container-side): filesystem isolation, network
   egress control, capability dropping. Apply via Docker / gVisor /
   Firecracker.

Each framework supports layer 2 differently. Layers 1, 3, and 4 are
framework-agnostic.

## Per-Framework Safety Primitives

### Claude Agent SDK

| Primitive | Mechanism |
|---|---|
| Tool allowlist | `allowed_tools` / `disallowed_tools` on agent options |
| Permission mode | `default`, `acceptEdits`, `plan`, `bypassPermissions` |
| Pre-tool hook | `PreToolUse` event; return `permissionDecision: "deny"` |
| Post-tool hook | `PostToolUse` event; audit trail |
| Sandbox | Built-in sandboxed Bash with filesystem/network isolation |

Strong native safety story. The harness enforces; the model cannot
bypass. The agent-foundry safety floor adds the never-run primitives
even when permission mode is permissive.

```python
agent = ClaudeAgent(options=ClaudeAgentOptions(
    permission_mode="acceptEdits",
    allowed_tools=["Read", "Grep", "search_tickets"],
    disallowed_tools=["Bash", "Write"],
))
```

### OpenAI Agents SDK

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Only register the tools the agent should have |
| Permission | Manual: wrap tool `execute` with a permission check |
| Pre-tool hook | None native; you build it into `execute` |
| Post-tool hook | None native; you build it into `execute` |
| Sandbox | None native; you bring your own |

Weaker native story. You build the safety layer into your tool
wrappers. Pair with the agent-foundry safety floor for the never-run
primitives.

```python
def with_permission(tool, allowed_roles):
    async def guarded(**kwargs):
        if not current_user_has_role(allowed_roles):
            raise PermissionError(f"{tool.name} requires {allowed_roles}")
        return await tool.execute(**kwargs)
    return replace(tool, execute=guarded)
```

### Copilot SDK

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent `allowedTools` config |
| Pre-tool hook | `pre-tool-use` shell hook; throw to deny |
| Post-tool hook | `post-tool-use` shell hook |
| Sandbox | Cloud sandbox (managed) or local sandbox config |
| Org policy | Enterprise admin controls |

Strong native safety, similar shape to Claude Code's hooks. The hook
shell command can deny by non-zero exit or by emitting a structured
deny.

### Google ADK

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent tool list at construction |
| Permission | Manual: filter tools; Vertex AI safety settings on the model |
| Pre-tool hook | None native |
| Post-tool hook | None native |
| Sandbox | None native |

The model-side safety settings (Vertex AI) are strong; the tool-side
safety is manual. Pair with the safety floor.

### MAF (Microsoft Agent Framework)

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent tool list; `AgentRuntime` enforces |
| Permission | Manual: per-agent filter; conversation-level policies |
| Pre-tool hook | `@tool_pre_handler` decorator |
| Post-tool hook | `@tool_post_handler` decorator |
| Sandbox | None native; Azure Container Apps sandbox |

Native pre/post handlers are the hook surface. Use them for audit,
redaction, and gating.

```python
@tool_pre_handler("deploy")
async def gate_deploy(ctx, **kwargs):
    if not ctx.user_has_role("deployer"):
        raise PermissionError("deploy requires deployer role")
```

### LangGraph

| Primitive | Mechanism |
|---|---|
| Tool allowlist | `llm.bind_tools([allowed_subset])` per node |
| Permission | Conditional edges route around disallowed tools |
| Pre-tool hook | `interrupt_before=["tool_node"]`; check then resume |
| Post-tool hook | Conditional edge after `ToolNode`; inspect result |
| Sandbox | None native |

LangGraph's graph structure IS the safety mechanism — you route around
danger. `interrupt_before` is the HITL hook surface.

```python
def route_after_model(state):
    if state["tool_call"]["name"] in DESTRUCTIVE:
        return "approval_gate"
    return "tool_executor"

builder.add_conditional_edges("model", route_after_model)
builder.add_node("approval_gate", approval_node)
```

### CrewAI

| Primitive | Mechanism |
|---|---|
| Tool allowlist | `Task.tools` filter; `Agent.tools` filter |
| Permission | Manual: tool wrapper or `human_input=True` |
| Pre-tool hook | None native |
| Post-tool hook | None native |
| Sandbox | None native |

CrewAI is permissive by default. Build the safety layer into your tool
wrappers and use `human_input=True` on destructive tasks.

### LlamaIndex

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent tool list |
| Permission | Manual |
| Pre-tool hook | `callback_manager.event_handlers` |
| Post-tool hook | Same |
| Sandbox | None native |

The callback manager is the observability AND hook surface. Add custom
event handlers for pre/post-tool checks.

### Pydantic AI

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent tool registration |
| Permission | Typed `Deps` enforce boundaries — the agent literally cannot call things `Deps` does not expose |
| Pre-tool hook | Decorate tool functions |
| Post-tool hook | Decorate tool functions |
| Sandbox | None native |

Pydantic AI's type system is a strong safety boundary: if `Deps` does
not expose a destructive capability, the agent has no way to call it.
Use this for least-privilege by construction.

```python
@dataclass
class ReadOnlyDeps:
    db: ReadOnlyDatabase  # no write methods

@agent.tool
async def search(ctx: RunContext[ReadOnlyDeps], query: str) -> list[dict]:
    return await ctx.deps.db.search(query)
# Agent literally cannot call db.write — ReadOnlyDeps doesn't expose it
```

### smolagents

| Primitive | Mechanism |
|---|---|
| Tool allowlist | `tools=[...]` per agent |
| Permission | `authorized_imports` (Python modules the agent can import) |
| Pre-tool hook | None native |
| Post-tool hook | None native |
| Sandbox | **Critical** — agent writes Python that runs in your process |

smolagents is the highest-risk framework for safety because the model
generates arbitrary Python. Sandbox aggressively: Docker container with
no network, read-only workspace mounts, no secrets in env, drop all
capabilities. The agent-foundry safety floor helps but is not
sufficient on its own.

```python
agent = CodeAgent(
    tools=[SearchTickets()],
    authorized_imports=["json"],  # narrowest possible
    max_steps=10,
)
# MUST run inside:
# docker run --network=none --read-only --security-opt=no-new-privileges \
#   --cap-drop=ALL ...
```

### Vercel AI SDK

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-call `tools` object passed to `streamText` / `generateText` |
| Permission | Manual: wrap `execute` with a check |
| Pre-tool hook | Manual: wrap `execute` |
| Post-tool hook | Manual: wrap `execute` |
| Sandbox | None native |

All hooks live in the tool's `execute` function. Wrap it for any
safety concern.

```typescript
const guardedTool = (tool, check) => ({
  ...tool,
  execute: async (args) => {
    if (!await check(args)) throw new Error('permission denied');
    return tool.execute(args);
  },
});
```

### Mastra

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Per-agent tool registration |
| Permission | Manual; workflow step gating |
| Pre-tool hook | Manual: wrap tool `execute` |
| Post-tool hook | Manual: wrap tool `execute` |
| Sandbox | None native |

Same shape as Vercel AI SDK.

### Custom Loop

| Primitive | Mechanism |
|---|---|
| Tool allowlist | Your tool registry filter |
| Permission | Your permission check before dispatch |
| Pre-tool hook | Your pre-dispatch hook |
| Post-tool hook | Your post-dispatch hook |
| Sandbox | Whatever you build |

The custom loop is the most flexible but requires the most work. The
agent-foundry safety floor (`tool.execute.before` throwing to deny) is
the canonical pattern for the never-run primitives layer.

## Universal Patterns Across Frameworks

### The Permission Wrapper

For frameworks without native permission checks, wrap every tool:

```python
def permission_checked(tool, allowed):
    async def execute(**kwargs):
        if not allowed(kwargs):
            raise PermissionError(f"{tool.name} denied")
        return await tool.original_execute(**kwargs)
    return replace(tool, execute=execute)
```

Apply this in frameworks where the native surface is weak: OpenAI
Agents SDK, CrewAI, LlamaIndex, Vercel AI SDK, Mastra.

### The Pre-Tool Audit Hook

For frameworks with hook surfaces, log every tool call:

```python
# Claude Agent SDK / Copilot SDK style
def pre_tool_use(tool_name, args, user):
    log.info("tool_call", tool=tool_name, args=args, user=user.id)
    if tool_name in NEVER_RUN:
        return {"permissionDecision": "deny", "permissionDecisionReason": "..."}
    return None  # defer
```

In frameworks without native hooks, the wrapper pattern does the same
job.

### The Destructive Tool Gate

Every framework should gate destructive tools with a HITL interrupt:

| Framework | Where the gate lives |
|---|---|
| Claude Agent SDK | `permission_mode: "default"` + `PreToolUse` |
| Copilot SDK | `pre-tool-use` hook |
| LangGraph | `interrupt_before` |
| CrewAI | `human_input=True` on destructive tasks |
| MAF | `@tool_pre_handler` |
| Custom loop | Pre-dispatch check + await async verdict |

For frameworks without native async verdict (OpenAI Agents SDK, Vercel
AI SDK, Mastra), the wrapper raises a "needs approval" exception; the
caller decides whether to retry with a verdict token.

## What the Safety Floor Adds (Universal)

Regardless of framework, the agent-foundry safety floor adds:

- **Never-run primitive blocks**: `curl | sh`, `rm -rf /`, `dd of=/dev/*`,
  writes to `/etc/passwd`, `~/.ssh/`, etc. These run as a
  `tool.execute.before` hook in OpenCode, or as a wrapper in other
  frameworks.
- **Optional secret-write scanner**: deny writes containing
  high-confidence credential material.
- **Optional audit trail**: bounded JSONL of every tool call.
- **Fail-open on parser errors**: a broken hook never bricks the agent.

These sit beneath the framework's own safety and the OS sandbox. See
`deterministic-hooks.md` for the full catalog.

## Pitfalls

1. **Trusting the framework's defaults in production.** The defaults
   are tuned for dev UX, not safety. Fix: review every default;
   tighten before launch.
2. **Allowlist that grows over time.** New tools added without review;
   blast radius grows. Fix: tool allowlist changes require PR review
   + eval-suite run.
3. **Destructive tool without a gate.** "We'll add approval later."
   Fix: gate from day one; retrofitting is harder than building.
4. **smolagents without a sandbox.** The model writes arbitrary
   Python; you trust it. Fix: Docker with no network, read-only
   mounts, no capabilities.
5. **Pre-tool hook that fails open silently.** A bug in the hook
   lets everything through. Fix: test the hook's failure modes;
   fail closed for safety rules, fail open for parse errors only.
6. **Different policy across replicas.** Replica A allows `deploy`;
   replica B does not. Fix: policy lives in shared config, not
   replica-local code.
7. **Model-side safety without tool-side safety.** The model refuses
   to call destructive tools, so you skip the tool gate. Fix: model
   refusals are advisory; tool gates are enforced.
8. **No audit trail for denied calls.** A deny happens; nobody knows.
   Fix: every deny emits a span; the audit trail is the incident
   timeline.

## See Also

- `owasp-agentic.md` — the threat taxonomy.
- `sandboxing-tiers.md` — the OS/container isolation ladder.
- `deterministic-hooks.md` — the never-run primitives catalog.
- `tool-policy.md` — OpenCode permission rules.
- `multi-tenant-isolation.md` — per-tenant boundaries.
- `../../framework-selection/references/framework-build-matrix.md` —
  the build counterpart.
- `../../agent-evals/references/framework-eval-matrix.md` — per-
  framework eval patterns.
- `../../agent-deployment/references/framework-deploy-matrix.md` —
  per-framework deploy recipes.
