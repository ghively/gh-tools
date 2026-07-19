# Cross-Platform Coding-Agent Surfaces

The 13 harnesses covered in this skill's `harness-comparison.md` are
the OpenCode/Claude/standalone SDK landscape. There is a parallel
landscape of coding-agent IDE platforms — Cursor, Windsurf, Aider,
Cline, Continue, Cody — each with its own extension surface.

This reference is the **porting layer**: how the agent-foundry
knowledge transfers to those platforms. The doctrine (design,
harness, eval, safety, deploy) is platform-neutral; the artifacts
(skills, commands, hooks, MCP) translate per platform.

## Platform Coverage Matrix

| Platform | Skill/command surface | Hook surface | MCP support | Custom tools | BYOK |
|---|---|---|---|---|---|
| **Cursor** | `.cursor/rules/*.mdc` (project rules); `.cursor/prompts/` (commands) | Limited (rules are guidance, not enforcement) | Yes (Cursor MCP settings) | Via MCP only | Yes |
| **Windsurf** (Codeium) | `.windsurfrules` (project rules); Cascade workflows | Limited | Yes | Via MCP | Yes |
| **Aider** | `.aider.conf.yml` (config); conventions via system prompt | None (CLI-only) | Limited (via scripts) | Via in-repo Python functions | Yes |
| **Cline** (VS Code) | `.clinerules/` (project rules); MCP config | Yes (extension settings) | Yes (extension configures MCP) | Via MCP + extension settings | Yes |
| **Continue** (VS Code / JetBrains) | `config.json` (rules, prompts, slash commands); `config.yaml` equivalent | Limited | Yes (MCP server blocks in config) | Via MCP + `@cmd` slash commands | Yes |
| **Sourcegraph Cody** | `.sourcegraph/*` rules; custom commands via JSON | Limited | Yes | Via Sourcegraph APIs + MCP | Yes |

Every platform supports BYOK (bring your own model) — including ZAI
via OpenAI-compatible base URL.

## The Translation Map

The agent-foundry primitives translate as follows:

| agent-foundry primitive | OpenCode | Cursor | Windsurf | Cline | Continue |
|---|---|---|---|---|---|
| Skill (model-invoked knowledge) | `.opencode/skills/<name>/SKILL.md` | `.cursor/rules/<name>.mdc` with description | `.windsurfrules` section | `.clinerules/<name>.md` | `config.json` rule |
| Command (user-invoked workflow) | `.opencode/commands/<name>.md` | `.cursor/prompts/<name>.md` | Cascade template | Custom instruction | Slash command in `config.json` |
| Hook (deterministic enforcement) | `tool.execute.before` plugin | Limited (rules are advisory) | Limited | Extension settings | Limited |
| Permission rule | `permission` block in `opencode.json` | Cursor settings | Windsurf settings | Cline extension settings | Continue `config.json` |
| MCP server | `mcp` block in `opencode.json` | Cursor MCP settings | Windsurf MCP settings | Cline MCP settings | Continue `config.json` |
| Subagent | `.opencode/agents/<name>.md` | Not supported directly; emulate via separate chat sessions | Not supported | Not supported | Not supported |

The biggest gap: most IDE platforms do not support subagents (isolated
specialists with their own context). You emulate this by opening
separate chat sessions or running the framework's CLI in a terminal.

## Per-Platform Notes

### Cursor

Cursor ships `.cursor/rules/*.mdc` — Markdown rules with frontmatter
(`description`, `globs`, `alwaysApply`). Skills translate naturally:

```markdown
---
description: Triage incoming support tickets; classify and route.
globs: ["**/*.md", "src/tickets/**"]
alwaysApply: false
---

# Ticket Triage Skill

You triage incoming support tickets...
```

Cursor MCP via Settings → MCP: register servers (ZAI via
OpenAI-compatible config). Hooks are limited — rules are guidance,
not deterministic enforcement. Cursor does not enforce hard denies;
you must rely on permission rules at the OS / runtime layer.

### Windsurf

Codeium's Windsurf uses `.windsurfrules` (a single file or directory
of files) as the project-guidance surface. Skills translate as
sections within `.windsurfrules`. MCP support is via Cascade settings.
Subagents not supported.

### Aider

Aider is a CLI coding agent with a `.aider.conf.yml` config file.
There is no skill surface; conventions go in the system prompt or in
a `CONVENTIONS.md` file the agent reads. Tools are Python functions
in the repo. No hook surface — Aider is unstructured by design.

For ZAI: Aider supports OpenAI-compatible providers via `--openai-api-base`.

### Cline

Cline is a VS Code extension with `.clinerules/` for project rules and
robust MCP support. Cline's settings allow per-tool permission rules
(similar to OpenCode's permission block). Of the IDE platforms, Cline
is closest to OpenCode in surface shape.

### Continue

Continue uses `config.json` (or `config.yaml`) for everything: rules,
slash commands, models, MCP servers. Slash commands are user-invoked
workflows (matching OpenCode commands). MCP via `mcpServers` block.
Limited hook surface.

## Porting Workflow

To port an agent-foundry skill library to a coding-agent platform:

1. **Translate skills → platform rules.** Each `SKILL.md` becomes a
   platform rule file. Preserve the `description` frontmatter; adjust
   the frontmatter shape to the platform's expectation (Cursor's
   `globs` / `alwaysApply`, Continue's `description`).
2. **Translate commands → slash commands / prompts.** Each
   `/agent-foundry-*` command becomes a platform slash command.
   Adjust `$ARGUMENTS` to the platform's variable convention.
3. **Translate hooks → permission rules.** Where the platform lacks
   deterministic hooks, express the safety floor as OS-level
   permission rules (filesystem ACLs, container sandboxing) or as
   pre-tool wrappers if the platform supports them.
4. **Register MCP servers via platform config.** Same MCP server
   works across platforms; only the config block shape changes.
5. **Drop subagents or emulate.** Subagents are the hardest port.
   Either drop them (consolidate into the primary agent) or run a
   framework SDK (Claude Agent SDK, OpenAI Agents SDK) in a terminal
   alongside the IDE agent.
6. **Verify the safety floor translates.** Many IDE platforms lack
   deterministic enforcement; the safety floor must move to the OS /
   container layer (Docker, gVisor, file permissions).

## ZAI Wiring Across Platforms

All platforms support OpenAI-compatible providers. For ZAI:

| Platform | Config |
|---|---|
| Cursor | Settings → Models → OpenAI API Base: `https://open.bigmodel.cn/api/paas/v4/` |
| Windsurf | Cascade settings → Custom Model → base URL |
| Aider | `--openai-api-base https://open.bigmodel.cn/api/paas/v4/` |
| Cline | API Provider: OpenAI Compatible → base URL |
| Continue | `config.json` → `models[].apiBase` |

Set the API key via the platform's secret store or env var.

## What Does NOT Translate

- **Deterministic safety hooks** — most IDE platforms lack a
  pre-tool hook that can fail-closed. The safety floor must move to
  OS/container.
- **Subagents** — most IDE platforms are single-agent.
- **Trajectory capture** — IDE platforms log differently; the eval
  harness needs platform-specific extraction.
- **Permission rules with pattern matching** — IDE platforms have
  coarse-grained permission (allow/deny a tool), not fine-grained
  pattern-based (deny `Bash(rm -rf *)`).

## Pitfalls

1. **Assuming the platform enforces.** Rules in `.cursor/rules/` are
   guidance, not enforcement. Fix: combine with OS-level controls.
2. **Single-source skills.** Skills live in `.cursor/rules/` AND
   `.opencode/skills/` AND `.github/copilot/skills/` — drift is
   inevitable. Fix: single source, generate platform-specific copies.
3. **MCP server config drift.** Same MCP server, three platforms,
   three config shapes. Fix: write the config once in a generator;
   emit per-platform.
4. **Ignoring subagent gaps.** Design assumes subagents; platform
   does not support them. Fix: either choose a different platform or
   restructure the design.
5. **No trajectory for eval.** IDE logs are not structured; the eval
   suite cannot assert on tool calls. Fix: route through a framework
   SDK when eval matters, not the IDE.

## See Also

- `../../agent-deployment/references/ci-resident-agents.md` — platform-native agents (Copilot, Duo) and the IDE/CI boundary.
- `../../opencode-authoring/references/plugin-to-standalone-agent.md` — porting between platforms at the architecture level.
- `harness-comparison.md` — the 13 OpenCode/Claude/standalone harnesses (this reference covers the IDE-platform landscape that sits alongside them).
- `../../agent-safety/references/framework-safety-matrix.md` — the safety primitives per harness (this reference extends that to IDE platforms).
