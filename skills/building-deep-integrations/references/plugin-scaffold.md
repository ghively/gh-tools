# Packaging the integration as a Claude Code plugin

The structure that worked. Adapt names; keep the shape.

```
my-integration/                     (plugin root = marketplace entry, or a subdir)
├── .claude-plugin/
│   └── plugin.json                 name, description, version, author, skills, commands
├── .mcp.json                       launches the MCP server (flat {server:{...}} map)
├── config.example.json             template (committed)
├── config.local.json               real host + secrets (GIT-IGNORED)
├── .gitignore                      ignores config.local.json, __pycache__, .venv
├── README.md
├── mcp/
│   └── server.py                   the MCP server (client + generic + curated tools)
├── skills/
│   └── <name>-control/
│       ├── SKILL.md                how to drive the server; discovery-first; safety
│       └── references/
│           ├── api-map.md          the FULL enumerated surface (from the system)
│           ├── common-tasks.md     verified call recipes for non-curated jobs
│           └── conventions.md      auth model, error codes, param encoding, quirks
└── commands/
    ├── health.md                   multi-step workflows as slash commands
    └── ...
```

## `.mcp.json` — reproducible, self-provisioning launch

Launch the server so it installs its own deps (no manual pip). With Python + `uv`, a
PEP 723 inline-deps script + `uv run --script` is ideal; `${CLAUDE_PLUGIN_ROOT}` makes
paths portable:

```json
{
  "my-integration": {
    "command": "uv",
    "args": ["run", "--script", "${CLAUDE_PLUGIN_ROOT}/mcp/server.py"],
    "env": { "MYAPP_CONFIG": "${CLAUDE_PLUGIN_ROOT}/config.local.json" }
  }
}
```

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.4.0", "httpx>=0.27"]
# ///
```

Node/other runtimes work too — the point is one command that self-provisions and reads
a git-ignored config.

## Client design checklist

- Config resolution: env vars override a git-ignored local file; never hardcode secrets.
- Session handling: login, cache session id + any CSRF token, **auto re-login on
  session-expiry error codes and retry once**.
- Sensitive-write **elevation** hook (`call(..., elevate=True)`) if the system gates
  some writes behind a re-confirmation token.
- Param encoding matching the backend (e.g. JSON-encode arrays/objects).
- **Version resolution**: default to the API's advertised version, but let callers
  override — some methods only exist at a specific (often not the max) version.
- All logs to stderr for stdio MCP servers; stdout is the protocol.

## MCP server surface

- Generic: `status`, `list_apis`/`discover`, `describe_api`, `call`, `batch`.
- Curated: one tool per common job, correct params/version baked in.
- Confirm-gate destructive tools (`confirm: bool`), and elevate the ones that need it.

## Adding a plugin to an existing marketplace

A marketplace is a repo/dir with `.claude-plugin/marketplace.json` listing plugins.
Add an entry pointing at the plugin's directory (`source`); the root plugin can use
`"./"` and additional plugins live in subdirectories:

```json
{
  "name": "my-marketplace",
  "plugins": [
    { "name": "my-integration",       "source": "./" },
    { "name": "deep-integration-builder", "source": "./deep-integration-builder" }
  ]
}
```

Install locally: `/plugin marketplace add <path>` → `/plugin install <name>@<marketplace>`
→ `/reload-plugins`.
