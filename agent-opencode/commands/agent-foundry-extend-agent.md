---
description: Extend a deployed agent — add a tool, skill, or behavior; re-run evals and smoke before re-releasing.
agent: build
---

Extend the agent at `$ARGUMENTS` with a new tool, skill, or behavior.
Uses the same build→eval→smoke→ship gates as a new agent, but
scoped to the addition.

Load `agent-deployment` (especially `tweaking-live-agents.md`,
`versioning-rollout.md`) and `agent-evals`. Process:

1. **Scope the extension.** Name the single capability being added:
   - A new tool (or MCP server registration).
   - A new skill (procedural knowledge the agent should load).
   - A new behavior (system-prompt or instruction change).
   - A widened authority (escalation tier change).

   One extension per run. Do not batch — every batched change
   complicates rollback and eval triage.

2. **Survey existing extensions first.** Check whether the capability
   already exists in the agent's skills, in a sibling plugin, or as
   an MCP server. Extending an existing surface beats creating a new
   one.

3. **Update `.foundry/design.md` first.** The design is the source of
   truth. Tools table gets a new row; Authority table gets an
   updated entry; Failure modes get the new failure paths. Widening
   authority requires explicit user approval before proceeding.

4. **Implement via the right framework primitive.** See
   `framework-build-matrix.md` for how each framework adds tools,
   changes authority, and registers skills. For OpenCode: add the
   tool under `mcp` config or register it via the plugin; for Hermes:
   edit `config.yaml`; for LangGraph: add a node or extend the
   tool list.

5. **Add eval cases BEFORE the eval suite re-runs.**
   - One capability case per new tool (proves the tool works).
   - One governance case per new authority row (proves the gate holds).
   - One regression case per known past bug class the extension
     might reintroduce.

6. **Run the full eval suite, not just the new cases.** Extensions
   can break adjacent behavior — the new tool can distract the model,
   the new authority can shift routing. The full suite catches that.

7. **Run `/agent-foundry-smoke-test`.** All Standard 8 steps must
   pass against the extended agent.

8. **Canary the extension.** Ship via the canary path in
   `versioning-rollout.md`. Watch the eval dashboard for drift in
   unrelated areas (a sign of context-window crowding or routing
   shift).

9. **Write back state.** Update `.foundry/state.json` with the
   extension's ship date and version. Update the changelog.

Anti-patterns:
- "Just one more tool" creep. Each addition is context cost + attack
  surface. The cost of N+1 is more than N.
- Authority widening "temporarily." There is nothing more permanent
  than a temporary permission grant. Fix the routing instead.
- Skipping the eval suite because the change is small. Small changes
  break adjacent behavior all the time.

Report: what was extended, the eval delta (new cases + any drift in
existing cases), the smoke verdict, and the canary status.