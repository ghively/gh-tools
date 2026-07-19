---
description: Build an agent only from an approved .foundry/design.md, including tools, authority enforcement, evals, and a pinned baseline.
agent: build
---

Build the agent at `$ARGUMENTS` or the current project. Read `.foundry/design.md`.
If missing or marked draft, stop and direct the user to `/agent-foundry-design-agent`.

Implement the design exactly, dispatching to the framework named in design.md:

1. **Scaffold the framework.** Load the `framework-selection` skill's
   `framework-build-matrix.md` reference. Find the row matching the
   design's Framework section. Copy the per-framework scaffold pattern
   (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF,
   LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI
   SDK, Mastra, or custom loop). Use the matching starter asset under
   `framework-selection/assets/` if one ships (Claude Agent SDK,
   LangGraph); otherwise copy the code block from the build matrix.
2. **Wire only the listed tools.** Translate the design's Tools table
   into the framework's tool primitive (`@tool` decorator, `tools=[]`
   list, `FunctionTool`, etc.). Do not add tools the design did not
   name.
3. **Enforce authority.** Translate the design's Authority table into
   the framework's permission primitive. Use the framework's native
   mechanism first (permission mode, conditional edges, typed `Deps`,
   pre-tool hooks) and add the agent-foundry safety floor beneath it
   for the never-run primitives. See the `agent-safety` skill's
   `framework-safety-matrix.md` for the per-framework enforcement
   patterns.
4. **Generate the eval suite.** Copy the `agent-evals` skill's
   `assets/eval-suite-template/` into `evals/`. Write one governance
   case per Authority escalate/never row, one capability case per
   tool, and behavioral cases from the Verification section. Wire
   trajectory capture per the `framework-eval-matrix.md` reference
   (each framework captures trajectory differently). Run the suite,
   pin the baseline (`--set-baseline`), record `evals_baselined` in
   `.foundry/state.json`.
5. **Wire deployment artifacts.** Copy the matching Dockerfile from
   `agent-deployment/references/framework-deploy-matrix.md` and the
   matching `docker-compose-templates/<shape>.yml` (single-agent for
   most; langgraph-checkpointer for LangGraph; opencode-serve for
   OpenCode). Set the provider env vars per
   `zai-provider-config.md` (or the equivalent for the chosen
   provider). Do not commit secrets.
6. **Write-back.** If reality forced any design change, update
   design.md in the same turn and flag it to me — widening authority
   requires my explicit yes first. Record `built` in state.json.

Finish by reporting: what was built vs the design (table), eval
baseline result, the framework-specific safety primitives wired, and
the two remaining pipeline steps — `/agent-foundry-smoke-test`, then
`/agent-foundry-ship-check`.
