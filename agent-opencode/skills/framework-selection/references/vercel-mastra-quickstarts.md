> Last verified: 2026-07. Vercel AI SDK (`ai`) and Mastra (`@mastra/core`) are TypeScript-native; verify against [sdk.vercel.ai/docs](https://sdk.vercel.ai/docs) and [mastra.ai](https://mastra.ai).

# Vercel AI SDK & Mastra Quickstarts

Two TypeScript-native frameworks. Vercel AI SDK is the canonical JS tool-loop library. Mastra adds workflows + memory on top.

## Vercel AI SDK

### When to Pick

- TypeScript codebase, especially Next.js / Vercel-edge deploys.
- You want the simplest JS tool-calling loop with streaming.
- You need BYOK across many providers via `@ai-sdk/*` packages.

### Adoption Level

Level 1 (provider SDK + tool loop).

### Minimal Example

```typescript
import { generateText, tool, stepCountIs } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { z } from 'zod';

const zai = createOpenAI({
  baseURL: 'https://open.bigmodel.cn/api/paas/v4/',
  apiKey: process.env.ZAI_API_KEY!,
});

const result = await generateText({
  model: zai('glm-4.7'),
  maxSteps: 15,
  stopWhen: stepCountIs(15),
  tools: {
    searchTickets: tool({
      description: 'Search the ticket system.',
      parameters: z.object({ query: z.string() }),
      execute: async ({ query }) => db.search(query),
    }),
  },
  messages: [{ role: 'user', content: 'Find open P1 tickets' }],
});

console.log(result.text);
```

### Streaming

```typescript
import { streamText } from 'ai';
const result = await streamText({ model: zai('glm-4.7'), prompt: '...' });
for await (const chunk of result.textStream) {
  process.stdout.write(chunk);
}
```

### Observability

```typescript
generateText({
  // ...
  experimental_telemetry: {
    isEnabled: true,
    functionId: 'triage-agent',
    recordInputs: false, // PII redaction at the source
  },
});
```

### Pitfalls

1. **Stateless.** `messages` array is yours to manage across turns. Fix: session store.
2. **`maxSteps` defaults to 1.** Single-turn only by default. Fix: set `maxSteps: N` and use `stopWhen`.
3. **No HITL primitive.** Fix: wrap `execute` with a permission check; raise to pause.

## Mastra

### When to Pick

- TypeScript codebase where ordered workflows matter more than free-form loops.
- You want memory + workflows + agents in one framework.
- Multi-step business processes (not just chat).

### Adoption Level

Level 3 (workflow + memory).

### Minimal Example

```typescript
import { Mastra } from '@mastra/core';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const searchTickets = createTool({
  id: 'search-tickets',
  description: 'Search the ticket system.',
  inputSchema: z.object({ query: z.string() }),
  execute: async ({ context }) => db.search(context.query),
});

const triageAgent = new Agent({
  name: 'triage',
  instructions: 'You triage support tickets.',
  model: openai('gpt-5.6'),
  tools: { searchTickets },
  maxSteps: 15,
});

const mastra = new Mastra({
  agents: { triage: triageAgent },
});

const result = await triageAgent.run('Find open P1 tickets');
```

### Workflows

```typescript
import { Workflow } from '@mastra/core/workflows';

const wf = new Workflow({
  name: 'ticket-triage',
  trigger: 'event',
  steps: [
    { id: 'classify', executor: classifyStep },
    { id: 'route', executor: routeStep },
    { id: 'assign', executor: assignStep },
  ],
});
```

### Memory

```typescript
import { MastraMemory } from '@mastra/memory';
const memory = new MastraMemory({
  backend: 'postgresql',
  connectionString: process.env.DATABASE_URL!,
});
```

### ZAI Wiring

Mastra uses Vercel AI SDK's provider pattern under the hood — same wiring as Vercel AI SDK:

```typescript
import { createOpenAI } from '@ai-sdk/openai';
const zai = createOpenAI({
  baseURL: 'https://open.bigmodel.cn/api/paas/v4/',
  apiKey: process.env.ZAI_API_KEY!,
});
const agent = new Agent({ model: zai('glm-4.7'), ... });
```

### Pitfalls

1. **Memory backend defaults to in-process.** Dies with the process. Fix: set `MASTRA_MEMORY_BACKEND=postgresql`.
2. **Workflow step caps.** Each step has its own max iterations; cross-step loops not bounded. Fix: cap at the workflow level.
3. **Fewer hooks than LangGraph.** No native `interrupt_before`. Fix: step-level suspend/resume.

## See Also

- `framework-build-matrix.md` — design → Vercel AI SDK / Mastra translation.
- `../../agent-evals/references/framework-eval-matrix.md` — trajectory capture.
- `../../agent-safety/references/framework-safety-matrix.md` — safety primitives.
- `../../agent-deployment/references/framework-deploy-matrix.md` — Dockerfile (Bun for Vercel AI SDK; Node for Mastra).
