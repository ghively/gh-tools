# gh-tools — deep infrastructure control for Claude Code and Hermes Agent

One methodology, 15 plugins: enumerate the system's full API surface, build a
generic passthrough + curated tools, live-verify everything, and report honestly
(works / fixable / hard limit). Each plugin lives in its own directory (see its
`README.md`) with an identical shape: `.claude-plugin/`, `.mcp.json`, `mcp/`,
`skills/`, `commands/`, `config.example.json`.

This repo works as-is with two agent runtimes:

- **Claude Code** — a native plugin marketplace. Install:
  `/plugin marketplace add <this repo>` → `/plugin install <name>@gh-tools` →
  `/reload-plugins`.
- **Hermes Agent** — the repo-root `skills/` directory and `hermes.mcp.example.yaml`
  make every skill and MCP server installable via `hermes skills tap` /
  `hermes skills install`; see [Using this repo with Hermes Agent](#using-this-repo-with-hermes-agent)
  below.

Both sides read from the same per-plugin source (`mcp/*.py`, `config.local.json`)
and neither one's files are touched by the other's tooling.

| Plugin | Controls | Highlights |
|---|---|---|
| `synology-nas` | Synology DS1817+ (DSM 7.3) | all ~870 SYNO.* APIs + 27 curated tools |
| `gitlab` | Self-hosted GitLab CE 19.0 | REST+GraphQL over 177 resource groups, 79 curated tools |
| `unifi-network` (`unifi/`) | Ubiquiti UniFi console (UDR7) | v1/v2/UniFi-OS APIs, ~30 curated tools |
| `emby` | Emby media server | ~484-op REST passthrough, ~30 curated tools |
| `romm` | RomM ROM-library server | ~189-op REST passthrough, ~70 curated tools |
| `romarr` | ROMarr (the *arr for games) | 53-op REST passthrough, ~44 curated tools, found a real credential-leak bug |
| `unraid-control` | Unraid server (7.x) | full GraphQL schema passthrough, 84 curated tools |
| `comfyui-control` | ComfyUI generation server | full API passthrough + image/video generation suite |
| `opencode-control` | OpenCode coding agent | 188-op passthrough + 49 curated tools, HTTP + ACP |
| `searxng-control` | Self-hosted SearXNG | search + 249-engine inventory + settings.yml tuning over SSH |
| `radarr-control` | Radarr movie manager | 467-op passthrough, 64 curated tools |
| `sonarr-control` | Sonarr TV manager | 463-op passthrough, 66 curated tools |
| `sabnzbd-control` | SABnzbd usenet downloader | 21 curated tools, double-gated lifecycle control |
| `tdarr-control` | Tdarr transcoding server | 67-endpoint passthrough + ~30 curated tools + 3,700+ line knowledge base |
| `deep-integration-builder` | — (methodology) | the skill + command used to build the others |

Each plugin reads its credentials from a git-ignored `config.local.json`
(`config.example.json` shows the shape). No secrets live in this repo.

---

# Using this repo with Hermes Agent

Everything above is the Claude Code side (`.claude-plugin/`, `.mcp.json`,
`commands/`) and is untouched by the rest of this section — Hermes Agent
(Nous Research's self-improving CLI agent) reads a different layout, so this
repo carries a second, parallel set of files for it.

## Installing the skills

Hermes discovers skills from a GitHub repo one level under a single
`skills/` path (`hermes skills tap add owner/repo`, default path `skills/`).
Every plugin here keeps its actual skill under `<plugin>/skills/<name>/`
(each plugin's own `.claude-plugin/plugin.json` requires that), so the
repo-root **`skills/`** directory is a generated flat mirror — one directory
per skill, 13 total — built by `scripts/sync_hermes_skills.py`. It doesn't
collide with anything Claude Code reads: no plugin's `plugin.json` points at
the repo-root `skills/` path (each plugin is in its own subdirectory, `synology-nas`
included), so this directory exists purely for Hermes.

- **Whole catalog at once:** `hermes skills tap add ghively/gh-tools` — the
  default path is exactly right, no extra config needed. Then `hermes skills
  browse` / `search` / `install <name>` see every skill here.
- **One skill without tapping:** `hermes skills install
  ghively/gh-tools/skills/<skill-name>` (e.g. `.../skills/sonarr-control`)
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
python3 scripts/sync_hermes_skills.py       # regenerate the repo-root skills/ mirror
python3 scripts/sync_hermes_skills.py --check   # CI: fails if it's stale
```

