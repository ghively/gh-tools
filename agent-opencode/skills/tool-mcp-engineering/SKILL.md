---
name: tool-mcp-engineering
description: "Giving agents new capabilities: tool design, choosing skill/script/CLI/MCP/plugin surfaces, MCP server authoring and debugging, and adapting HTTP APIs into MCP servers. Use when an agent needs a new action, a tool schema is confusing the model, an MCP server fails to start, or an existing API needs an agent-safe wrapper. Does not cover tool policy and permissions in depth (see agent-safety) or OpenCode skill/plugin authoring craft in general (see opencode-authoring)."
---

# Tool and MCP Engineering

Tools are where agent intent becomes side effect. Design the smallest capability surface that gives the model the right affordance and gives operators the right safety boundary.

The recurring failure mode in this area is overbuilding: reaching for a full MCP server when a script would do, wrapping one tool per API endpoint when the model needs task-level operations, or shipping a destructive tool with no guard. This skill's decision tree exists to push you to the *lowest* surface that solves the problem — built-in tool, then skill+script, then existing MCP server, then a new MCP server, then a full plugin — and only escalate when the lower surface genuinely cannot carry the capability.

## When to Use

- The agent needs a capability it does not currently have.
- You are deciding between a skill, script, CLI wrapper, existing MCP server, new MCP server, or plugin.
- A tool exists but the model calls it incorrectly.
- An MCP server fails to start, list tools, authenticate, or respond.
- You need to adapt an HTTP API into MCP.

**Don't use for:** permission policy and sandbox enforcement (`agent-safety` skill), broader OpenCode surface authoring (`opencode-authoring` skill), or model choice (`model-selection` skill).

A symptom often points at a different layer than where the fix lives: "the model calls the wrong tool" is usually a *naming/schema* problem, not a model problem; "the tool is missing" is usually a *server startup/handshake* problem, not a registration problem; "the agent does the wrong thing" is often a *return-format* problem (raw blob vs actionable summary). This skill helps you locate the right layer before editing it.

## Capability Surface Decision Tree

```
Built-in tool already covers it?
├─ yes -> write instructions or a skill
└─ no
   Existing CLI/script/client covers it?
   ├─ yes -> skill + script/CLI wrapper
   └─ no
      Maintained MCP server exists?
      ├─ yes -> connect and audit it
      └─ no
         Reusable across MCP clients?
         ├─ yes -> build MCP server
         └─ no -> build a script-backed skill first
```

### Worked Cases

| Need | Lowest surface | Why |
|---|---|---|
| Agent should run the test suite with the right flags | Skill (instructions) | Built-in shell tool already runs it; a skill just teaches the invocation |
| Deterministic file transform the model gets wrong | Skill + script | Logic is local and deterministic; no need for a server |
| Read issues from a tracker the agent has no tool for | Existing MCP server | A maintained server already covers it; connect and audit |
| Typed capability reused by three different MCP clients | New MCP server | Cross-client reuse justifies the protocol work |
| One local agent needs a niche API | Script-backed skill | Only one client; a server is overhead |
| Bundle of skills + hooks + agents + assets | Full plugin | Multiple surface types must ship together |

When in doubt, start one rung lower than your instinct. Promoting a script to a server later is cheap; demoting an overbuilt server to a script is painful because consumers already depend on it.

## Tool Design Checklist

| Check | Rule |
|---|---|
| Name | User intent, not implementation detail. |
| Description | Says when to call and when not to call. |
| Parameters | Flat, typed, bounded, with examples where useful. |
| Return | Summarizes result and tells the model the next useful action. |
| Errors | Auth/rate-limit/validation/retryability are explicit. |
| Side effects | Idempotent or preview/apply gated. |
| Scope | One task-level operation, not arbitrary admin power. |

The checklist is a gate, not a style guide. A tool with an implementation-shaped name (`run_sql_query_against_postgres`) will be called at the wrong times because the model cannot tell when it applies; a tool that returns a raw blob forces the model to re-parse every call; a destructive tool without a preview is an incident waiting to happen. Before-and-after naming and schema examples live in `references/tool-design.md`.

## MCP Minimum Bar

- Start with stdio unless remote HTTP is necessary.
- Implement `initialize` cleanly and make `tools/list` fast.
- Keep tool names unique.
- Load secrets from documented env/config locations.
- Provide read-only probes before writes.
- Test with MCP Inspector and an isolated health check before attaching to an agent.

The minimum bar exists because most MCP failures are not logic bugs — they are startup, handshake, and auth failures that only appear once the server is detached from the agent. Testing in isolation (Inspector, the bundled `scripts/mcp-health-check.py`) catches these before they reach the model, where they manifest as confusing "tool missing" or "tool hung" symptoms. A complete minimal server (Python FastMCP and TypeScript) and the debugging decision tree live in the references below.

The handshake the minimum bar protects is short and worth memorizing: the client sends `initialize` (with a protocol version), the server replies with its version and capabilities, the client sends `notifications/initialized`, and only then can the client call `tools/list` and `tools/call`. A server that fumbles any step of that exchange is broken even if its tool logic is perfect — which is why the health-check script runs exactly this sequence and nothing more.


## Reference Router

| Load | When |
|---|---|
| `references/tool-design.md` | Designing names, schemas, returns, errors, and idempotent side effects. |
| `references/when-to-build-what.md` | Choosing built-in tools, skill+script, existing MCP, new MCP, or full plugin. |
| `references/mcp-security-and-primitives.md` | Advanced: server-side security (tool-result injection, description poisoning), OAuth for remote MCP (DCR + PKCE), Streamable HTTP, prompts vs resources vs tools, tool annotations, outputSchema, sampling/roots/elicitation, MCP client patterns |
| `references/mcp-server-authoring.md` | Building MCP servers against the current protocol and official SDKs. |
| `references/mcp-debugging.md` | Diagnosing startup, `tools/list`, auth, package, and timeout failures. |
| `references/api2mcp-guide.md` | Adapting HTTP APIs with the bundled template and OpenAPI tool generation. |
| `scripts/mcp-health-check.py` | Run stdio initialize + `tools/list` probes from a YAML/JSON server list. |
| `assets/api2mcp-template/` | TypeScript starter for generic HTTP API wrappers with generated `tools.json`. |

Typical entry points: a *new capability* starts at the decision tree and `when-to-build-what.md`; a *tool the model misuses* starts at `tool-design.md`; a *server that will not start* starts at the debugging decision tree in `mcp-debugging.md`; an *HTTP API to wrap* starts at `api2mcp-guide.md` and the template. The references are written so you can land in the right one from the symptom, not from a table of contents.

### Symptom → Reference

| Symptom | Read first |
|---|---|
| "What surface should this capability be?" | `when-to-build-what.md` |
| "The model calls the wrong tool / wrong args" | `tool-design.md` (naming + schema) |
| "The tool returns garbage the model can't use" | `tool-design.md` (return + error format) |
| "My MCP server won't start / list / auth" | `mcp-debugging.md` (decision tree) |
| "How do I write an MCP server at all?" | `mcp-server-authoring.md` (minimal servers) |
| "I have an HTTP API and want agent tools" | `api2mcp-guide.md` + `assets/api2mcp-template/` |
| "A server broke after a package upgrade" | `scripts/mcp-health-check.py` in CI |

 |

## Pitfalls

1. **Building a whole MCP server for one local need.** If a script plus skill works, start there.
2. **Wrapping one tool per endpoint.** Agents need task-level operations, not your API's internal resource map.
3. **Shipping destructive tools with no guard.** Writes need preview, idempotency, and explicit enablement.
4. **Ignoring existing official servers.** Do not hand-roll GitHub/Slack/Notion-style integrations without checking maintained servers first.
5. **Returning raw blobs.** The model needs actionable summaries and stable IDs.
6. **Debugging through the agent.** Test MCP servers in isolation before blaming the model.
7. **Exposing admin/delete endpoints because the OpenAPI spec contains them.** The spec is an inventory, not a tool surface — curate it.
8. **Trusting a server that lists tools but fails the handshake.** `tools/list` returning data does not mean `initialize` is healthy; run the full handshake probe.
