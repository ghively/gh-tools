# Building for opencode — real-world patterns, recipes & gotchas

Distilled from a deep survey of the opencode ecosystem (oh-my-openagent, joelhooks/
opencode-config, markerikson/opencode-config-example, weisser-dev & wildwasser agent
packs, the `@opencode-ai/plugin` source, dozens of real plugins, and the opencode issue
tracker). Everything here was verified against real files/source. Model names in examples
are **illustrative** — always confirm what's available with `oc_models`.

Repo note: `sst/opencode` → **`anomalyco/opencode`**; `code-yeongyu/oh-my-opencode` →
**`code-yeongyu/oh-my-openagent`** (both redirect). Docs stay at opencode.ai.

## The two ways people build on opencode

1. **Dotfiles-style config** (joelhooks, markerikson, most of the community): a git repo
   cloned straight into `~/.config/opencode/` — `opencode.json` + `agent/*.md` +
   `command/*.md` + `skill/*/SKILL.md` + `tool/*.ts` + `plugin/*.ts`. The directory *is*
   the config. Any power user can replicate this; the `oc_*_write` tools produce exactly
   these files.
2. **Packaged plugin** (oh-my-openagent): a TypeScript monorepo published to npm and
   registered in the `plugin` array — programmatic agent construction, dozens of custom
   tools, and 50+ lifecycle hooks. The heavyweight end.

They compose: oh-my-openagent installs *as* config into `~/.config/opencode/`.

---

## Multi-agent orchestration patterns (the real ones)

**Fixed role team (wildwasser "Oscar/Scout/Ivan/Jester").** A primary *orchestrator*
that never does work itself — it only delegates: `@scout` (research+plan, read-only) →
`@ivan` (implement, full write) → `@jester` (adversarial review). Oscar's prompt hard-
codes rules like "NEVER write code yourself — delegate to @ivan." Lesson: give the
orchestrator `write:false, edit:false` and a bash allowlist of only `git status`/`gh`
read commands, and put the delegation rules in the prompt body.

**Coordinator/worker swarm (joelhooks).** The coordinator's context is "expensive" (kept
on a strong model) and is forbidden from reading/grepping/editing — it spawns a *worker*
subagent for literally everything, including single-file reads, so implementation detail
never pollutes the coordinator's context. Workers get "disposable context." A mandatory
per-worker review loop (max 3 retries → escalate to human) gates completion.

**Plan → build gate.** Insert a dedicated `plan-reviewer` subagent between planning and
implementation whose only job is "can a developer execute this plan without getting
stuck?" — approve/reject with ≤3 blocking issues. Approval-biased by default; a stricter
mode triggers on the words "strict/exhaustive/ruthless" in the request.

**Consensus / adversarial fan-out.** Spawn N reviewers with *different models or personas*
in parallel in a single message, then synthesize agreement/disagreement/unique-insight.
oh-my-openagent's `hyperplan` skill self-spins-up 5 hostile team members (each a distinct
adversarial persona on a distinct model category) to cross-critique a plan before handing
distilled insights to the planner. wildwasser's "Jester Consensus" runs three model-variant
reviewers at temperature 0.8.

**Scope → plan → build pipeline.** A pre-planning `scope-analyst` classifies intent
(refactor / build-from-scratch / bug-fix / …), each with its own MUST/MUST-NOT directives
for the downstream planner, and emits executable acceptance criteria.

**Sub-agent orchestration as a custom tool.** A plugin custom tool can call
`client.session.create({body:{parentID}})` → `client.session.prompt({body:{agent,parts}})`
→ `client.session.messages()` to drive a subagent from inside a tool — hand-rolled
delegation with no special API (real: `derekbar90/opencode-conductor`).

---

## Agent design patterns (distilled from ~30 real agents)

- **Read-only analysis agents**: reviewers/auditors/explorers/debuggers set
  `edit:false`/`write:false` (or `permission.edit:deny`) and a bash allowlist of only
  `git diff/log/show/blame`, `rg`, `head/tail/wc`, then `"*": deny`. Never `bash:ask`
  (stalls unattended) or `bash:allow` (unsafe).
- **Glob-scoped write** — the most powerful safety idiom: a `docs` agent that can write
  *only* markdown, a `test-writer` that can write *only* test files:
  ```jsonc
  "agent": {
    "docs":        { "permission": { "write": { "**/*.md": "allow", "**/*.mdx": "allow", "*": "deny" } } },
    "test-writer": { "permission": { "write": { "**/*.test.ts": "allow", "**/*.spec.ts": "allow", "*": "deny" } } }
  }
  ```
- **Temperature by role**: analysis/security/build 0.1; general dev 0.2–0.3; docs/creative
  0.3; adversarial "oracle" reviewer 0.8 (intentionally noisy — "1 in 5 points hits, but
  that one is the thing everyone missed").
- **`description` drives auto-selection**: write it as an imperative capability + explicit
  trigger ("Use for…", "Use when…"). Routing agents embed a literal keyword→agent table in
  the prompt body.
- **`hidden: true`** hides an internal/orchestrator subagent from `@`-autocomplete while
  leaving it Task-invokable.
- **`steps` caps by role**: code-writing unbounded; review/analysis 10–15; orchestration
  5–10; docs/fast 5–10; debugging 15–20.
- **Programmatic agent construction** (oh-my-openagent): a factory builds the same agent
  bound to different models, with `createAgentToolRestrictions([...])` and date-awareness
  guards (`${new Date().getFullYear()}`) injected into the prompt to stop stale-date
  hallucination.

## ⚠️ Permission / subagent security gotchas (from real issues — TEST, don't assume)

These shipped as real bugs; behavior varies by opencode version — verify on the installed
version before relying on it:

1. **Disabling tools on a primary agent does NOT restrict subagents it spawns.** An agent
   with `write:false` can still write by calling `task` to spawn a subagent that *can*
   write. To actually contain it, lock down `permission.task` too. (issue #20549)
2. **Never set `task: allow` globally.** It removes the single-level nesting guard for
   every subagent (incl. built-ins), enabling *unbounded recursive spawning* — `steps`
   and `doom_loop` don't catch it (each new subagent gets a fresh session/counter).
   Depth 10 → ~1,024 sessions. Scope `task` per-agent with explicit globs. (issue #17721)
3. **Permissive parent rules don't propagate down.** A `permission:"allow"` orchestrator
   can spawn a subagent that hits its own default `ask` and blocks forever with no human
   present. For CI/unattended, give every subagent it may spawn explicit `allow`. (#12566)
4. **`permission.task` in frontmatter has been flaky across versions** — sometimes only
   the older `tools:{task:allow}` syntax worked; sometimes frontmatter `task:allow` caused
   a startup failure. Verify orchestrator spawning actually works. (#8114, #14308)
5. **Restrict `task` to named subagents** the clean way:
   `permission: { task: { "contextscout": "allow", "*": "deny" } }` — a subagent allowed
   to call exactly one other subagent (real: `darrenhinde/OpenAgentsControl` BuildAgent).

---

## Model routing & cost control

- **`small_model`** — set a cheap model; opencode auto-uses it for titles/summaries. You
  can also target the hidden `title` agent directly: `"agent": {"title": {"model": "…"}}`.
- **Per-agent models**: cheap model for read-only search/review (`explore`, reviewers),
  strong model for `build`. In practice people route by **permission + temperature** at
  least as much as by model — joelhooks keeps every agent on one model, differentiating by
  permission/temperature.
- **Category-based routing (oh-my-openagent's best idea)**: delegate by *task intent*, not
  model name. Define categories that resolve to model+variant+reasoning-effort+fallbacks:
  ```jsonc
  "categories": {
    "quick":              { "model": "opencode/gpt-5-nano" },
    "deep":               { "model": "openai/gpt-5.x",   "variant": "xhigh" },
    "visual-engineering": { "model": "google/gemini-x",  "variant": "high"  }
  }
  ```
- **Fallback chains carry per-entry settings**, not just a flat list:
  `"fallback_models": ["openai/gpt-5.x", {"model":"google/gemini-x","variant":"high","temperature":0.2}]`.
- **Model variants / reasoning effort**: Anthropic `high`/`max`; OpenAI
  `none…xhigh`; Google `low`/`high`. Set via `provider.<id>.models.<m>.options.reasoningEffort`
  or per agent. There's a `variant_cycle` keybind to change it live.
- **Local models** (all `@ai-sdk/openai-compatible`): Ollama `http://localhost:11434/v1`,
  LM Studio `http://127.0.0.1:1234/v1`, llama.cpp `http://127.0.0.1:8080/v1`.
- **`policies`** (org-level, distinct from permissions): `{"effect":"deny","action":
  "provider.use","resource":"<id>"}` — a project config **cannot** re-enable a provider the
  org denied. Use for governance.
- **MCP token cost**: each attached MCP server adds ~500–2000 tokens of tool descriptions
  per request. Disable globally, enable per-agent: `"tools": {"my-mcp*": false}` then
  `"agent": {"x": {"tools": {"my-mcp*": true}}}`.

---

## Plugin cookbook (ground truth from `@opencode-ai/plugin` source)

A plugin is `async (input, options?) => Hooks`. `input` gives `client` (the SDK, to drive
opencode), `$` (Bun shell), `directory`, `worktree`, `project`, `serverUrl`. Every hook is
`(input, output) => Promise<void>` where **`output` is mutated in place**; hooks run in
registration order and later hooks see earlier mutations.

**The real hook keys** (correcting the common misconception): there is exactly **one**
`event` hook that you `switch` on — `session.idle`, `session.created`, `permission.asked`,
etc. are `Event.type` *values*, not separate hooks.

| Hook | Fires / does |
|---|---|
| `event(input:{event})` | ONE handler for all bus events; switch on `event.type` |
| `config(cfg)` | startup; **can mutate opencode's own config** (register a command, set a permission) |
| `tool: { name: ToolDefinition }` | register custom tools |
| `auth` / `provider` | custom auth providers (OAuth/device/api) + dynamic model list/re-costing |
| `chat.message` / `chat.params` / `chat.headers` | mutate a new message / temp·topP·maxTokens / HTTP headers |
| `permission.ask(input, output)` | override the ask/allow/deny decision (e.g. auto-allow for unattended) |
| `command.execute.before` | mutate injected parts before a slash-command runs |
| `tool.execute.before(input, output)` | **mutate `output.args`, or throw to abort the tool call** |
| `tool.execute.after` | mutate a completed tool's title/output/metadata |
| `shell.env` | inject/override env for every bash/shell exec |
| `tool.definition` | rewrite a tool's description/JSON-schema sent to the LLM |
| `experimental.chat.messages.transform` | rewrite the ENTIRE message history before each LLM call (most powerful MITM hook) |
| `experimental.chat.system.transform` | mutate the system-prompt array |
| `experimental.session.compacting` | append context / replace the compaction prompt |
| `experimental.compaction.autocontinue` | suppress the synthetic "continue" turn after compaction |
| `experimental.provider.small_model` | override which model counts as the small model |
| `experimental.text.complete` | post-process completed text (e.g. restore redactions) |
| `dispose` | cleanup |

**Custom tools** — the `tool()` helper (`tool.schema` **is** zod):
```ts
import { tool } from "@opencode-ai/plugin"
export default tool({
  description: "Get current git context",
  args: { verbose: tool.schema.boolean().optional() },
  async execute(args, ctx) {          // ctx: sessionID, directory, worktree, abort, metadata(), ask()
    return (await Bun.$`git status -sb`.text())
  },
})
```
Custom tools are also just **files**: drop `.ts`/`.js` in `.opencode/tool/` (project) or
`~/.config/opencode/tool/` (global) — filename becomes the tool name, multiple named
exports become `<file>_<export>`. `oc_plugin_write` writes plugin files; write standalone
tool files with the Write tool into the tool dir.

**Real plugin recipes** (all verified in the wild):
- **Guardrail / abort a tool** — throw in `tool.execute.before` to block (`.env` reads,
  protected paths). Sanitize args by mutating `output.args`.
- **PII/secret round-trip** (`opencode-vibeguard`) — redact in
  `experimental.chat.messages.transform` (so the LLM only sees placeholders), restore real
  values in `tool.execute.before` (so the tool runs for real) and `experimental.text.complete`.
- **Telemetry** — one `event` handler filtering completed tool parts (wakatime), or an
  `auth.loader` returning a custom `fetch` to inject headers on every LLM call (helicone).
- **Notifications** — `event` on `session.idle`/`permission.asked` → desktop notify.
- **Context compression** (`opencode-dynamic-context-pruning`) —
  `experimental.chat.messages.transform` replaces stale tool outputs with placeholders +
  registers its own `/compress` command via the `config` hook.
- **Custom auth / dynamic models** — `AuthHook.methods` (OAuth browser + device + api key)
  and `provider.models(provider, ctx)` filtering/re-costing the catalog per auth type
  (opencode's own `openai/codex.ts` is the reference).

**Plugin gotchas** (from real plugins):
- **Only a default export** (or one named export) — extra named exports cause *double
  registration* (`joelhooks/opencode-config/plugin/swarm.ts` comment).
- **Keep the plugin self-contained**: only import `@opencode-ai/plugin`,
  `@opencode-ai/sdk`, `node:*`. Transitive deps crash opencode's plugin runtime → "PATTERN:
  plugin wrapper is DUMB, CLI is SMART" — shell out to a real CLI for heavy logic.
- **Plugins load as separate module instances** — share cross-instance state via a file,
  not an in-memory singleton.
- The user-facing plugin dir is singular **`.opencode/plugin/`** (plural `plugins/` is
  internal test-fixture only). Local generated plugins register best via an absolute
  `file://` URL in the `plugin` array.
- Local plugins needing npm deps get their own `.opencode/package.json` (Bun installs at
  startup).

---

## Advanced capabilities most people miss

- **GitHub agent CI** — `opencode github install` (or hand-write the workflow) runs opencode
  in Actions. Trigger on `/oc` / `/opencode` issue/PR comments, or on a `schedule:` cron
  with a `prompt:`. Uses `anomalyco/opencode/github@latest`; auth via OIDC (commits appear
  as the app) or `use_github_token:true` (needs `contents/pull-requests/issues: write`).
  Inline PR-review comments give opencode file path + line numbers + diff context.
- **ACP editor integration — "all features supported"** (built-in tools, custom tools, MCP,
  AGENTS.md, formatters, permissions). `opencode acp` for Zed, JetBrains, avante.nvim,
  codecompanion (which can define per-model `commands` like `["opencode","acp","-m","…"]`).
  Only `/undo`·`/redo` are unavailable over ACP. (This plugin's `oc_acp_*` tools are a
  headless ACP client for the same channel.)
- **`references`** — expose *other* repos/dirs into a session without copying:
  `"references": {"docs": {"path": "../product-docs"}}` or `{"repository": "owner/repo"}`.
  `@alias` attaches, `@alias/` searches within; references bypass the external-directory
  permission boundary.
- **Cross-tool skills** — opencode discovers `SKILL.md` from `.opencode/skills`,
  `~/.config/opencode/skills`, **`.claude/skills`, `~/.claude/skills`**, `.agents/skills`,
  `~/.agents/skills`. A Claude-Code skills dir works unmodified. Agents invoke via the
  native `skill` tool. Skills can even carry their own scoped MCP servers.
- **`AGENTS.md` / `CLAUDE.md` interop** — upward traversal, `AGENTS.md` then `CLAUDE.md`
  per tier, global `~/.config/opencode/AGENTS.md` then `~/.claude/CLAUDE.md`. Disable with
  `OPENCODE_DISABLE_CLAUDE_CODE[_PROMPT|_SKILLS]`. `instructions` globs support
  `.cursor/rules/*.md` **and remote URLs** (5s fetch).
- **`doom_loop` permission** — fires when the same tool call repeats 3× with identical
  input; set `deny` for CI to hard-stop infinite loops. `--auto` auto-approves anything not
  explicitly denied.
- **LSP feeds the agent, not just the editor** — `"lsp": true` makes the model see
  compiler/linter diagnostics as tool output. **Formatters auto-run on every write/edit**
  (`"formatter": true`, or custom `{command:["deno","fmt","$FILE"], extensions:[".md"]}`).
- **Session UX** — `/fork` branches a conversation while the main agent keeps running;
  `leader g` opens a visual timeline to revert/fork/copy; `/share` → public link,
  `"share":"disabled"` (checked into git) enforces a no-share policy; `opencode export|import`
  works with local files *and* share URLs.
- **Worktrees are NOT native** — you `git worktree add` and launch opencode inside, or use
  community plugins (`kdcokenny/opencode-worktree`). This plugin's `oc_worktree` drives the
  experimental worktree API where present.
- **Themes/keybinds live in `tui.json`** (schema `opencode.ai/tui.json`), not `opencode.json`.
  No native custom statusline yet (community: `ocstatusline`).

---

## Starter configs worth reading

- **joelhooks/opencode-config** — the dotfiles flagship (25 commands, custom tools, a
  3341-line swarm plugin, glob-scoped agents). Clone into `~/.config/opencode`.
- **markerikson/opencode-config-example** — the minimal, well-commented reference; keeps a
  separate `dev-plans/` repo for work-tracking (config and project-memory decoupled).
- **code-yeongyu/oh-my-openagent** — the heavyweight packaged plugin (category routing,
  Team Mode, hyperplan, 50+ hooks, `ultrawork` magic word). Install via `bunx
  oh-my-openagent install`; never global-install.
- **awesome-opencode/awesome-opencode** & **weisser-dev/awesome-opencode** — the curated
  indexes for the long tail of agents/plugins/themes/MCP configs.
