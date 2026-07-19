> Last verified: 2026-07. MCP specification and SDKs are actively evolving; verify against the current specification and SDK release line before implementation.

# MCP Server Authoring

Primary sources checked: [MCP specification](https://modelcontextprotocol.io/specification), [official TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk), and [official Python SDK](https://github.com/modelcontextprotocol/python-sdk).

## Protocol Model

MCP uses JSON-RPC between a host/client and server. Servers expose tools, resources, and prompts. Clients can provide roots, sampling, and elicitation. Connections negotiate capabilities at initialize time.

A session begins with the client sending `initialize` (protocol version + client capabilities + client info); the server responds with its version and capabilities; the client sends `notifications/initialized`; then the client can call `tools/list`, `tools/call`, `resources/list`, and so on. The bundled `scripts/mcp-health-check.py` exercises exactly this handshake (`initialize` → `notifications/initialized` → `tools/list`) so you can verify a server answers correctly before ever attaching an agent. Most startup bugs are caught right at this boundary: a server that never replies to `initialize` or hangs on `tools/list` is broken regardless of how correct its tool logic is.

## Current Spec Signals

The public specification page points to a 2025-11-25 schema as authoritative while SDK repositories are actively preparing 2026-07 spec support. Treat v2 SDK lines as pre-release until their docs mark them stable; v1 SDK lines remain the production default where the repositories say so.

## Transports

| Transport | Use when |
|---|---|
| stdio | Local subprocess server launched by the host. Best first implementation path. |
| Streamable HTTP | Remote or service-hosted MCP with HTTP infrastructure, auth, and scaling. |

## Auth

Current MCP auth guidance centers on OAuth-style authorization for HTTP servers, with the server behaving like a resource server and clients obtaining/using access tokens. For local stdio servers, auth usually comes from environment variables or local config. Never bake secrets into server code or plugin assets.

A practical split: for stdio servers, read secrets from documented env vars at startup and fail loudly (with a clear message) if a required var is missing — the host launches the subprocess with the env it needs. For Streamable HTTP servers, treat the server as a resource server and require a bearer access token obtained out-of-band (or via the OAuth flow the spec describes). Either way, secrets live in the environment or a secret store, never in source or in a plugin asset.

## Server Features

| Feature | Use |
|---|---|
| Tools | Model-invoked actions with schemas. |
| Resources | Readable context/data surfaces. |
| Prompts | Reusable prompt templates/workflows. |
| Elicitation | Server asks the client/user for missing information. |
| Sampling | Server requests model assistance through the client, subject to host controls. |
| Structured output | Return machine-readable content when the client supports it. |

## TypeScript Quickstart

Use the official SDK package line recommended by the repository for your stability target. A minimal server registers a tool with a schema and connects a stdio transport. Keep generated or domain-specific tools small and task-oriented.

Minimal server (illustrative; mirrors the SDK's documented `McpServer` + `StdioServerTransport` pattern used by the bundled `assets/api2mcp-template/`). Verify imports against the current SDK release before copying:

```typescript
// Illustrative minimal MCP server (TypeScript). Verify against current SDK.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const server = new McpServer({ name: "docs-server", version: "0.1.0" });

server.tool(
  "search_docs",                                         // tool name (intent)
  "Search the docs index. Use when the user asks about documented features.", // description
  { query: z.string().min(1), limit: z.number().int().min(1).max(20).default(5) },
  async (input) => {
    const hits = await index.search(input.query, input.limit);   // your logic
    return {
      content: [{ type: "text", text: formatHits(hits) }]        // model-readable summary
    };
  }
);

await server.connect(new StdioServerTransport());
```

The shape to notice: `server.tool(name, description, zodSchema, handler)` — name and description are model-facing, the schema becomes the tool's input contract, and the handler returns `content` the model reads. This is the same structure the api2mcp template uses for its generic tools.

## Python Quickstart

Use the official `mcp` package and FastMCP/MCPServer API appropriate to the release line. Type hints and docstrings become schemas and tool descriptions. Use `mcp dev server.py`/Inspector workflows where supported for local debugging.

Minimal server (illustrative; uses the documented FastMCP decorator pattern). Verify the import path and run command against the current SDK release before copying:

```python
# Illustrative minimal MCP server (Python). Verify against current SDK.
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("docs-server")


@mcp.tool()
def search_docs(query: str, limit: int = 5) -> str:
    """Search the docs index. Use when the user asks about documented features.

    Args:
        query: Non-empty search string.
        limit: Max hits to return (1..20).
    """
    hits = index.search(query, limit)        # your logic
    return format_hits(hits)                 # model-readable summary


if __name__ == "__main__":
    mcp.run()                                # stdio transport by default
```

In the FastMCP style, the function signature *is* the schema: type hints become parameter types, the docstring becomes the tool description, and defaults become defaults. That is the whole contract — no separate schema object. Debug locally with `mcp dev server.py` (where supported) or the MCP Inspector.

## Naming and Schema Rules

- Tool names should be verbs at task level: `search_docs`, `create_ticket`, `get_customer`.
- Inputs should be flat, typed, documented, and bounded.
- Avoid arbitrary JSON blobs unless the tool is intentionally generic.
- Separate preview from apply for destructive actions.
- Return concise text plus structured data when useful.

### Tool schema checklist (per tool)

Before registering a tool, confirm each item — a tool that fails any of these will confuse the model or the operator:

| Item | Check |
|---|---|
| Name | Verb at task level; unique across the server |
| Description | States when to call *and* when not to call |
| Parameters | Flat, typed, bounded, with examples in descriptions |
| Return | Summarizes outcome + next useful action or stable ID |
| Errors | Auth / validation / rate-limit / retryability in text |
| Destructive? | Has preview/dry-run path and idempotency |

A server that registers 40 tools where half fail this checklist is worse than a server with 8 clean tools — the model has to navigate noise, and the operator cannot audit the surface. Fewer, task-level tools win.

## Distribution

MCP servers are distributed through package registries, vendor repos, curated registries, and direct config snippets. Prefer official/vendor-maintained servers for major services. Audit third-party servers as code with the user's authority.

A client config snippet mounts a server as a subprocess (stdio) with its command, args, and environment. Shape (illustrative; matches the api2mcp template README's example):

```json
{
  "mcpServers": {
    "docs-server": {
      "command": "node",
      "args": ["/absolute/path/to/dist/server.js"],
      "env": { "DOCS_INDEX": "/var/data/docs.idx" }
    }
  }
}
```

Two distribution rules hold regardless of channel: absolute paths in args (the host may not share your working directory), and secrets in `env` (never in args, where they are visible in process lists). When consuming a third-party server, read its source or at minimum its tool list and permissions before enabling it — a server runs with the user's authority, so treat it as code you are executing.

