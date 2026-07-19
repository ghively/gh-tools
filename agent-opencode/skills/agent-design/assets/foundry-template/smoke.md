# Smoke Test Record

<!-- This file is written by /agent-foundry-smoke-test and read by
     /agent-foundry-ship-check. It is the durable evidence that the
     Standard 8 sequence passed against the built agent. Stale passes
     are failures — re-run if the file's date predates the last code
     change (git log the project). -->

**Agent:** <name from .foundry/design.md>
**Version:** <git SHA or release tag>
**Date:** <YYYY-MM-DD HH:MM TZ>
**Runner:** <who/what ran the sequence — human session, CI job ID>
**Verdict:** <ALL-PASS | FAIL-AT-STEP-N>

## The Standard 8

For each step: PASS or FAIL with the concrete command or prompt used
and the observed evidence. Cite file:line where the behavior lives.

| # | Step | Verdict | Evidence |
|---|---|---|---|
| 1 | Reachability — invoke on the intended surface | PASS | <how invoked, what responded> |
| 2 | Context inspection — only intended rules and memory in context | PASS | <command/prompt that dumped context, what was/wasn't there> |
| 3 | Tool inventory — expected tools and authority reported | PASS | <tool list the agent reported, match against design.md Tools table> |
| 4 | Read path — harmless read/query succeeds | PASS | <the query, the result summary> |
| 5 | Write path — low-risk write drafted and verified | PASS | <the change, the verification> |
| 6 | Escalation path — asks before high-impact action | PASS | <the destructive probe, the approval prompt observed> |
| 7 | Failure path — tool error handled without loop or fabrication | PASS | <the injected failure, the agent's response> |
| 8 | Persistence path — state survives session restart | PASS | <fact written, session restarted, fact recovered> |

## Additions Beyond the Standard 8

<If `design.md` named smoke additions beyond the Standard 8 — one row
per addition, same shape. Common additions: persona/voice match for
character agents, multi-turn coherence, tool-result size handling,
streaming first-token latency, HITL approval timeout.>

| Name | Verdict | Evidence |
|---|---|---|
| ... | PASS | ... |

## Failures (if any)

For each FAIL: step number, what was expected, what happened, the
smallest fix that resolves it, and whether that fix re-runs the
eval suite (it should — anything that changes behavior re-runs evals).

## Run Record

<The trajectory JSON or run-record artifact path. CI runs upload this
as an artifact; interactive runs record the session ID.>

- **Session/artifact:** <path or ID>
- **Token cost:** <if captured>
- **Wall clock:** <if captured>
