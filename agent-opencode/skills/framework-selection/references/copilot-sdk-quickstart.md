> Last verified: 2026-07. The Copilot SDK is GitHub's harness for driving Copilot programmatically. Fast-moving — verify against [docs.github.com/en/copilot/copilot-sdk](https://docs.github.com/en/copilot/copilot-sdk/getting-started).

# GitHub Copilot SDK Quickstart

The Copilot SDK lets you drive Copilot sessions programmatically: create sessions, register custom tools, attach hooks, dispatch fleets of parallel sub-agents. Sessions can be cloud-resident (Mission Control) or local (Copilot CLI).

## When to Pick

- GitHub-resident work where the platform already owns identity, audit, and approval flow.
- You want Copilot's capabilities (skills, hooks, fleet mode, MCP) without driving the CLI by hand.
- Multi-tenant SaaS shape — each user authenticates via their GitHub account.

## Adoption Level

Level 4 (platform wrapper) — you inherit Copilot's full surface.

## Current Mechanics

- Packages: `@github/copilot-sdk` (Node.js), `GitHub.Copilot.Sdk` (.NET).
- Auth: GitHub App (recommended for production), user OAuth, or BYOK.
- Sessions: cloud (Mission Control) or local (Copilot CLI as a subprocess).
- Hooks: `pre-tool-use`, `post-tool-use`, session lifecycle (Node.js / .NET event handlers).
- Custom agents: defined per-org or per-repo (`.github/copilot/agents/`).
- Skills: `.github/copilot/skills/<name>/SKILL.md` — same shape as OpenCode/Claude skills.
- Plugins: installable bundles (agents + skills + hooks + MCP + LSP).
- Fleet mode: parallel sub-agents via the `task` tool.

## Minimal Example (Node.js)

```typescript
import { Copilot } from '@github/copilot-sdk';

const copilot = new Copilot({
  auth: { type: 'github-app', appId: ..., privateKey: ..., installationId: ... },
});

// Register a custom tool
copilot.tools.register('search_tickets', {
  description: 'Search the ticket system.',
  parameters: { query: { type: 'string' } },
  execute: async ({ query }) => db.search(query),
});

// Create a session
const session = await copilot.sessions.create({
  agent: 'triage-agent',  // custom agent defined in .github/copilot/agents/
});

// Subscribe to events (streaming)
for await (const event of session.events()) {
  if (event.type === 'tool_call') console.log('tool:', event.tool);
  if (event.type === 'text') process.stdout.write(event.text);
}

// Prompt
await session.prompt('Find open P1 tickets');
```

## Hooks (Deterministic Enforcement)

```typescript
copilot.hooks.onPreToolUse(async (event) => {
  if (event.tool === 'deploy' && !event.userIsAdmin) {
    return { decision: 'deny', reason: 'deploy requires admin' };
  }
});

copilot.hooks.onPostToolUse(async (event) => {
  audit.log({ tool: event.tool, args: event.args, user: event.user });
});
```

## Fleet Mode

```typescript
const session = await copilot.sessions.create({ agent: 'coordinator' });
await session.prompt('/fleet Split this task across 5 workers');
// Coordinator dispatches sub-agents; their results aggregate
```

## Custom Agent Definition

`.github/copilot/agents/triage-agent.copilot-agent.md`:

```markdown
---
description: Triages incoming support tickets.
model: gpt-5.6
allowedTools:
  - search_tickets
  - create_comment
  - add_label
---

You triage incoming support tickets. For each ticket:
1. Classify severity (P0/P1/P2/P3).
2. Route to the right team via labels.
3. Comment with a one-line summary.
```

## ZAI Wiring (BYOK)

Copilot SDK supports BYOK — bring any model via your own API key:

```typescript
const copilot = new Copilot({
  auth: { type: 'github-app', ... },
  byok: {
    provider: 'openai-compatible',
    baseURL: 'https://open.bigmodel.cn/api/paas/v4/',
    apiKey: process.env.ZAI_API_KEY!,
    model: 'glm-4.7',
  },
});
```

## Cloud Sessions vs Local Sessions

| Mode | When to use |
|---|---|
| **Cloud** (`Mission Control`) | Multi-device access; no local CLI; team-shared sessions |
| **Local** (Copilot CLI subprocess) | Single-user; lower latency; runs in your env |

Cloud sessions resume across devices; local sessions resume across processes only if you persist them.

## Observability

```typescript
copilot.onTelemetry((event) => {
  // GenAI-compliant spans: gen_ai.system, gen_ai.request.model, gen_ai.usage.*
  otel.export(event);
});
```

Pair with OTel collector; GitHub also surfaces per-session metrics via the user-facing UI.

## Pitfalls

1. **User OAuth in shared deployments.** Tokens tangle; per-user state leaks. Fix: GitHub App auth (not user tokens).
2. **Per-user billing.** AI Credits bill per user; a runaway agent burns credits fast. Fix: set session limits.
3. **Hooks that fail open silently.** A bug lets everything through. Fix: test hook failures; fail closed on safety rules.
4. **`allowedTools` grows over time.** Blast radius creeps. Fix: tool allowlist changes require PR review.
5. **Lock-in.** Skills, hooks, and agents are platform-shaped. Fix: keep skill bodies portable (OpenCode/Claude shape); treat platform wrappers as adapters.

## Migration Notes

- From Claude Code: hooks translate (`PreToolUse` → `pre-tool-use`); skills are nearly identical (`.github/copilot/skills/` vs `.claude/skills/`); custom agents map to Claude subagents.
- From OpenCode: skills translate directly; commands need re-shaping (OpenCode commands → Copilot agents); permissions become hook-based.

## See Also

- `framework-build-matrix.md` — design → Copilot SDK translation.
- `../../agent-evals/references/framework-eval-matrix.md` — trajectory capture for Copilot sessions.
- `../../agent-safety/references/framework-safety-matrix.md` — safety primitives (Copilot section).
- `../../agent-deployment/references/framework-deploy-matrix.md` — Dockerfile for Copilot SDK apps.
- `../../agent-deployment/references/ci-resident-agents.md` — platform-native Copilot automations vs this SDK.
