# Context Engineering — Write / Select / Compress / Isolate

Managing what enters the model's context window is as important as what you ask
it to do. Context windows are finite, every token costs money and attention, and
agents degrade in characteristic ways as context fills. This file gives the
four-strategy framework, the four failure modes, and concrete platform mappings.

## The four context failure modes

Diagnose before you fix. Each failure mode has a distinct symptom and a distinct
remedy:

| Failure mode | What happens | Symptom you'll observe | Primary remedy |
|---|---|---|---|
| **Context poisoning** | A hallucination or error enters the context and gets treated as ground truth in later turns | Agent confidently cites a "fact" it generated earlier; errors compound | Compress out the bad span; re-verify against source of truth; restart the session if entrenched |
| **Context distraction** | So much accumulated context that the model attends to history instead of its training/instructions | Agent repeats past actions, loses focus, gives generic answers | Compress; trim old tool results; tighten Select |
| **Context confusion** | Superfluous or conflicting content influences the response | Agent uses irrelevant tools, mixes up entities, answers the wrong question | Select harder — load fewer tools/documents; scope retrieval |
| **Context clash** | Contradictory instructions or facts from different sources | Agent follows the wrong instruction, contradicts itself, oscillates | Establish precedence explicitly ("if X and Y disagree, X wins"); remove the loser |

The clash remedy deserves emphasis: when two sources can disagree (a cached
status file vs. live API, a summary vs. reality, an old plan vs. new
instructions), **declare the winner in the prompt**. "If the plan file and the
user's latest message disagree, the user's message wins." Agents without a
precedence rule pick unpredictably.

## Strategy 1: Write — store context outside the window

Don't hold everything inline. Persist information to external storage and
retrieve it on demand.

- **Scratchpads / plan files** — session-scoped working state. In Claude Code:
  task lists (TodoWrite), plan-mode plan files, a `NOTES.md` in the working
  tree. In frameworks: LangGraph state objects, a workspace file the agent
  reads/writes. The point: a plan written to a file **survives compaction**;
  a plan held only in conversation does not.
- **Memory files** — facts that persist across sessions. In Claude Code:
  `CLAUDE.md` (auto-loaded operating rules), auto-generated memory directories,
  or project docs the agent is instructed to maintain. In frameworks: a memory
  store keyed by user/project. Keep memory files curated and small — they are
  loaded every session, so every stale line is a poisoning vector.
- **Structured note-taking** — for long tasks, have the agent append findings
  to a file as it works (decisions made, dead ends, current hypothesis). This
  turns the file, not the transcript, into the durable record.

Rule of thumb: **the transcript is a stream of consciousness nobody reads
twice.** Anything worth remembering past this task belongs in a file.

## Strategy 2: Select — pull only relevant context

Don't dump everything into every prompt. Retrieve what's needed for the current
step.

- **Just-in-time file reads** — read the section you need (offset/limit, grep
  for the symbol), not the whole file. An agent that reads 2,000 lines to use
  10 has spent 99% of those tokens on distraction.
- **Retrieval over bulk-loading** — semantic/keyword search that returns
  relevant chunks beats loading whole documents. (Building the retrieval
  pipeline itself is the `memory-rag` skill's territory.)
- **Progressive tool/skill loading** — don't front-load every tool description.
  Claude Code skills do this natively: only name + description load at startup;
  the body loads when triggered; `references/` files load only when needed.
  For custom agents, the same pattern (a tool-search or deferred-schema
  mechanism) measurably improves tool selection when the catalog is large.
- **Selective state exposure** — in framework agents, surface only the state
  fields relevant to the current node/step, not the entire state object.

## Strategy 3: Compress — retain only essential tokens

When context grows, summarize and trim — deliberately, not just when forced.

- **Summarize tool output before reasoning over it.** A 500-line command output
  usually contains 5 lines of signal. Extract the signal; never re-quote bulk
  output back into your own reasoning.
- **Compaction** — replacing the transcript with a summary. Claude Code
  auto-compacts near window capacity and supports manual `/compact`. Two hard
  rules:
  1. **Compact at a natural boundary** (task finished, plan written), not
     mid-investigation — summaries lose exactly the fine detail you're using.
  2. **Treat post-compaction summaries as presumptively stale.** A mid-session
     summary carries "in progress" and "blocked" claims that may already be
     resolved. Re-verify runtime claims (test status, branch state, service
     health) against live probes before acting on them.
- **Trim completed-task context.** Once a subtask is done and its result is
  recorded, its intermediate tool calls are dead weight.
- **Compaction gates for autonomous systems** — production agent harnesses add
  thresholds (e.g., warn at ~75% capacity, block new delegations and force
  summarization at ~85%) rather than letting agents run to the wall. If you're
  building a harness, enforce this in code (a hook or wrapper), not in the
  prompt.

## Strategy 4: Isolate — split context into separate windows

When one window can't hold the work — or when a subtask would pollute the main
thread — split it.

- **Subagent isolation** — each subagent gets a fresh window focused on one
  narrow task and returns only conclusions (see `long-horizon-context.md` for
  the full firewall pattern, and the `multi-agent-orchestration` skill for
  coordination). Cost warning: multi-agent orchestration can cost ~15x the
  tokens of a single-agent pass (Anthropic's multi-agent research finding).
  Isolation is a trade, not a savings.
- **Sandbox / code-execution isolation** — run heavy operations in an execution
  environment and return only results. A script that processes a 50 MB log and
  prints a 20-line summary keeps the 50 MB out of every subsequent turn.

## Token budgeting for delegation

| Pattern | Token cost | When to use |
|---|---|---|
| Single agent, sequential | 1x baseline | Default for most tasks |
| Delegate to 1 subagent | ~2x (parent + child) | Isolate one heavy subtask |
| Parallel fan-out (N agents) | ~Nx + parent synthesis | Genuinely independent workstreams |
| Orchestrator + workers | up to ~15x | Complex decomposition needing coordination |

## Practical rules

1. **Don't read entire files when you need one section.** Targeted reads and
   searches; whole-file loads are the single biggest source of context bloat.
2. **Don't dump full tool output into reasoning.** Summarize findings; discard
   the rest.
3. **Prefer retrieval over loading.** A recall query returns relevant chunks;
   a file load returns everything.
4. **Persist plans to files before long work.** Compaction erases in-context
   plans; files survive.
5. **Split into subagents only when context would genuinely overflow or
   pollute** — remember the multiplied token cost.
6. **Name the precedence when sources can conflict.** Live state vs. cached
   docs, user message vs. old plan — say which wins.
7. **Watch for the failure modes.** Hallucinated "facts" from earlier turns =
   poisoning. Generic drifting answers = distraction. Wrong-tool usage =
   confusion. Self-contradiction = clash. Each has its remedy above.

## Pitfalls

- **Loading everything "just in case."** More context is not better — it costs
  money, latency, and attention. Select aggressively.
- **Treating tool output as inherently interesting.** Most of it is data to act
  on, not to reason over at length.
- **Forgetting compaction loses scratchpad state.** Plan only in context →
  plan gone after compaction.
- **Over-using multi-agent as a token optimization.** It isolates context but
  multiplies total spend.
- **Curating memory files never.** Stale memory-file lines are loaded into
  every future session — that's institutionalized context poisoning.
