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

**⚠️ Permission does not propagate across the Task boundary — this bites people.**
Disabling `write`/`edit` on a *primary* agent does NOT stop a subagent it spawns from
writing; lock down `permission.task` too. Never set `task: allow` *globally* — it removes
the nesting guard and enables unbounded recursive spawning (`steps`/`doom_loop` don't catch
it). And a permissive parent's `allow` rules don't flow down — for unattended/CI runs, give
every subagent it may spawn explicit `allow`. Scope task the clean way:
`permission: { task: { "reviewer": "allow", "*": "deny" } }`. These have been real, version-
dependent bugs — verify on the installed version. Full detail + issue refs in
`references/ecosystem-and-recipes.md`.

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

Skills are model-invoked capability docs: `<config>/skills/<name>/SKILL.md`. The stable spec
recognizes only `name`, `description` (required), and optional `license`, `compatibility`,
`metadata` — **no `allowed-tools`/`model`** (those are Claude-Code fields opencode ignores).
The `description` decides when the model reaches for it — make it a precise trigger. Discovered
from six paths (incl. `.claude/skills` — a Claude skills dir works unmodified); the body loads
on-demand via the `skill` tool, so reference extra files from a `references/` subdir. Author
with `oc_skill_write(name, description, body, license, metadata, confirm=true)`. Full spec,
skill-scoped MCP, and gating in `references/skills-eval-enterprise.md`. (opencode ships a
built-in `customize-opencode` skill for editing its own config.)

## Plugins (JS/TS hooks — deeper extension)

`.opencode/plugin/*.{js,ts}` (singular dir) or global; or npm packages in the `plugin`
array. A plugin is `async (input, options?) => Hooks`; `input` gives `client` (the SDK, to
drive opencode), `$` (Bun shell), `directory`, `worktree`, `project`, `serverUrl`. Each
hook is `(input, output) => Promise<void>` and **mutates `output` in place**.

**There is exactly ONE `event` hook** that you `switch` on — `session.idle`,
`session.created`, `permission.asked`, etc. are `Event.type` *values*, not separate hooks.
The real hook keys: `event`, `config` (can mutate opencode's own config), `tool` (register
custom tools), `auth`, `provider`, `chat.message`, `chat.params`, `chat.headers`,
`permission.ask`, `command.execute.before`, `tool.execute.before` (**throw to abort a
tool**), `tool.execute.after`, `shell.env`, `tool.definition`, and the `experimental.*`
hooks (`chat.messages.transform`, `chat.system.transform`, `session.compacting`,
`compaction.autocontinue`, `provider.small_model`, `text.complete`).

Use plugins for guardrails (block `.env` reads), telemetry, PII redaction, context
compression, custom auth providers, dynamic model injection, or custom tools. Author with
`oc_plugin_write(name, body, confirm=true)`. Gotcha: use **only a default export** (extra
named exports double-register) and keep the file self-contained (only import
`@opencode-ai/plugin`, `@opencode-ai/sdk`, `node:*` — shell out for heavy logic).

**Custom tools** don't need a full plugin — drop a `.ts`/`.js` file in `.opencode/tool/`
(or `~/.config/opencode/tool/`); filename becomes the tool name. Use the `tool()` helper
(`tool.schema` is zod). See `references/ecosystem-and-recipes.md` for the full plugin
cookbook, real examples, and orchestration patterns.

## Optimization playbook

**Model selection / cost**
- Set `small_model` to a cheap model — opencode uses it for titles/summaries automatically.
- Use model **variants** (e.g. reasoning-effort dials) rather than swapping providers for
  cost/quality tuning.
- Trim the catalog: `disabled_providers`/`enabled_providers` (openrouter alone adds 340
  models to every picker — disable what you don't use).
- Per-agent `model`: give cheap read-only agents (`explore`, reviewers) a small model and
  reserve the big model for `build`. In practice, permission + temperature routing is used
  at least as much as model routing for cost/safety control.
- **Category-based routing** (oh-my-openagent's signature pattern): delegate by task-intent
  → a `categories` map that resolves to model+variant+reasoning-effort+fallbacks, instead
  of hardcoding model names per task. See `references/ecosystem-and-recipes.md`.

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
