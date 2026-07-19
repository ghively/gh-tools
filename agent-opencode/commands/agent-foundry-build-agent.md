---
description: Build an agent only from an approved .foundry/design.md, including tools, authority enforcement, evals, and a pinned baseline.
agent: build
---

Build the agent at `$ARGUMENTS` or the current project. Read `.foundry/design.md`.
If missing or marked draft, stop and direct the user to `/agent-foundry-design-agent`.

Implement the design exactly: scaffold the selected framework, wire only the
listed tools, enforce authority with OpenCode permissions and deterministic
safety code where required, create the `agent-evals` suite, run it, and record
the baseline in `.foundry/`. Update state only with evidence; do not widen
authority without explicit approval.
