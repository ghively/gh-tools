# deep-integration-builder

A Claude Code plugin that captures a **methodology** for building comprehensive,
deeply-tested control integrations — an MCP server + control skill + workflow commands,
packaged as a plugin — for any system that exposes an API (a NAS, router, home-automation
hub, cloud console, SaaS, database, appliance…).

It was distilled from building [`synology-nas`](../README.md), a plugin that reached all
~870 APIs of a Synology DiskStation, including reverse-engineering its undocumented backup
APIs from the web UI's own traffic.

## What's inside

- **Skill `building-deep-integrations`** — the 6-phase workflow and the principles that
  create the depth. Triggers whenever you ask to build a plugin / MCP / integration to
  "control" or "fully cover" a system.
  - `references/reverse-engineering.md` — capture undocumented API calls from a UI's
    network traffic (the XHR-interceptor technique) when guessing fails.
  - `references/gap-taxonomy.md` — the safe write-probe pattern and the
    **Works / Fixable / Hard-limit** classification.
  - `references/plugin-scaffold.md` — concrete plugin structure and a self-provisioning
    MCP server pattern.
- **Command `/build-integration <system>`** — kicks off the workflow for a named system.

## The core idea

**"Covered" means the operation actually works for the user — not that an API exists for
it.** Real coverage needs four things to line up: the right method name, the right params,
the dependency running, and permission granted. Every gap is a failure of one of these.
The skill turns that principle into a repeatable process: discover the full surface first,
build a generic-passthrough + curated-tools plugin, verify every tool live, then
gap-audit every domain into Works / Fixable / Hard-limit and close what's fixable —
reverse-engineering from real UI traffic when needed, and reporting honestly about the
edges.

## Use it

```
/plugin install deep-integration-builder@gh-tools
/reload-plugins
```

Then: `/build-integration my UniFi controller at 10.0.0.1` — or just say "build me a
plugin to fully control X" and the skill will trigger.

## Layout

```
deep-integration-builder/
├── .claude-plugin/plugin.json
├── skills/building-deep-integrations/
│   ├── SKILL.md
│   └── references/{reverse-engineering,gap-taxonomy,plugin-scaffold}.md
├── commands/build-integration.md
└── README.md
```
