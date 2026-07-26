# SearXNG `settings.yml` reference (grounded in the live 2026.5.7 config)

The complete control surface. On gh-arm it lives at `/etc/searxng/settings.yml`
(1981 lines) inside the `searxng` container (Docker volume `searxng-data`). Edit
with the `searx_setting_set` / `searx_engine_*` tools (they preserve comments and
auto-backup); **a container restart applies changes.** Top-level sections below,
with the values actually set on this instance.

> Never commit `server.secret_key` or any secret value.

## `general`
```
contact_url: false        # public contact link (false = hidden)
debug: false              # verbose logging (leave false in prod)
donation_url: false
enable_metrics: true      # per-engine timing/error stats (powers /stats, /stats/errors)
instance_name: SearXNG
privacypolicy_url: false
```

## `search`
```
autocomplete: ''          # '' = off. Set to a backend: google | duckduckgo |
                          #   brave | qwant | wikipedia | startpage | mwmbl | ...
autocomplete_min: 4       # min chars before autocomplete fires
default_lang: auto        # default result language ('' | auto | en | en-US | all)
favicon_resolver: ''      # favicon proxy backend ('' = off)
formats:                  # which output formats /search will emit
  - html
  - json                  # ADD csv, rss here to enable those API formats
ban_time_on_fail: 5       # base seconds an engine is banned after a failure
max_ban_time_on_fail: 120 # cap for the escalating ban
safe_search: 0            # 0 off | 1 moderate | 2 strict
suspended_times:          # how long a suspended engine stays benched (SECONDS)
  SearxEngineCaptcha: 3600            # 1 hour
  SearxEngineTooManyRequests: 180
  SearxEngineAccessDenied: 180
  cf_SearxEngineCaptcha: 1296000      # Cloudflare CAPTCHA = 15 days
  cf_SearxEngineAccessDenied: 86400
  recaptcha_SearxEngineCaptcha: 604800
```
`suspended_times` is central to reliability tuning — see `engine-tuning.md`.

## `server`
```
base_url: false           # set to the public URL if behind a reverse proxy
bind_address: 127.0.0.1   # app bind (container-internal; Docker maps 8888→8080/here)
port: 8888
method: POST              # default form method for the UI
http_protocol_version: '1.0'
image_proxy: false        # proxy result images through SearXNG (privacy; costs CPU)
limiter: false            # bot/rate limiter for CLIENTS (needs valkey.url). OFF here.
public_instance: false    # extra hardening for public instances
secret_key: <redacted>    # REQUIRED, must be unique/secret. Never commit.
default_http_headers:     # security headers added to every response
  Referrer-Policy: no-referrer
  X-Content-Type-Options: nosniff
  X-Download-Options: noopen
  X-Robots-Tag: noindex, nofollow
```

## `ui`
```
default_theme: simple
theme_args: { simple_style: auto }   # auto | light | dark
center_alignment: false
default_locale: ''                   # UI language ('' = browser)
hotkeys: default                     # default | vim
query_in_title: false
search_on_category_select: true
url_formatting: pretty               # pretty | full | host
static_path: ''  templates_path: ''  # custom asset overrides
```

## `outgoing` (how SearXNG fetches from engines — key for reliability)
```
request_timeout: 3.0      # seconds per engine request. 3.0 is aggressive; 6–10
                          #   catches slow engines (fewer false timeouts).
enable_http2: true
pool_connections: 100     # total connection pool
pool_maxsize: 20          # per-host pool
useragent_suffix: ''
# Not set here but available & useful on datacenter IPs:
# retries: 1              # retry a failed engine request
# max_redirects: 30
# proxies:                # route engine traffic through a proxy (dodge IP blocks)
#   all://:
#     - socks5://user:pass@host:port
# using_tor_proxy: true   # route via Tor (with proxies to the Tor SOCKS port)
# source_ips: [ ... ]     # rotate outgoing source IPs
```

## `engines` (list — the biggest section)
Each engine is a list item. Live example (mojeek, disabled by default):
```
- name: mojeek
  engine: mojeek          # the engine module in searx/engines/
  shortcut: mjk           # bang prefix: !mjk
  categories: [general, web]
  disabled: true          # true = off by default (still usable via !bang / engines=)
```
Common per-engine keys: `name`, `engine`, `shortcut`, `categories`, `disabled`,
`timeout` (override outgoing.request_timeout), `weight` (result ranking boost),
`tokens` (private-engine access tokens), `about`, plus engine-specific keys
(`base_url`, `api_key`, `search_type`, …).

This instance: **249 engines, 93 enabled by default.** Toggle with
`searx_engine_toggle(name, disabled=…)`; inspect one with `searx_engine_show`.

### Custom engine templates (for `searx_engine_add` → `extra_yaml_json`)

**JSON API engine** (any REST search API returning JSON):
```json
{ "search_url": "https://api.example.com/search?q={query}&format=json",
  "results_query": "results",
  "url_query": "url", "title_query": "title", "content_query": "snippet",
  "paging": false, "timeout": 5.0 }
```
with `engine="json_engine"`.

**XPath (HTML scrape) engine:**
```json
{ "search_url": "https://example.com/search?q={query}",
  "results_xpath": "//div[@class='result']",
  "url_xpath": ".//a/@href", "title_xpath": ".//a", "content_xpath": ".//p",
  "timeout": 5.0 }
```
with `engine="xpath"`.

**Another SearXNG instance** (federate): `engine="searxng_engine"`,
extra `{ "base_url": "https://other.searxng/", "timeout": 6.0 }`.

Full engine catalog & keys: https://docs.searxng.org/dev/engines/index.html

## `plugins`
Each `searx.plugins.<x>.SXNGPlugin: { active: bool }`. Active here: calculator,
hash, hostnames, self_info, time_zone, unit_converter, tracker_url_remover,
ahmia_filter. Inactive: infinite_scroll, oa_doi_rewrite, tor_check. Toggle with
`searx_setting_set("plugins.searx.plugins.<x>.SXNGPlugin.active", true)`.

## `categories_as_tabs`
Which categories render as UI tabs (general, images, videos, news, map, music,
it, science, files, social media here). Cosmetic.

## `doi_resolvers` / `default_doi_resolver`
Open-access DOI rewriting (oadoi.org default; doi.org, sci-hub.* available).

## `valkey`
```
url: false                # Valkey/Redis URL. Required by server.limiter and some
                          # rate-limited engines. OFF here (no limiter).
```

## `brand`
docs_url / issue_url / public_instances / wiki_url — footer links.
