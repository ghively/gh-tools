# Skills, evaluation & enterprise/security

Authoring skills, validating agent setups, and deploying opencode safely. Verified against
`anomalyco/opencode` docs/source and real repos. `oc_skill_write` authors skills;
`oc_config_get`/`oc_config_update` inspect/patch the enterprise knobs.

## Skills

### SKILL.md spec (stable) — only FIVE fields
```yaml
---
name: git-release                    # required; 1–64 chars, lowercase, single hyphens
description: Create consistent releases and changelogs   # required; 1–1024 chars
license: MIT                         # optional
compatibility: opencode              # optional
metadata:                            # optional; string→string free-form map
  audience: maintainers
---
<markdown body — the skill's instructions; can reference files in a sibling references/ dir>
```
**opencode SKILL.md does NOT support `allowed-tools` or `model`** (unlike Claude Code) —
those keys are silently ignored on the stable spec (they exist only in the separate
`opencode2`/v2 beta). Use `metadata` as free-form tags. `oc_skill_write` emits the correct
name+description frontmatter; add `license`/`metadata` by hand if wanted.

### Discovery — SIX paths (walks up to the git worktree)
`.opencode/skills/<n>/SKILL.md`, `~/.config/opencode/skills/…`, **`.claude/skills/…`,
`~/.claude/skills/…`** (Claude-Code drop-in — a Claude skills dir works unmodified),
`.agents/skills/…`, `~/.agents/skills/…` (vendor-neutral).

### Invocation & gating
Agents load a skill via the native **`skill` tool** — available skills are listed
(name+description) in the tool description at session start (cheap), and the **full body loads
only on invocation** (progressive disclosure). Reference extra files from a `references/`
subdir to keep the base skill lean. Gate with `permission.skill`:
```json
"permission": { "skill": { "*": "allow", "internal-*": "deny", "experimental-*": "ask" } }
```
Disable per-agent with `tools: { skill: false }` (omits the `<available_skills>` section).

### Skill-scoped MCP (`skill_mcp`) — real but UNDOCUMENTED
A skill can bundle its own MCP server that stays **hidden until the skill is loaded**, then is
called via the `skill_mcp` tool (global MCP servers become direct tools; skill-embedded ones
don't until loaded). This keeps tool descriptions out of context until needed. It's real (seen
in the issue tracker) but not in any versioned spec — the team is still iterating, so build on
it cautiously. (oh-my-openagent uses its own `mcp.json`-in-skill-folder convention — that's a
community convention, not the official mechanism.)

## Evaluating & testing agents/skills/configs

There's **no `opencode config validate` or `opencode eval` subcommand** — config validation is
editor-side via `"$schema": "https://opencode.ai/config.json"` (and `opencode.ai/tui.json` for
themes/keybinds). `opencode debug config` shows the resolved merged config. The eval ecosystem
is thin but real:
- **`nano-step/eval-harness`** — the most opencode-native reusable framework; behavior-
  regression tests at `.opencode/skills/<skill>/evals/cases/*.yaml`, 6 check kinds incl.
  `llm_judge` (3-sample majority vote), failure attribution (skill-changed / fixture-stale /
  model-changed / drift), pre-push hook + GitHub Action.
- **`evalite`** (`.eval.ts` with `createScorer`) — used by joelhooks' swarm-evals to score
  task-decomposition quality with real LLM calls; must run in a **separate CLI package** (it
  crashes if imported inside the plugin runtime).
- **oh-my-openagent** ships a per-skill eval harness (`evals/evals.json` with
  prompt/expected/assertions) reporting with-skill vs without-skill lift (~+45%), and an honest
  note that a strong skill can *encourage over-engineering* — worth heeding.
- **Config linting**: `jjmartres/ai-coding-agents` uses a pre-commit JSONC validator +
  markdownlint/shellcheck/detect-private-key. That's syntax, not schema, validation.

For this plugin, the pragmatic test loop: author with `oc_agent_write`/`oc_skill_write`,
verify it loads (`oc_agents`/`oc_skills`), then exercise it read-only via
`oc_acp_prompt(mode=<agent>, permission=reject)` on a representative prompt.

## Enterprise / self-hosting / security

### Config precedence (8 layers, later wins)
remote `.well-known/opencode` → global `~/.config/opencode` → `OPENCODE_CONFIG` → project
`opencode.json` → `.opencode/` dirs → `OPENCODE_CONFIG_CONTENT` → managed dir → macOS
`.mobileconfig` MDM (highest, not user-overridable). **⚠️ Doc/behavior mismatch**: open issues
report global config sometimes overriding project config in practice — **test on your target
version**, don't trust the ordering blindly.

- **Managed config dirs**: macOS `/Library/Application Support/opencode/`, Linux
  `/etc/opencode/`, Windows `%ProgramData%\opencode`. macOS MDM preference domain
  `ai.opencode.managed` (deploy via `.mobileconfig`, Jamf/FleetDM). Managed keys can't be
  overridden downstream.
- **`.well-known/opencode`** org config: opt-in is **explicit** — a user runs
  `opencode auth login <org-url>`, which fetches the config and **executes its `auth.command`
  immediately without a confirmation prompt** (an open security concern) and refetches on every
  startup. Account for that in any rollout.
- **`experimental.policies`** — provider governance (`{effect, action:"provider.use",
  resource}`); global policy beats project (a repo can't re-enable a globally-denied provider).
  The newer replacement for `disabled_providers`/`enabled_providers`.

### Sharing & secrets
- **`/share`** sends the conversation to opencode.ai-hosted pages (`opncd.ai/s/<id>`, public to
  anyone with the link). Config `"share": "disabled"` (check it into git) enforces no-share;
  enterprise options are disable / SSO-only / self-host (self-host is **roadmap-only** today).
- **Secrets**: use `{env:VAR}` / `{file:path}` — never plaintext keys. **⚠️ Keys added via
  `/connect` are stored PLAINTEXT in `~/.local/share/opencode/auth.json`** (no keychain/
  encryption — an open, unresolved enterprise blocker). Flag this for regulated environments.

### Network / proxy
`HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY` (set `NO_PROXY=localhost,127.0.0.1` or the TUI↔local-
server loop breaks), `NODE_EXTRA_CA_CERTS=/path/ca.pem` for corporate CAs. Don't hardcode
proxy basic-auth in the URL; for NTLM/Kerberos route through an LLM gateway.

### ⚠️ Sandboxing — permissions are ADVISORY, not a security boundary
opencode has **no OS-level sandbox**. `permission` prompts gate tool calls, but an allowed
`bash` can write outside `edit` restrictions via `python`/`node`/shell redirects/`cp`/`mv`,
and `external_directory` gates paths at the permission layer, not by process containment
(unenforced on Windows/Git Bash in some cases). Default posture is **permissive**; `--auto`
auto-approves anything not explicitly denied. **If opencode may run untrusted or semi-trusted
code, treat the permission system as advisory and add real isolation yourself** (container/VM/
seccomp — e.g. community `opencode-sandbox` images, `docker sandbox create opencode`). This is
the single most important safety fact for anyone automating opencode.
