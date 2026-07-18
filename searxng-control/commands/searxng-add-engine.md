---
description: Add and verify a custom search engine in SearXNG
argument-hint: what to add, e.g. "a JSON API at example.com/search" or "engine mojeek"
---

# Add a custom SearXNG engine

Use the `searxng` MCP tools. **Writes settings.yml** (confirm-gated, auto-backup,
applies on restart). Templates are in `references/settings-reference.md`.

1. **Clarify the engine** from `$ARGUMENTS`: is it (a) a built-in SearXNG engine
   that's just disabled (then use `searx_engine_toggle(name, disabled=False)`), or
   (b) a genuinely new engine — a JSON API, an HTML page (xpath), or another
   SearXNG instance?
2. **Check for a collision.** `searx_engine_show(<name>)` — if it exists, prefer
   toggling/editing over adding a duplicate.
3. **Build the block.** Pick `engine` (`json_engine` | `xpath` | `searxng_engine`
   | a built-in module), a unique `name`, a free `shortcut` (bang), `categories`,
   and the engine-specific `extra_yaml_json` (search_url, *_query/*_xpath, api_key,
   timeout…). See the templates in the settings reference.
4. **Add (confirm).** `searx_engine_add(name=…, engine=…, shortcut=…,
   categories=…, extra_yaml_json=…, confirm=True)` — after showing the user the
   exact block.
5. **Apply + test.** `searx_restart(confirm=True)`, then
   `searx_search("<test query>", engines="<name>")` and confirm results come from
   the new engine (`results[].engines` includes it). If it errors, check
   `searx_engine_errors` and `searx_logs`, fix the block, restart, retest.
6. **Rollback** via the printed backup / `searx_settings_restore` if it misbehaves.

Report: the block added, that it was applied and returned real results (or the
exact error and how you resolved it).
