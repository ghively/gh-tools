# Any-API MCP Template

A minimal TypeScript MCP server for adapting an existing HTTP API into agent-safe tools.

## What You Get

- Generic tools: `api_probe`, `api_get`, `api_post`, `api_put`, `api_delete`
- Auth modes: `none`, `bearer`, `header`, `basic`, `query`
- GET retry with backoff for common transient statuses
- Destructive-operation guard via `ALLOW_DESTRUCTIVE=false`
- Optional dynamic tools loaded from `tools.json`
- `scripts/generate-tools.mjs` to generate `tools.json` from an OpenAPI JSON file

## Install

```bash
npm ci
npm run build
```

## Configure

```bash
API_BASE=https://api.example.com/v1
AUTH_MODE=bearer
AUTH_TOKEN=replace-me
ALLOW_DESTRUCTIVE=false
```

## Run

```bash
npm run dev
```

MCP client config example:

```json
{
  "mcpServers": {
    "any-api": {
      "command": "node",
      "args": ["/absolute/path/to/dist/server.js"],
      "env": {
        "API_BASE": "https://api.example.com/v1",
        "AUTH_MODE": "bearer",
        "AUTH_TOKEN": "replace-me",
        "ALLOW_DESTRUCTIVE": "false"
      }
    }
  }
}
```

## Generate Dynamic Tools

```bash
OPENAPI_FILE=./openapi.json TOOLS_FILE=./tools.json npm run generate:tools
```

The generated file is an inventory. Review it before use, remove dangerous endpoints, and rewrite descriptions into task-level language.

## Tool Notes

- `api_probe` is for safe exploration and response previews.
- `api_get` retries on 429/502/503/504.
- `api_post`, `api_put`, and `api_delete` require `ALLOW_DESTRUCTIVE=true`.
- Generated tools use path templates such as `/users/{id}` with `pathParams`.

## Customize

Promote frequently used generic calls into named task-level tools in `src/server.ts`. Keep schemas flat, names intent-based, and errors model-readable.
