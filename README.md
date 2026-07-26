# gh-tools — a Claude Code plugin marketplace for deep infrastructure control

Four plugins, one methodology: enumerate the system's full API surface, build a
generic passthrough + curated tools, live-verify everything, and report honestly
(works / fixable / hard limit). Install: `/plugin marketplace add <this repo>` →
`/plugin install <name>@gh-tools` → `/reload-plugins`.

| Plugin | Controls | Highlights |
|---|---|---|
| `synology-nas` (repo root) | Synology DS1817+ (DSM 7.3) | all ~870 SYNO.* APIs + 67 curated tools |
| `gitlab` | Self-hosted GitLab CE 19.0 | ~170 REST domains + GraphQL, ~35 curated tools, admin ops |
| `unifi-network` | Ubiquiti UniFi console (UDR7) | v1/v2/UniFi-OS APIs, ~30 curated tools |
| `deep-integration-builder` | — (methodology) | the skill + command used to build the others |

Each plugin reads its credentials from a git-ignored `config.local.json`
(`config.example.json` shows the shape). No secrets live in this repo.

---

# synology-nas — full Synology DSM control for Claude Code

A Claude Code plugin that gives Claude complete, authenticated control of a Synology
DiskStation over the DSM Web API. Built and tested against **gh-storage**, a
**DS1817+** running **DSM 7.3.1**.

## What's inside

- **MCP server** (`mcp/synology_server.py`) — authenticates to DSM (session id +
  CSRF token, auto re-login) and exposes:
  - **Generic passthrough** (`synology_call`, `synology_batch`, `synology_list_apis`,
    `synology_describe_api`) reaching **all ~870 SYNO.\* APIs** on the box.
  - **27 curated tools** for system health, storage, File Station, Download Station,
    packages, services, users, groups, shares, and power.
- **Skill** (`skills/synology-control/`) — teaches Claude how to drive the server,
  with a full categorized **API map** of this NAS, verified **task recipes**, and the
  **auth/conventions** reference.
- **Commands** (`commands/`) — `/syno-health`, `/syno-storage`, `/syno-downloads`,
  `/syno-find-large`.

## Setup

1. **Credentials.** Copy `config.example.json` → `config.local.json` and fill in your
   NAS host, port, username, and password. `config.local.json` is git-ignored so your
   password is never committed. Any field can instead be set via environment variables
   (`SYNOLOGY_HOST`, `SYNOLOGY_PORT`, `SYNOLOGY_HTTPS`, `SYNOLOGY_USERNAME`,
   `SYNOLOGY_PASSWORD`, `SYNOLOGY_OTP_CODE`, `SYNOLOGY_VERIFY_SSL`), which override the
   file.
2. **Runtime.** The MCP server launches via [`uv`](https://docs.astral.sh/uv/)
   (`uv run --script`), which auto-provisions its dependencies (`mcp`, `httpx`) in a
   cached environment — no manual `pip install` needed. `uv` must be on PATH.
3. **Load the plugin** in Claude Code (install from this directory / your marketplace),
   then run `/reload-plugins` or restart. Ask Claude to "check the NAS" or run
   `/syno-health`.

## Security notes

- The password lives only in `config.local.json` (git-ignored) or your environment.
- HTTPS to a LAN NAS uses a self-signed cert, so certificate verification is off by
  default (`verify_ssl: false`). Set it true if you've installed a trusted cert.
- Destructive tools (`synology_reboot`, `synology_shutdown`, `synology_fs_delete`)
  require `confirm=True`. The skill instructs Claude to confirm any write/disruptive
  action with you first.

## Coverage notes (this DSM)

- **Container Manager** `SYNO.Docker.*` is available only while the ContainerManager
  package is running (its APIs register only then). Curated container/image/Compose
  tools are included; if they return 102, start the package with
  `synology_package_control(package_id="ContainerManager", action="start")`.
- **Virtual Machine Manager** APIs are present but require per-user VMM privileges
  (and a Pro license for full API control) before calls succeed.

See `skills/synology-control/references/` for the full API map and details.

---

# Using this repo with Hermes Agent

Everything above is the Claude Code side (`.claude-plugin/`, `.mcp.json`,
`commands/`) and is untouched by the rest of this section — Hermes Agent
(Nous Research's self-improving CLI agent) reads a different layout, so this
repo carries a second, parallel set of files for it.

## Installing the skills

Hermes discovers skills from a GitHub repo one level under a single
`skills/` path (`hermes skills tap add owner/repo`, default path `skills/`).
That default is already claimed here by the `synology-nas` Claude plugin
(repo-root `skills/synology-control/`), so all 13 skills are mirrored — flat,
one directory per skill — into **`hermes-skills/`** instead
(`scripts/sync_hermes_skills.py` generates it; the per-plugin `skills/`
directories remain the source of truth for Claude Code).

- **Whole catalog at once:** run `hermes skills tap add ghively/gh-tools`,
  then edit `~/.hermes/taps.json` and change that entry's `"path"` from
  `"skills/"` to `"hermes-skills/"` (the plain CLI only offers the default
  path; the custom path is honored once it's in the file — this is the same
  field Hermes' own `skills tap` snapshot/restore uses). After that,
  `hermes skills browse` / `search` / `install <name>` see every skill here.
- **One skill without tapping:** `hermes skills install
  ghively/gh-tools/hermes-skills/<skill-name>` (e.g. `.../hermes-skills/sonarr-control`)
  works immediately — `hermes skills install` accepts any `owner/repo/path`
  identifier, tapped or not.

Each `SKILL.md` carries a `metadata.hermes` block (`tags`, `category`,
`requires_tools` so the skill only surfaces once its MCP server is actually
configured) plus `required_environment_variables` for whichever secret that
plugin needs — Hermes prompts for and persists those the first time the
skill loads.

## Wiring up the MCP servers

Hermes doesn't read `.mcp.json` — it has its own `mcp_servers:` block in
`~/.hermes/config.yaml`. **`hermes.mcp.example.yaml`** (repo root) has a
ready-to-merge entry for every plugin, pointing at the exact same
`mcp/*.py` script and `config.local.json` each Claude Code plugin already
uses (the servers are plain stdio MCP processes — they don't care which
client launched them). Copy the servers you want into your own
`config.yaml`, swap `<GH_TOOLS_REPO>` for where you cloned this repo, and
make sure each plugin's `config.local.json` is filled in as usual.

## Keeping it in sync

If you edit a plugin's `SKILL.md` (or add/remove a plugin), re-run:

```bash
python3 scripts/sync_hermes_skills.py       # regenerate hermes-skills/
python3 scripts/sync_hermes_skills.py --check   # CI: fails if it's stale
```

