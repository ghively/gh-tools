---
description: Re-verify design approval, build, evals, smoke, audit, safety floor, and operations, then return SHIP or DO-NOT-SHIP.
agent: build
---

Ship-check `$ARGUMENTS`. Re-verify live evidence for approved design, build
matching design, green eval baseline, current smoke pass, clean audit, installed
deterministic safety floor, and operational logging/rollback answers. Never
trust `.foundry/state.json` alone. Return SHIP only when all seven pass;
otherwise return DO-NOT-SHIP with exact remediation steps.
