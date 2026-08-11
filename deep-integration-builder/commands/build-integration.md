---
description: Build a deep, fully-tested control integration (MCP + skill + workflows) for a system with an API
argument-hint: the system to integrate, e.g. "my UniFi controller at 10.0.0.1" or "the Todoist API"
---

# Build a deep integration

Use the **building-deep-integrations** skill to build a comprehensive control
integration for: **$ARGUMENTS**

Follow the skill's phases in order — do not skip to coding:

1. **Connect & prove conventions** — reach the system, enumerate its FULL API/capability
   surface from the system itself, and prove auth + call conventions with live calls
   before writing a client. Keep secrets out of committed files.
2. **Two-layer architecture** — a generic passthrough (reaches everything) + curated
   tools (ergonomic common jobs), packaged as a plugin (self-provisioning MCP server,
   control skill, workflow commands).
3. **Build + verify each tool against the live system** — reads for real; write methods
   probed safely (no mutation).
4. **Systematic gap audit** — sweep every domain; sort findings into Works / Fixable /
   Hard-limit and show the user the table.
5. **Close fixable gaps** — check the gotcha list (version-specific methods, CSRF/
   elevation tokens, dependency-gated APIs, hidden APIs, wrong entity names).
6. **Reverse-engineer undocumented parts** from the UI's own traffic when guessing fails.
7. **Safety** — confirm-gate writes; never self-run live writes; verify writes reversibly
   with the user's go-ahead; report honestly (built vs. verified vs. hard limit).
8. **Publish to gh-tools** — every finished integration ships to the
   `ghively/gh-tools` repo (see the skill's Phase 7): plugin in its own
   subdirectory, entry in `.claude-plugin/marketplace.json`, refresh the Hermes
   `skills/` mirror (`scripts/sync_hermes_skills.py`), commit + push,
   refresh the local marketplace clone, and hand-place the git-ignored
   `config.local.json` into the installed plugin root. Do NOT scatter
   integrations into other repos or leave them unpublished.

Remember the core principle: **"covered" means the operation actually works for the
user, not that an API exists for it.** Be honest about the edges.
