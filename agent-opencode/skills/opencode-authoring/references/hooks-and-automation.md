# Hooks and Automation

Hooks are deterministic automation points. Use them for checks, formatting,
policy enforcement, and workflow glue that should fire from events rather
than from model memory.

## OpenCode Hook Surface

OpenCode plugins expose hooks. A plugin is a TypeScript or JavaScript module
that exports a default function returning a hooks object.

```ts
import type { Plugin } from "@opencode-ai/plugin"

const plugin: Plugin = async ({ client }, options) => {
  return {
    "tool.execute.before": async (input, output) => {
      // inspect output.args; throw to deny
    },
    "tool.execute.after": async (input, output) => {
      // best-effort audit; never throw
    },
  }
}

export default plugin
```

Register it under `plugin` in `opencode.json`:

```json
{
  "plugin": [
    ["./plugins/my-plugin/index.ts", { "enableFeature": true }]
  ]
}
```

A `*.ts` or `*.js` file under `.opencode/plugin/` or `.opencode/plugins/`
is auto-discovered; explicit `plugin` entries are still required for
non-default locations.

## Available Hooks

Mutate `output` in place and return `void`. Throw inside
`tool.execute.before` to deny the tool call.

- `event(input)` — every bus event.
- `config(cfg)` — once on init with the merged config.
- `chat.message`, `chat.params`, `chat.headers`.
- `tool.execute.before` — inspect or mutate `output.args` before a tool runs.
- `tool.execute.after` — best-effort audit after a tool runs.
- `tool.definition` — adjust tool definitions.
- `command.execute.before`.
- `shell.env`.
- `permission.ask`.
- `experimental.chat.messages.transform`,
  `experimental.chat.system.transform`,
  `experimental.session.compacting`,
  `experimental.compaction.autocontinue`,
  `experimental.text.complete`.

There is no first-class permission-decision object equivalent to Claude's
`hookSpecificOutput.permissionDecision`. The supported deny mechanism is to
`throw new Error(...)` inside `tool.execute.before`.

## Tool Argument Shapes

`output.args` and `input.args` are typed as `any`; validate every field at
runtime. The built-in shapes are:

| Tool | Fields |
|---|---|
| `bash` | `command: string`, optional `timeout`, `workdir` |
| `write` | `filePath: string`, `content: string` |
| `edit` | `filePath: string`, `oldString: string`, `newString: string`, optional `replaceAll` |
| `apply_patch` | `patchText: string` (parse `*** Add/Update/Delete File:` and `*** Move to:` markers) |

Guard `write`, `edit`, AND `apply_patch` to avoid a native edit-bypass.

## Hard Rules

- Hooks enforce; prompts guide. Do not use a prompt instruction where
  deterministic blocking is required.
- Throw for denials, not for parser or logging errors — fail open there so a
  broken hook never bricks operations.
- Audit failures are fail-open; safety rule matches are fail-closed.
- Validate runtime shapes yourself. Do not trust `args` typing.
- Restart OpenCode after changing a registered plugin file; plugins load at
  startup, not on hot reload.

## Verification

1. Unit-test the pure decision functions directly.
2. Exercise positive (block) and negative (near-miss allow) vectors.
3. Load the plugin in a fresh OpenCode session and exercise a real tool call.
4. Confirm audit logs are written and that parser failures fail open.
