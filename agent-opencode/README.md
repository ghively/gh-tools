# agent-opencode

The agent-engineering skill library from [agent-foundry](https://github.com/ghively/agent-marketplace),
ported from Claude Code to [OpenCode](https://opencode.ai). 13 pillars
covering the full agent SDLC, plus 14 workflow commands, 4 specialist
subagents, a primary `agent-foundry` workstation agent, and a deterministic
safety floor.

## What's in the package

```
agent-opencode/
├── skills/                    # 13 skill pillars (the knowledge library)
│   ├── agent-design/          # pre-code design discipline
│   ├── agent-harness/         # the runtime loop itself (NEW pillar)
│   ├── framework-selection/   # choosing LangGraph/CrewAI/Claude SDK/...
│   ├── deterministic-agents/  # structured outputs, durable execution
│   ├── prompt-context-engineering/
│   ├── model-selection/       # cloud + local model matrices, routing
│   ├── memory-rag/            # RAG pipelines, memory backends
│   ├── multi-agent-orchestration/
│   ├── tool-mcp-engineering/  # tool design, MCP authoring
│   ├── agent-evals/           # eval taxonomy, golden suites
│   ├── agent-safety/          # OWASP, sandboxing, deterministic hooks
│   ├── agent-deployment/      # packaging, serving, CI, Copilot, Duo
│   └── opencode-authoring/    # authoring OpenCode extensions
├── commands/                  # 14 /agent-foundry-* slash commands
├── agents/                    # 4 subagent definitions (.md)
├── plugins/
│   └── agent-foundry-safety/  # TypeScript safety plugin + tests
├── opencode.example.json      # canonical config (skills path, permission floor, 5 agents)
├── install.sh                 # installer
└── README.md                  # this file
```

## Quick install

```bash
git clone https://github.com/ghively/gh-tools.git
cd gh-tools/agent-opencode
./install.sh
```

The installer:
1. Copies `skills/` and `plugins/` to `~/.config/opencode/agent-opencode/`.
2. Copies the 14 commands to `~/.config/opencode/commands/`.
3. Copies the 4 subagents to `~/.config/opencode/agents/`.
4. Creates or merges `~/.config/opencode/opencode.json` from the example.
5. Builds and tests the safety plugin.

Restart OpenCode after install.

## What you get

- **`Tab` to `agent-foundry`** — a primary agent with the full skill library loaded.
- **`@agent-foundry-agent-architect`** — read-only design specialist.
- **`@agent-foundry-security-auditor`** — read-only security auditor.
- **`@agent-foundry-rag-engineer`** — RAG/retrieval specialist.
- **`@agent-foundry-eval-runner`** — eval-suite runner.
- **14 `/agent-foundry-*` commands** — new-agent pipeline, design, build, smoke,
  ship-check, cost-audit, pick-model, new-mcp-server, new-skill, new-subagent,
  new-eval-suite, review-agent, refresh-matrices, security-audit.
- **Permission-based safety floor** — denies `curl|sh`, `rm -rf /`, writes to
  `/etc/passwd`, `~/.ssh/`, etc., at the OpenCode permission layer.

## The 13 pillars

| Pillar | Covers |
|---|---|
| `agent-design` | Pre-code design: scope, threat model, architecture, authority, failure modes |
| `agent-harness` | The runtime loop: tool dispatch, context management, sessions, error recovery, streaming, HITL, observability, caching, doom-loop prevention. Includes a 13-harness comparison (Claude SDK, OpenAI SDK, Copilot SDK, ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop) |
| `framework-selection` | Choosing LangGraph, CrewAI, LlamaIndex, MSAF, DSPy, Pydantic AI, smolagents, NeMo Agent Toolkit, Claude Agent SDK |
| `deterministic-agents` | Structured outputs, durable execution (Temporal, Inngest, Restate, DBOS), proof contracts |
| `prompt-context-engineering` | Prompting patterns, context framework (Write/Select/Compress/Isolate), DSPy, injection defense |
| `model-selection` | Cloud + local matrices, Bedrock, routing, cost tracking, Azure + Cohere coverage |
| `memory-rag` | RAG pipeline, memory architectures (MemGPT/Letta/Cognee/Mem0), vector backends (Pinecone, Weaviate, Milvus, FAISS, pgvector, Qdrant, Chroma) |
| `multi-agent-orchestration` | Orchestrator-worker, subagent design, routing, review panels, A2A/MCP |
| `tool-mcp-engineering` | Tool design, MCP authoring (stdio + Streamable HTTP), api2mcp template |
| `agent-evals` | Eval taxonomy (governance/capability/behavioral/regression), golden suites, CI wiring |
| `agent-safety` | OWASP agentic threats, sandboxing tiers, guardrails, deterministic hooks, tool policy, multi-tenant isolation |
| `agent-deployment` | Packaging, serving, CI-resident (GitHub Actions, GitLab CI, Copilot cloud agent, Duo Workflow), streaming UX, observability, versioning |
| `opencode-authoring` | Authoring OpenCode skills, commands, subagents, plugins, MCP — ported from Claude Code |

## Platform-native coverage

The deployment pillar covers the platform-native agent runtimes:

- **GitHub Copilot**: cloud agent, automations, custom agents, agent skills, hooks, plugins, code review, Agentic Workflows, Spaces, Memory, sandbox, BYOK, Copilot SDK, Copilot CLI, third-party coding agents (Claude, Codex), agent apps, Jira/Slack/Teams/Linear/Azure Boards integrations
- **GitLab Duo**: Chat, Code Review (Duo Reviewer), Workflow, Agent Platform (DAP), AI Context, Cloud Seed, self-hosted models, vendor routing, settings/policies, MCP support

## The safety floor

Two layers, both active:

1. **Native OpenCode `permission` rules** in `opencode.json`:
   - Bash: denies `curl|sh`, `wget|bash`, `rm -rf /`, `dd of=/dev/*`, `mkfs*`, fork bombs; asks for everything else.
   - Edit: denies writes to `/etc/sudoers`, `/etc/passwd`, `/etc/shadow`, `/boot/*`, `/proc/*`, `/sys/*`, cron dirs, systemd, `~/.ssh/*`; asks for everything else.

2. **TypeScript safety plugin** (`plugins/agent-foundry-safety/`):
   - Same block catalog as the Claude Code source (28+ never-run shell primitives + protected write paths).
   - Optional secret-write scanner (`enableSecretCheck: true`).
   - Optional JSONL audit trail (`enableAuditTrail: true`).
   - 5 unit tests pass; TypeScript compiles clean.
   - **Note**: OpenCode 1.18.3 has a bug where local TypeScript plugins fail to load
     (`plugin config hook failed: null is not an object`). The permission
     rules cover the safety floor until the upstream fix lands. The plugin
     code and tests are retained for when the bug is resolved.

## Verification

After install + restart:

```bash
opencode run 'say ok'                  # should print 'ok', no errors
```

In an OpenCode session:
- `Tab` should show `agent-foundry` as a primary agent.
- `@` should show the 4 specialist subagents.
- `/` should show the 14 `agent-foundry-*` commands.
- Skills auto-discover via their descriptions.

## Source

Ported from [ghively/agent-marketplace](https://github.com/ghively/agent-marketplace)
`plugins/agent-foundry/` v1.4.0 (Claude Code plugin). Adapted under the MIT
license. The Claude-specific surfaces (`.claude-plugin/plugin.json`,
`PreToolUse` hooks, `permissionDecision` JSON, Claude path variables) have
been replaced with OpenCode-native equivalents throughout.

## License

MIT — same as the source plugin.
