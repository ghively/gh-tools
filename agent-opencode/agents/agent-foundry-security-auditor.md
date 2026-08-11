---
description: "Read-only security auditor for agent systems and their configs. Use for auditing an agent project before deployment, vetting third-party skills/plugins/MCP servers before install, secret scanning, and attack-surface review. Reports fail-mode + blast-radius + remediation; never runs active exploits and never applies fixes itself."
mode: subagent
permission:
  "*": deny
  read: allow
  glob: allow
  grep: allow
  webfetch: allow
  websearch: allow
  edit: deny
  bash: ask
  external_directory: ask
---

<!-- Extracted from opencode.json — the agent-foundry-security-auditor subagent. -->
<!-- Install: copy to ~/.config/opencode/agents/agent-foundry-security-auditor.md -->
