---
name: opencode-authoring
description: Authoring OpenCode skills, commands, subagents, permissions, plugins, and MCP registrations, plus porting extensions from other hosts (Claude Code, Cursor, Windsurf) into OpenCode. Use when creating, reviewing, packaging, testing, or migrating OpenCode extensions. Does not cover MCP implementation internals or generic agent architecture.
---

# OpenCode Authoring

Use the smallest OpenCode surface that satisfies the requirement and verify it
in a fresh session. This port keeps the original decision discipline while
replacing Claude-specific manifests, hooks, paths, and tool names.

## Surface Decision

| Need | OpenCode surface |
|---|---|
| Standing project guidance | `AGENTS.md` or `instructions` |
| Reusable model-invoked procedure | `SKILL.md` under `.opencode/skills/<name>/` |
| User-invoked workflow with arguments | `.opencode/commands/<name>.md` |
| Isolated specialist | `.opencode/agents/<name>.md` with `mode: subagent` |
| Deterministic enforcement | OpenCode plugin hook or permission rule |
| External structured capability | MCP server under `mcp` config |
| Reusable installed behavior | OpenCode plugin entry in `opencode.json` |

Prefer the smaller surface. Prompts guide; permissions and plugin hooks enforce.

## Skills

Use a directory named for the skill containing `SKILL.md`. Frontmatter requires
`name` and a trigger-focused `description`; optional fields are `license`,
`compatibility`, and string-valued `metadata`. Keep the main body concise and
link deeper references with relative paths. Do not use Claude variables or
unsupported frontmatter.

## Commands

Use `.opencode/commands/<name>.md` or the global command directory. Frontmatter
requires `description`; optional `agent`, `model`, `variant`, and `subtask` are
supported. The body is the template and may use `$ARGUMENTS` and `$1`, `$2`.
Commands are user-invoked, so side effects must be explicit and gated.

## Agents

Use `.opencode/agents/<name>.md` or the global agent directory. Set `mode` to
`subagent`, `primary`, or `all`; omit `model` to inherit the caller model. Use
an explicit `permission` policy, preferably default deny with narrow allows.
Read-only specialists should allow `read`, `glob`, and `grep`, deny `edit`, and
make `bash` `ask` only when command execution is essential. Include prompt
defense whenever the agent reads issues, logs, web pages, tickets, or code from
untrusted sources.

## Plugins and MCP

An OpenCode plugin exports a default `Plugin` function from JavaScript or
TypeScript and is registered in `plugin`. Use `tool.execute.before` for hard
pre-execution decisions and throw to stop a tool call; use `tool.execute.after`
for best-effort auditing. Validate runtime argument shapes and fail open only
for parser/logging errors, never for a matched safety rule.

Register MCP servers under `mcp`: local servers require `type: "local"` and a
command array; remote servers require `type: "remote"` and a URL. Keep secrets
in environment variables or OAuth configuration, never in source or config.

## Verification

1. Validate JSON against `https://opencode.ai/config.json`.
2. Check every skill's frontmatter and relative reference link.
3. Typecheck and unit-test plugins.
4. Launch a fresh OpenCode session and exercise positive and negative triggers.
5. Exercise every hard-deny vector and at least one routine near miss.
6. Quit and restart after config-time changes; OpenCode does not hot reload them.
