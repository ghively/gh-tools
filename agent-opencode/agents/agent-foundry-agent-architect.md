---
description: "Read-only agent-systems design specialist. Use when the user wants an agent system designed, an architecture reviewed, or a requirements interview conducted BEFORE any code is written — it produces a design document, never files or code. Delegate to it for "design an agent for X", "review this agent architecture", "what shape should this system be"."
mode: subagent
permission:
  *: deny
  read: allow
  glob: allow
  grep: allow
  webfetch: allow
  websearch: allow
  edit: deny
  bash: deny
  external_directory: ask
---

<!-- Extracted from opencode.json — the agent-foundry-agent-architect subagent. -->
<!-- Install: copy to ~/.config/opencode/agents/agent-foundry-agent-architect.md -->
