# claude-agent-sdk-starter

A minimal-but-complete Claude Agent SDK (Python) project that demonstrates the
five things every production agent here ends up needing, in ~100 lines:

1. **Scoped tool surface** — `allowed_tools` names exactly what the job needs.
2. **A custom tool** — in-process MCP server via `@tool`, no separate process.
3. **A deterministic safety hook** — `PreToolUse` deny floor the model cannot
   talk its way past (see the `agent-safety` pillar for the doctrine).
4. **A delegable subagent** — cheaper model for fan-out work.
5. **Cost/session capture** — `ResultMessage` gives you `total_cost_usd` and
   `session_id` for resume.

This is the stage-7 artifact of the `agent-design` process: copy it AFTER the
design stages 1–6 are answered, then replace the demo tool/subagent with your
real ones.

## Run

```bash
pip install claude-agent-sdk          # Python >= 3.10
cp .env.example .env                  # set ANTHROPIC_API_KEY
python src/agent.py "summarize the TODOs in this repo"
```

## Where to go from here

- Wire real evals before you extend it: copy the eval-suite template from the
  `agent-evals` skill (`assets/eval-suite-template/`) and pin a baseline.
- Deployment shapes (CLI vs service vs worker): `agent-deployment` skill.
- The SDK option reference and session/fork/resume patterns:
  `framework-selection` skill, `claude-agent-sdk.md` reference.

API surface last verified: 2026-07 against claude-agent-sdk 0.2.x. If this
starter fails to import, check the reference's `Last verified` banner and the
SDK changelog first.
