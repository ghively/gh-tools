# SearXNG engine reliability & CAPTCHA playbook

The single most common SearXNG problem: **searches return few or zero results.**
This is almost never "SearXNG is down" — it's upstream engines blocking the
instance's IP. This playbook diagnoses and fixes it. Grounded in live behavior on
arm-host (an Oracle Cloud aarch64 VM = **datacenter IP**).

## Why it happens

Public search engines fight scrapers. From a **datacenter/VPS IP**, Google,
DuckDuckGo, Brave, and Startpage return CAPTCHAs or 429s quickly. On each such
failure SearXNG **suspends** that engine for `search.suspended_times` —
**1 hour** for a CAPTCHA, **15 days** for a Cloudflare CAPTCHA, 3 min for
TooManyRequests. Under any real query volume several defaults suspend at once and
`results` drops toward 0. It "works for a few queries, then goes empty."

Residential IPs suffer far less; datacenter IPs suffer a lot. arm-host is a
datacenter IP, so **engine selection is the lever**, not raw uptime.

## Diagnose (read-only)

1. `searx_status` → look at `probe_search_results`. >0 = working now; 0 = degraded.
2. `searx_engine_errors` → which engines are failing and the exception class:
   - `SearxEngineCaptchaException` → benched 1h (15d if Cloudflare). Chronic on datacenter IPs: **duckduckgo, startpage, google**.
   - `SearxEngineTooManyRequestsException` → benched 3 min. Often **brave**.
   - `SearxEngineAccessDeniedException` → benched 3 min. e.g. **karmasearch**.
   - `httpx.*` / timeout → slow or unreachable; consider raising `outgoing.request_timeout`.
3. `searx_engines(category="general", enabled_only=True)` → what the default
   general search depends on. If that list is dominated by the CAPTCHA offenders,
   that's the problem.

## Fix — shift to datacenter-tolerant engines

**Verified on arm-host:** `searx_search("x", engines="bing,mojeek")` returns full
results even while duckduckgo/startpage/brave are suspended.

Engines that tolerate datacenter IPs well (enable / prefer these):
- **bing** — reliable, broad general results. The workhorse.
- **mojeek** — independent index, no CAPTCHA (disabled by default here → enable it).
- **mwmbl**, **marginalia** — independent, tolerant.
- **wikipedia / wikidata** — always fine (though wikipedia can 429 under bursts).
- **brave** — sometimes works (TooManyRequests, short bench) — keep but expect gaps.
- Category-specific: **qwant** (news), **bing images/videos/news**, **github/
  stackexchange** (it), **arxiv/pubmed/semantic scholar** (science).

Engines to disable (or accept as flaky) on a datacenter IP:
- **duckduckgo, startpage, google** — chronic CAPTCHA. Disabling them stops the
  1h/15d suspensions from dragging the default set down.

### Recommended tuning actions (each is `confirm=True`, then one restart)
```
searx_engine_toggle("mojeek",    disabled=False, confirm=True)   # enable a solid one
searx_engine_toggle("mwmbl",     disabled=False, confirm=True)
searx_engine_toggle("duckduckgo",disabled=True,  confirm=True)   # stop the CAPTCHA drag
searx_engine_toggle("startpage", disabled=True,  confirm=True)
searx_setting_set("outgoing.request_timeout", "6.0", confirm=True)  # fewer false timeouts
searx_setting_set("outgoing.retries", "1", confirm=True)           # one retry
searx_restart(confirm=True)                                        # apply all at once
```
Then re-probe: `searx_status` / `searx_search("news today")` — expect steady results.

## Deeper fixes (when engine selection isn't enough)

- **Proxy the outgoing traffic** off the datacenter IP. In `outgoing.proxies`
  point `all://` at a residential/SOCKS proxy; the CAPTCHA-prone engines then
  behave. (`searx_setting_set("outgoing.proxies", '{"all://":["socks5://…"]}',
  confirm=True)`.)
- **Tor** — `outgoing.using_tor_proxy: true` + a Tor SOCKS proxy. Helps some
  engines, hurts others (many block Tor exit nodes). Mixed.
- **Tune `suspended_times` down** so engines retry sooner — marginal; they just
  get re-blocked. Prefer disabling chronic offenders over shortening their bench.
- **Enable the bot limiter** (`server.limiter: true` + `valkey.url`) only if the
  instance is exposed beyond the tailnet; it protects *your* instance, it does
  not help with upstream blocks.

## Rule of thumb

On a datacenter IP: **lean on bing + mojeek + a couple of independents, disable
the CAPTCHA trio, give requests 6s and one retry.** That converts "empty half the
time" into "reliable, slightly less diverse." For maximum diversity you need a
residential IP or a proxy.
