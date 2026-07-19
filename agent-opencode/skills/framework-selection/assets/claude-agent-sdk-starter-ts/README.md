# claude-agent-sdk-starter-ts

The TypeScript twin of `claude-agent-sdk-starter/` (see that README for the
full rationale). Same five load-bearing pieces in one file: scoped tool
surface, a custom in-process MCP tool (zod-typed), a deterministic PreToolUse
deny floor, a cheap-model subagent for fan-out, and cost/session capture.

## Run

```bash
npm install
cp .env.example .env        # set ANTHROPIC_API_KEY
npm start -- "summarize the TODOs in this repo"
```

## Where to go from here

Same pointers as the Python starter: eval-suite template from `agent-evals`
assets before extending; deployment shapes in `agent-deployment` (its
`assets/deploy-templates/` include a Dockerfile and worker/scheduled shapes);
full SDK option reference in `framework-selection`'s claude-agent-sdk.md.

API surface last verified: 2026-07 against @anthropic-ai/claude-agent-sdk
0.3.x. If imports fail, check the reference's `Last verified` banner and the
SDK changelog first.
