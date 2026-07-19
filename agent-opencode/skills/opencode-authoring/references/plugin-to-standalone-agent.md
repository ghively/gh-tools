# Plugin-to-Standalone-Agent Conversion

The agent-foundry doctrine for converting any plugin-shaped extension into a
standalone agent applies regardless of host. This OpenCode port keeps the
strategy framework and substitutes OpenCode specifics.

## Conversion Strategies

- **Strategy A — SDK-native.** Rehost the capability against a general agent
  SDK (the OpenAI Agents SDK, LangGraph, Claude Agent SDK, etc.). Highest
  fidelity for behavior; highest engineering cost.
- **Strategy B — Skills-portable rehost.** Carry the SKILL.md knowledge and
  supporting references into another skills-native runtime with minimal
  translation. Lowest cost; preserves knowledge, not host integration.
- **Strategy C — Full translation.** Rewrite the extension against the
  target runtime's native surfaces. Highest fidelity when the target is the
  production host.

Pick the strategy against the capability audit
(`plugin-capability-audit.md`) and the framework matrix
(`conversion-framework-matrix.md`).

## OpenCode-Specific Notes

- OpenCode already supports skills, commands, subagents, plugins, and MCP
  natively. A Claude Code plugin converting into OpenCode is a Strategy C
  translation, not a portable rehost.
- Surface mappings:
  - `CLAUDE.md` → `AGENTS.md`
  - `.claude/skills/<name>/SKILL.md` → `.opencode/skills/<name>/SKILL.md`
  - `.claude/commands/<name>.md` → `.opencode/commands/<name>.md`
  - `.claude/agents/<name>.md` → `.opencode/agents/<name>.md`
  - `tools: Read, Grep` → `permission: { "*": "deny", "read": "allow", ... }`
  - `hooks/hooks.json` with `PreToolUse` → OpenCode plugin with
    `tool.execute.before` (throw to deny)
  - `.claude-plugin/plugin.json` → entry in `opencode.json` under `plugin`
  - `.mcp.json` / `claude mcp add` → `mcp` config in `opencode.json`

## Vendor Lock-In Doctrine

Four vectors to evaluate before committing to a target runtime: data
ownership, control plane, default telemetry, and exit cost. For each, name
the hedge (export format, self-host option, telemetry toggle, and migration
script availability).

## Honest "Don't Convert" Verdict

If the capability is already covered by an OpenCode built-in, a generic MCP
server, or a small `AGENTS.md` rule, do not convert. The audit in
`plugin-capability-audit.md` should produce that verdict when it applies.

The Claude-specific conversion matrices that used to live here
(`conversion-framework-matrix.md`, `conversion-runtime-matrix.md`,
`skills-porting-cookbook.md`) are retained as historical references but are
not authoritative for OpenCode work; OpenCode's own surfaces are.
