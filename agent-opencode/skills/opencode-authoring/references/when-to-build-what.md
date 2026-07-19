# When to Build What

Pick the smallest OpenCode surface that satisfies the requirement. Document
rejected alternatives.

| User wants... | Build... | Why |
|---|---|---|
| Standing project guidance | `AGENTS.md` or `instructions` | Always available, no invocation |
| Reusable model-invoked procedure | Skill (`.opencode/skills/<name>/SKILL.md`) | Description triggers on demand; body loads when needed |
| User-invoked workflow with args | Command (`.opencode/commands/<name>.md`) | Explicit slash invocation and `$ARGUMENTS` substitution |
| Isolated specialist | Subagent (`.opencode/agents/<name>.md`, `mode: subagent`) | Separate context, tools, model, and prompt |
| Deterministic lifecycle enforcement | Plugin hook (`tool.execute.before`) | Runs outside model discretion; throw to deny |
| External structured tools | MCP server (`mcp` config) | Tool schema and protocol boundary |
| Reusable installed behavior | Plugin entry in `opencode.json` | Namespaced, versioned, installable package |

## Decision Order

1. Could a one-line `AGENTS.md` rule cover it? If yes, stop.
2. Is it triggered by what the user said? Use a skill.
3. Is it explicitly invoked with arguments? Use a command.
4. Does it need isolated context or a narrow tool set? Use a subagent.
5. Must it run even if the model would rather skip it? Use a plugin hook.
6. Does it expose an external service? Use an MCP server.

## Anti-Patterns

- **Mega-skill router.** One skill that dispatches every related task. Split
  by trigger.
- **Prompt where hook is required.** "Never push to main" as prose still
  allows the push. Use `tool.execute.before` with a throw.
- **Hook where instruction is enough.** A `tool.execute.before` that nudges
  style on every Edit wastes cycles and adds failure surface. Use prose.
- **Plugin for everything.** A plugin pays loading and complexity cost. Use
  one only when you need deterministic enforcement or runtime config hooks.
- **Command that calls another command.** OpenCode does not expand commands
  inside commands. Inline the shared procedure or move it to a skill.

## Versus Claude Code

Claude's `CLAUDE.md`, `tools:`, `permissionMode`, `argument-hint`,
`.claude-plugin/plugin.json`, and `hookSpecificOutput.permissionDecision`
have no OpenCode equivalent. Translate the intent, not the artifact.
