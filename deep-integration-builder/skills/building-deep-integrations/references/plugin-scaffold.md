# Packaging the integration as a Claude Code plugin

The structure that worked. Adapt names; keep the shape.

```
my-integration/                     (plugin root = marketplace entry, or a subdir)
├── .claude-plugin/
│   └── plugin.json                 name, description, version, author, skills, commands
├── .mcp.json                       launches the MCP server (flat {server:{...}} map)
├── config.example.json             template (committed)
├── config.local.json               real host + secrets (GIT-IGNORED)
├── .gitignore                      ignores config.local.json, __pycache__, .venv, *.pyc
├── README.md
├── mcp/
│   ├── server.py                   the MCP server (client + generic + curated tools)
│   └── _smoketest.py               rerunnable live check of every curated read tool
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
# dependencies = ["mcp>=1.4.0,<2.0.0", "httpx>=0.27"]
# ///
```

**Pin `mcp<2.0.0`.** The 2.0 release renamed `FastMCP` → `MCPServer`; an unpinned
script self-provisions the new major on a fresh install and dies at import. Every
plugin in this repo carries this exact pin — keep it until the code targets 2.x.

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

## `mcp/_smoketest.py` — keep verification rerunnable

Capture Phase 2's live verification as a script so it survives the build session.
Same uv-script header as the server; it imports `server.py` via
`importlib.util.spec_from_file_location`, calls **every curated read tool** against
the live system, and prints each result shape (truncated). It must **never call a
confirm-gated write tool**. Run it after any server change:

```
cd my-integration && uv run --script mcp/_smoketest.py
```

## Control-skill frontmatter

The bundled `SKILL.md` needs `name` and a `description` that says **when to trigger**
— name the system, enumerate the jobs it covers, and end with "do not answer from
memory; drive the live server through the tools." Plugins in this repo also carry a
`metadata.hermes` block (`tags`, `category`, `requires_tools`, `config` prompts) so
the same skill installs under Hermes Agent — copy the shape from any sibling.

## Adding a plugin to an existing marketplace

A marketplace is a repo/dir with `.claude-plugin/marketplace.json` listing plugins.
Add an entry pointing at the plugin's subdirectory (`source`), with an honest
description that says what was live-verified (version tested, tool counts, known
limits) and a `version` matching `plugin.json`:

```json
{
  "name": "my-marketplace",
  "plugins": [
    {
      "name": "my-integration",
      "source": "./my-integration",
      "description": "Control of X (live-verified on X 1.2.3) — N-op passthrough + M curated tools. All writes confirm-gated.",
      "category": "infrastructure",
      "version": "0.1.0"
    }
  ]
}
```

Install locally: `/plugin marketplace add <path>` → `/plugin install <name>@<marketplace>`
→ `/reload-plugins`.
