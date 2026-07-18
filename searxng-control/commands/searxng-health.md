---
description: Full health check of the SearXNG instance (liveness, probe search, engine failures, config layer)
argument-hint: (optional) focus area, e.g. "engines" or "images"
---

# SearXNG health check

Use the `searxng` MCP tools. Read-only. Lead with an overall verdict
(**Healthy / Degraded / Down**), then details.

1. `searx_status` — version, engine counts, and the **probe_search_results**
   number (the real signal: 0 = degraded even if the server is up).
2. `searx_health` — liveness + a probe search + suspended-engine summary.
3. `searx_engine_errors` — if any engines are failing, list them by exception
   class (CAPTCHA / TooManyRequests / AccessDenied / timeout).
4. `searx_engines(failing=True)` — the currently-suspended set; and
   `searx_engines(category="general", enabled_only=True)` — what default search
   leans on. Flag if the default set is dominated by failing engines.
5. Config layer: `searx_settings_read(section="search")` and `section="outgoing"`
   — note `request_timeout`, `formats`, `suspended_times`, `limiter`.
6. If `$ARGUMENTS` names a focus (engines/images/news), scope a `searx_search`
   in that category and report result counts per engine.

Close with the verdict and, if degraded, point to `/searxng-diagnose`.
Suggest fixes; do not change anything.
