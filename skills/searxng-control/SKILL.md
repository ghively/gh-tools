---
name: searxng-control
description: Control, configure, tune, and diagnose a self-hosted SearXNG metasearch instance via the searxng MCP server. Use whenever the user wants to search through SearXNG, inspect or change its configuration (engines, limiter, outgoing/timeouts, UI, formats), add custom search engines, or troubleshoot it — especially "why are my SearXNG results empty", "tune SearXNG", "enable/disable an engine", "add a search engine", "SearXNG on arm-host". Drive the live server through the tools; do not answer from memory.
metadata:
  hermes:
    tags: [searxng, search, metasearch, self-hosted, privacy, mcp, homelab, web-search]
    category: infrastructure
    requires_tools: [searx_status]
    config:
      - {key: searxng.base_url, prompt: SearXNG base URL, default: "http://arm-host:8888"}
version: 0.2.1
author: ghively
---

# SearXNG control

Drive a self-hosted **SearXNG** metasearch instance through the `searxng` MCP
server. Verified live against a recent **SearXNG** release on arm-host. The server has
three layers; know which one a task needs:

1. **Runtime HTTP API** (read-only): search, autocomplete, `/config`, `/stats`,
   `/stats/errors`, health. Always available.
2. **Config management** (`settings.yml` over SSH): enable/disable engines, add
   custom engines, tune `outgoing`/`server`/`search`/`ui`, backup/restore,
   restart. Needs `ssh_host` + `container` in config. **Writes are confirm-gated
   and auto-backed-up; changes apply only on container restart.**
3. **Knowledge**: `references/` — the full HTTP surface, every settings.yml
   option, and the engine-reliability/CAPTCHA playbook.

## Start here

- `searx_status` — identity + a live probe search. The `probe_search_results`
  number is the real "is it working" signal (0 = degraded).
- `searx_endpoints` — the HTTP route map for the generic `searx_http` passthrough.

## Searching

- `searx_search(q, categories=, engines=, language=, time_range=, safesearch=,
  pageno=, fmt=, limit=)` — `fmt="json"` (default) returns `{url,title,content,engines}`
  for up to `limit` results (default 20, max 50).
  Scope to reliable engines with `engines="bing,mojeek"` when the defaults are
  degraded. `categories` = general/news/images/videos/it/science/…
- `searx_autocomplete(q)` — only returns suggestions if a backend is set
  (`search.autocomplete` in settings; empty by default → `[]`).

## The #1 issue: empty / degraded results

SearXNG aggregates public engines. When it runs from a **datacenter IP**
(arm-host is an Oracle Cloud VM), Google/DuckDuckGo/Brave/Startpage **CAPTCHA or
rate-limit** it, and SearXNG then **suspends** the engine — `search.suspended_times`:
CAPTCHA = **1 hour**, Cloudflare-CAPTCHA = **15 days**, TooManyRequests = 3 min.
With several defaults suspended, `results` collapses toward 0.

Diagnose → fix:
1. `searx_engine_errors` — shows exactly which engines are failing and the
   exception class (Captcha / TooManyRequests / AccessDenied / timeout).
2. `searx_engines(failing=True)` — the currently-failing set; `searx_engines(
   category="general", enabled_only=True)` — what the default search relies on.
3. **Fix** = shift the default set toward engines that tolerate datacenter IPs
   (**bing, mojeek, mwmbl, wikidata, wikipedia**, sometimes brave) and disable
   the chronic CAPTCHA offenders. See `references/engine-tuning.md`. Proven:
   `searx_search("x", engines="bing,mojeek")` returns full results even when the
   defaults are suspended.

## Configuring / tuning (writes)

All config lives in `settings.yml`; there is **no config API** — these tools edit
the file over SSH and a **restart applies it**. Every write needs `confirm=True`
and auto-creates a `settings.yml.bak.<ts>`.

- `searx_settings_read(section=)` — read any section (search/server/outgoing/
  ui/general/plugins/valkey/brand). `searx_engine_show(name)` — one engine's block.
- `searx_engine_toggle(name, disabled, confirm=True, apply=)` — enable/disable.
- `searx_engine_add(name, engine, shortcut, categories=, extra_yaml_json=,
  confirm=True)` — add a **config-only** engine (JSON API / xpath / SQL / command /
  mediawiki / another SearXNG). Templates in `references/settings-reference.md`.
- `searx_engine_module_deploy(module_name, python_code, register_name, shortcut,
  categories=, confirm=True)` / `searx_engine_module_remove(...)` — deploy/remove
  a **custom Python engine module** (for sources needing real code). The module
  is syntax-checked before registering. **Authoring guide: `references/writing-
  engines.md`** (the full engine knowledgebase — every generic type, the Python
  engine API, the result-dict schema, and result templates).
- `searx_setting_set(key_path, value, confirm=True)` — any scalar/list, e.g.
  `outgoing.request_timeout` `6.0`, `server.limiter` `true`,
  `search.autocomplete` `"duckduckgo"`, `search.formats` `["html","json","csv","rss"]`.
- `searx_settings_backups` / `searx_settings_restore(backup, confirm=True)`.
- `searx_restart(confirm=True)` — apply pending changes (brief downtime).

**Batching:** make several edits with `apply=False`, then one `searx_restart` —
avoids repeated downtime. Read the value back after restart to confirm it took.

## Safety rules

- **Confirm every write with the user first**, then pass `confirm=True`. State
  what changes and that a restart is needed.
- Prefer **reversible proofs**: the auto-backup + `searx_settings_restore` is your
  undo. For a risky change, note the backup path so you can roll back.
- `searx_restart` causes brief downtime — say so.
- Never put `server.secret_key` (or any secret) into chat summaries or files.
- Report honestly: "changed settings.yml + restarted + re-probed" is verified;
  "wrote the file, not yet restarted" is not yet live.

## References

- `references/api-map.md` — full HTTP surface, search params, response shapes, conventions.
- `references/settings-reference.md` — every settings.yml section & option, engine-block format, custom-engine templates.
- `references/engine-tuning.md` — the reliability/CAPTCHA playbook, datacenter-IP engine picks, limiter & outgoing tuning, proxies/Tor.
- `references/writing-engines.md` — **the engine-authoring knowledgebase**: all
  search-resource types (JSON API, HTML/xpath, SQL/NoSQL, command, MediaWiki,
  federated SearXNG), config-only vs Python-module paths, the request/response
  API, the full result-dict schema, and all 11 result templates — with worked
  examples from the live source and the dev loop using this plugin's tools.
