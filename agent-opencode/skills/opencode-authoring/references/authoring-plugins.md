# Authoring OpenCode Plugins

A plugin is a TypeScript or JavaScript module that exports a default function
returning a hooks object.

## Module Shape

```ts
import type { Plugin } from "@opencode-ai/plugin"

const myPlugin: Plugin = async ({ client, project, directory }, options) => {
  return {
    config: (cfg) => {
      // mutate the live merged config
    },
    "tool.execute.before": async (input, output) => {
      // throw to deny; mutate output.args to reshape
    },
    "tool.execute.after": async (input, output) => {
      // best-effort audit
    },
  }
}

export default myPlugin
```

Install the SDK once per machine:

```bash
npm install @opencode-ai/plugin
```

## Registration

In `opencode.json`:

```json
{
  "plugin": [
    "opencode-foo",
    "opencode-bar@1.2.3",
    "./plugins/my-plugin/index.ts",
    ["opencode-with-options", { "enableFeature": true }]
  ]
}
```

A `*.ts` or `*.js` file under `.opencode/plugin/` or `.opencode/plugins/`
is auto-discovered without an explicit entry.

## Hook Surface

Mutate `output` in place; return `void`. Throw inside `tool.execute.before`
to deny a tool call.

Common hooks: `event`, `config`, `chat.message`, `chat.params`,
`chat.headers`, `tool.execute.before`, `tool.execute.after`,
`tool.definition`, `command.execute.before`, `shell.env`, `permission.ask`.

See `./hooks-and-automation.md` for the full surface and semantics.

## Plugin Layout

```text
plugins/my-plugin/
├── package.json
├── tsconfig.json
├── index.ts
├── tests/
│   └── plugin.test.ts
└── references/
    └── decisions.md
```

## Rules

- Plugins are self-contained. Do not import files outside the plugin
  directory.
- Keep denials inside `tool.execute.before` (throw). Parser and logging
  errors fail open.
- Do not invent hook names or hook signatures. Verify against the SDK type
  definitions in `@opencode-ai/plugin` before adding a field.
- Unit-test the pure decision functions in isolation. Mock `client.app.log`
  for audit-trail tests.
- Restart OpenCode after registering or changing a plugin; plugin code is
  loaded at startup, not on hot reload.

## Versus Claude Code Plugins

OpenCode plugins are function modules, not directories with a
`.claude-plugin/plugin.json` manifest. There is no `${CLAUDE_PLUGIN_ROOT}`,
no `hooks/hooks.json`, no marketplace manifest, and no `permissionDecision`
return object. Adapt the doctrine, not the wire protocol.
