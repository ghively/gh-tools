# Configuring opencode — the complete config reference

Read this before editing `opencode.json` or advising on configuration. Verified against
opencode 1.18.3 (repo `anomalyco/opencode`). Patch config with `oc_config_update(patch,
confirm=true, scope=...)`, or write files directly for deletions/complex edits.

## File locations & precedence

opencode merges config from many sources (later wins; deep object merge):

1. Global: `~/.config/opencode/{config.json → opencode.json → opencode.jsonc}` (XDG:
   `$XDG_CONFIG_HOME/opencode`). All three names load; later in the list wins.
2. `OPENCODE_CONFIG` (exact file path env override).
3. Project `opencode.json`/`.jsonc` — found by walking **up from cwd to the git worktree root**.
4. `.opencode/` dirs (project + `$HOME/.opencode` + `OPENCODE_CONFIG_DIR`), each may hold
   its own config plus auto-discovered `command/`, `agent/`, `plugin/` subfolders.
5. `OPENCODE_CONFIG_CONTENT` (inline JSON string).
6. Managed/enterprise config; on macOS an MDM `.mobileconfig` wins over everything.

Merge mechanics: objects deep-merge, scalars/arrays are **replaced** by later sources —
**except `instructions`**, which is concatenated + de-duplicated across all sources. `.jsonc`
with trailing commas and comments is supported everywhere.

**Split-out files:** `theme` and `keybinds` do **not** live in `opencode.json` — they are
stripped from it and belong to a separate `tui.json` (schema `https://opencode.ai/tui.json`).

## Variable substitution (in any string value, before JSONC parse)

- `{env:VAR}` → env var value (empty string if unset).
- `{file:./path}` → JSON-escaped file contents; supports `~/`, relative (to the config
  file's dir), and absolute paths. Missing file → hard error. A `{file:...}` on a `//`
  comment line is left untouched.

Use these for secrets: `"apiKey": "{env:OPENAI_API_KEY}"` instead of a literal key.
(Note: this host's current `opencode.json` has a **plaintext** provider apiKey — worth
migrating to `{env:...}` if the user wants secrets out of the file.)

## Top-level schema (every key)

| Key | Type | Notes |
|---|---|---|
| `$schema` | string | `https://opencode.ai/config.json`, auto-injected |
| `model` | `"provider/model"` | main model |
| `small_model` | `"provider/model"` | cheap model for titles/summaries/lightweight tasks |
| `default_agent` | string | must be a primary agent; falls back to `build` |
| `subagent_depth` | int ≥0 | default `1`; raise to let subagents spawn subagents |
| `username` | string | display-name override |
| `agent` | `Record<string, AgentInfo>` | inline agent defs (also `agent/*.md` files) — see agents-and-workflows.md |
| `command` | `Record<string, CommandInfo>` | inline commands (also `command/**/*.md`) |
| `provider` | `Record<string, ProviderConfig>` | custom/override providers |
| `mcp` | `Record<string, McpLocal\|McpRemote\|{enabled}>` | MCP servers |
| `permission` | string \| object | access control (see below) |
| `tools` | `Record<string, boolean>` | shorthand, folds into `permission` |
| `instructions` | `string[]` | paths/globs of rule files; concatenated across sources |
| `formatter` | `boolean \| Record<string, {command,extensions,...}>` | code formatters |
| `lsp` | `boolean \| Record<string, {command,extensions,...}>` | language servers |
| `disabled_providers` | `string[]` | blocklist |
| `enabled_providers` | `string[]` | if non-empty, an **allowlist** (disables all others) |
| `share` | `"manual"\|"auto"\|"disabled"` | session sharing (`autoshare` deprecated) |
| `autoupdate` | `boolean\|"notify"` | |
| `snapshot` | boolean | default true; filesystem undo tracking |
| `server` | object | `{port,hostname,mdns,mdnsDomain,cors}` for `opencode serve` |
| `watcher.ignore` | `string[]` | file-watcher exclusions |
| `compaction` | object | `{auto,prune,tail_turns,preserve_recent_tokens,reserved}` |
| `attachment.image` | object | `{auto_resize,max_width,max_height,max_base64_bytes}` |
| `tool_output` | object | `{max_lines(2000),max_bytes(51200)}` before disk truncation |
| `logLevel` | `DEBUG\|INFO\|WARN\|ERROR` | |
| `shell` | string | default shell for bash/terminal |
| `plugin` | `(string\|[string,object])[]` | npm plugin specs |
| `skills` | object | extra skill-folder paths |
| `references` | object | named git/local-dir references |
| `experimental` | object | `{disable_paste_summary,batch_tool,openTelemetry,primary_tools[],continue_loop_on_deny,mcp_timeout,policies[]}` |

Deprecated: `mode` (→ `agent`), `autoshare` (→ `share`), `layout`, `maxSteps` (→ `steps`),
per-agent `tools` (→ `permission`).

## Providers & models

Known providers (via **models.dev**, 75+ providers) need no context/pricing overrides —
just credentials (`opencode auth login` or `provider.<id>.options.apiKey`). Model names are
always `"provider/model"`.

Custom / local (Ollama, any OpenAI-compatible endpoint):
```jsonc
{
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": { "baseURL": "http://127.0.0.1:11434/v1" },
      "models": { "llama3.1": { "limit": { "context": 128000, "output": 8192 },
                                 "cost": { "input": 0, "output": 0 }, "tool_call": true } }
    }
  },
  "model": "ollama/llama3.1"
}
```
Per-model overrides: `name, family, release_date, reasoning, tool_call, cost{input,output,
cache_read,cache_write}, limit{context,input,output}, modalities{input[],output[]}, status,
variants`. Trim the catalog with `disabled_providers` / `enabled_providers`.

## MCP servers

Discriminated union on `type`. Secrets via `{env:...}`.
```jsonc
{
  "mcp": {
    "playwright": { "type": "local", "command": ["npx","-y","@playwright/mcp"],
                     "environment": { "FOO": "{env:FOO}" }, "enabled": true, "timeout": 5000 },
    "linear": { "type": "remote", "url": "https://mcp.linear.app/mcp",
                 "headers": { "Authorization": "Bearer {env:LINEAR_API_KEY}" },
                 "oauth": { "clientId": "{env:ID}", "scope": "tools:read" }, "enabled": true }
  }
}
```
Remote OAuth is automatic on 401 (RFC 7591 DCR); tokens in `~/.local/share/opencode/mcp-auth.json`.
CLI helpers: `opencode mcp {add,list,auth,logout,debug}`. Or drive dynamically with
`oc_mcp(action, name, config)`. MCP tools appear namespaced as `servername_toolname` and are
gated by `tools`/`permission` globs (e.g. `"my-mcp*"`).

## Permissions

`Action = ask|allow|deny`. `permission` is a string (`"ask"` → `{"*":"ask"}`) or an object.
- Pattern-capable keys: `read, edit, glob, grep, list, bash, task, external_directory, lsp, skill`.
- Action-only keys: `todowrite, question, webfetch, websearch, doom_loop`.
- Last matching pattern wins; `*` = any chars, `?` = one char; `~`/`$HOME` expand.
- Put a catch-all `"*"` first, then specific overrides.
```jsonc
{
  "permission": {
    "edit": "ask",
    "bash": { "*": "ask", "git *": "allow", "npm run *": "allow",
               "rm *": "deny", "git push *": "deny" },
    "webfetch": "ask"
  }
}
```
`.env` reads default to `deny` (`.env.example` allowed). `OPENCODE_PERMISSION` (JSON) can
override at runtime.

## Rules / instructions

- `AGENTS.md` (project root, upward-traversed; also global `~/.config/opencode/AGENTS.md`) —
  scaffold with the `/init` command (`oc_command(id,'init')`).
- **`CLAUDE.md` is a supported fallback** (project, then `~/.claude/CLAUDE.md`) when no
  AGENTS.md. Disable via `OPENCODE_DISABLE_CLAUDE_CODE*` env vars.
- `instructions: [...]` pulls in extra rule files/globs (e.g. `.cursor/rules/*.md`) —
  additive, concatenated across all merged config.

## LSP & formatters

`lsp` / `formatter` are `true` (auto) or a map of custom servers. Custom LSP needs
`command` + `extensions`. LSP powers `/find/symbol` and code intelligence — without a
configured+running server for the language, symbol search returns empty (see conventions.md).
