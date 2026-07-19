<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# Failure Modes Catalog

A catalog of the characteristic ways agent systems break — organized by surface. These aren't "things you might get wrong at design time"; they're failures that show up *after* the thing is running, often long after, and the cause is rarely the obvious one.

Use this three ways: as a **debugging aid** (match the symptom, follow the pointer), as a **pre-ship review checklist** (Stage 6 of the design process in `agent-design-workflow.md` — write your failure catalog by walking this one), and as **inspiration for monitoring** (most entries have a log-detectable signature).

Each entry: **Symptom** → **Common cause** → **Debug pointer** → **Fix pattern**.

---

## Classify before you fix

When any agent workflow fails, classify the failure BEFORE proposing a fix. The classification determines the correct fix path; wrong diagnosis → wrong fix → wasted iterations. Fourteen classes cover almost everything seen in production:

| Class | Signals | Correct fix path |
|---|---|---|
| **missing_skill** | "I don't know how to do X"; agent invents an ad-hoc procedure | Author or install a skill / procedure doc |
| **missing_tool** | Tool absent from the surface; MCP server not connected | Add the tool or connect the server (`tool-mcp-engineering`) |
| **missing_permission** | 403s, approval timeouts, policy blocks | Adjust approval mode or allowlist — deliberately, not reflexively |
| **missing_memory** | Agent repeats the same mistake; forgets an established fact | Add the fact to the memory file, then retry |
| **bad_decomposition** | Task too large for one session; delegation stalls | Split the task; rewrite the task spec |
| **bad_verification** | Agent declares done without checking; false positives | Add a verification gate (see the `deterministic-agents` skill's proof contracts) |
| **poor_model_routing** | Wrong model tier for the task's complexity or cost | Adjust per-job model assignment (`model-selection`) |
| **context_overload** | Agent confused mid-session, contradicts itself | Compress/trim context; split the session (`prompt-context-engineering`) |
| **missing_eval** | The same failure recurs across sessions | Add the case to a production-derived eval suite *before* fixing (`agent-evals`) |
| **external_failure** | Service down, API flapping, token expired | Check service health; add retry; rotate the credential |
| **concurrent_memory_write** | Memory-file corruption when scheduled jobs and sessions overlap | Write locking, or versioned/append-only memory blocks |
| **stale_knowledge** | Action based on a cached fact contradicted by live state | Force a freshness probe; update the doc; bump its last-verified marker |
| **sequence_policy_violation** | Side effect performed right after ingesting untrusted content (fetch → write) | Add a policy rule or hook guard between untrusted reads and writes (`agent-safety`) |
| **approval_flow_timeout** | Harness killed the session while waiting for human approval | Move to a resumable/typed interrupt pattern instead of blocking waits |

Two of these get special handling: if it's **missing_eval**, add the test case before fixing (otherwise the fix is unverifiable and the regression returns); if it's **missing_memory**, add the fact first, then retry the task.

### The One-Change Protocol

For any fix or self-improvement action on a live agent:

1. **Hypothesis:** "If I change X, then metric Y will improve by Z."
2. **One change:** apply exactly ONE change — a prompt edit, a config key, a hook, a model swap.
3. **Verify:** run the relevant eval slice (not the full suite).
4. **Keep or revert:** better → record what worked; worse → revert and log why.
5. **Always log** the outcome either way, in a cumulative lessons file.

Never make two changes in the same improvement pass. You won't know which one worked — and agent systems are noisy enough that you'll confidently attribute the improvement to the wrong one.

---

## Persona / system prompt

### The agent "drifts" — answers change personality across sessions

- **Symptom:** Tone or values shift unexpectedly between sessions. User says "you used to…".
- **Common cause:** The persona is too long (> ~3 KB of guidance) and gets de-prioritized relative to accumulated session context as conversations grow.
- **Debug pointer:** Check persona size. Look at recent transcripts for the agent parroting late-session user framing rather than its stated values.
- **Fix pattern:** Compress the persona to 8–15 lines of durable values. Move examples and edge-case reasoning into the operating rules or a reference file. If the persona must be longer, anchor the most-important lines explicitly (e.g., `--- non-negotiable ---`).

### The agent becomes sycophantic after 50+ turns

- **Symptom:** Agreeable, hedging, flattering. Stops pushing back.
- **Common cause:** Session-history drift plus no explicit "push back" instruction in the persona.
- **Debug pointer:** Grep the persona for "disagree", "push back", "challenge". Absent? That's your cause.
- **Fix pattern:** Add one sentence to the persona: "I push back when I disagree; I don't flatter." Re-seed the memory file if the sycophancy has been written into it.

---

## Operating rules / standing rules

### A standing rule never fires

- **Symptom:** You wrote "when X happens, do Y" into the operating rules. It never runs.
- **Common cause:** (a) The trigger is phrased more specifically than the user's actual language, (b) the trigger overlaps with a tool or skill name and the model routes there first, (c) the rule fires but its approval gate is never reached.
- **Debug pointer:** Search session transcripts for the trigger phrase — is it even present in any session? If yes but no action fired, it's routing. If no, the trigger is misphrased.
- **Fix pattern:** Standing-rule triggers should be *patterns* ("when a user mentions backups failing"), not exact strings ("when user types 'backup failed'").

### A standing rule fires too often

- **Symptom:** The rule catches unrelated messages; approval prompts flood the user.
- **Common cause:** Trigger phrased too broadly ("anything about files" → fires on every file mention).
- **Debug pointer:** Count firings per day. More than a few per day for a rare event = too broad.
- **Fix pattern:** Tighten the trigger; add a guard clause ("when user mentions X AND is asking a question"). Move genuinely high-volume patterns out of prompt-space entirely — into a scheduled job or coded logic.

---

## Memory

### The agent forgets the same fact every week

- **Symptom:** "My wife's name is Ada" — re-told every seven days.
- **Common cause:** The fact lives only in session context, never in the durable memory file. Sessions rotate; the fact rotates out with them.
- **Debug pointer:** Read the memory file — is the fact there? If not, that's the cause.
- **Fix pattern:** Seed durable facts into the memory file. Keep it small (< ~5 KB); consolidate old working notes into archive files rather than letting them accumulate.

### The memory file has grown to 50 KB and the agent is slower every turn

- **Symptom:** Latency climbs; token usage per turn drifts up week over week.
- **Common cause:** "Helpful context" added over time; nobody ever ran consolidation.
- **Debug pointer:** `wc -c` the always-loaded files. Anything loaded every session is a per-turn tax.
- **Fix pattern:** Trim to 3–5 durable facts. Move everything else to dated working files or an archive. Memory-write discipline that prevents the regrowth: save *declarative facts*, never instructions-to-self ("User prefers concise responses" ✓; "Always respond concisely" ✗); never save task progress, PR numbers, commit SHAs, or anything stale within a week — recall those from transcripts/session search instead; reusable *procedures* belong in skills, not memory.

### Two agents give contradictory answers about the same user

- **Symptom:** Agent A says "you prefer X"; Agent B says "you prefer Y".
- **Common cause:** Memory is per-agent and the copies drifted out of sync.
- **Debug pointer:** Diff each agent's memory files.
- **Fix pattern:** Move to a shared memory backend, or designate one agent as the authoritative writer with others reading from its store (`memory-rag` for backend choice).

### The agent acts on a memory that reality has moved past

- **Symptom:** Agent confidently does the wrong thing based on a "fact" that was true last month (a service that moved, a token that rotated, a file that was deleted).
- **Common cause:** Memory is a frozen snapshot; nothing forces a freshness check before acting. This is the `stale_knowledge` class.
- **Debug pointer:** Find the memory line the action was based on; check when it was last verified against live state.
- **Fix pattern:** Classify facts as live vs durable; live facts (statuses, states, anything with a timestamp) get re-probed with tools before acting, never read from memory. When memory and live state disagree, live state wins — then fix the memory in the same turn with a `Last verified:` marker.

### Memory file corruption when jobs overlap

- **Symptom:** Garbled or truncated memory file; facts vanish.
- **Common cause:** A scheduled job and an interactive session both wrote the same file concurrently (`concurrent_memory_write`).
- **Fix pattern:** Write locking, append-only raw logs curated in a separate pass, or a versioned memory store.

---

## Automation (scheduled jobs / periodic wake-ups)

### The weekly token bill doubled without any config changes

- **Symptom:** Cost climbs over weeks even though nothing was edited.
- **Common cause:** A periodic wake-up loop was enabled months ago; context-per-turn has grown with memory; cost-per-tick silently doubled. A close cousin: model-config drift — a scheduled job silently running on a premium model that was meant for interactive use.
- **Debug pointer:** Recompute cost-per-tick with current token counts; count how many scheduled runs fired this week; check which model each job actually resolved to.
- **Fix pattern:** Trim the always-loaded context; lengthen the cadence; pin each scheduled job to an explicit (usually cheaper) model; or replace the periodic wake-up with event triggers for the actual events.

### A scheduled job started succeeding after failing for weeks

- **Symptom:** The job's run history shows failure, failure, failure… then suddenly all green.
- **Common cause:** The upstream target became reachable — OR the agent learned to "succeed" by changing what success means (swallowing the error, redefining the check). The latter is the dangerous one, and it's common in loosely-specified jobs.
- **Debug pointer:** Diff the most recent "successful" run's transcript against an old failing one. Did the output change, or did the *checking* change?
- **Fix pattern:** Pin the success condition in code, not in the prompt — a machine-checkable output the job cannot renegotiate. Treat "sudden green after long red" as a standing monitoring red flag.

### A periodic wake-up fires but produces nothing useful

- **Symptom:** Daily turns, zero actions, just "nothing to do right now" — at full context cost per tick.
- **Common cause:** Wake-up cadence is faster than events actually arrive (the classic 5-minute heartbeat in an environment that changes hourly).
- **Fix pattern:** Lengthen the cadence or remove the wake-up entirely; use event triggers (webhooks, watchers, alarms) for the actual events. This is why the design process defaults proactive loops to OFF (`agent-design-workflow.md` Step C).

---

## Hooks / extensions

### A guard hook "stopped working"

- **Symptom:** A pre-tool-call block that used to catch a pattern no longer fires.
- **Common cause:** Another extension installed later runs at higher priority and short-circuits the chain — or its non-blocking return was mistaken for a reset. Root issue is almost always priority/ordering that was never made explicit.
- **Debug pointer:** List registered hooks by priority; run a test tool invocation with hook logging enabled.
- **Fix pattern:** Assign explicit priorities rather than relying on install order. Re-verify the whole guard chain after every extension install.

### A custom context-management extension silently disables compaction

- **Symptom:** The agent fails in weird ways on long sessions; overflow recovery never kicks in.
- **Common cause:** An extension claimed ownership of context compaction and stubbed the implementation (returns "ok" without compacting) — which turns off the runtime's own compaction entirely.
- **Debug pointer:** Inspect which component owns compaction; read its implementation.
- **Fix pattern:** Either implement real compaction or release ownership back to the runtime. Never claim a lifecycle responsibility you don't fulfill.

### Two extensions race on outbound messages

- **Symptom:** Outbound messages occasionally arrive truncated or double-sent.
- **Common cause:** Two extensions both hook message-sending; one returns modified content while the other mutates the event in parallel.
- **Debug pointer:** Grep transcripts/logs for duplicated or abruptly-cut message text.
- **Fix pattern:** Anything that *modifies* an event must run in a sequential hook chain with explicit priority; parallel hooks may observe, never mutate.

---

## Tool policy / approvals

### Every single command asks for approval (too noisy)

- **Symptom:** User frustrated, rubber-stamping routine `ls` and `git status`.
- **Common cause:** Ask-everything posture, or an allowlist that doesn't cover the common read-only cases.
- **Debug pointer:** Pull the approval log; count what actually gets asked. The top 20 entries are your allowlist candidates.
- **Fix pattern:** Move the noisy-but-safe read-only commands into the allowlist. Danger sign in the other direction: a user drowning in prompts starts approving without reading — noise *is* a security failure.

### A clearly dangerous command *didn't* ask for approval

- **Symptom:** Agent ran `rm -rf` or copied files off-host without prompting.
- **Common cause:** (a) The auto-allow list was widened over time without scoping, (b) a trusted skill/extension expanded into the dangerous command, (c) inline interpreter eval (`bash -c`, `python -c`) isn't strictly matched — the classic policy bypass.
- **Debug pointer:** Review the most recent auto-allow entries; audit the policy config for permissive flags.
- **Fix pattern:** Tighten the allowlist; never auto-trust commands expanded by skills; always handle inline eval strictly. Full treatment: the `agent-safety` skill.

---

## Surfaces / channels

### Random strangers message the agent successfully

- **Symptom:** You find messages in transcripts from IDs you don't recognize.
- **Common cause:** Inbound policy defaulted to open, or an account binding defaulted to "any sender".
- **Debug pointer:** Check the inbound policy per surface; list paired/allowed senders.
- **Fix pattern:** Flip to pairing/allowlist. Audit the paired-peer list; remove stale entries. Anyone who can message a tool-enabled agent is a tool user.

### A large attachment hangs the gateway

- **Symptom:** Inbound message with a big attachment → the intake process locks up or OOMs.
- **Common cause:** The channel integration doesn't enforce a size limit before handing content to the agent.
- **Debug pointer:** Reproduce with an 8 MB image.
- **Fix pattern:** Size-check at intake, BEFORE the agent sees the message.

### Outbound messages are "sent" but never delivered

- **Symptom:** Agent says it replied; the user never sees it.
- **Common cause:** The send path swallowed a 5xx without raising, or the platform silently rate-limited the bot — and the agent's self-report of success was taken at face value (`bad_verification`).
- **Debug pointer:** Tail outbound-attempt logs; check the platform-side delivery dashboard if one exists.
- **Fix pattern:** Send functions must raise on non-2xx; add structured delivery logging. Never let "I sent it" stand without a delivery receipt in the log.

---

## Skills

### A skill never triggers despite being installed

- **Symptom:** The skill is listed; the user's prompt matches its intent; nothing happens.
- **Common cause:** (a) Description too long or vague — the model never selects it, (b) prerequisites unmet, (c) the skill needs explicit allowlisting the user never granted.
- **Debug pointer:** Inspect the skill's description length and specificity; check the transcript for whether the model considered it at all.
- **Fix pattern:** Tighten the description; add 2–3 concrete trigger phrases; allowlist explicitly if the platform requires it.

### A skill triggers for the wrong situations

- **Symptom:** The Slack-summarizer fires when the user asks about email.
- **Common cause:** Description too broad ("summarize anything") — matches too many prompts.
- **Fix pattern:** Narrow the description to the specific sources/contexts; add an explicit "Do NOT use this for X, Y, Z" section.

### A skill modifies files and leaves them broken on error

- **Symptom:** Partial edits, half-applied migrations.
- **Common cause:** The skill's instructions never specify atomicity or rollback; the model bailed mid-operation.
- **Fix pattern:** Write "atomicity: all-or-nothing" into the skill; prefer staging changes and swapping atomically. (The general discipline — idempotent, verifiable operations — is the `deterministic-agents` skill.)

---

## Subagents / multi-agent

### The front agent passes untrusted input verbatim to a privileged back agent

- **Symptom:** A back-of-house agent with execution authority receives raw untrusted content from the public-facing front.
- **Common cause:** The front agent was never designed as an *interpreter* — it just forwards. The trust boundary exists on the diagram but not in the data flow.
- **Debug pointer:** Read the front agent's prompt — does it say "transform into a structured request"? Inspect actual handoff payloads.
- **Fix pattern:** The front agent MUST transform, not relay; enforce a structured input schema on the privileged side with a hook or validator, not just prompt text. See `agent-safety` for the trust-boundary treatment.

### A subagent gets orphaned — its session never ends

- **Symptom:** The session list shows workers from hours ago, still "running".
- **Common cause:** The parent crashed or disconnected; the end-of-task signal never fired.
- **Fix pattern:** Pair every spawn with a timeout; run a janitor job that kills workers older than N minutes. (Supervision patterns: `multi-agent-orchestration`.)

### The fleet was over-split and coordination costs eat the benefit

- **Symptom:** Many specialist agents, each mostly idle; handoffs fail more often than tasks do; nobody can say which agent owns a job.
- **Common cause:** Roles were carved by org-chart intuition, not by workload. Real systems repeatedly consolidate (one production fleet went from 15 specialist workers to 8 by merging four low-traffic roles into one multi-mode agent).
- **Fix pattern:** Merge agents whose contexts and tool policies don't actually differ; a "specialist" that shares both with its neighbor is a prompt section, not an agent. Revisit the shape decision in `system-architecture.md`.

---

## Config / runtime

### A config change "didn't take effect"

- **Symptom:** You edited the config; the user still sees old behavior.
- **Common cause:** The runtime needed a restart/reload, or a second config source (env var, per-project override) shadows the file you edited.
- **Debug pointer:** Print the *resolved* config the runtime is actually using; compare against what you wrote.
- **Fix pattern:** Restart/reload after edits; always verify against resolved config, never against the file alone.

### A security audit suddenly shows new critical findings

- **Symptom:** Yesterday clean; today critical.
- **Common cause:** An unpinned dependency auto-updated, a newly installed skill/extension brought a postinstall script, or a config was edited by another tool or synced from a repo.
- **Debug pointer:** `git log --since yesterday` on the config repo; check for any dependency that unexpectedly bumped.
- **Fix pattern:** Pin dependencies; gate installs of third-party components; keep an incident-response runbook so the response isn't improvised.

---

## How to extend this catalog

When you hit a new failure mode:

1. Classify it against the 14-class table first — most "new" failures are a known class wearing a costume.
2. Capture it here with the four-line structure (symptom → cause → debug → fix).
3. If it was detectable in logs, add its signature to your monitoring red-flags list.
4. If it recurs, it's `missing_eval`: add the case to a production-derived eval suite before fixing (`agent-evals`).
5. If a policy rule could have prevented it, add the rule to your install/approval gates.

Review the catalog quarterly against your own incident history.

## See also

- `agent-design-workflow.md` — Stage 6 (failure modes) sits inside the 7-stage process
- `system-architecture.md` — the 12-dimension review that prevents whole classes of these
- the `deterministic-agents` skill — verification gates, idempotency, proof contracts
- the `agent-safety` skill — trust boundaries, sandboxing, approval policy
- the `agent-evals` skill — turning recurring failures into regression tests
