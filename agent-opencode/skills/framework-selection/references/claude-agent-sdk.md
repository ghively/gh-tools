# Claude Agent SDK — The Claude Code Agent Loop as a Library

> Last verified: 2026-07. Versions, option names, and hook lists move fast — re-check
> [docs.claude.com/en/api/agent-sdk/overview](https://docs.claude.com/en/api/agent-sdk/overview)
> (also served at code.claude.com/docs/en/agent-sdk) before relying on exact signatures.

## What it is

The Claude Agent SDK (formerly "Claude Code SDK" — renamed; the package names were always
`claude-agent-sdk` / `@anthropic-ai/claude-agent-sdk`) embeds the **same agent harness that
powers the Claude Code CLI** — the agent loop, built-in tools, context management,
permission system, subagents, and session persistence — as a library in your own
application. You host and run it; Anthropic does not.

What the harness gives you out of the box:

- **The loop**: turns, tool invocation, result streaming, and context accumulation are
  managed — you never write `while stop_reason == "tool_use"`.
- **Built-in tools**: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, plus the
  Agent tool for subagents, AskUserQuestion (clarifying prompts), and Monitor (background
  process management). This is the big differentiator: every other option starts you
  with zero tools.
- **Context management**: automatic prompt caching and automatic compaction when the
  conversation approaches the context limit (a `PreCompact` hook fires first if you want
  to archive the transcript).
- **Permission system**: modes, allow/deny rules, and a programmatic approval callback.
- **Sessions**: persisted to disk, resumable, forkable.

**Mechanics to know:** each `query()` spawns a `claude` CLI subprocess (bundled with the
SDK — no separate install) that owns the shell, working directory, and session files under
`~/.claude/projects/<encoded-cwd>/`. Multiple concurrent agents = multiple subprocesses.

Don't confuse it with three near neighbors on the Anthropic stack:

| Surface | What you get | Who hosts |
|---|---|---|
| Raw Messages API (`anthropic` SDK) | API access; you build the loop and every tool | You |
| **Claude Agent SDK** (this file) | Full Claude Code harness + built-in tools + sessions/permissions | You |
| Managed Agents (REST, beta) | Anthropic runs the loop AND hosts a per-session sandbox | Anthropic |

## Install

```bash
pip install claude-agent-sdk        # Python ≥3.10; 0.2.x line as of 2026-07
npm install @anthropic-ai/claude-agent-sdk   # Node ≥18; 0.3.x line as of 2026-07
```

Both bundle the CLI/native binaries. Auth: `ANTHROPIC_API_KEY`, or set
`CLAUDE_CODE_USE_BEDROCK=1` / `CLAUDE_CODE_USE_VERTEX=1` / `CLAUDE_CODE_USE_FOUNDRY=1`
with the respective cloud credentials.

Runnable starters live in this skill's assets — Python
(`assets/claude-agent-sdk-starter/`) and TypeScript
(`assets/claude-agent-sdk-starter-ts/`), each with scoped tool surface,
in-process MCP tool, deterministic PreToolUse floor, cheap-model subagent,
cost/session capture. Copy one as the stage-7 artifact once design stages 1–6
are answered; `/agent-foundry:build-agent` does exactly that from an approved
`.foundry/design.md`.

## Minimal working example — Python

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

async def main():
    async for message in query(
        prompt="Find and fix the bug in auth.py, then run the tests",
        options=ClaudeAgentOptions(
            allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
            permission_mode="acceptEdits",   # auto-approve edits in cwd
            cwd="/path/to/repo",
            max_turns=30,
        ),
    ):
        if isinstance(message, ResultMessage):
            print(message.result)
            print(f"cost: ${message.total_cost_usd:.4f}  session: {message.session_id}")

asyncio.run(main())
```

`query()` is one-shot (fresh session each call). For multi-turn conversations in one
process use `ClaudeSDKClient`, which tracks the session internally:

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=ClaudeAgentOptions(allowed_tools=["Read", "Grep"])) as client:
    await client.query("Analyze the auth module")
    async for message in client.receive_response():
        ...
    await client.query("Now refactor it to use JWT")   # same session, full context
    async for message in client.receive_response():
        ...
```

## Minimal working example — TypeScript

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const message of query({
  prompt: "Find and fix the bug in auth.ts, then run the tests",
  options: {
    allowedTools: ["Read", "Edit", "Bash", "Glob", "Grep"],
    permissionMode: "acceptEdits",
    cwd: "/path/to/repo",
    maxTurns: 30,
  },
})) {
  if (message.type === "result" && message.subtype === "success") {
    console.log(message.result);
    console.log(`cost: $${message.total_cost_usd.toFixed(4)}`);
  }
}
```

TypeScript's `query()` returns an async generator with extra methods —
`setPermissionMode()`, `interrupt()`, `streamInput()` (feed follow-up prompts into a live
session without closing it).

## The options that matter

Python `ClaudeAgentOptions` (snake_case) / TypeScript `Options` (camelCase):

| Option | Purpose |
|---|---|
| `allowed_tools` | Tools auto-approved without prompting (`["Read", "Edit", "Bash"]`) |
| `tools` | If set, ONLY these tools exist in Claude's context |
| `disallowed_tools` | Remove tools (`"Bash"`) or deny patterns (`"Bash(rm *)"`) |
| `system_prompt` | Your agent's persona. **Since the v0.1 rename, the Claude Code default system prompt is NOT applied** — supply your own, or opt into the preset |
| `permission_mode` | `default` / `acceptEdits` / `plan` / `dontAsk` / `bypassPermissions` |
| `mcp_servers` | External MCP servers (stdio/HTTP) and in-process SDK servers |
| `agents` | Subagent definitions (below) |
| `hooks` | Lifecycle callbacks (below) |
| `setting_sources` | Which filesystem settings to load (`["project"]` = `.claude/` in cwd, `["user"]` = `~/.claude/`). **Loads `.claude/` from cwd and `~/.claude/` by default**; pass `setting_sources=[]` to suppress all filesystem settings |
| `cwd` | Agent's working directory — the sandbox root for file tools |
| `model` | `"sonnet"` / `"opus"` / `"haiku"` or a full model ID |
| `max_turns` | Hard cap on agentic turns |
| `resume`, `fork_session`, `continue_conversation` | Session controls (below) |
| `env` | Environment variables for the subprocess |

## Custom tools — in-process MCP servers

Custom tools are delivered as an **in-process MCP server** — no separate process, no
socket; the SDK routes calls to your function directly. Tool names become
`mcp__<server>__<tool>`:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, query, ClaudeAgentOptions

@tool("get_temperature", "Get current temperature at a location",
      {"latitude": float, "longitude": float})
async def get_temperature(args):
    temp = await fetch_weather(args["latitude"], args["longitude"])
    return {"content": [{"type": "text", "text": f"Temperature: {temp}°F"}]}

weather = create_sdk_mcp_server(name="weather", version="1.0.0", tools=[get_temperature])

options = ClaudeAgentOptions(
    mcp_servers={"weather": weather},
    allowed_tools=["mcp__weather__get_temperature"],   # or "mcp__weather__*"
)
```

```typescript
import { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

const getTemperature = tool(
  "get_temperature", "Get current temperature at a location",
  { latitude: z.number(), longitude: z.number() },
  async (args) => ({
    content: [{ type: "text", text: `Temperature: ${await fetchWeather(args)}°F` }],
  }),
);
const weather = createSdkMcpServer({ name: "weather", version: "1.0.0", tools: [getTemperature] });
```

External MCP servers (any stdio command or HTTP URL) plug into the same `mcp_servers`
map — the whole MCP ecosystem is your tool catalog. This is also the pattern for the
media/data tools you'd otherwise write as framework `@tool` functions.

## Hooks

Deterministic callbacks at loop lifecycle points — the SDK's answer to "middleware":

```python
from claude_agent_sdk import HookMatcher

async def block_dangerous(input_data, tool_use_id, context):
    if "rm -rf" in str(input_data.get("tool_input", {})):
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "dangerous command",
        }}
    return {}

options = ClaudeAgentOptions(
    hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[block_dangerous])]},
)
```

Key events (both SDKs unless noted): `PreToolUse` (block/modify/approve a call),
`PostToolUse` (inspect/rewrite results), `PostToolUseFailure`, `UserPromptSubmit`, `Stop`,
`SubagentStart`/`SubagentStop`, `PreCompact`, `PermissionRequest`, `Notification`;
TypeScript adds `SessionStart`/`SessionEnd`, `MessageDisplay`, `PostToolBatch`. Matchers
are tool-name regexes (`"Write|Edit"`, `"^mcp__github__"`).

## Subagents

Programmatic `AgentDefinition`s give the main agent delegable specialists with isolated
context (a subagent inherits tools and project config, not conversation history):

```python
from claude_agent_sdk import AgentDefinition

options = ClaudeAgentOptions(
    allowed_tools=["Read", "Glob", "Grep", "Agent"],
    agents={
        "code-reviewer": AgentDefinition(
            description="Expert code review specialist. Use for security and quality review.",
            prompt="You are a code review specialist... be thorough but concise.",
            tools=["Read", "Grep", "Glob"],
            model="haiku",          # cheaper model for the fan-out work
        ),
    },
)
```

Claude invokes subagents automatically based on `description`, or explicitly when the
prompt names them. Definitions support `maxTurns`, `background` (non-blocking), `effort`,
and per-agent `mcpServers`. This is the SDK-native orchestrator-worker pattern — see the
`multi-agent-orchestration` skill for when to reach for it.

## Sessions: capture, resume, fork

```python
# capture
async for message in query(prompt="Design the refactor"):
    if isinstance(message, ResultMessage):
        session_id = message.session_id

# resume with full context (possibly hours later, different process)
options = ClaudeAgentOptions(resume=session_id)

# fork — branch the conversation; original stays intact
options = ClaudeAgentOptions(resume=session_id, fork_session=True)

# or just continue the most recent session in this cwd
options = ClaudeAgentOptions(continue_conversation=True)
```

Sessions persist to local disk by default (lost with the container); a `SessionStore`
adapter (S3/Redis/Postgres/custom) makes them survive host changes. Forking branches the
*conversation*, not the filesystem — file edits by a fork are real.

## Permissions

Evaluation order: hooks → deny rules → ask rules → permission mode → allow rules →
`can_use_tool` callback. Modes:

| Mode | Behavior |
|---|---|
| `default` | Unmatched tool calls fall through to your `can_use_tool` callback |
| `acceptEdits` | Auto-approve file edits + filesystem ops inside `cwd` |
| `plan` | Read-only exploration; edits always require approval |
| `dontAsk` | Deny instead of prompting — anything not explicitly allowed is refused |
| `bypassPermissions` | Approve everything (container-only; deny rules and hooks still apply) |

```python
async def can_use_tool(tool_name: str, tool_input: dict) -> bool:
    return not (tool_name == "Bash" and "rm" in tool_input.get("command", ""))

options = ClaudeAgentOptions(can_use_tool=can_use_tool)
```

For the design question of *what* to gate (irreversible actions, spend, external sends),
see the `agent-safety` skill.

## Cost and context management

- Every `ResultMessage` carries `total_cost_usd` — a **client-side estimate** from a
  bundled price table; use the Usage & Cost API for authoritative billing.
- Per-message `usage` gives input/output/cache tokens; `model_usage` breaks cost down per
  model (main agent vs subagents). Parallel tool-call messages share an ID and identical
  usage — **deduplicate by message ID** or you'll double-count.
- Prompt caching is automatic (default ~5-min TTL). To extend a cached block's TTL to 1 h,
  set `"cache_control": {"type": "ephemeral", "ttl": "1h"}` on that block in the request
  (1-h cache writes are billed at a higher write multiplier — see Anthropic's prompt-caching
  docs).
- Compaction is automatic near the context limit; hook `PreCompact` to archive transcripts.
- Cost levers, in order: cheaper `model` for subagents; `max_turns`; trimming `tools` (each
  tool schema is context on every turn); `effort` on subagent definitions.

## When to choose it vs LangGraph vs the raw API

| Situation | Pick |
|---|---|
| Agent works on files/repos/shell — coding agent, SRE bot, data-wrangling, CI automation | **Claude Agent SDK** — the built-in tool suite and permission system are exactly this job |
| You want MCP servers, subagents, session resume, and permissions without building a harness | **Claude Agent SDK** |
| You need explicit control flow — branches, retries, human-in-the-loop interrupts at arbitrary nodes, resumable graphs | **LangGraph** (see `langgraph-quickstart.md`) — the SDK's loop is model-driven, not graph-driven |
| Multi-provider or local-model requirement | **LangGraph / LlamaIndex / Pydantic AI** — the Agent SDK runs Claude models only (first-party, Bedrock, Vertex, Foundry) |
| A few tools, tight latency/token budget, no filesystem | **Raw API + your own loop** — the Agent SDK's harness overhead (system prompt, tool schemas, subprocess) isn't free |
| You want Anthropic to host loop + sandbox | **Managed Agents** (REST), not the SDK |

Rule of thumb: the Agent SDK occupies the middle ground the raw API (too bare) and
LangGraph (bring-your-own-everything, but any model) leave open — *provided* your model is
Claude and your agent benefits from a computer (files, shell, web).

## Headless / container deployment

- **Runtime**: Python 3.10+/Node 18+; budget ~1 GiB RAM, 5 GiB disk, 1 CPU per concurrent
  agent as a starting point, then measure peak RSS at your real session length.
- **Network**: outbound HTTPS to `api.anthropic.com` (or Bedrock/Vertex/Foundry endpoints)
  plus any MCP servers. No inbound requirements beyond your own app's port.
- **Isolation**: the agent has `bash` — treat the container as the sandbox. Run non-root,
  read-only rootfs where possible, restrict egress. Per-tenant: separate `cwd`,
  `setting_sources=[]`, and `CLAUDE_CONFIG_DIR` per tenant so sessions/settings never leak.
- **Session patterns**: ephemeral container per task (CI jobs, one-shot extractions);
  long-running container per user/thread (chat products) — pin sessions to containers by
  hashing `session_id`; hybrid with `SessionStore` + resume for pause-and-continue work.
- **Headless CLI cousin**: `claude -p "prompt" --output-format stream-json` gives the same
  harness from shell scripts; the SDK is that, with types and hooks.
- **Observability**: OpenTelemetry export via `CLAUDE_CODE_ENABLE_TELEMETRY=1` and
  standard `OTEL_*` env vars; prompt/tool payloads excluded unless opted in.

## Gotchas (recent breaking changes)

1. **`ClaudeCodeOptions` → `ClaudeAgentOptions`** at the v0.1 rename. Old snippets using
   the former (or `claude-code-sdk` on PyPI) are pre-rename.
2. **No default system prompt** since the rename — an SDK agent does NOT get Claude Code's
   CLI persona unless you opt in. If your agent behaves "dumber" than the CLI, this is why.
3. **Filesystem settings ARE loaded by default**: the SDK reads `.claude/` from the cwd and
   `~/.claude/` unless you pass `setting_sources=[]`. This is *different* from the system
   prompt (see #2) — project skills, `settings.json`, and CLAUDE.md config apply, but the
   CLI persona does not. Per-tenant isolation requires `setting_sources=[]` plus a separate
   `CLAUDE_CONFIG_DIR`.
4. **Sessions die with the container** unless you configure a `SessionStore` or mount a
   durable volume over the config dir.
5. **Cost is an estimate** — see above; also budget for the harness's own token overhead
   (system prompt + tool schemas per turn) when comparing against a raw-API design.
