# Writing SearXNG engines — the complete knowledgebase

How to add **any search resource** to SearXNG. Grounded in a recent SearXNG release
source (`/usr/local/searxng/searx/engines/`), which ships every engine as a
worked example. Official reference: https://docs.searxng.org/dev/engines/index.html

There are **two paths**:

| Path | Code? | Use when |
|---|---|---|
| **Generic engine** (config-only) | none — just `settings.yml` | The source is a JSON/REST API, an HTML page, a SQL/NoSQL DB, a shell command, a MediaWiki, or another SearXNG. This covers most needs and the `searx_engine_add` tool does it live. |
| **Python engine module** | a `.py` in `searx/engines/` | The source needs custom request signing, pagination math, HTML/JSON shaping, auth flows, or a non-standard protocol. Deploy with `searx_engine_module_deploy`. |

---

## Part 1 — "All search resources": the generic engine types

Every generic engine is `engine: <type>` in `settings.yml` plus type-specific
keys. Add them with `searx_engine_add(name, engine, shortcut, categories,
extra_yaml_json)` → restart → test with `searx_search(q, engines="<name>")`.

### 1. `json_engine` — any JSON/REST search API
Request keys: `search_url` (with `{query}`, `{pageno}` placeholders), `method`,
`request_body`, `headers`, `cookies`, `lang_all`, `soft_max_redirects`.
Paging: `paging`, `page_size`, `first_page_num`.
Time range: `time_range_support`, `time_range_url`, `time_range_map`.
Safe search: `safe_search_support`, `safe_search_map`.
JSON extraction (dotted/space paths into the response):
`results_query` (the array), `url_query`, `url_prefix`, `title_query`,
`content_query`, `thumbnail_query`, `thumbnail_prefix`, `suggestion_query`.
Post-process: `title_html_to_text`, `content_html_to_text`, `no_result_for_http_status`.

```yaml
- name: mdn
  engine: json_engine
  paging: true
  search_url: https://developer.mozilla.org/api/v1/search?q={query}&page={pageno}
  results_query: documents
  url_query: mdn_url
  url_prefix: https://developer.mozilla.org
  title_query: title
  content_query: summary
  shortcut: mdn
  categories: [it]
```
**Another SearXNG instance** is just a JSON engine against its `/search?format=json`
(`results_query: results`, `url_query: url`, `title_query: title`,
`content_query: content`).

### 2. `xpath` — scrape any HTML page
Same Request/Paging/Time/Safe keys as `json_engine`, plus XPath selectors:
`results_xpath` (rows), `url_xpath`, `title_xpath`, `content_xpath`,
`thumbnail_xpath`, `suggestion_xpath`.
```yaml
- name: bitbucket
  engine: xpath
  paging: true
  search_url: https://bitbucket.org/repo/all/{pageno}?name={query}
  url_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]/@href
  title_xpath: //article[@class="repo-summary"]//a[@class="repo-link"]
  content_xpath: //article[@class="repo-summary"]/p
  shortcut: bb
```

### 3. `command` — run a local shell command as a search
Keys: `command` (list; `{{QUERY}}` = user terms), `delimiter` ({`char`, `keys`}),
`parse_regex` (dict of key→regex), `query_type` (`path`|`enum`), `query_enum`,
`working_dir`, `result_separator`. **Security:** gate with `tokens` (private
engine) — it runs shell commands. Example: `['find', '/data', '-name', '*{{QUERY}}*']`.

### 4. SQL engines — `mysql_server`, `postgresql`, `sqlite`
Keys: `database`, `username`/`password`/`host`/`port` (server ones),
`query_str` (SQL with `:query` bind), `limit`, `paging`,
`result_type: MainResult | KeyValue` (MainResult → url/title/content columns;
KeyValue → shows all columns). `sqlite` needs only a file `database` path.
```yaml
- name: mydb
  engine: sqlite
  database: /data/index.db
  query_str: 'SELECT title, url, snippet AS content FROM docs WHERE body LIKE :query LIMIT 10'
  result_type: MainResult
  shortcut: db
  disabled: false
```

### 5. NoSQL — `mongodb`, `elasticsearch`
`mongodb`: `host`/`port`/`database`/`collection`/`key` (+ `exact_match_only`).
`elasticsearch`: `base_url`/`index`/`username`/`password`/`query_type`
(`match`/`simple_query_string`/`term`/`terms`/`custom`)/`custom_query_json`.

### 6. `mediawiki` — any MediaWiki (`w/api.php`)
Keys: `base_url` (`https://{language}.example.org/`), `api_path` (`w/api.php`),
`search_type` (`nearmatch`|`text`|`title`), `number_of_results`, `categories`,
`paging`. Point it at any wiki running MediaWiki.

---

## Part 2 — Python engine modules (full control)

A module is a `.py` in `searx/engines/` exposing module-level attributes and
two functions. Minimal real example (`github.py`, trimmed):

```python
from urllib.parse import urlencode
from dateutil import parser

about = {                       # metadata (shown in /preferences, docs)
    "website": "https://github.com/", "use_official_api": True,
    "require_api_key": False, "results": "JSON",
}
categories = ["it", "repos"]    # which category tabs it appears under
search_url = "https://api.github.com/search/repositories?sort=stars&{query}"

def request(query, params):
    # build the outgoing HTTP request by mutating `params`
    params["url"] = search_url.format(query=urlencode({"q": query}))
    params["headers"]["Accept"] = "application/vnd.github.preview.text-match+json"
    return params

def response(resp):
    # parse the HTTP response into a list of result dicts
    results = []
    for item in resp.json().get("items", []):
        results.append({
            "template": "packages.html",
            "url": item["html_url"], "title": item["full_name"],
            "content": item.get("description") or "",
            "thumbnail": item.get("owner", {}).get("avatar_url"),
            "package_name": item.get("name"),
            "publishedDate": parser.parse(item["updated_at"]),
            "popularity": item.get("stargazers_count"),
        })
    return results
```

### Module attributes (defaults from `ENGINE_DEFAULT_ARGS`)
`engine_type` (`online` default | `offline` | `online_currency` |
`online_dictionary` | `online_url_search`), `categories` (`["general"]`),
`paging` (False), `time_range_support` (False), `safesearch` (False),
`enable_http` (False — https only), `shortcut` (`-`), `timeout`
(outgoing.request_timeout), `disabled`, `inactive`, `display_error_messages`,
`about` ({}), and optional `weight`, `send_accept_language_header`, `language_support`.

### `request(query, params)` — the params dict you fill in
`url` (required), `method` (`GET`/`POST`), `headers` (dict), `data` (form),
`json` (JSON body), `content` (binary), `cookies`, `allow_redirects`,
`max_redirects`, `soft_max_redirects`, `verify`, plus read-only inputs already
set: `params['pageno']`, `params['time_range']`, `params['safesearch']`,
`params['searxng_locale']`, `params['language']`. For `offline` engines there's
no HTTP — do the work in `request`/`response` directly (DB/file/command).

### `response(resp)` → list of result dicts
`resp` is an httpx response (`.text`, `.json()`, `.url`). Return a list of dicts.
You may also append special items: `{"suggestion": "..."}`,
`{"answer": "...", "url": ...}`, `{"correction": "..."}`,
`{"infobox": ..., "urls": [...]}`, `{"number_of_results": N}`.

### Optional hooks
`init(engine_settings)` — one-time setup at load. `fetch_traits(engine_traits)` —
populate supported languages/regions (run via `searxng-manage`/CI, cached in
`searx/data/engine_traits.json`).

---

## Part 3 — The result dict schema (what a result can carry)

Common keys: `url`, `title`, `content`, `template` (default `default.html`),
`thumbnail`, `publishedDate` (a `datetime`), `metadata`, `priority`
(`high`/`low`), `engine` (auto-set).

**Result templates** (`template:` value) and their extra keys — pick the one that
fits the source:

| template | For | Extra keys |
|---|---|---|
| `default.html` | web results | (the common keys) |
| `images.html` | image search | `img_src`, `thumbnail_src`, `resolution`, `img_format`, `source` |
| `videos.html` | video search | `iframe_src` or `url`, `thumbnail`, `length`, `author`, `views` |
| `torrent.html` | torrents | `magnetlink`, `torrentfile`, `seed`, `leech`, `filesize`, `files` |
| `map.html` | places | `latitude`, `longitude`, `boundingbox`, `geojson`, `address` |
| `paper.html` | scholarly | `authors`, `journal`, `doi`, `publishedDate`, `pdf_url`, `comments`, `tags` |
| `packages.html` | software pkgs | `package_name`, `version`, `maintainer`, `license_name`, `license_url`, `homepage`, `source_code_url`, `popularity`, `tags` |
| `products.html` | shopping | `price`, `shipping`, `source_country`, `thumbnail` |
| `code.html` | code snippets | `codelines`, `code_language`, `repository` |
| `file.html` | files | `filename`, `size`, `time`, `mtype`, `subtype`, `abstract` |
| `keyvalue.html` | tabular/DB rows | any dict — rendered as a key/value table |

---

## Part 4 — settings.yml engine keys (every engine)

`name` (unique), `engine` (module/generic type), `shortcut` (bang, e.g. `!gh`),
`categories` (list), `disabled` (off by default; still usable via bang/`engines=`),
`inactive` (fully off), `timeout` (override), `weight` (ranking multiplier, default
1), `enable_http`, `display_error_messages`, `about` (metadata), and engine-specific
keys. **Private engine:** add `tokens: ['secret']` — the engine only runs when the
request carries a matching token (essential for `command`/SQL engines).

---

## Part 5 — The dev loop with this plugin

1. **Config-only engine:** `searx_engine_add(name, engine, shortcut, categories,
   extra_yaml_json='{...}')` → `searx_restart(confirm=True)` →
   `searx_search("test", engines="<name>")`. If it errors: `searx_engine_errors`
   + `searx_logs`, fix with `searx_engine_show`/`searx_setting_set`, restart, retest.
2. **Python module:** `searx_engine_module_deploy(module_name, python_code,
   register_name, shortcut, categories, confirm=True)` — writes
   `searx/engines/<module_name>.py` into the container, adds the settings entry,
   and (with apply) restarts. Then test as above. Roll back with the printed
   backup / `searx_settings_restore` and delete the module.
3. **Always verify live:** a result whose `engines` list includes your engine name
   is proof it works. `number_of_results` alone is unreliable.

## References
- Engine dev guide: https://docs.searxng.org/dev/engines/index.html
- Generic engines: https://docs.searxng.org/dev/engines/generic/index.html
- Online engines API: https://docs.searxng.org/dev/engines/online/index.html
- Result types/templates: https://docs.searxng.org/dev/result_types/index.html
- Every built-in engine is a worked example in `searx/engines/*.py` (read via
  `searx_logs`-adjacent SSH, or the GitHub mirror).
