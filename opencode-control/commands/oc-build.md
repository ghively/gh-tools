---
description: Build something for opencode the right way — agent, command, plugin, workflow, or config (using real ecosystem patterns)
---

Build this for opencode: **$ARGUMENTS**

First read `references/ecosystem-and-recipes.md` (real-world patterns, plugin cookbook,
orchestration recipes, security gotchas) and the relevant one of `agents-and-workflows.md`
/ `configuring-opencode.md`. Then:

1. **Classify** what's being built: an agent/subagent, a custom command, a skill, a plugin
   (JS/TS hooks or a custom tool), a multi-agent workflow/orchestration, or a config/model-
   routing change. Ask only if genuinely ambiguous.
2. **Design using proven patterns**, not from scratch:
   - Agents → narrowest permissions (read-only reviewers get `edit:deny` + git-only bash
     allowlist; glob-scoped writes for docs/test agents), temperature by role, a trigger-
     shaped `description`. Route models per role (cheap for search/review).
   - Orchestration → pick a real shape (coordinator/worker, plan→build gate, adversarial
     consensus) and **respect the permission-security gotchas** (task perms don't propagate;
     never `task: allow` globally; scope `task` to named subagents).
   - Plugins → one default export, self-contained imports, the correct hook (one `event`
     hook you switch on; `tool.execute.before` throws to abort; `experimental.*` for MITM).
     Prefer a standalone `.opencode/tool/*.ts` file for a simple custom tool.
   - Commands → `$ARGUMENTS`/`$1`, `` !`shell` `` injection, `@file` refs; `subtask` to run
     in a subagent.
3. **Show the user** the proposed file(s)/config patch and the reasoning. On approval, write
   with the matching tool (`oc_agent_write` / `oc_command_write` / `oc_skill_write` /
   `oc_plugin_write` / `oc_config_update`), all `confirm=true`.
4. **Verify**: `oc_agents`/`oc_commands`/`oc_skills`/`oc_config_get` should reflect it; for
   an agent, optionally test it read-only via `oc_acp_prompt(mode=<agent>, permission=reject)`.
   Explain how to invoke what you built.
