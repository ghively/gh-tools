---
description: Run the complete agent-foundry lifecycle from approved design through build, evals, smoke test, security audit, and release gate.
agent: build
---

Develop an agent for: $ARGUMENTS

Use `.foundry/state.json` as a resumable bookmark. Inspect it before starting
and resume at the first incomplete phase. Run the phases in order:

1. Design: conduct the design interview and write `.foundry/design.md`; stop for explicit approval.
2. Build: implement only from the approved design and create the eval baseline.
3. Smoke: run the eight-step live smoke sequence and write `.foundry/smoke.md`.
4. Audit: delegate read-only review to `agent-foundry-security-auditor` and write `.foundry/audit.md`.
5. Ship check: re-verify all criteria and return SHIP or DO-NOT-SHIP.

Do not skip approval gates or claim a phase passed without evidence.
