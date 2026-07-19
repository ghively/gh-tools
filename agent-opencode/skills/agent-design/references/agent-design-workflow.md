<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# Agent Design Workflow — From Zero to Running

This is the sequence for designing an agent system from nothing. Follow it in order. Skipping steps creates the most common class of problems: bloated context, leaky tool policy, wrong persona, agents that forget their job between turns — and, worst of all, systems built around a framework that was chosen before the requirements existed.

## The spine: the mandatory 7-stage design process

When asked to design or plan an agent, ALWAYS walk these stages in order before selecting a framework or starting any implementation. Each stage gates the next — skipping ahead to "what framework" or "where to deploy" before scoping the task is a known, repeatedly-observed failure mode.

| Stage | What to establish | Output |
|---|---|---|
| **1. Scope** | What exactly does the agent own? What's in/out? Get user intent, with clarifiers if ambiguous. | One-paragraph scope statement |
| **2. Task analysis** | Decompose into concrete operations. Which tasks need LLM reasoning vs deterministic API sequences? What's the tradeoff of each decomposition choice? | Task catalog with reasoning patterns |
| **3. Architecture pattern** | Pick the agent shape from the pattern table (`agent-patterns.md`) and the system shape (`system-architecture.md`). Single ReAct loop? Orchestrator-workers? Graph with branches? Scheduled jobs alongside conversational? | Pattern(s) with rationale |
| **4. Tool surface** | Map every API, data source, and action the agent needs. One tool per task-level operation, not one per API endpoint. | Tool catalog (name + purpose) |
| **5. Decision boundaries** | What's autonomous vs requires escalation? What's the harm if the LLM mis-decides? | Decision matrix (auto / report / escalate) |
| **6. Failure modes** | What breaks? What does the agent do about it? How does it tell the user? | Failure catalog (mode + response) — seed from `failure-modes.md` |
| **7. Framework + deployment** | NOW consult the `framework-selection` skill. Run its decision table against the requirements from stages 1-6. Also: standalone service vs plugin vs CLI tool? | Framework choice + deployment strategy |

**THE CRITICAL RULE: Never skip to stage 7.** If a user says "build an agent for X", they mean stages 1-6 first. The framework decision is the RESULT of the design process, not the starting point. Defaulting to any specific framework without walking the stages is a documented real-world failure — the framework that fits the actual requirements often differs from your personal default. (Origin story: a user asked for a "containerized standalone agent" and got it wired into the authoring agent's own runtime, because stage 7 was answered before stage 1.)

Stages 1-2 are fed by `requirements-elicitation.md` (the seven-dimension discovery). Stage 3 is `system-architecture.md` + `agent-patterns.md`. Stage 5 is where threat modeling starts (deepen with the `agent-safety` skill). Stage 6 is `failure-modes.md`. The rest of this file expands the stages into a concrete build workflow.

## How to work through this with the user

**Plan before build.** Do not draft any files until the user has approved the complete plan. Walk through all stages as a planning exercise first — discuss what each file will contain, what the config will look like, what the tests will verify. Produce ONE cohesive plan. Get approval. Then build.

**Pace:** A real agent design takes 30-60 minutes of back-and-forth, NOT one giant prompt-and-draft. Work through the stages as a conversation, not a dump.

**Don't:**
- Dump all stages as a wall of text
- Draft files before the user has made the decisions those files depend on
- Skip pre-flight because the user seems ready to build
- Draft ANY file until the user has approved the complete plan

**Do:**
- Push back on vague answers during pre-flight ("an assistant for stuff" is not a job)
- Sketch what each artifact WILL contain in prose during planning — that's the plan, not the file
- After approval, draft artifacts one at a time in build mode
- Deliver config as paste-ready blocks, not running prose — but only during build mode

**Deployment is a separate conversation.** This process designs agents. Where/how the system runs in production is the `agent-deployment` skill. If the user asks about deployment mid-flow, answer briefly and return to design.

## Stage 1 expanded — Pre-flight: decide what this agent is FOR

Before touching anything, answer in one sentence:

> This agent's job is to _______ for _______ on _______.

Examples:
- "This agent's job is to manage my personal inbox and calendar for me on Slack and CLI."
- "This agent's job is to monitor my home server's storage and alert me on Telegram."
- "This agent's job is to triage inbound support tickets for the team in Zendesk."

If you can't fill that sentence in, stop. An agent without a clear job becomes a general-purpose helper that does everything badly and hits its context window twice a day. You can always add agents later — start narrow.

Next, decide scope of authority (this drives every other decision):

- **Chat-only** — answers messages; never runs commands, writes files, or browses
- **Read-only tools** — can read files, search the web, query APIs; never mutates anything
- **Full operator** — can run shell commands, edit files, drive a browser, send messages on the user's behalf

Write it down. A chat-only agent should never ship with mutation-capable config "just in case"; a full operator should never ship without an approval allowlist, ask-on-miss behavior, and strict handling of inline interpreter eval (`python -c`, `bash -c` are the classic policy bypass). Multi-agent systems assign an authority tier per agent — differentiate agents by role rather than duplicating one permissive policy.

## Stage 2 expanded — Task analysis

For every workload from elicitation, classify:

1. **Deterministic** — fixed steps, checkable outputs → script or coded workflow. No LLM needed, or LLM only inside individual steps. See `workflow-vs-agent.md` and the `deterministic-agents` skill.
2. **Bounded reasoning** — LLM judgment needed at known points (classify, draft, summarize) but control flow is fixed → workflow with LLM steps.
3. **Open-ended** — steps can't be predicted; the model must decide what to do next → agent loop.

Most "agent" requests decompose into mostly (1) and (2) with a thin layer of (3). The design should reflect that ratio.

## Stage 3 expanded — Architecture pattern

Pick the loop shape per workload from `agent-patterns.md` (ReAct, planner-executor, evaluator-optimizer, orchestrator-worker, graph state machine, memory-augmented) and the system shape from `system-architecture.md` (single agent / peer agents / hub-and-spoke / pipeline / event pipeline). Record the rationale — "orchestrator-worker because the research fans out across 8 independent sources and each source's content would blow a single context window," not "multi-agent because it's a big task."

## Stage 4 expanded — Tool surface

List every action and data source. Then consolidate: one tool per *task-level operation* ("create_calendar_event"), not one per API endpoint ("POST /v3/events", "GET /v3/freebusy", ...). Check existing MCP servers and built-in tools before designing custom anything. Capture, for each tool: name, purpose, read vs write, sensitivity. Design depth (schemas, descriptions, error contracts) belongs to `tool-mcp-engineering`.

## Stage 5 expanded — Decision boundaries

Build a three-column matrix for every action class:

| Action class | Autonomous | Report after | Escalate before |
|---|---|---|---|
| Read/query | ✓ | | |
| Draft content (unsent) | ✓ | | |
| Send to third parties | | | ✓ |
| Modify files in workspace | ✓ | ✓ | |
| Deploy / delete / spend money | | | ✓ |

The question that fills the matrix: *what's the harm if the LLM mis-decides?* Reversible + low-blast-radius → autonomous. Irreversible or externally visible → escalate. This matrix is the seed of your threat model; skipping it is one of this pillar's named pitfalls.

## Stage 6 expanded — Failure modes

Before building, write the failure catalog: for each workload, what breaks (tool errors, hallucinated success, context overflow, prompt injection via fetched content, stale memory), what the agent does about it (retry once with a different approach, then report — never silent retry loops), and how the user finds out. `failure-modes.md` is the catalog to steal from.

## Stage 7 expanded — Framework, then the build sequence

Only now choose the framework (`framework-selection` skill) and walk the build:

### Step A — Identity and persona
- **Agent ID:** short, stable, lowercase. It ends up in session keys, paths, config. Choose once. Good: `main`, `ops`, `inbox`. Bad: `my-ai-assistant-v2`, `test`, `bot1`.
- **Persona / system prompt:** voice and values, 8-15 lines, separate from procedure. Is it a character or "your assistant"? Does it push back? What won't it do?
- **Operating rules** (CLAUDE.md / rules file): procedural. Execute-verify-report; never "I'll do that" — do it and report the result; on failure, one retry with a different approach, then report; memory conventions; tool preferences.
- Keep persona (voice) and operating rules (procedure) in SEPARATE artifacts. Mixing them is a classic day-one mistake. Craft depth: `prompt-context-engineering`.

### Step B — Project setup and versioning
Put every prompt, rules file, and memory seed in a git repo from day one. The context IS the agent's identity — losing it means starting over. Never commit: API keys, credentials, session transcripts. Add a `.gitignore` before the first commit, not after the first leak.

### Step C — Context files, conservative defaults
- **Memory seed:** 3-5 durable facts only (user name, timezone, core preferences, long-term goals). Keep it small (~under 5 KB). Volatile context goes in dated working files, not the always-loaded seed.
- **User context file:** what the agent needs to know to serve the user well — communication style, technical level, boundaries. Loaded every session; keep it ≤ ~2 KB.
- **Proactive/heartbeat behavior: OFF by default.** Enable periodic wake-ups only after the agent has been observably stable and you can write down a narrow checklist of what it should actually do on a tick. Day-one heartbeats burn tokens before you know what the agent should do proactively.

### Step D — Model selection
Pick per the `model-selection` skill, with one design-level hard rule: **tool-enabled agents on untrusted input get top-tier instruction-hardened models only.** Small/older models get jailbroken easily and should not drive tools that touch the world. Cost-optimize on sub-agents and background jobs, not on the security-critical main loop.

### Step E — Tool policy and sandboxing
Map the Stage 5 matrix into enforcement: allowlists, ask-on-miss approval, filesystem scoping, strict inline-eval handling. Sandboxing decision: trusted single user → optional; agent reads untrusted input (email, web, multi-sender channels) → sandbox mandatory; agent serves anyone besides the builder → sandbox everything, no workspace access. Depth: `agent-safety`.

### Step F — One surface first
Wire ONE interaction surface. Don't connect five messaging apps on day one. Get one working, then expand. Inbound policy: pairing/allowlist by default, never open; in group contexts require explicit mention; use a dedicated account/number for the agent, never the user's personal one.

### Step G — Smoke test (the Standard 8)
Run the **canonical Standard 8** from `SKILL.md`: (1) Reachability — can the user invoke it on the intended surface? (2) Context inspection — does it know only the intended rules and memory? (3) Tool inventory — does it report the expected tools and authority? (4) Read path — can it perform a harmless read/query task? (5) Write path — can it draft or apply a low-risk change with verification? (6) Escalation path — does it ask before a high-impact action? (7) Failure path — does it handle a tool error without looping or fabricating success? (8) Persistence path — if memory/state exists, does it survive a session restart? If (8) fails, memory is broken; fix before anything else. The template at `assets/foundry-template/smoke.md` and the `/agent-foundry-smoke-test` command both reference this same list — do not invent a different one.

### Step H — Lock down and iterate
Restrict file permissions on config containing secrets; enable command/tool-call audit logging; commit. Then run the system for a week before adding anything:

1. **Voice and behavior** — read transcripts; tone off → adjust persona; procedure off → adjust operating rules. Small changes, in git, so you can diff the effect.
2. **Memory hygiene** — prune trivia from the seed; keep it small; move transient context to dated files.
3. **Capabilities** — note repeated manual workflows; check existing skills/MCP servers before building; audit anything third-party before enabling.
4. **Automation** — only after the agent is trusted: one narrow scheduled job or standing rule at a time. Observe before adding the next.

Do NOT add five skills and three integrations in the first week. Every addition is context cost and attack surface.

## Common day-one mistakes

1. **Framework chosen before requirements** — the anti-pattern this whole file exists to prevent.
2. **Biography-stuffed persona** — persona is voice, not backstory.
3. **Procedure mixed into persona (or vibes in the rules file)** — keep them separate.
4. **Proactive loops on day 1** — burns tokens before you know what "proactive" should mean.
5. **Open inbound policy** — any stranger who finds the agent becomes a tool user.
6. **Agent on the user's personal account/number** — every DM the user gets becomes agent input.
7. **Config editable from chat** — anyone with message access can rewrite the agent's policy.
8. **No git backing** — losing the context files means starting identity, memory, and personality from zero.

## See also

- `requirements-elicitation.md` — feeds stages 1-2
- `system-architecture.md` — stage 3's system-shape decision + 12-dimension completeness review
- `agent-patterns.md` — stage 3's loop-shape vocabulary
- `workflow-vs-agent.md` — stage 2's core classification
- `failure-modes.md` — stage 6's catalog
- `research-discipline.md` — when to stop and verify instead of designing from memory
