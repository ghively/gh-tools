# The Design Artifact Contract (`.foundry/`)

Load this when a foundry pipeline command (`/design-agent`, `/build-agent`,
`/smoke-test`, `/ship-check`, `/new-agent`) needs to read or write the
project's design state. This contract is what lets the pipeline stages hand
off to each other across sessions: the design lives in the *target project*,
not in anyone's conversation history.

## Layout

Inside the agent project being built:

```
.foundry/
├── design.md     # THE design artifact — single source of design truth
├── state.json    # pipeline progress record (machine-checkable)
├── smoke.md      # latest smoke-test run report (written by /smoke-test)
└── audit.md      # latest security-audit report (written by /security-audit-agent)
```

Commit `.foundry/` to the project's repo. It is documentation with teeth —
`/ship-check` reads all four files.

Fillable templates for design.md and state.json live in this skill's
`assets/foundry-template/` — copy them rather than reconstructing the
section list from memory.

## design.md format

Exactly the Minimal Design Artifact from the `agent-design` skill, plus a
status header. Every section heading is mandatory; "N/A — <reason>" is a
valid body, an absent section is not:

```markdown
# Design: <agent name>

Status: draft | approved <YYYY-MM-DD>
Designed with: /agent-foundry:design-agent (or "imported")

## Job
This agent's job is to ___ for ___ on ___.

## Users & surface
## Threat model
Who sends input, what is untrusted, worst acceptable outcome.

## Task split
Deterministic / bounded-reasoning / open-ended, per operation.

## Pattern
Chosen architecture and why (and the ladder rungs rejected below it).

## Tools
| Tool | Purpose | read/write | Sensitivity |

## Authority
| Action class | autonomous / report-after / escalate-before |

## State
What persists, where, how pruned.

## Failure modes
| Mode | Response | User-visible signal |

## Verification
Smoke-test additions, proof contract, eval seeds (governance cases come
from the Failure modes + Authority tables).

## Framework, model, deployment
Chosen LAST. Framework + rationale, model tier per role, deployment shape.
```

**The status line is load-bearing.** `/design-agent` writes `Status: draft`
and flips it to `approved <date>` only on the user's explicit approval.
`/build-agent` MUST refuse to build from a draft — the fix is finishing the
design conversation, not editing the status line by hand.

## state.json format

```json
{
  "design_approved": "2026-07-14",
  "built":           "2026-07-14",
  "evals_baselined": "2026-07-14",
  "smoke_passed":    null,
  "audit_clean":     null,
  "ship_checked":    null
}
```

Dates are set by the command that completed the stage; `null` = not done.
`/ship-check` does NOT trust this file — it re-verifies each claim (runs the
evals, reads smoke.md/audit.md, checks the floor is installed) and only then
updates `ship_checked`. state.json exists so any session can see where the
pipeline stands in one read, not as proof.

## Rules for consuming commands

1. **Read before asking.** A command that needs design facts (tool surface,
   authority, failure modes) reads design.md first and asks the user only
   about gaps.
2. **Write back what changed.** If the build forces a design change (a tool
   turns out infeasible, authority needs widening), update design.md in the
   same turn and tell the user — silent drift between design and code is the
   failure this file exists to prevent. Widening AUTHORITY always requires
   the user's explicit yes before the edit.
3. **One artifact, no copies.** Never write DESIGN-v2.md next to it. The git
   history of design.md is the design log.
4. **Imported projects.** For an agent that predates the pipeline,
   `/review-agent` can reconstruct the implicit design; save its
   reconstruction as design.md with `Status: draft` and let the user approve
   or amend it. That is the on-ramp for existing code.
