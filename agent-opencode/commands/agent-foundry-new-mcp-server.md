---
description: Design and scaffold an MCP server after checking whether an existing server or CLI is simpler.
agent: build
---

Design an MCP server for `$ARGUMENTS`. Load `tool-mcp-engineering`. First check
existing servers and the CLI-plus-skill alternative. Then define task-level
tools, typed inputs, return contracts, idempotency, destructive guards,
transport, auth, and tests. After approval, scaffold with env-based secrets,
run the handshake health check, and register it in `opencode.json` under `mcp`
using `type: local` and an argument array, or `type: remote` and a URL. Do
not use the Claude-style `.mcp.json` file or its CLI registration command in
an OpenCode project.
