<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# System Architecture — Choosing the Shape

You've done requirements elicitation. You know what the system needs to do, for whom, via which surfaces, with what automation. Now decide the SHAPE.

Wrong shape is the most expensive mistake in agent-system design. A single agent doing four unrelated jobs gets rebuilt as a multi-agent system later. A multi-agent system built too early creates maintenance burden for workloads that should have been skills or tools in one agent. Sub-agents fired inline where a scheduled job was needed produce flaky results.

Your job in this phase is to match the requirements to the right system shape, justify the choice, and then walk the user through the component designs that make that shape work.

## How to work through this with the user

**Pace:** 10-20 minutes. This phase is about deciding; detailed drafting happens after.

**Sequence:** Review requirements → propose shape with reasoning → discuss alternatives → confirm → enumerate components to design.

**Don't:**
- Propose the most complex shape because it sounds sophisticated
- Default to "one agent" without checking — some requirements genuinely need more
- Split into multiple agents because the user mentioned "different contexts" — that's often a prompt/routing/skill answer, not a multi-agent answer
- Skip the reasoning — always explain WHY the proposed shape fits the requirements

**Do:**
- Start with the simplest shape that could possibly work
- Call out explicitly when you're over-engineering and offer the simpler path
- Discuss tradeoffs — every shape has costs
- Map each workload from requirements to a specific component in the chosen shape
- Check each workload against `workflow-vs-agent.md` first — a workload that can be a deterministic workflow should not become an agent inside ANY shape

**What "done" looks like:** The user has confirmed a shape (one of the patterns below) and you've listed the specific components to be designed (e.g., "one main agent with persona X, three skills Y/Z/W, two scheduled jobs A/B, one sub-agent pattern for C").

## The system shapes — five patterns

### Pattern 1 — Single agent (the default)

```
[User] <--> [Agent] <--> [Model API]
              |
         [Project / context files]
         [Tools: skills, built-ins, MCP]
         [Optional: scheduled jobs]
```

**When this fits:**
- Single user (or one trust tier of users)
- 1-3 distinct job categories that share personality and context
- All surfaces can use the same voice
- No workload is heavy enough to blow the context window alone

**Example:** "Personal assistant for inbox, calendar, and self-hosted infrastructure on Slack + CLI." One agent, one context, one persona. Skills for specific domains (inbox triage, calendar operations, infra health). Scheduled jobs for recurring work (morning brief). Optional sub-agents for research.

**Why this is the default:** Lower maintenance, one context to version-control, one identity to iterate on, one set of credentials. Most requirements fit here.

**Signs you should STAY with single-agent even when tempted to split:**
- "I want different personas for different surfaces" → one agent, context-aware rules in the system prompt / operating rules
- "I want a serious one and a casual one" → same agent; the persona handles context
- "I want work stuff separate from personal" → maybe, maybe not — see Pattern 2

### Pattern 2 — Peer agents (independent specialists)

```
[User] <--> [Agent A: personal] <--> [Model]
[User] <--> [Agent B: work]     <--> [Model]
[User] <--> [Agent C: team]     <--> [Model]

Separate contexts, separate credentials, separate session stores.
```

**When this fits:**
- Genuinely different personas that would contradict each other in one agent (blunt personal vs professional external-facing)
- Different trust models (personal agent has full tool access; work agent read-only)
- Different model/cost preferences per agent
- Per-user isolation (each user gets their own agent with separate memory)

**Example:** "My personal assistant is blunt and has full tool access to my home server. My work agent is professional-toned, read-only, and only sees work channels." Two agents, two contexts, routing per surface.

**Cost:**
- N contexts to maintain, version, update
- N sets of credentials (unless deliberately shared)
- Context does NOT flow between them — agent A doesn't know what agent B discussed

**When to push back on this pattern:**
- User wants two agents because "one gets confused about context" → that's a memory/context-engineering problem, not a multi-agent problem (see `prompt-context-engineering`)
- User wants two agents to split cost → cheaper sub-agents inside one agent may solve this better

### Pattern 3 — Hub and spoke (one main agent, spawned sub-agents)

```
[User] <--> [Main Agent]
                |
           spawns sub-agents
                |
    [Sub-agent A]  [Sub-agent B]  [Sub-agent C]
    (research)     (data crunch)  (content draft)
```

**When this fits:**
- Main agent handles the user-facing conversation and synthesis
- Discrete workloads are parallelizable or context-heavy and benefit from isolation
- Work fans out, then results synthesize back in the main agent

**Example:** "Research assistant that spawns workers to investigate 5 topics in parallel, then synthesizes." One main agent, ephemeral sub-agents spawned per task, spawn depth capped at 1.

**Cost:**
- Sub-agents run on their own model + token budget (mitigate with a cheaper model tier for workers)
- Sub-agents don't inherit the main agent's persona or accumulated context — task prompts must carry everything they need
- Result delivery is best-effort; if the runtime dies mid-run, results can be lost

**When this is overkill:**
- Task is sequential, not parallel → main agent handles it directly
- Task is short (<30 sec) → sub-agent overhead exceeds the benefit
- Task needs the user's tone/full conversational context → sub-agent can't easily inherit it

### Pattern 4 — Pipeline (orchestrator + workers, depth 2)

```
[User] <--> [Main Agent]
                |
           spawns orchestrator
                |
           [Orchestrator]
                |
           spawns workers
                |
   [Worker A]  [Worker B]  [Worker C]
```

**When this fits:**
- Workload is genuinely multi-stage: fan out to workers, synthesize in an orchestrator, deliver via the main agent
- The main agent should NOT be tied up in the fan-out/synthesis work
- The orchestration itself is substantial (not just a for-loop — if it's a for-loop, write a for-loop; see `workflow-vs-agent.md`)

**Example:** "Weekly research report: gather from 10 sources, synthesize into 3 themes, package as final report." Main agent takes the ask, spawns an orchestrator, orchestrator spawns 10 workers, collects results, produces themed synthesis, reports back.

**Cost:**
- Spawn depth 2 required — debugging a depth-2 problem is 2x harder than depth-1
- Cost multiplies (main + orchestrator + workers) if all run premium models

**Default recommendation:** Don't go to depth 2 unless you've tried depth 1 and specifically hit the "orchestration should be its own agent" wall. Most systems never need this. Runtime mechanics (handoffs, shared state, supervision) belong to the `multi-agent-orchestration` skill.

### Pattern 5 — Event pipeline (external triggers + schedules + agents)

```
[External event: email, webhook, file, schedule]
                |
           [Trigger layer: cron / webhook / queue]
                |
       [Isolated agent run]
                |
   (optional: spawns sub-agents)
                |
           [Deliver result: notification, PR, report]
```

**When this fits:**
- Most work is AUTOMATED, not interactive
- External events drive the agent (inbound email, webhooks, CI events, file watchers)
- Results are delivered via notifications/artifacts, not conversation
- The "main agent" is mostly asleep; triggers wake it for specific jobs

**Example:** "Monitor my servers and alert me. Watch for email from investors and draft replies. Weekly metrics report." This is NOT a conversational agent — it's a set of automated pipelines that occasionally deliver to the user.

**Design notes:**
- Scheduled jobs are first-class; they're not afterthoughts
- Deterministic triggers only — no "wake up periodically and figure out what to do" loops until proven necessary
- Minimal context per triggered run; each job gets a narrow task prompt
- Interactive use reuses the same agent for manual check-ins
- Many event-pipeline jobs are better as deterministic workflows with LLM steps than as agents — see the `deterministic-agents` skill

## How to pick a shape — the decision flow

Given the requirements elicitation output, apply in order:

1. **Multiple users with different trust levels?** → Pattern 2 (peer agents)
2. **Genuinely contradicting personas across contexts?** → Pattern 2 (peer agents)
3. **Most work is automated (cron/webhook/events)?** → Pattern 5 (event pipeline)
4. **One workload has genuine fan-out parallelism?** → Pattern 3 (hub + sub-agents) for that workload; Pattern 1 for the rest
5. **The orchestration itself is substantial?** → Pattern 4 (depth-2 pipeline), but only after proving Pattern 3 isn't enough
6. **None of the above?** → Pattern 1 (single agent)

Most systems land on Pattern 1 with some Pattern 3 elements for specific workloads. That's healthy. Resist the urge to show sophistication by proposing Pattern 2 or Pattern 4 when simpler works.

**Migrations between shapes.** When a deployed system outgrows its starting shape — Pattern 1 splitting into Pattern 2, a single agent gaining sub-agents, or an over-split system consolidating back — treat the migration as architectural: a fresh design pass with memory preservation, context forking, and rollback safety. Do not treat it as tweaks.

## Architecture completeness review — MANDATORY before finalizing

Passive workload-mapping is not enough. Users frequently under-describe requirements, meaning workloads that SHOULD exist get omitted. Proactively walk every capability dimension before finalizing architecture — do NOT wait for the user to bring them up.

For each dimension, either (a) map it to a specific component you're including, or (b) explicitly confirm with the user that it's not needed. Never leave a dimension unanswered by assuming silence means "not needed."

### Dimension 1 — Skills / task packages
For each distinct task-domain: does it need its own skill (specific, repeatable, bounded task)? Or is it a general operating rule (belongs in the system prompt / CLAUDE.md-style rules file)? Does an existing skill from a plugin marketplace already cover it?
Ask: "For each of these workloads, do you want a dedicated skill or is this general enough to live as an operating rule?"

### Dimension 2 — Tools
For every capability: do built-in tools (shell, file read/write, web fetch, search) cover it? Does an existing MCP server cover it? Does it need a custom CLI the agent drives via shell? Does it need a typed tool definition? Deep guidance: `tool-mcp-engineering` skill.
Ask: "What external services / APIs / tools does this system need? For each: does something already exist, or do we build?"

### Dimension 3 — Extensions and hooks
Do any of these apply? Intercepting tool calls (policy, logging), modifying prompts, custom context assembly, a custom model provider, a new interaction surface, custom HTTP endpoints.
Ask: "Do you need anything to observe, block, or modify agent behavior across tools? Audit trails? Policy gates?"

### Dimension 4 — MCP servers
Check: existing public servers for GitHub, Notion, Slack, filesystems, databases, etc. (search the official MCP servers registry before building); your own server only for proprietary integrations or cross-client reuse.
Ask: "Any third-party services the agent should interact with? I'll check if a server already exists before we build anything." When a candidate server comes up and you lack current detail, STOP AND RESEARCH (`research-discipline.md`).

### Dimension 5 — Automation (schedules, webhooks, standing rules)
For each proactive/scheduled behavior: schedule (cron expression, session mode, model tier, delivery target, failure destination); webhooks (what triggers, what auth); standing rules (what authority, what approval gate, what escalation). Periodic "wake up and look around" loops default to OFF until proven.
Ask: "What should happen automatically without you present? Scheduled reports? Event monitoring? Health checks?"

### Dimension 6 — Sub-agents
Any workload that's parallelizable? Heavy enough to blow the main context? Needs isolation from the main session (untrusted content)? Depth 1 or depth 2? Per sub-agent: task prompt structure, tool scope (default deny, allow narrowly), sandbox posture, model tier, result-delivery pattern.
Ask: "Any tasks that should run in parallel or in isolation from the main conversation?"

### Dimension 7 — Hooks for audit and policy
Command/tool-call logging for an audit trail (recommended for any system running third-party code); session-end memory persistence; pre-install policy gates for third-party skills/plugins.
Ask: "Should we enable command logging for audit? A security gate before installing third-party components?"

### Dimension 8 — Memory architecture
Backend choice (flat files vs vector store vs structured wiki vs managed memory service); consolidation strategy; external collections (notes vault, internal docs); cross-agent memory (only if Pattern 2); embedding provider. Depth: `memory-rag` skill.
Ask: "Besides conversational memory, does the agent need structured knowledge — a notes vault, internal docs, a wiki?"

### Dimension 9 — Tool policy & security
Per agent: posture (chat-only / read-only / full operator); sandboxing (off / sub-agents-only / all; filesystem scope); command approval policy (denylist/allowlist, ask-on-miss, strict handling of inline interpreter eval); who can reach the agent (pairing/allowlist — never open inbound on a personal agent); where approval prompts get delivered. Depth: `agent-safety` skill. This dimension IS your threat model — skipping it is the classic design failure.
Ask: "What's the trust model? Who can talk to this agent, and what should it be allowed to do on their behalf?"

### Dimension 10 — Surfaces
Confirm: surface list, primary vs secondary, DM/inbound policy per surface, group behavior (mention required?), admin/control access path, approval delivery per surface.
Ask: "Confirmed surface list — anything else?"

### Dimension 11 — Project layout & versioning (design-side only)
Per agent: where do context files live; git backing for prompts/rules/memory (strongly recommended — losing them means starting the agent's identity over); template-seeded vs generated fresh. Full deployment is the `agent-deployment` skill.
Ask: "Do you want the agent's context and config git-tracked from the start?"

### Dimension 12 — Testing and iteration
Smoke-test checklist per agent; how to iterate on persona when voice drifts; how to iterate on operating rules when procedure fails; how to monitor scheduled-job reliability; eval plan for the core workloads (see `agent-evals`).
Ask: "Are you comfortable with the feedback loop for iterating on this after launch?"

## Final architecture summary template

After walking all 12 dimensions, produce the final architecture document:

```
SYSTEM ARCHITECTURE: [name]

SHAPE: Pattern [N] — [pattern name]
REASONING: [2-3 sentences from requirements]

AGENTS:
- [agent-id]
  - Purpose: [one sentence]
  - Surfaces: [list]
  - Model: [provider/model — see model-selection skill]
  - Sandbox: [mode + filesystem scope]
  - Tool posture: [chat-only / read-only / full] with [specific allow/deny]
  - Approval policy: [policy]

SKILLS: [name: purpose] ...
TOOLS: [custom tools + which are covered by built-ins] ...
MCP SERVERS: [existing to connect / to build] or None
HOOKS: [audit, policy, memory hooks] or None

AUTOMATION:
- Scheduled jobs: [name — schedule + session mode + delivery]
- Webhooks: [trigger + auth]
- Standing rules: [list]

SUB-AGENT PATTERNS: [pattern — depth, task prompt shape, tool scope, model tier] or None

MEMORY: [backend, collections, consolidation]

SECURITY BASELINE: [audit logging, install gates, file permissions, no dangerous flags]

DEPLOYMENT TARGET: [host + network access + git backing] (details → agent-deployment)

OPEN QUESTIONS: [decisions deferred to the user]

NEXT STEPS (design order): [ordered component list]
```

Deliver this summary. Get EXPLICIT approval before moving to component design:

> Here's the complete plan. Before I start drafting anything, I need your explicit approval. Is anything missing? Is anything wrong? Ready to proceed?

Wait for a clear "go". Do NOT infer consent from hedging language ("looks good", "sure") — follow up with "Approved to start building?" if the response is ambiguous. If the user catches something missed (they often will), revise and re-present. The plan must be CURRENT and COMPLETE at the moment of approval.

## Why every dimension matters

The most expensive architecture mistakes are things the user didn't realize they needed to consider:

- **Forgot about MCP servers** — system gets built with custom integrations for things existing servers cover
- **Forgot about hooks** — no audit trail, no install gate, can't trace behavior later
- **Forgot about memory backend** — defaults work until the memory store scales past what flat files handle
- **Forgot about security posture** — agent ships with permissive defaults because they "sounded reasonable"; no threat model for untrusted input reaching a tool-enabled agent
- **Forgot about sub-agent cost** — workers running on premium models; sticker shock
- **Forgot about approval delivery** — approval prompts never reach the user on their actual surface
- **Forgot about git backing** — disaster on first hardware failure

None of these show up in basic requirements elicitation. They surface only when you actively walk the capability dimensions.

## Common architecture mistakes

- **Over-splitting into agents.** User mentions "work vs personal" and you propose two agents. Often one agent with context-aware rules is enough. Only split when the agents would genuinely contradict each other's operating rules or trust models.
- **Under-using sub-agents.** "Research 5 things in parallel and synthesize" done inline will blow the main context. That's a sub-agent job.
- **A skill for what should be an operating rule.** "Always confirm before destructive operations" is not a skill — it's a standing rule.
- **An agent for what should be a workflow.** The workload has fixed steps and checkable outputs → code with LLM steps, not an agent. See `workflow-vs-agent.md`; this is the single most common over-build.
- **A scheduled job with no manual trigger.** "Daily brief" → schedule it, yes, but also make it invocable on demand. Skill + schedule, not schedule alone.
- **A sub-agent for what should be inline.** "Summarize this file" — the main agent does this directly.
- **Event pipeline built when interactive is fine.** A user who talks to their agent 10 times a day needs a good interactive agent with a few scheduled jobs, not a full event pipeline.
- **Missing a capability dimension entirely.** The worst one. The 12-dimension review exists specifically to prevent it.

## After architecture is confirmed

Output of this phase is the confirmed shape + the components-to-design list. Next: design one component at a time, verify with the user, move to the next. Persona/prompts → `prompt-context-engineering`; tools → `tool-mcp-engineering`; memory → `memory-rag`; multi-agent runtime → `multi-agent-orchestration`; security → `agent-safety`; framework → `framework-selection` (LAST — see `agent-design-workflow.md`).

## See also

- `requirements-elicitation.md` — inputs to the shape decision
- `workflow-vs-agent.md` — classify workloads before assigning them to agents
- `agent-design-workflow.md` — the full 7-stage process this phase sits inside
- `failure-modes.md` — pre-ship review against known failure classes
