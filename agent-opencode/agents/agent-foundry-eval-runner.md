---
description: "Runs eval suites, reports pass/fail with diagnosis. Use when executing golden eval tests, regression tests, or capability checks. Needs read + bash (to run the test command), but never writes to source unless explicitly asked to apply fixes."
mode: subagent
permission:
  *: deny
  read: allow
  glob: allow
  grep: allow
  edit: deny
  bash: ask
  external_directory: ask
---

<!-- Extracted from opencode.json — the agent-foundry-eval-runner subagent. -->
<!-- Install: copy to ~/.config/opencode/agents/agent-foundry-eval-runner.md -->
