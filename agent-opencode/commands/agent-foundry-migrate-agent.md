---
description: Migrate an agent from one framework to another — freeze behavior with evals, port one path at a time, re-run after each.
agent: build
---

Migrate the agent at `$ARGUMENTS` from its current framework to a new
one. The migration preserves behavior, not code: the design is
re-built on the new framework's primitives.

Load `framework-selection` (especially `framework-build-matrix.md`,
`framework-landscape.md`) and `agent-evals`. Process:

1. **Extract the stable design.** Read `.foundry/design.md` if it
   exists; otherwise reconstruct from code + prompts + config. The
   design (job, tools, authority, failure modes, evals) is
   framework-agnostic — that is what makes migration possible.

2. **Freeze behavior BEFORE porting.** Run the existing eval suite
   against the old framework; pin the baseline. Add cases for any
   behavior you observe that is not yet in the suite. The frozen
   baseline is the migration's success criterion.

3. **Pick the new framework.** Use `framework-build-matrix.md` to
   confirm the new framework implements every design primitive the
   old one did. Flag any gap as a migration risk; either accept it
   (with a documented reason) or pick a different target.

4. **Port one path at a time.** Start with the read-only tools and
   the simplest happy path. After each ported path:
   - Re-run the eval suite.
   - Compare to the frozen baseline.
   - Investigate any drift BEFORE porting the next path.

5. **Side-by-side.** Keep old and new systems running in parallel
   until outputs and tool trajectories are understood. Shadow traffic
   to the new framework; compare responses. Disagreements are signal,
   not noise.

6. **Delete dead abstractions AFTER parity, not before.** Old
   framework glue that's no longer called is a liability, but ripping
   it out mid-migration breaks your fallback path.

7. **Cut over via canary.** When the new framework holds the baseline
   for N days of shadow traffic, canary production traffic to it.
   Roll back on any regression. See `versioning-rollout.md`.

Common migration patterns:

- **LangGraph → CrewAI**: graph nodes become Crew tasks; conditional
  edges become `expected_output` validation; checkpointer → Flow state.
- **CrewAI → LangGraph**: crews become subgraphs; delegation becomes
  handoffs; Flow state → checkpointer.
- **Claude Agent SDK → OpenCode**: hooks → permission rules + plugin;
  `PreToolUse` → `tool.execute.before`; `.claude/` → `.opencode/`.
- **Any framework → custom loop**: extract the design; rebuild the 6
  loop steps; the eval suite is the acceptance gate.

Anti-pattern: line-by-line porting of framework glue. The new
framework has its own idioms — rebuild the design on them, not the
old framework's shape.

Report: the source and target frameworks, the frozen baseline, the
porting order, current progress (which paths ported, which pending),
and any accepted gaps.