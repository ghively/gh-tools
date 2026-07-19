---
description: Author a least-privilege OpenCode subagent with explicit mode, permissions, prompt defense, and output contract.
agent: build
---

Create an OpenCode subagent for `$ARGUMENTS`. Challenge whether a skill or
inline work is better first. Write `.opencode/agents/<name>.md` or the global
`~/.config/opencode/agents/<name>.md` with `description`, `mode: subagent`, an
explicit `permission` policy, prompt-defense baseline, mission, non-goals,
method, and output contract. Use `read/glob/grep` for read-only work; keep
`edit` denied and `bash` ask unless execution is essential. Do not use Claude
`tools:`, `permissionMode`, `.claude/agents`, or plugin-only fields.
