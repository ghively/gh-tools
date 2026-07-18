---
description: Diagnose why SearXNG results are empty or degraded, and propose fixes
argument-hint: (optional) a query that's returning too little
---

# Diagnose empty / degraded SearXNG results

Use the `searxng` MCP tools. This is the "why are my results empty" workflow.
Read-only — end with a recommendation, don't change config unless the user then
asks (that's `/searxng-tune-reliability`).

1. **Reproduce.** `searx_search($ARGUMENTS or "news today")`. Note
   `number_of_results` and `unresponsive_engines`.
2. **Root cause.** `searx_engine_errors` — group failing engines by exception:
   - CAPTCHA / Cloudflare-CAPTCHA → benched 1h / 15d (datacenter-IP blocking).
   - TooManyRequests / AccessDenied → benched 3 min.
   - timeouts / httpx errors → slow or unreachable engines.
3. **Confirm it's engine-side, not the limiter.** `searx_settings_read(
   section="server")` → if `limiter: false`, empties are upstream suspensions.
4. **Prove the fix works.** `searx_search("<same query>", engines="bing,mojeek")`
   — if that returns full results, the instance is fine; the *default engine mix*
   is the problem (datacenter IP + CAPTCHA-prone defaults).
5. **Report** using the buckets from `references/engine-tuning.md`: which engines
   are chronically blocked, which reliable ones to enable/prefer, and whether a
   proxy is warranted. Offer to run `/searxng-tune-reliability` to apply it.
