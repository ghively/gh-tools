<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# Research Discipline — When to Stop and Verify

Agent platforms, model APIs, pricing, framework imports, and plugin schemas move faster than design principles. Good agent design therefore has two modes: answer from stable engineering knowledge when the claim is durable, and pause to verify when a stale detail would produce a wrong build.

## The Rule

When the user's outcome depends on a current external fact, fetch current primary documentation before you design or implement around it.

This is not performative humility. It is a reliability practice. A wrong flag name, retired model ID, changed framework import path, or stale pricing assumption can invalidate an otherwise good architecture.

## Must-Verify Cases

Fetch current docs when the user asks about or your design depends on:

- Exact CLI commands, flags, config fields, manifest schemas, or hook event names.
- Current model IDs, context windows, pricing, batch discounts, rate limits, or deprecation status.
- Framework APIs that have churned recently: imports, decorators, checkpointers, workflow runtime behavior, human-in-the-loop APIs.
- MCP server capabilities, auth behavior, transport support, tool schemas, or registry/distribution status.
- Provider-specific structured-output, tool-calling, prompt-cache, batch, or file-upload behavior.
- External service behavior: auth scopes, webhook payloads, API limits, destructive-operation semantics.
- Security-sensitive assumptions: sandbox guarantees, permission-rule syntax, allowed paths, network isolation, credential handling.

If the design would be materially different depending on the answer, verify.

## Usually Stable Enough From References

These categories are durable enough to answer from this plugin's references unless the user asks for a version-specific detail:

| Stable topic | Why it is stable |
|---|---|
| Workflow vs agent distinction | The architectural tradeoff is conceptual, not tied to a release |
| Seven-stage agent design process | Scope, task analysis, pattern, tools, boundaries, failure modes, framework remains the right order |
| Tool-design principles | Intent-named tools, typed flat parameters, explicit errors, idempotency are platform-independent |
| Proof contracts | Diff/tests/evidence/report/decision is a verification pattern, not a product feature |
| Context failure modes | Poisoning, distraction, confusion, and clash are model-behavior patterns |
| Least-agency principle | Smaller authority surfaces remain safer across platforms |

## Version-Volatile Map

| Claim type | Default action |
|---|---|
| "Use this import path" | Verify against primary docs or installed package |
| "This model costs X" | Verify provider pricing page |
| "This supports prompt caching" | Verify provider feature docs and model support table |
| "This MCP server supports OAuth" | Verify server README/docs and current protocol spec |
| "This hook blocks X" | Read the actual hook code and tests |
| "This framework supersedes that one" | Verify official migration docs or release notes |
| "This API is safe to retry" | Verify idempotency semantics in the API docs |

## Primary-Source Order

1. Official product/framework documentation.
2. Official API reference or SDK reference.
3. Release notes, changelog, migration guide, or deprecation page.
4. Official GitHub repository examples and tests.
5. Maintainer-authored blog posts or design notes.
6. Community examples only after checking that they match current docs.

Do not let a blog post outrank the API reference when they disagree. Treat LLM memory as below all of the above for volatile details.

## Batch Research

When several uncertain items appear in one task, research them together. A framework choice may require checking three docs: current LangGraph checkpointers, CrewAI Flow syntax, and LlamaIndex AgentWorkflow state handling. Batch the fetches, then make the decision.

Use sequential research only when one answer determines which source to check next.

## Scripts for Transparent Uncertainty

Use concise language with the user:

> "I need to verify the current import path and checkpoint API before I write this; those have changed recently."

> "This depends on current pricing and batch discounts, so I am checking provider docs before recommending a model route."

> "I can explain the stable pattern now, but I should verify the exact permission syntax before giving you config."

After fetching, say what changed or what you confirmed. The user should know whether you are relying on fresh docs or stable design knowledge.

## How to Use Research in Design

1. Separate the stable architecture from volatile mechanics.
2. Continue the design using stable concepts while marking volatile facts as pending.
3. Fetch before the volatile fact becomes a build decision.
4. Cite the primary source inline when the fact is load-bearing.
5. Record verification date in researched references so future readers know what may be stale.

## Anti-Patterns

1. **Guessing plausible field names.** Fix: fetch the schema or inspect examples before writing config.
2. **Trusting a remembered import path.** Fix: verify against current quickstart or installed package.
3. **Designing around assumed provider features.** Fix: verify model support and platform differences before committing.
4. **Using community snippets as current truth.** Fix: reconcile with official docs and release notes.
5. **Researching after implementation fails.** Fix: pause earlier when a stale fact would change the plan.
