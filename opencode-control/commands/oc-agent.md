---
description: Design and author an opencode agent or subagent — $ARGUMENTS describes the role
---

Design and create an opencode agent for: **$ARGUMENTS**

Read `references/agents-and-workflows.md` first. Then:

1. Clarify the role if needed: is it a **primary** agent (talk to directly) or a
   **subagent** (specialist invoked via Task/@)? What should it be allowed to do?
2. Choose a tight, honest design:
   - `description` — a precise trigger describing when to use it.
   - `mode` — primary | subagent | all.
   - `model` — pick appropriately (cheap model for read-only/search roles, capable model
     for implementation). Check `oc_models` for what's available.
   - `permission`/`tools` — narrowest that fits (a reviewer/explorer gets `edit: deny`,
     `bash: deny` or a git-only allowlist).
   - `temperature` — low for analytical/deterministic roles.
   - the prompt body — clear operating instructions.
3. Show the user the proposed agent file (frontmatter + prompt).
4. On approval, `oc_agent_write(..., scope=<global|project>, confirm=true)`.
5. Verify: `oc_agents` should now list it. Explain how to invoke it (Tab to cycle for
   primary, `@<name>` or Task for subagent).
