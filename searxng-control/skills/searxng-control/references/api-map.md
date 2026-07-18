# SearXNG HTTP surface (live-enumerated, verified 2026.5.7)

SearXNG has **no OpenAPI document** — this is the hand-enumerated route map,
proven with live calls. Reach any of these with `searx_http(path, params_json,
method)`; the curated tools wrap the common ones.

## Routes

| Route | Methods | Returns | Notes |
|---|---|---|---|
| `/search` | GET, POST | html / json / csv / rss | The core endpoint. `format` param picks the shape (JSON must be enabled in `search.formats`). POST is used by the UI; GET works for the API. |
| `/autocompleter` | GET, POST | `application/x-suggestions+json` | `[term, [suggestions...]]`. Empty unless `search.autocomplete` names a backend. |
| `/config` | GET | JSON | Instance config: `version`, `categories[]`, `engines[]` (name/enabled/categories/shortcut), `plugins`, defaults. The engine inventory source. |
| `/stats` | GET | HTML | Per-engine reliability %, response times, result counts. `?engine=<name>` focuses one. |
| `/stats/errors` | GET | **JSON** | Per-engine error records: `exception_classname`, `filename`, `function`, `line_no`, `log_message`. The key diagnostic. |
| `/preferences` | GET, POST | HTML | User preferences. **Per-cookie, not global** — cannot set instance defaults here; use settings.yml. |
| `/healthz` | GET | text `OK` | Liveness probe. |
| `/opensearch.xml` | GET | XML | OpenSearch descriptor (browser search-engine add). |
| `/info/<locale>/<page>` | GET | HTML | Built-in docs, e.g. `/info/en/search-syntax`. |
| `/image_proxy` | GET | image | Requires `url` + `h` (HMAC) params; only when `server.image_proxy: true`. |
| `/` | GET | HTML | Search UI. |

Not present on this build (404): `/stats/checker` (the engine checker cron is
not enabled), `/clientip`, `/translations.js`.

## `/search` parameters (all verified)

| Param | Values | Meaning |
|---|---|---|
| `q` | string | Query. Supports bangs (`!bing test`, `!!` for first result), `site:`, etc. |
| `format` | `json` `csv` `rss` `html` | Output shape. JSON/CSV/RSS require the format to be listed in `search.formats`. |
| `categories` | `general,news,images,videos,it,science,files,music,map,...` | Comma list; restricts which engines run. |
| `engines` | e.g. `bing,mojeek` | Comma list; run ONLY these engines (overrides categories). Best lever for reliability. |
| `language` / `lang` | `en`, `en-US`, `all`, `auto` | Result language. |
| `pageno` | int | Page number (1-based). |
| `time_range` | `day` `week` `month` `year` | Recency filter (engine-dependent). |
| `safesearch` | `0` `1` `2` | Off / moderate / strict. |
| `theme` | `simple` | UI theme (html only). |
| `enabled_plugins` / `disabled_plugins` | plugin ids | Per-request plugin toggles. |

### JSON response shape
```
{ "query", "number_of_results" (often 0 — unreliable; use len(results)),
  "results":[{ "url","title","content","engine","engines":[..],"score","category",
               "publishedDate","thumbnail"? }],
  "answers":[], "corrections":[], "infoboxes":[], "suggestions":[],
  "unresponsive_engines":[["engine","reason"]] }
```
`unresponsive_engines` tells you which engines failed *this* request (CAPTCHA,
"too many requests", timeout). `number_of_results` is frequently `0` even when
`results` is populated — **count `results`, not that field.**

## Conventions & quirks

- **Auth:** none on the HTTP API (open on the trusted tailnet). The config layer
  authenticates by SSH key to the host + `docker exec` (container runs as root).
- **Config layer:** SearXNG exposes **no API to change configuration.** All tuning
  is `settings.yml` + restart. The MCP config tools do this over SSH.
- **JSON must be enabled:** `format=json` 404s/HTML-errors unless `json` is in
  `search.formats` (it is here). CSV/RSS likewise.
- **Bot limiter:** `server.limiter: true` (needs Valkey/Redis) rate-limits
  *clients*; it is **off** here, so empty results are upstream-engine suspensions,
  not the limiter throttling you.
- **Engine suspension:** on repeated failures an engine is benched for
  `search.suspended_times` (Captcha 3600s, cf_Captcha 1296000s, TooManyRequests
  180s, AccessDenied 180s). This is the mechanism behind "it worked, then went
  empty."
- **Errors** surface as `unresponsive_engines` per-request and aggregate under
  `/stats/errors`. There is no global error code vocabulary beyond the SearXNG
  exception classes (`SearxEngineCaptchaException`,
  `SearxEngineTooManyRequestsException`, `SearxEngineAccessDeniedException`,
  timeouts, `httpx.*`).
