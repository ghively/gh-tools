# searxng-control

Deep control of a self-hosted **SearXNG** metasearch instance from Claude Code —
search, introspect, diagnose, and **tune** it. Verified live against **SearXNG
2026.5.7**.

SearXNG has no configuration API: its control surface is the runtime HTTP API
(read) plus `settings.yml` inside the container (write). This plugin bridges both.

## Three layers

1. **Generic HTTP passthrough** — `searx_http` reaches any route; `searx_endpoints`
   maps the surface (SearXNG ships no OpenAPI, so the map is hand-enumerated + live-verified).
2. **Curated runtime tools** — `searx_status`, `searx_search` (all query params),
   `searx_autocomplete`, `searx_config`, `searx_engines` (249-engine inventory),
   `searx_engine_errors` / `searx_stats` / `searx_health` (diagnostics).
3. **Config management (SSH → settings.yml → restart)** — `searx_settings_read`,
   `searx_engine_show`, `searx_engine_toggle`, `searx_engine_add`,
   `searx_setting_set`, `searx_settings_backups` / `searx_settings_restore`,
   `searx_restart`, `searx_logs`. **Every write is confirm-gated and
   auto-backed-up; changes apply on restart.**

## Configure

Copy `config.example.json` → `config.local.json` (git-ignored):

```json
{
  "base_url": "http://gh-arm:8888",
  "ssh_host": "gh-arm",
  "container": "searxng",
  "settings_path": "/etc/searxng/settings.yml",
  "verify_ssl": false,
  "timeout": 30
}
```

- `base_url` alone enables search + introspection + diagnostics.
- `ssh_host` + `container` enable the config-management layer (edits `settings.yml`
  in the container over SSH — needs key-based SSH to the host and `docker` access).
  Leave `ssh_host` empty for search/read-only mode.

## Install

```
/plugin install searxng-control@gh-tools
/reload-plugins
```

Then hand-place your `config.local.json` in the installed plugin dir (it is
git-ignored and never ships with the plugin).

## Skill & workflows

- Skill `searxng-control` — how to drive the server, plus references: full HTTP
  surface (`api-map.md`), every `settings.yml` option (`settings-reference.md`),
  and the engine-reliability/CAPTCHA playbook (`engine-tuning.md`).
- Commands: `/searxng-health`, `/searxng-diagnose`, `/searxng-tune-reliability`,
  `/searxng-add-engine`.

## Note on reliability

On a **datacenter IP** (e.g. a cloud VM), Google/DuckDuckGo/Brave/Startpage
CAPTCHA the instance and SearXNG suspends them (1h, or 15d for Cloudflare),
collapsing results. The fix is engine selection — lean on **bing + mojeek +
independents** and disable the CAPTCHA-prone defaults. `/searxng-diagnose` and
`/searxng-tune-reliability` automate this. See `engine-tuning.md`.
