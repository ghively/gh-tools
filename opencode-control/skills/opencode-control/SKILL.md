---
name: opencode-control
description: Control and configure the OpenCode AI coding agent (sst/anomalyco opencode) end-to-end via the opencode MCP server. Use whenever the user wants to drive, inspect, configure, optimize, or extend their opencode install — including ANY of: check server/health/status, run a prompt or coding task through opencode, list/create/manage sessions, design or author agents & subagents, write custom slash-commands, create skills, tune opencode.json (models, providers, MCP servers, permissions, formatters, LSP, instructions), manage the model/provider catalog, drive a running TUI, search the project, or call opencode over ACP (Agent Client Protocol) as an agent from anywhere. Trigger even when the user just says "my opencode", "run this in opencode", "make an opencode agent", "optimize my opencode config", "call opencode", or "set up opencode" — drive the live system through the tools, don't answer from memory.
---

# Controlling opencode

You drive a live **opencode** install two ways, both exposed by the `opencode` MCP server:

1. **HTTP server** (`opencode serve`) — the same REST+SSE API the TUI/desktop/IDE
   clients use. ~162 operations. Reached via a **generic passthrough** (`oc_call` /
   `oc_discover` / `oc_schema`) plus **curated tools** for the common jobs.
2. **ACP** (Agent Client Protocol) — `oc_acp_prompt` spawns `opencode acp` and drives
   it as a JSON-RPC agent over stdio. This runs prompts **without needing a running
   server** and is the "call opencode from anywhere" path.

Plus on-disk **authoring** tools (`oc_agent_write`, `oc_command_write`, `oc_skill_write`,
`oc_config_update`) for configuring agents, commands, skills, and `opencode.json`.

## First move: orient with a live read

Do **not** answer opencode questions from memory — the system is fast-moving (multiple
releases/day) and the user's config is specific. Start with:

- `oc_status` — reachability, health, version, paths, current project, default
  model/agent, session count, configured providers. **Always start here.**
- If `oc_status` says the server is unreachable, the HTTP tools won't work. Run
  `oc_server(action='start')` to launch a headless `opencode serve`, or tell the user
  to run `opencode serve --port 4096`. (The ACP tools and `*_write` tools work
  regardless — they don't need a running server.)

For anything not covered by a curated tool: `oc_discover("<keywords>")` to find the
endpoint, `oc_schema("<operationId>")` to get its params, then `oc_call(...)`.

## The toolbox

**Orientation & passthrough**
- `oc_status` · `oc_discover(query)` · `oc_schema(operation)` · `oc_call(method, path, params, body, confirm)`
- `oc_server(action)` — status | start | stop a headless server for the HTTP tools

**Sessions & running work**
- `oc_sessions` · `oc_session(id, messages, todos)` · `oc_session_create` · `oc_messages`
- `oc_prompt(text, session_id, agent, model, files, wait)` — send a prompt, wait for the
  reply. Creates a session if none given. **This runs a model — it costs tokens.**
- `oc_shell(id, command)` · `oc_command(id, command, arguments)` — run a slash-command
- `oc_abort(id)` · `oc_session_manage(id, action)` — summarize|fork|share|unshare|init|rename|delete

**Config & authoring** (see `references/configuring-opencode.md` and `references/agents-and-workflows.md`)
- `oc_config_get(scope)` · `oc_config_update(patch, confirm, scope)`
- `oc_agents` · `oc_agent_write(name, prompt, description, mode, model, tools, ...)`
- `oc_commands` · `oc_command_write(name, template, ...)`
- `oc_skills` · `oc_skill_write(name, description, body, ...)`
- `oc_plugin_write(name, body, ...)` — author a JS/TS plugin (hooks/custom tools)
- `oc_models(provider)` · `oc_providers` · `oc_mcp(action, name, config)` · `oc_resources`
- `oc_auth(action, provider, key)` — provider credentials (methods|set|remove)

**Interaction with running agents**
- `oc_permissions(action, ...)` — list/reply to pending permission requests (once|always|reject)
- `oc_questions(action, ...)` — list/reply/reject agent questions
- `oc_tools(provider, model, schemas)` — the tools opencode agents can call

**Project, VCS & UI**
- `oc_projects(action, ...)` — list|current|directories|init_git|update
- `oc_worktree(action, ...)` — git worktrees (list|create|remove|reset)
- `oc_find(query, kind)` — text|file|symbol · `oc_file(path, read)`
- `oc_vcs(action, patch)` — status|diff|raw|info|apply · `oc_diagnostics` — lsp/formatter/file status
- `oc_revert(session_id, action, message_id)` — undo/redo in a session
- `oc_message` · `oc_session_diff` — inspect a single message / a session's file diff
- `oc_pty(action, ...)` — PTY lifecycle (shells|list|create|get|remove; no live terminal I/O)
- `oc_tui(action, ...)` — drive a running TUI · `oc_events(seconds)` — tail the SSE bus

**Maintenance & data**
- `oc_stats` — token usage & cost · `oc_export(session_id)` / `oc_import(file)` — session data
- `oc_upgrade(target)` — upgrade opencode

**ACP connector** (see `references/acp.md`)
- `oc_acp_probe(cwd)` — prove the ACP channel (handshake only, no model call, always safe)
- `oc_acp_prompt(prompt, cwd, mode, files, permission, confirm, timeout)` — run one
  prompt as an ACP agent

## Safety — confirm-gate every write

Reads are free. **Writes are confirm-gated in the tools and you must confirm intent with
the user before calling them.** Specifically:

- `oc_call` with a non-GET method needs `confirm=true`.
- These need `confirm=true`: `oc_config_update`, `oc_agent_write`, `oc_command_write`,
  `oc_skill_write`, `oc_plugin_write`, `oc_mcp(add/connect/disconnect)`,
  `oc_session_manage(delete/unshare)`, `oc_auth(set/remove)`, `oc_permissions(reply)`,
  `oc_questions(reply/reject)`, `oc_projects(init_git/update)`, `oc_worktree(create/remove/reset)`,
  `oc_revert`, `oc_message(delete)`, `oc_pty(create/remove)`, `oc_vcs(apply)`,
  `oc_upgrade`, `oc_import`.
- `oc_prompt` and `oc_acp_prompt` **run models and can change files/run commands**.
  `oc_acp_prompt` defaults to `permission='reject'` (read-only: opencode can read, plan,
  and answer, but every edit/bash is rejected). To let it modify the project, pass
  `permission='allow'` (or `'always'`) **and** `confirm=true` — and confirm with the user first.
- Never run a mutating write autonomously to "self-test." Prefer reversible proofs
  (create a throwaway agent/session, verify, delete) and only with the user's go-ahead.
- `oc_config_update(scope='global')` rewrites the user's `~/.config/opencode` config on
  disk. Show the exact patch and confirm before writing. Back up substantial changes.

## Where things live

opencode config is **files**, not just API state. Agents, commands, and skills are
markdown files under `~/.config/opencode/` (global) or `<project>/.opencode/` (project);
`opencode.json` holds models/providers/MCP/permissions. The `*_write` tools produce the
correct on-disk format (verified: opencode loads what they write). `oc_config_update`
patches `opencode.json` (deep-merged; the `instructions` array is concatenated, not
replaced). Restart of opencode is not needed — config is re-read per session.

## References (read the relevant one before non-trivial work)

- `references/conventions.md` — auth model, error vocabulary, param encoding, the
  two API generations, quirks, the "covered vs reachable" honesty rules.
- `references/api-map.md` — the full 188-operation surface, grouped by domain.
- `references/configuring-opencode.md` — `opencode.json` schema (every key), config
  file locations & precedence, providers/models, MCP servers, permissions, plugins,
  rules/instructions, variable substitution. **Read before editing config.**
- `references/agents-and-workflows.md` — designing agents & subagents, custom commands,
  skills, plugins, and model/permission **optimization** patterns. **Read before
  authoring agents or workflows.**
- `references/acp.md` — the ACP protocol, the connector's behavior, permission policy,
  and how to drive opencode as an agent.

## Honesty

"Covered" means the operation actually works for the user, not that an endpoint exists.
When you report, distinguish built-and-verified from method-present-but-unrun, and name
hard limits plainly (see conventions.md's gap taxonomy). Surface real findings you notice
(a stopped server, a plaintext API key in config, an LSP that isn't running).
