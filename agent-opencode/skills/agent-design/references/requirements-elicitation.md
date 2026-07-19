<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# Requirements Elicitation — Discovery Before Design

Before you design any agent system, understand what you're actually being asked to build. Users consistently under-describe their requirements — not out of carelessness, but because they don't know which details matter to the architecture.

Your job in this phase is to extract the full picture through structured questioning. Do NOT start drafting prompts, recommending agents, picking frameworks, or choosing models until this phase is substantially complete. Jumping to design with incomplete requirements produces wrong architectures that get rebuilt later.

## How to work through this with the user

**Pace:** 15-30 minutes of discovery conversation. Feels slow. Is worth it.

**Sequence:** Work through the seven requirement dimensions below, one at a time. Ask 2-4 questions per dimension. Summarize what you heard back to the user before moving to the next.

**Don't:**
- Skip questions because the user "seems to know what they want"
- Accept vague answers ("just a general assistant") — push for specificity
- Jump to solutions mid-elicitation ("that sounds like a LangGraph node...") — stay in discovery mode until the full picture is there
- Ask all questions as a wall-of-text checklist — work through them conversationally

**Do:**
- Reflect back what you heard after each dimension ("OK, so what I'm hearing is...")
- Call out contradictions or gaps ("You said X but also Y — which is it, or is it both?")
- When the user mentions something specific you don't know from memory, say so and offer to research (see `research-discipline.md`)
- Use concrete examples to clarify abstract answers ("When you say 'monitor my infrastructure' — what specifically? Just uptime, or also logs, disk space, container health, certificate expiry?")

**What "done" looks like:** You have clear answers to every dimension below, or you've explicitly noted which are unknown/deferred. You can write a 1-paragraph summary of the system the user needs. The user has confirmed that summary is correct.

## The seven requirement dimensions

Work through these in order. Each has 2-4 sub-questions. Don't skip any dimension, even if the user seems to have answered some of it already — confirm explicitly.

**Pre-flight = dimensions 1 and 2.** These two alone give you enough to commit to a rough authority tier (chat-only / read-only / full operator) and a first guess at system shape. Dimensions 3–7 refine *components and policy within* that choice. It's fine to sketch a tentative shape after dimensions 1–2 and let the remaining dimensions confirm or challenge it. If dimensions 3–7 change your answer to "what authority does this agent need?", reopen the shape choice; otherwise move forward.

### Dimension 1 — Purpose and users

What is this system FOR, and who interacts with it?

- **Primary purpose (one sentence):** "The system's job is to ___ for ___ on ___"
- **Who talks to it?** Just the builder (single-user personal agent)? A team? Customers? Multiple isolated users?
- **Trust level of users:** All fully trusted? Partially trusted (internal but broad)? Untrusted-inbound possible (public chat, inbound email, web forms)?
- **What does success look like?** What would make the user say "this is working"?

If the user says "just me", confirm: no teammates, no customers, not even read-only? That answer changes EVERYTHING about trust, isolation, and sandboxing — it is the first input to threat modeling (see the `agent-safety` skill).

### Dimension 2 — Workloads and tasks

What does the system actually DO? Not at a high level — specifically.

- **List every distinct job the user wants automated or assisted.** Push for at least 3-5 concrete examples.
- **For each job: is it reactive (user asks, system responds) or proactive (system acts on its own)?**
- **For each job: how often does it happen?** Continuous? Scheduled (cron)? Triggered by event (email, webhook, PR opened)? Ad-hoc (user-initiated)?
- **For each job: what's the input volume?** Short messages? Long documents? Live streams? File uploads?

This is where users under-describe the most. "Help me manage my inbox" could be:
- Reactive: "draft replies when I ask" (one skill, one agent)
- Proactive: "triage everything that arrives, draft responses for review, alert on urgent" (three distinct workloads — scheduled trigger + triage logic + alert logic)

Extract the specifics. Don't let "manage my inbox" stand. Each concrete workload will later get classified as workflow-vs-agent territory (see `workflow-vs-agent.md`) — you can't classify vague workloads.

### Dimension 3 — Channels and surfaces

Where does the user (or the world) interact with the system?

- **Which surfaces?** Chat app (Slack, Discord, Telegram, WhatsApp), CLI, web UI, IDE, email, HTTP API?
- **Primary vs secondary surfaces?** Is one the main entry point, or do they want full parity?
- **Group / shared contexts involved?** Or 1:1 only?
- **Non-interactive surfaces?** Webhooks, CI pipelines, message queues, scheduled runners?

Surface decisions drive session design, identity/auth complexity, and latency budgets. A single-surface system is simple. Multi-surface with different personas per surface is where multi-agent designs start to emerge (and where they're often over-proposed).

### Dimension 4 — Data and context

What does the system need to know or remember?

- **Long-term memory:** What durable facts about the user, their business, their environment, their preferences?
- **Working memory:** What context accumulates across a day / week / project?
- **Shared knowledge:** Are there structured knowledge sources (wiki, Notion/Confluence, internal docs, a codebase)?
- **External data sources:** APIs it'll query, databases it'll read, files it'll parse?

The answer to "do you have a knowledge base it should know about" determines whether you need retrieval infrastructure, a structured memory store, or just a small set of always-loaded context files. Capture the need here; the design decision belongs to the `memory-rag` skill.

### Dimension 5 — Tools and capabilities

What does the system DO in the world?

- **Read-only tasks:** Query, fetch, summarize, research?
- **Write/act tasks:** Send messages, modify files, run commands, execute deployments, post to external services?
- **Sensitive actions:** Anything involving money, deletion, publishing, sending to other people, credentials?
- **Existing integrations:** APIs the user already uses (Jira, GitHub, Notion, cloud providers, etc.)?
- **Custom CLIs / scripts:** Binaries the user has built that the agent should drive?

This maps directly to tool policy, sandboxing decisions, approval gates, and (critically) whether each capability should be a script, a tool, an MCP server, or a skill. Don't decide yet — just capture. Tool-surface design belongs to the `tool-mcp-engineering` skill.

### Dimension 6 — Automation and timing

What happens WITHOUT the user being present?

- **Scheduled work:** Daily briefs, weekly reports, periodic health checks?
- **Event-driven work:** "When email arrives from X, do Y"? "When a webhook fires, do Z"? "When a PR opens, review it"?
- **Background monitoring:** Infrastructure alerts, status checks, polling?
- **Long-running jobs:** Things that might take hours (research, indexing, large summarization)?

This maps to cron jobs, webhooks, standing rules, and background-worker patterns. Again — capture, don't decide.

### Dimension 7 — Constraints and non-functional

What limits or requirements matter?

- **Hosting:** Where does this run? Local machine? A home server? VPS? Cloud? Serverless? Matters for sandboxing, performance, and network reach.
- **Budget:** Cost-sensitive? OK with premium models? Cheap models for background/sub-agent work?
- **Latency:** Interactive chat (seconds OK)? Voice (sub-second)? Batch (hours OK)?
- **Privacy:** Data stays local? Cloud APIs OK? Specific services off-limits?
- **Compliance / security posture:** Regulated data? Shared workstation? Untrusted inputs reaching a tool-enabled agent?
- **Availability expectations:** 24/7? Business hours? Best-effort?
- **Maintenance budget:** How much time per week can the user spend iterating on it?

A user who says "I want everything running 24/7 with no maintenance" is describing a different system than one who says "I'll happily tune this weekly."

## The summary step

After all seven dimensions, write a summary back to the user. Format:

```
Here's what I'm hearing:

PURPOSE: [1-sentence system purpose]
USERS: [who interacts with it + trust model]
WORKLOADS: [numbered list of distinct jobs, each tagged reactive/proactive/scheduled/event]
SURFACES: [primary + secondary]
DATA: [memory needs + external sources]
CAPABILITIES: [read-only / writes / sensitive]
AUTOMATION: [scheduled / event / background / interactive]
CONSTRAINTS: [hosting, budget, latency, privacy, posture, maintenance]

Before I design architecture — is this complete and correct? Anything I missed or got wrong?
```

Wait for confirmation or corrections. DO NOT move to architecture design until the user has confirmed the summary is accurate.

Iterate on the summary if the user corrects it. Two or three rounds of "no wait, also..." is normal and healthy — it means requirements are surfacing.

## Research discipline during elicitation

Elicitation is a high-uncertainty conversation — users drop platform names, MCP servers, APIs, and model IDs you may not have fresh memory of. Whenever a user mentions a specific capability, feature, or service whose current behavior will drive a design decision, **pause and research before continuing**.

The full discipline, scripts, and failure modes are in `research-discipline.md`. Summary for elicitation:

- If a user-mentioned specific matters to the design, fetch the service's current docs rather than guessing.
- Batch uncertain items in a single research pass when possible — one pause, not three.
- Tell the user what you checked: "Just pulled the Slack API docs and confirmed inbound voice messages are supported; that changes dimension 3's answer."
- A research pause during elicitation is *low-cost* — the user already expects probing. Use that budget.

## Common elicitation failure modes

**User gives a narrow answer to a broad question.**
User: "I want to help with my email"
Wrong move: accept it and design an email assistant
Right move: "Is email the only thing? I want to make sure I'm capturing the full system — anything else you'd want it to help with in the same agent, or a separate agent?"

**User conflates multiple jobs into one.**
User: "It should handle my infrastructure"
Wrong move: design one "infrastructure agent"
Right move: "What specifically? Health monitoring, deployment, backup verification, security scanning? These might be one agent, might be three — depends on the specifics."

**User describes what they DON'T want without describing what they DO.**
User: "Not another chatbot that just pastes info back at me"
Wrong move: affirm and move on
Right move: "Got it. So if not that, what DOES a good outcome look like? Walk me through a specific example."

**User has an architecture in mind but hasn't said so.**
User: "...and I want a different persona for work stuff"
Wrong move: treat "different persona" as a prompt tweak
Right move: "That might be a separate agent — different context, possibly different model and tool policy. Is that what you had in mind, or one agent that code-switches?"

**User answers quickly because they think they've already told you.**
User: [answers dimension 2 in 3 seconds]
Wrong move: accept the quick answer
Right move: "That was quick — let me make sure. When you said X, did you mean [narrow interpretation] or [broader interpretation]?"

**User states a solution instead of a requirement.**
User: "I need a multi-agent system with a supervisor"
Wrong move: start designing the supervisor
Right move: "What's the underlying job? Let's capture the workloads first — the shape falls out of them. A supervisor may or may not be the right answer."

## Output of this phase

At the end of requirements elicitation, you should have a confirmed summary that includes:

1. System purpose (1 sentence)
2. User(s) and trust model
3. 3-7 specific workloads with their triggers (reactive/proactive/scheduled/event)
4. Surface list with primary/secondary
5. Data/memory needs
6. Capability profile (read-only / write / sensitive)
7. Automation pattern (scheduled / event / background / interactive)
8. Constraints (hosting, budget, latency, privacy, availability, maintenance)
9. The user's confirmation that the summary is accurate

Only THEN do you move to `system-architecture.md` to decide the shape of the system.

## See also

- `research-discipline.md` — canonical home for the research-pause rule
- `system-architecture.md` — the next step after elicitation
- `workflow-vs-agent.md` — classify each captured workload before assuming it needs an agent
- `agent-design-workflow.md` — where elicitation sits in the full 7-stage design process
