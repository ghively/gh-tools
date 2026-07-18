---
description: Tune SearXNG engines/timeouts for reliable results (esp. on a datacenter IP)
argument-hint: (optional) "aggressive" to also disable the CAPTCHA trio
---

# Tune SearXNG for reliability

Use the `searxng` MCP tools. This **writes settings.yml** — every change is
confirm-gated and auto-backed-up, and applies on restart. **Confirm the plan with
the user before any `confirm=True` call.** Follow `references/engine-tuning.md`.

1. **Baseline (read).** `searx_engine_errors` + `searx_engines(failing=True)` +
   `searx_settings_read(section="outgoing")`. Show the user the current failing
   set and the plan.
2. **Propose the change set** (state it, get a yes):
   - Enable reliable independents: `searx_engine_toggle("mojeek", disabled=False)`,
     `searx_engine_toggle("mwmbl", disabled=False)` (and any others that fit).
   - Raise robustness: `searx_setting_set("outgoing.request_timeout", "6.0")`,
     `searx_setting_set("outgoing.retries", "1")`.
   - If `$ARGUMENTS` = "aggressive": disable the chronic CAPTCHA offenders —
     `searx_engine_toggle("duckduckgo", disabled=True)`,
     `searx_engine_toggle("startpage", disabled=True)` (keep bing + brave).
3. **Apply once.** Make all edits with `apply=False`, then a single
   `searx_restart(confirm=True)` (note the brief downtime).
4. **Verify.** After restart, `searx_status` (probe results > 0) and a couple of
   real `searx_search` calls across categories. Report before/after result counts.
5. **Rollback path.** Every write printed a backup path; `searx_settings_backups`
   lists them, `searx_settings_restore(<path>, confirm=True)` reverts. Tell the
   user how to undo.

Report honestly: what changed, that it was applied + re-verified, and the
before/after result counts.
