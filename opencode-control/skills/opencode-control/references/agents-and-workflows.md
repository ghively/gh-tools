# Designing agents, commands, skills & workflows — and optimizing them

Read this before authoring agents/commands/skills or tuning opencode for a task. The
`oc_agent_write` / `oc_command_write` / `oc_skill_write` tools produce the exact on-disk
format opencode loads (verified: opencode loaded an authored agent live).

## Agents: primary vs subagent

- **Primary** agents are the ones you talk to directly (cycle with Tab). `build` (default,
  full tool access) and `plan` (edit-restricted design mode) are built in.
- **Subagents** are specialists invoked automatically via the Task tool or manually with
  `@agent-name`. Built-in subagents: `general` (multi-step work), `explore` (fast read-only
  codebase search). (`compaction`/`title`/`summary` are hidden internal agents.)
- `mode: all` (default) = usable both ways.

Design principle: **give each agent the narrowest permissions and clearest description that
fit its job.** A read-only reviewer should have `edit: deny`, `bash: deny`. The `description`
is load-bearing — it's how the orchestrator and users decide when to invoke a subagent.

### Agent file format (`oc_agent_write` emits this)

`~/.config/opencode/agent/<name>.md` (global) or `<project>/.opencode/agent/<name>.md`:
```markdown
---
description: Reviews code for quality, bugs, security — never edits
mode: subagent
model: anthropic/claude-sonnet-4-5
temperature: 0.1
tools:
  edit: false
  write: false
---

You are in code review mode. Focus on correctness, edge cases, security, and performance.
Report findings with file:line references. Do not modify files.
```

Frontmatter fields: `description`, `mode` (primary|subagent|all), `model`, `variant`,
`temperature`, `top_p`, `prompt` (or use the body), `permission` (preferred over `tools`),
`disable`, `hidden` (hide subagent from `@`-autocomplete), `color`, `steps` (max agentic
iterations). Prompts can pull a file: `prompt: "{file:./prompts/review.txt}"`.

`tools: {edit:false}` is the simple shorthand; for fine control use `permission:` with the
same keys/patterns as global permissions (see configuring-opencode.md). Example:
```yaml
permission:
  edit: deny
  bash: { "*": ask, "git diff": allow, "git log*": allow }
  webfetch: deny
```

### Authoring via the tool
```
oc_agent_write(name="reviewer", mode="subagent", model="anthropic/claude-sonnet-4-5",
               temperature=0.1, tools={"edit": false, "write": false},
               description="Read-only code reviewer",
               prompt="You are a meticulous code reviewer. ...", confirm=true)
```
`scope="global"` → user config dir; `scope="project"` + `project_dir=...` → repo `.opencode/`.
Or scaffold interactively on the host: `opencode agent create`.

## Subagent orchestration

The Task tool spawns a **child session** per subagent: `{description, prompt, subagent_type,
background?}`. Nesting is capped by `subagent_depth` (default 1 — raise it in config to let
subagents spawn subagents). Restrict which subagents an agent may call with the `task`
permission key (glob on subagent names). Use subagents to parallelize independent work
(e.g. an `explore` pass feeding a `build` implementation) and to sandbox risky steps behind
tighter permissions than the primary.

## Custom commands (slash-commands = reusable workflows)

`<config>/command/<name>.md` or `.opencode/command/<name>.md`. The body is the prompt
template. Frontmatter: `description`, `agent` (route to a specific agent), `model`,
`subtask` (force subagent isolation).

Template features:
- `$ARGUMENTS` — the full raw argument string. `$1`,`$2`… — positional (the highest-numbered
  placeholder slurps all remaining args).
- `` !`shell cmd` `` — **`!` immediately before a backtick** — runs the shell command,
  stdout is injected. Multiple run in parallel.
- `@path` — attach a file or directory (relative to worktree root; no globbing). Shared
  syntax with `@agent` mentions.

```markdown
---
description: Draft release notes for a component
agent: build
---
Draft user-facing release notes for component "$1".

Uncommitted diff:
!`git diff`

For context:
@src/components/$1.tsx
```
Invoke live: `oc_command(session_id, command="release-notes", arguments="Button")`. Author
with `oc_command_write(name, template, description, agent, ..., confirm=true)`. Built-ins:
`/init`, `/review`, `/undo`, `/redo`, `/share`, `/help`.

## Skills

Skills are model-invoked capability docs: `<config>/skills/<name>/SKILL.md` with frontmatter
(`name`, `description`) and a markdown body. The `description` decides when the model reaches
for it — make it a precise trigger. Author with `oc_skill_write(name, description, body,
confirm=true)`. (opencode ships a built-in `customize-opencode` skill for editing its own config.)

## Plugins (JS/TS hooks — deeper extension)

`.opencode/plugins/*.{js,ts}` or global; or npm packages in the `plugin` array. A plugin is
`async (input) => Hooks`. Hooks include: `event`, `config`, `tool` (register custom tools via
the `tool()` helper), `chat.message`, `chat.params`, `chat.headers`, `permission.ask`,
`command.execute.before`, `tool.execute.before` (**throw to abort a tool call**),
`tool.execute.after`, `shell.env`, `tool.definition`, and `experimental.*` transforms.
Package: `@opencode-ai/plugin`. Use plugins for guardrails (block reading `.env`),
telemetry, dynamic model/provider injection, or custom tools. This plugin doesn't author
plugin files (they're code) — write them directly with the Write tool when needed.

## Optimization playbook

**Model selection / cost**
- Set `small_model` to a cheap model — opencode uses it for titles/summaries automatically.
- Use model **variants** (e.g. reasoning-effort dials) rather than swapping providers for
  cost/quality tuning.
- Trim the catalog: `disabled_providers`/`enabled_providers` (openrouter alone adds 340
  models to every picker — disable what you don't use).
- Per-agent `model`: give cheap read-only agents (`explore`, reviewers) a small model and
  reserve the big model for `build`.

**Speed / focus**
- Tighten `permission` so routine safe commands (`git *`, `npm run *`) are `allow` and never
  interrupt, while dangerous ones (`rm *`, `git push *`) are `deny`.
- `compaction` and `tool_output.max_lines/max_bytes` control context bloat on long sessions.
- Raise `subagent_depth` only if you actually need nested subagents.

**Quality / guardrails**
- Put durable project knowledge in `AGENTS.md` (`/init` scaffolds it) and pull extra rules
  via `instructions`.
- Read-only `plan` mode for design passes; a dedicated read-only reviewer subagent before
  merges.
- A `tool.execute.before` plugin for hard guardrails (secret files, protected paths).

**A good "optimize my opencode" pass**: `oc_config_get` → `oc_providers`/`oc_agents` →
propose a patch (small_model set, catalog trimmed, permissions tightened, per-agent models,
AGENTS.md present) → show the diff → `oc_config_update(confirm=true)` after the user agrees.
