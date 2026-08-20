# opencode conventions, auth, quirks, and the gap taxonomy

Verified live against **opencode 1.x**. The project moves fast (multiple releases/day)
and `sst/opencode` now redirects to **`anomalyco/opencode`** — treat `GET /doc` (the live
OpenAPI spec) as the source of truth, not any hardcoded snapshot.

## Auth model

- The HTTP server binds **`127.0.0.1` only** by default and is **unauthenticated** unless
  `OPENCODE_SERVER_PASSWORD` is set. It prints `Warning: OPENCODE_SERVER_PASSWORD is not
  set; server is unsecured.` on startup.
- When secured, auth is **HTTP Basic**: username defaults to `opencode` (override with
  `OPENCODE_SERVER_USERNAME`), password is `OPENCODE_SERVER_PASSWORD`. `/doc` and every
  route sit behind it. The MCP server sends the Basic header automatically when `password`
  is set in `config.local.json`.
- Alternative for header-less clients (SSE/EventSource): `?auth_token=<base64(user:pass)>`.
- **Never** bind to `0.0.0.0` (e.g. `--mdns`, which flips the host) without a password.
- ACP mode (`opencode acp`) uses the host's existing provider credentials (from
  `opencode auth login`); it advertises an `opencode-login` auth method but if you're
  already logged in on the host you don't need to authenticate over the wire.

## Two API generations

There are two parallel HTTP surfaces:
- **Legacy** unprefixed routes (`/session`, `/config`, `/file`, `/tui/*`, `/event`) — what
  the stable `@opencode-ai/sdk` uses. The curated tools target these.
- **v2** under `/api/*` (`/api/session`, `/api/event`, `/api/fs/*`) — newer, thinner-
  documented, the direction of travel. Reach it with `oc_call('GET','/api/...')`.

Both are live. Prefer legacy for curated work; use v2 explicitly when you need something
only it exposes (e.g. `/api/fs/*`, `/api/integration/*`, `/api/pty` token flow).

## Call conventions

- Plain JSON in and out. Legacy routes return **bare arrays/objects** (not enveloped).
- Query params are standard querystring; bodies are JSON.
- `/file` and `/file/content` **require** a `path` query param (use `path=.` to list root).
- `/find` uses `pattern=`; `/find/file` and `/find/symbol` use `query=`.
- Some responses are huge: `/provider` is ~4 MB and `/config/providers` ~280 KB
  (openrouter alone lists 340 models). The curated `oc_providers`/`oc_models` tools
  filter server-side; if you `oc_call` these raw, expect large payloads.
- The `directory` header/`?directory=` query scopes a call to a specific project worktree
  when the server manages more than one.

## Error vocabulary

- `400` `{ "name": "BadRequest", "data": { "message": "...", "kind": "Query" } }` — missing/
  wrong param. The route exists; fix the params.
- `401` with `WWW-Authenticate: Basic` — server is secured; supply Basic auth.
- `404` — route/entity not found.
- A `400` on a POST/PATCH probe means the **method exists** (it validated your body) —
  useful to confirm a write method is present without mutating anything.

## Events / streaming

- `GET /event` is **per-project** (filtered by directory); `GET /global/event` is cross-
  instance. Both are SSE (`text/event-stream`) with a `server.heartbeat` every **10s**.
- MCP tool calls are request/response, so `oc_events(seconds=N)` only **tails** the bus
  for a bounded window and returns. There is no persistent subscription from a tool call —
  that's a transport limit, not a gap in opencode.

## Gap taxonomy — Works / Fixable / Hard-limit

Honest map from the live audit (opencode 1.x on this host). "Works" = read verified
and/or write path proven; "Fixable" = reachable but state/param-dependent; "Hard-limit" =
not practical through this integration.

### Works (verified live) — 49 curated tools
- Health/status/paths/current-project; config get/patch.
- Providers & models catalog; **provider auth** methods + API-key set/remove (`oc_auth`);
  MCP resources (`oc_resources`); the tool catalog agents can call (`oc_tools`).
- Sessions: list/get/create/messages/todos/children/abort; lifecycle (fork/share/summarize/
  init/rename/delete); **prompt proven live over both HTTP and ACP**; single-message get/
  delete, session diff, **revert/unrevert (undo/redo)**.
- Agents list; **agent authoring verified reversibly** (opencode loaded a written agent).
- Commands list + authoring; skills list + authoring; **plugin authoring** (`oc_plugin_write`).
- MCP status + add/connect/disconnect.
- **Interaction with running agents**: pending permission requests list + reply
  (once/always/reject), questions list + reply/reject.
- Projects list/current/directories/init-git/update; **git worktrees** create/remove/reset.
- Files list/read/status; find text/file/symbol; diagnostics (LSP/formatter/file status).
- VCS info/status/diff/raw + apply-patch.
- TUI control (verified live); PTY lifecycle (shells/list/create/get/remove).
- Maintenance: **stats** (token/cost), export/import sessions, upgrade.
- Full passthrough over all 188 operations; ACP handshake + prompt proven live, with
  per-session model override (best-effort via set_config_option).

### Fixable / conditional (reachable; depends on state or params)
- `/vcs/diff` returns **400 without ref params** and needs a git repo with changes; use
  `oc_vcs('status')` first, or pass refs via `oc_call`.
- LSP status, formatter status, `/find/symbol` return empty unless an **LSP server is
  configured and running** for the project's language (dependency-gated — configure `lsp`
  in `opencode.json` and open a real project dir).
- MCP/PTY/permission/question lists are empty until those things **exist** (no MCP
  configured, no terminal open, no pending prompt) — not a defect.
- `oc_config_update` deep-merges; to **remove** a key you often must rewrite the file, not
  patch (JSON-merge can't delete). For deletions, read → edit → write the file directly.
- Provider/MCP **OAuth** flows (`/provider/*/oauth/*`, `/mcp/*/auth/*`) are reachable but
  need a **browser round-trip** to complete — do the interactive step with the user.

### Hard limits (not practical here)
- **Live PTY terminal I/O**: `/pty` create/list work, but interactive attach is a
  WebSocket with ticket auth — streaming a live shell isn't something a request/response
  MCP tool can host. Passthrough can create/inspect PTYs; it can't be a terminal.
- **Persistent event subscription**: only bounded tailing (see above).
- **ACP audio content blocks**: opencode advertises `image`+`text` only (no `audio`).
- **ACP `reject_always`**: opencode offers only once/always/reject permission options.
- **No official Python SDK**: we talk raw HTTP (fine) — not a limitation for this plugin.

### Deliberately passthrough-only (reachable via `oc_call`, not curated)
These are niche multi-client / cloud / experimental features — reach them with `oc_call`
when needed rather than as curated tools:
- **Workspaces & sync** (`/experimental/workspace/*`, `/sync/*`) — multi-client session
  sync/steal/replay and workspace warp/adapters.
- **Console / control-plane** (`/experimental/console/*`, `/experimental/control-plane/*`) —
  opencode Zen/Console org switching and moving sessions between locations.
- **Project copies** (`/experimental/project/{id}/copy*`) — project duplication.
- **v2 `/api/*` mirrors** (integration/credential/reference/location/pty) — the newer API
  generation; use `oc_call('GET','/api/...')`. `oc_discover` lists them all.
- **Provider/MCP OAuth** (`/provider/*/oauth/*`, `/mcp/*/auth/*`) — need a browser round-trip;
  do the interactive step (`opencode auth login`, `opencode mcp auth <name>`) on the host.
- **Background subagents** (`/experimental/session/{id}/background`) — gated behind an
  experimental env flag on the host.

## "Covered" vs "reachable"

An endpoint existing ≠ the operation working for the user. Four things must line up: right
method, right params, dependency running, permission granted. When you report, say
"reaches the API" for passthrough coverage and reserve "works" for verified-live.
