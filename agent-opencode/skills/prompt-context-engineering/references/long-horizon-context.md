> Last verified: 2026-07. Context-window sizes, compaction features, prompt-cache TTLs, and provider-specific context editing behavior change quickly; verify model/provider docs before relying on exact limits.

# Long-Horizon Context — Sessions That Outlive One Window

Long-running agents fail when they treat the transcript as durable memory. Context windows fill, summaries lose detail, tool outputs bloat attention, and stale claims become "facts." Long-horizon context engineering makes state explicit, compresses deliberately, isolates risky work, and restarts when needed.

## Core Strategy

| Strategy | Purpose | Example |
|---|---|---|
| Write | Move durable state outside the prompt | Plan file, task board, memory file, structured notes |
| Select | Load only what the next step needs | Targeted file read, retrieval query, tool search |
| Compress | Replace bulk with checked summaries | Tool-output summary, compaction at milestone |
| Isolate | Use separate contexts for risky or bulky subtasks | Subagent research, sandboxed log analysis |

## Compaction and Summarization

Compaction is lossy. Treat it as a state transition, not a garbage collection event.

| Moment | Action |
|---|---|
| Before long work | Write plan, assumptions, task IDs, and success criteria to a file or durable state |
| Before compaction | Record current state and unresolved questions outside the transcript |
| After compaction | Re-verify live claims: tests, file contents, service status, branch state |
| After task completion | Compress conclusions, evidence, and decisions; discard intermediate noise |

Good summaries include:

- Goal and current status.
- Decisions made and why.
- Files/artifacts changed or inspected.
- Known failures and next action.
- Source/evidence pointers.
- Explicit uncertainty.

Bad summaries include:

- Unverified "tests pass" claims.
- Raw command output pasted wholesale.
- Old plans not marked as superseded.
- Instructions copied from untrusted fetched text.

Anthropic current docs describe server-side compaction as a primary strategy for long conversations and note that cached prompt prefixes still count toward context windows. Primary source: https://docs.anthropic.com/en/docs/build-with-claude/context-windows

## Subagent Isolation as a Context Firewall

Use a subagent when a subtask would pollute or overflow the main context, or when independent investigation benefits from a fresh window.

The spawn prompt must carry everything the subagent needs:

- Task objective.
- Relevant files/URLs/data pointers.
- Constraints and exclusions.
- Required output format.
- Verification requirements.
- Budget: max files, max sources, max tokens/time.

The subagent should return only:

- Conclusion.
- Evidence.
- Files/sources inspected.
- Commands/tests run, if any.
- Open questions or blockers.

Do not ask subagents to dump full transcripts. The point is context isolation.

## Memory Files Across Sessions

Memory files are for durable facts and operating rules, not live task state.

| Store | Put here | Do not put here |
|---|---|---|
| Durable memory | Stable preferences, project conventions, recurring constraints | Temporary task progress, stale API responses |
| Working notes | Current plan, decisions, source findings | Secrets, credentials, untrusted instructions |
| Task board | Step status and blockers | Large raw outputs |
| Retrieval store | Source chunks and metadata | Instructions that should outrank system/developer rules |

Memory needs pruning. A stale always-loaded memory line is permanent context poisoning.

## Prompt-Cache-Aware Layout

Prompt caching rewards stable prefixes. It does not expand the context window.

| Layout rule | Why |
|---|---|
| Stable tool definitions first | Tool changes invalidate downstream cache |
| Stable system/rules before volatile task data | Reuse shared prefix across turns |
| Retrieved/fetched content after stable instructions | Retrieval changes frequently |
| Timestamps after cache breakpoints | Time changes break exact-match caches |
| Sort context chunks by stable key | Prevent nondeterministic cache misses |

Current Anthropic prompt caching supports automatic caching and explicit breakpoints, default 5-minute TTL, optional 1-hour TTL, and up to four explicit breakpoints. Put a breakpoint at the last block whose prefix is identical across calls. Primary source: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching

## Context Budgets Per Delegation

Set budgets before spawning work.

| Delegation type | Budget |
|---|---|
| Quick file inspection | 1-3 files, concise findings |
| Source research | 3-8 primary sources, quote only load-bearing lines |
| Code investigation | Search/read targeted files, no edits unless requested |
| Review panel | Independent findings only; no duplicate summaries |
| Long-running worker | Persist notes every milestone |

If the subtask cannot fit a clear budget, split it.

## When to Split the Session Outright

Restart or split when:

- The context contains known-bad assumptions that keep influencing responses.
- The task changed substantially and old context is now distraction.
- Compaction would lose details still needed for active reasoning.
- Tool outputs dominate the context and cannot be safely summarized in place.
- A new phase needs different tools, authority, or safety posture.

Carry forward a hand-written state packet: goal, completed work, current files/artifacts, verified facts, unresolved questions, and next action.

## Pitfalls

1. **Compacting mid-investigation.** Fix: compact at boundaries after writing state externally.
2. **Assuming cached tokens do not count.** Fix: remember caching affects cost/latency, not context capacity.
3. **Letting subagents return raw dumps.** Fix: require conclusion/evidence/output contract.
4. **Using memory as task progress.** Fix: put task progress in working state with timestamps and expiry.
5. **Trusting summaries as live truth.** Fix: re-read files, rerun checks, or query APIs before acting.
