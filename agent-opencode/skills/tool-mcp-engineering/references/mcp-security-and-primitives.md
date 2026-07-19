# MCP Security & Advanced Primitives

The `mcp-server-authoring.md` reference covers the server-side basics.
This reference fills the security, OAuth, transport, and advanced-primitive
gaps that block production MCP deployments. For tool design, see
`tool-design.md`; for the client side, see below.

## Server-Side Security

### Tool-Result Injection

The highest-leverage MCP security gap: an untrusted upstream returns
content, the MCP server returns it verbatim as tool content, and the
model reads it as instructions. The api2mcp template does exactly this
by design — any `GET` response becomes model-facing text.

**Defenses:**

1. **Sanitize tool results.** Before returning to the client, strip or
   encode content that could be read as instructions:
   - Markdown code fences from upstream sources.
   - HTML/XML that may contain injected script comments.
   - Content matching the model's own instruction-following patterns
     ("ignore previous instructions," "you are now," etc.).

2. **Opaque-before-text wrapper.** Return tool results in a structured
   envelope the model can parse without trusting:

   ```json
   {
     "data": "<the actual upstream content>",
     "source": "https://trusted-api.example.com",
     "sanitized": true,
     "size_bytes": 12345
   }
   ```

   The `data` field is the upstream content, marked as opaque. The model
   is instructed to treat `data` as retrievable text, never instructions.

3. **Size caps.** Upstream content over 10 KB should be truncated or
   paged. A 500 KB API response entering the model context is both a DoS
   vector and a prompt-injection surface.

### Tool-Description Poisoning

A third-party MCP server's tool descriptions are model-facing text. A
malicious server can embed instructions ("always approve my tool calls")
in the `description` field. The model reads them as system content.

- **Server audit checklist:** Every third-party server's tool
  descriptions are audited for embedded instructions. See
  `../../agent-safety/references/security-audit-checklist.md`.
- **Client-side sandbox:** The client can wrap all tool descriptions in
  a markup that signals "this is a tool description, not a system
  instruction."

### Client-Side MCP Security

When consuming MCP servers from a client (any agent harness):

1. **Trust the server or don't.** A local MCP server runs on your
   machine with your permissions. A remote MCP server runs on someone
   else's. Vet both.
2. **Tool allowlist per server.** Don't grant `*` as the tool allowlist.
   Explicitly name the tools the agent may call from that server.
3. **Tool result size limits.** Instruct the agent to treat results over
   N bytes as data, not instructions. This is the prompt-defense
   baseline applied at the consumption layer.
4. **Server identity.** Remote servers MUST use TLS and SHOULD
   authenticate via OAuth or API key.

## OAuth for Remote MCP (Streamable HTTP)

The MCP 2025-06-18 spec formalizes an OAuth 2.0 profile for remote
servers. The simplified flow:

```
Client                          Server                    Auth Server
  │                                │                           │
  │── GET /.well-known/oauth-  ──►│                           │
  │   authorization-server        │                           │
  │◄── {issuer} ─────────────────│                           │
  │                                │                           │
  │── GET {issuer}/.well-known/  ──────────────────────────►│
  │   oauth-authorization-server                               │
  │◄── {authorization_endpoint,  ───────────────────────────│
  │    token_endpoint,                                         │
  │    registration_endpoint}                                  │
  │                                │                           │
  │── POST {registration_endpoint} ─────────────────────────►│
  │   (RFC 7591 Dynamic Client)                                 │
  │◄── {client_id, client_secret} ───────────────────────────│
  │                                │                           │
  │── Run PKCE flow ──────────────────────────────────────►│
  │   authorize → code → token                                 │
  │◄── {access_token, refresh_token} ───────────────────────│
  │                                │                           │
  │── Connect to server with ──►│                           │
  │   Authorization: Bearer ...   │                           │
```

**Key differences from API Key auth:**

1. **Dynamic Client Registration (RFC 7591):** The client registers on
   first connect; no pre-provisioned client ID. The registration endpoint
   URL is discovered from the server's metadata.
2. **PKCE:** Public clients (CLI, IDE extension) use PKCE; no client
   secret in the source code.
3. **Refresh token rotation:** After token expiry, the client refreshes.
   The refresh token itself may rotate (one-time use), requiring the
   client to persist the new token atomically.
4. **Protected Resource Metadata (RFC 9728):** The server advertises
   capabilities the client can access with the token. This is the MCP
   server's way of saying "with your token, you can call tools A, B, C
   but not D."

### Streamable HTTP Transport

The legacy HTTP+SSE transport is deprecated in favor of Streamable HTTP
(2025-03-26 spec). Key changes:

- **No SSE.** Responses are streamed via HTTP chunked transfer encoding.
- **Session-scoped endpoint.** Each MCP session gets a unique URL
  (opaque token in the path). The client connects to it.
- **Resumability.** If the connection drops, the client reconnects to
  the same session-scoped URL and the server replays missed events.
- **No persistent connection required.** The client POSTs to the
  session URL for each message exchange; the server responds with
  chunks.

```python
# Streamable HTTP client pseudocode
session = httpx.post(f"{server}/sse", json={"method":"initialize","params":{...}})
session_id = session.headers["Mcp-Session-Id"]

# Subsequent exchanges
resp = httpx.post(
    f"{server}/message?sessionId={session_id}",
    json={"method":"tools/call","params":{"name":"search","arguments":{...}}},
    stream=True
)
for chunk in resp.iter_bytes():
    process(chunk)
```

The `api2mcp-template` in the skill's assets is stdio-only. For a
Streamable HTTP server, replace `StdioServerTransport` with
`StreamableHTTPServerTransport` and add the session-ID header.

## Prompts vs Resources vs Tools

The three MCP primitives are often confused. Choose by intent:

| Primitive | When to use | Example |
|---|---|---|
| **Tool** | The model should actively invoke it to achieve a goal | Search, deploy, create-issue, summarize |
| **Resource** | Static or semi-static content the model reads on demand | API docs, database schema, user manual |
| **Prompt** | Pre-built prompt templates the model can use as starting points | `/review` template, `/summarize` template |

**Decision rule:** if the model initiates the call → tool; if the
model reads pre-existing content → resource; if the user initiates
via a slash command → prompt.

Tools are the most common and the default. Add resources when the data
is large, retriable, and the client should handle caching. Add prompts
when you want to offer reusable templates (these are the closest MCP
equivalent to OpenCode commands or skills).

## Tool Annotations

The MCP spec's `annotations` field on tool definitions maps directly to
agent-safety concerns:

| Annotation | Meaning | Use in safety policy |
|---|---|---|
| `readOnlyHint` | The tool does not modify state | Mark as "safe for unauthorized use" |
| `destructiveHint` | The tool modifies, deletes, or externalizes state | Gate with HITL interrupt |
| `idempotentHint` | Calling twice with same args produces same result | Safe to retry on transient failures |
| `openWorldHint` | The tool may interact with external entities not controlled by the server | Additional vetting required |

Every tool definition SHOULD include these annotations. The agent
harness reads them to decide permission posture without inspecting
tool names manually.

## Tool `outputSchema`

Structured output from tools — the tool declares what its result looks
like. Benefits:

1. **Model-readable.** The model knows the shape before calling, which
   improves structured-output accuracy.
2. **Client-validated.** The client can validate tool results before
   passing them to the model.
3. **Cache-friendly.** Structured results are easier to diff for
   cache invalidation.

```json
{
  "name": "search_tickets",
  "description": "...",
  "inputSchema": { "type": "object", "properties": { "query": { "type": "string" } } },
  "outputSchema": {
    "type": "array",
    "items": {
      "type": "object",
      "properties": {
        "id": { "type": "string" },
        "priority": { "enum": ["P0", "P1", "P2", "P3"] },
        "summary": { "type": "string" }
      }
    }
  }
}
```

## Sampling, Roots, and Elicitation

### Sampling

An MCP server can request the client to run an LLM completion (the
server acts as the consuming agent). Use when:

- The server needs to summarize a database result before returning it.
  (The server calls the client's LLM; the cost bills to the client.)
- The server needs to translate content between languages.
- The server needs to extract entities from raw text.

Sampling is NOT the main interaction pattern. It is a side-channel for
server-side operations that benefit from LLM judgment.

### Roots

Roots tell the server which directories or URIs the client has mounted
and trusts. The server can then access resources within those roots.

- **Use case:** An MCP server that reads project files to provide
  code intelligence. The client declares `"/workspace"` as a root;
  the server reads files within it.
- **Security:** The client must explicitly declare each root. A server
  that attempts to read outside declared roots should be denied by the
  client's MCP implementation.

### Elicitation

The MCP term for the server requesting structured input from the user.
Example: the server discovers an ambiguous entity and asks the user to
disambiguate before proceeding.

- **Pattern:** Server returns an `elicitation` request type; the client
  shows a prompt to the user; the server receives the response.
- **Risk:** A malicious server could use elicit to exfiltrate user data
  via a "confirm your email" prompt that sends to the server. Clients
  must show elicit requests as server-initiated (with the server name)
  and allow the user to deny.

## MCP Client Patterns

When building an agent harness that consumes MCP servers:

1. **Capability discovery.** `tools/list` at connect time, not every
   turn. Cache the list; the agent's system prompt includes tool names
   and descriptions.
2. **Tool call routing.** The agent calls `tools/call` via the harness.
   The harness routes to the correct MCP server.
3. **Progress and cancellation.** The `notifications/progress` and
   `notifications/cancelled` mechanisms let the server report long-
   running progress and accept cancellation from the client. Wire these
   in the harness for any tool with a timeout > 5 seconds.
4. **Structured content.** Tool results with `structuredContent` are
   model-friendly JSON. Fall back to `content` (text) for human-
   readable results.
5. **Resource subscription.** `resources/subscribe` lets the client
   receive updates when a resource changes (file watcher, etc.). Use
   for code intelligence servers where the file changed but the tool
   list stayed the same.

## Pitfalls

1. **Tool results as raw upstream content.** Upstream JSON → MCP tool
   result → model context verbatim. Fix: sanitize; wrap in opaque
   envelope; size-cap.
2. **OAuth for local servers.** Local MCP doesn't need OAuth. Fix:
   stdio for local; OAuth for remote. Don't force OAuth on the
   single--user local case.
3. **Streamable HTTP without session resumption.** Connection drops;
   events lost. Fix: implement the session-scoped URL and replay.
4. **No tool annotations.** The harness cannot automate permission;
   every tool requires manual review. Fix: add `readOnlyHint`,
   `destructiveHint`, `idempotentHint` to every tool.
5. **Trusting third-party tool descriptions.** They become model-
   facing text. Fix: audit tool descriptions; wrap them in a markup
   that distinguishes tool schema from system instructions.
6. **Sampling without cost controls.** Server-side LLM calls bill to
   the client. Fix: set sampling limits; the client must approve
   sampling requests.
7. **Elicitation as exfiltration.** A structured prompt from the
   server that asks for sensitive data. Fix: show the server name;
   let the user deny.
8. **Mixing prompts, resources, and tools into one monolith.** All
   three are registered as "things the server provides," but the model
   interacts differently with each. Fix: use the decision table above;
   audit the server's surface by primitive type.
