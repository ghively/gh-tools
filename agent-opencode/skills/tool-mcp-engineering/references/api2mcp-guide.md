# API to MCP Guide

The `assets/api2mcp-template/` directory is a small TypeScript template for wrapping an existing HTTP API as an MCP server.

## Pattern

Start with generic tools:

| Tool | Purpose |
|---|---|
| `api_probe` | Safe method/path probe with response preview. |
| `api_get` | Safe GET with query parameters and retry. |
| `api_post` | Guarded write. |
| `api_put` | Guarded update. |
| `api_delete` | Guarded deletion. |

Then generate or hand-author task-level tools once you know the useful operations.

## Auth

The template supports no auth, bearer, custom header, basic, and query-token modes through environment variables. OAuth should usually be handled outside the generic server first, then passed in as a bearer token unless you are building a full product-grade OAuth flow.

The mapping is mechanical: set `API_BASE`, pick `AUTH_MODE` (`none` / `bearer` / `header` / `basic` / `query`), and provide the token/credential the chosen mode reads. The destructive guard (`ALLOW_DESTRUCTIVE`) is independent of auth — you authenticate *as* someone, and separately decide whether mutating tools fire at all. Keep the guard `false` while you are still learning the API's shape.

## Destructive Guard

Mutating tools require `ALLOW_DESTRUCTIVE=true`. Keep it false while probing an API. For production, add preview/apply tools and idempotency keys for create/update/delete operations.

## OpenAPI to Tools

The included `scripts/generate-tools.mjs` reads an OpenAPI JSON file and emits a `tools.json` with method/path templates. This is a starting inventory, not the final interface. Rename generated tools into task-level operations and delete endpoints the agent should never call.

### Worked Example: OpenAPI → tools.json → task-level tools

Starting from a small OpenAPI snippet (illustrative):

```json
{
  "paths": {
    "/v1/tickets": {
      "get": { "summary": "List tickets", "operationId": "getTickets" },
      "post": { "summary": "Create a ticket", "operationId": "createTicket" }
    },
    "/v1/tickets/{id}": {
      "get": { "summary": "Get a ticket", "operationId": "getTicket" },
      "delete": { "summary": "Delete a ticket", "operationId": "deleteTicket" }
    }
  }
}
```

`generate-tools.mjs` produces a `tools.json` inventory using its documented shape (`name`, `description`, `method`, `pathTemplate`, `guarded`):

```json
{
  "tools": [
    { "name": "gettickets",        "description": "List tickets",         "method": "GET",    "pathTemplate": "/v1/tickets",        "guarded": false },
    { "name": "createticket",      "description": "Create a ticket",      "method": "POST",   "pathTemplate": "/v1/tickets",        "guarded": true  },
    { "name": "getticket",         "description": "Get a ticket",         "method": "GET",    "pathTemplate": "/v1/tickets/{id}",   "guarded": false },
    { "name": "deleteticket",      "description": "Delete a ticket",      "method": "DELETE", "pathTemplate": "/v1/tickets/{id}",   "guarded": true  }
  ]
}
```

This inventory is *not* the final interface. Rename to task-level intent, rewrite descriptions to say when to call, and decide which tools survive:

| Generated | Renamed / decided | Action |
|---|---|---|
| `gettickets` | `list_open_tickets` (description: "List open tickets; use when checking queue status") | Keep, sharpen |
| `createticket` | `create_ticket` (description: "Create a support ticket from a summary") | Keep, add idempotency |
| `getticket` | `get_ticket` (description: "Get a ticket by id to check progress") | Keep |
| `deleteticket` | — | **Delete**: agent should not call this through a generic surface |

The deletion tool is the important edit: the OpenAPI spec contains it, so the generator emits it, but exposing `delete` through a generic guarded path is exactly the kind of admin power an agent should not receive without a dedicated, preview-gated tool.

## Good Adaptation Sequence

1. Configure `API_BASE` and read-only auth.
2. Probe health and a few safe GET endpoints.
3. Generate `tools.json` from OpenAPI if available.
4. Remove dangerous or irrelevant generated tools.
5. Add task-level descriptions and path parameter names.
6. Enable writes only after preview, idempotency, and policy are designed.

## Warnings

- One endpoint is not always one good tool.
- Generated names are implementation-shaped; rewrite them for user intent.
- Never expose admin/delete endpoints just because the OpenAPI spec contains them.
- Rate limits and pagination belong in tool behavior, not in model guesswork.

Pagination is the warning most people miss. A generated `list_*` tool that returns the raw first page teaches the model to keep calling it with guessed offsets — slow, error-prone, and sometimes destructive (re-fetching side-effectful "list" endpoints). Bake pagination into the tool: accept a cursor or page token, return a stable `next_cursor` in the model-readable summary, and cap page size. The model should advance through a cursor you returned, not invent offsets.

