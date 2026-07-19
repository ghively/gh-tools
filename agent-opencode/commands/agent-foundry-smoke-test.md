---
description: Run the eight-step live smoke sequence for a built agent and record evidence in .foundry/smoke.md.
agent: build
---

Smoke-test the agent at `$ARGUMENTS`. Verify startup, tool connectivity,
permission gates, the happy path, error handling, edge cases, cleanup, and a
performance baseline. Record each PASS/FAIL with commands and evidence in
`.foundry/smoke.md`; do not call it green when any step is unverified.
