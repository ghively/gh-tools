# The ACP connector — driving opencode as an agent

**ACP** (Agent Client Protocol, by Zed / agentclientprotocol.com) is a JSON-RPC 2.0
protocol over stdio that lets any client drive a coding agent. opencode implements the
**agent** side via `opencode acp`. This plugin's `oc_acp_prompt` / `oc_acp_probe` tools
implement the **client** side, so you can run opencode as an agent from anywhere —
**no HTTP server required**.

## Why use ACP vs the HTTP `oc_prompt`?

| | `oc_prompt` (HTTP) | `oc_acp_prompt` (ACP) |
|---|---|---|
| Needs `opencode serve` running | yes | **no** (spawns its own process) |
| Isolation | shares the server's sessions/state | fresh process per call |
| Streaming detail | message parts via API | full `session/update` stream (thoughts, tool calls, plan) |
| File edits land | on the server's host | **on this host** (client handles `fs/write_text_file`) |
| Best for | integrating with an existing running opencode | one-shot agent calls, embedding, scripting |

Use ACP when you want a clean, self-contained agent run. Use HTTP when you're operating an
already-running opencode instance (its sessions, its TUI).

## Protocol facts (verified against opencode 1.x)

- Transport: **newline-delimited JSON** (NDJSON) over stdio — one JSON object per line, no
  embedded newlines. (Not LSP Content-Length framing.)
- `protocolVersion` is the integer **`1`** (v1 stable schema). opencode targets v1.
- Handshake: `initialize` → `session/new {cwd, mcpServers:[]}` → `session/prompt
  {sessionId, prompt:[ContentBlock]}` → streamed `session/update` notifications → final
  response with `stopReason` (`end_turn|max_tokens|max_turn_requests|refusal|cancelled`).
- opencode advertises: `loadSession`, `promptCapabilities {image, embeddedContext}` (**no
  audio**), `mcpCapabilities {http, sse}`, `sessionCapabilities {list, resume, close, fork}`,
  and an `opencode-login` auth method.
- Agent→client callbacks the connector services: `session/request_permission`,
  `fs/read_text_file`, `fs/write_text_file`. **The connector implements `fs/write_text_file`
  so approved edits actually land on disk** — without it, opencode's edit tool can't persist
  changes through an external client.
- `session/update` variants captured into the transcript: `agent_message_chunk` (reply text),
  `agent_thought_chunk` (reasoning), `tool_call` / `tool_call_update`, `plan`,
  `available_commands_update`, `usage_update` (tokens + cost).

## Permission policy — the safety dial

`oc_acp_prompt(permission=...)` controls how the connector answers opencode's permission
requests:

- **`reject`** (default) — READ-ONLY. opencode can read files, search, reason, plan, and
  answer, but **every edit and bash command is rejected**. Always safe; needs no `confirm`.
- **`allow`** — approve each action **once** as it's requested. Runs real edits/commands.
- **`always`** — approve and remember (opencode's "always allow"). Runs real edits/commands.

Any value other than `reject` **runs mutating operations**, so the tool requires
`confirm=true` and you must confirm intent with the user first. opencode offers only
`once`/`always`/`reject` options (no `reject_always`).

## Tools

- `oc_acp_probe(cwd)` — spawn `opencode acp`, run `initialize` + `session/new`, return the
  protocol version, agent info, capabilities, and auth methods. **No model call — always
  safe.** Use it to prove the channel and see what opencode advertises.
- `oc_acp_prompt(prompt, cwd, mode, files, permission, confirm, timeout)` — run one prompt.
  - `cwd`: absolute project dir the agent operates in (must be absolute; defaults to
    `default_cwd`/`$HOME`).
  - `mode`: optional agent/mode to switch to before prompting (e.g. `plan`, `build`).
  - `files`: absolute paths attached as `resource_link` content blocks.
  - Returns a structured transcript: `reply_text`, `reasoning`, `tool_calls`, `plan`,
    `commands_available`, `permissions_requested`, `files_written`, `usage`, `stop_reason`.

## Example flows

Read-only code question (safe):
```
oc_acp_prompt(prompt="Summarize the architecture of this repo and list entrypoints.",
              cwd="/home/user/projects/foo")     # permission defaults to reject
```

Let opencode actually make a change (confirm with the user first):
```
oc_acp_prompt(prompt="Add a --version flag to the CLI and a test for it.",
              cwd="/home/user/projects/foo",
              permission="allow", confirm=true, timeout=600)
# transcript.files_written lists what it changed; review the diff with oc_vcs('diff') or git.
```

Plan-mode design pass (read-only by nature):
```
oc_acp_prompt(prompt="Propose a migration plan to Postgres.", mode="plan",
              cwd="/home/user/projects/foo")
```

## Model / agent selection in ACP

opencode picks the session model from the **project's opencode.json** (`model` key), else
the best model from the `opencode` provider, else the best across all configured providers.
To change it, set `model` in the project/global config (`oc_config_update`) before the ACP
call, or switch mode with the `mode` param. Per-session arbitrary model override exists in
ACP only via unstable extensions, so the reliable lever is the config default.

## Reference implementations

Official ACP SDKs (if you build a richer client): TS `@agentclientprotocol/sdk`, Python
`agent-client-protocol` (PyPI), Rust/Kotlin/Java. Schema: `agentclientprotocol/agent-client-protocol`
`schema/v1`.
