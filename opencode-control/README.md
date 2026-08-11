# opencode-control

Deep control of the **OpenCode** AI coding agent (`anomalyco/opencode`, formerly
`sst/opencode`) from Claude Code — a Claude Code plugin with an MCP server, a control
skill, and workflow commands. Built with the
[deep-integration-builder](../deep-integration-builder) methodology and **live-verified
against opencode 1.18.3**.

## Two connectors

1. **HTTP server** (`opencode serve`) — the same REST+SSE API the TUI/desktop/IDE clients
   use. A **generic passthrough** (`oc_call`/`oc_discover`/`oc_schema`) reaches all **188
   operations** (self-discovered from the live `GET /doc` OpenAPI spec), plus ~30 curated
   tools for the common jobs.
2. **ACP** (Agent Client Protocol) — `oc_acp_prompt` spawns `opencode acp` and drives it as
   a JSON-RPC agent over stdio, **with no running server required**. The connector
   implements the client side of ACP v1, including the `fs/write_text_file` callback so
   opencode's edits actually land on disk.

Plus on-disk **authoring** of agents, commands, and skills, and `opencode.json` patching.

## Tools (49)

- **Orientation/passthrough**: `oc_status`, `oc_discover`, `oc_schema`, `oc_call`, `oc_server`
- **Sessions/running**: `oc_sessions`, `oc_session`, `oc_session_create`, `oc_prompt`,
  `oc_messages`, `oc_message`, `oc_shell`, `oc_command`, `oc_abort`, `oc_session_manage`,
  `oc_revert`, `oc_session_diff`
- **Config/authoring**: `oc_config_get`, `oc_config_update`, `oc_agents`, `oc_agent_write`,
  `oc_commands`, `oc_command_write`, `oc_skills`, `oc_skill_write`, `oc_plugin_write`,
  `oc_models`, `oc_providers`, `oc_mcp`, `oc_resources`, `oc_auth`
- **Running-agent interaction**: `oc_permissions`, `oc_questions`, `oc_tools`
- **Project/VCS/UI**: `oc_projects`, `oc_worktree`, `oc_find`, `oc_file`, `oc_vcs`,
  `oc_diagnostics`, `oc_pty`, `oc_tui`, `oc_events`
- **Maintenance/data**: `oc_stats`, `oc_export`, `oc_import`, `oc_upgrade`
- **ACP**: `oc_acp_probe`, `oc_acp_prompt`

Everything else in opencode's 188-operation surface is reachable via `oc_call`
(`oc_discover` finds it) — see the skill's `conventions.md` for what's deliberately
left to passthrough (workspaces/sync, console/control-plane, OAuth flows, v2 `/api/*`).

## Install

```
/plugin install opencode-control@gh-tools
/reload-plugins
```

Then copy `config.example.json` → `config.local.json` (git-ignored) and set `base_url` to
your `opencode serve` address (default `http://127.0.0.1:4096`). The HTTP tools need a
running server — start one with `oc_server(action='start')` or `opencode serve --port 4096`.
The ACP tools and `*_write` authoring tools work without a server.

If the server was started with `OPENCODE_SERVER_PASSWORD`, set `password` (and `username`
if not the default `opencode`) in `config.local.json` — auth is HTTP Basic.

To verify against a live server: `cd opencode-control && uv run --script mcp/_smoketest.py`
(read-only; exits cleanly with a note if no server is reachable).

## Skill & commands

- Skill **opencode-control** — how to drive the server, plus references on the full API
  map, conventions/auth/gap-taxonomy, configuring opencode, designing agents/workflows,
  the ACP protocol, and **`ecosystem-and-recipes.md`** — real-world build patterns
  distilled from a deep survey of the opencode ecosystem (oh-my-openagent, joelhooks/
  opencode-config, dozens of real plugins): multi-agent orchestration recipes, the plugin
  cookbook (real hook table + `tool()` helper + real examples), category-based model
  routing, GitHub-agent CI, ACP editor integration, and the permission/subagent security
  gotchas from the issue tracker. Plus `sdk-and-automation.md` (the SDK, headless automation,
  raw-HTTP-from-any-language, and **forge CI** — GitHub agent + GitLab/other via `opencode
  run`, incl. why there's no first-party GitLab agent + a working `.gitlab-ci.yml`),
  `events-and-context.md` (the event streams + compaction/context cost tuning), and
  `skills-eval-enterprise.md` (SKILL.md spec, agent/skill evaluation, and enterprise/security
  — config precedence, sharing, the plaintext-`auth.json` risk, and the important fact that
  **opencode's permission system is advisory, not an OS sandbox**).
- `/oc-health` — full health & orientation check
- `/oc-run <task>` — run a coding task through opencode (ACP)
- `/oc-agent <role>` — design & author an agent
- `/oc-build <thing>` — build an agent/command/plugin/workflow using real ecosystem patterns
- `/oc-optimize` — audit & optimize the config

## Safety

Reads are free; **writes are confirm-gated** in the tools and require user approval. ACP
runs read-only by default (`permission='reject'`); making changes requires
`permission='allow'` + `confirm=true`. See the skill's `conventions.md` for the honest
Works / Fixable / Hard-limit gap taxonomy.

## Requirements

`opencode` on PATH (the ACP/lifecycle tools shell out to it) and `uv` (the MCP server
self-provisions its deps via a PEP-723 inline-deps script).
