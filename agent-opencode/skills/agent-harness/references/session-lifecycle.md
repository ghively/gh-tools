# Session Lifecycle

A session is the durable state of a conversation: the message history,
the agent's working memory, the active tool set, and the metadata that
lets a run resume after an interruption. The harness owns the session
lifecycle: create, resume, fork, share, export, end.

This is distinct from run-level context (the active loop, covered in
`agent-loop.md`) and from long-term memory (covered in the `memory-rag`
skill). A session is the middle layer: it survives process death but
not necessarily a user's departure.

## Session States

```
created ─► active ─► idle ─► archived
              │        │
              │        └─► resumed (back to active)
              │
              └─► forked (new session, shared history)
              │
              └─► shared (URL, read-only or collaborative)
              │
              └─► exported (JSON, markdown, trace)
```

| State | What it means |
|---|---|
| **created** | Session exists but no turns yet |
| **active** | A run is in progress or about to start |
| **idle** | The last run finished; the session is waiting for the next user input |
| **archived** | The session is read-only; no new runs |
| **resumed** | An idle or archived session is back to active |
| **forked** | A new session was created from this one's history |
| **shared** | The session is accessible via URL (read-only or collaborative) |
| **exported** | The session has been serialized to a portable format |

## The Session-State Contract

Every session has:

| Field | Purpose |
|---|---|
| `session_id` | Unique identifier; stable across resumes |
| `created_at` | Timestamp |
| `last_active_at` | Updated on each turn |
| `status` | Current state from the diagram above |
| `messages` | The conversation history (the durable form of run-level context) |
| `metadata` | User, tenant, agent config snapshot, model preference |
| `permissions` | What tools and paths this session is allowed |
| `memory_refs` | Pointers to durable memory entries (not the memory itself) |
| `fork_parent` | If forked, the parent session ID |
| `share_url` | If shared, the URL and access policy |

The harness persists this contract to durable storage at every turn
boundary. A crash between turns must not lose the session.

## Create

Creating a session:

1. Allocate a `session_id`.
2. Snapshot the agent config (model, tools, permissions, instructions).
3. Initialize empty `messages`.
4. Load any session-level memory the user/agent has accumulated.
5. Persist to durable storage.
6. Return the session to the caller.

The config snapshot is important: if the user changes the agent's tools
or model mid-session, the session still knows what it was created with.

## Resume

Resuming a session after an interruption:

1. Load the session by `session_id`.
2. Reconstruct the context window from `messages` (with compaction if
   needed — see `context-management.md`).
3. Re-establish tool connections (MCP servers, database handles).
4. Resume the loop from the last turn boundary.

Resume must be **idempotent**: resuming twice produces the same state as
resuming once. Resume must be **tested after crash**, not just after
clean shutdown — the two are different failure modes.

### Resume After Crash

A crash mid-turn is the hard case. The harness must:

- Detect that the session was active when the crash happened (the
  `status` field was `active`, not `idle`).
- Decide whether to retry the interrupted turn or surface the
  interruption to the user.
- **Never silently double-execute** a side-effecting tool. If the crash
  happened after a tool call was dispatched but before its result was
  recorded, the harness must check whether the side effect landed before
  retrying. This is the idempotency doctrine of the `deterministic-agents`
  skill, applied at the session layer.

## Fork

Forking creates a new session with a copy of the current session's
history up to the fork point. After the fork, the two sessions diverge.

Use cases:

- "What if I had taken a different path at turn 3?" — fork at turn 3,
  explore the alternative.
- "Run this same task with a different model." — fork, swap the model,
  compare results.
- "Branch this conversation for a different team member." — fork, share
  the fork.

The fork parent is recorded in the new session's `fork_parent` field.
Forks are cheap because they share the immutable history; only the new
turns after the fork are unique to each session.

## Share

Sharing a session produces a URL that others can use to view (or
collaborate on) the session. The harness must:

- Decide the access policy (read-only, comment, full edit).
- Redact secrets from the shared view (the transcript may contain
  credentials that the original user could see but the share recipient
  should not).
- Set an expiry (shared sessions should not live forever by default).
- Log the share event for audit.

## Export

Exporting serializes the session to a portable format:

| Format | Use case |
|---|---|
| JSON | Programmatic replay; import into another harness |
| Markdown | Human-readable transcript; documentation |
| Trace (OTel) | Observability; replay in an eval harness |

Export must include the full trajectory (every tool call, every result),
not just the visible text — otherwise the export cannot be replayed.

## End

Ending a session:

1. Finalize any pending tool calls (or abort them).
2. Write a session summary to durable memory (optional; the model may
   be asked to produce this).
3. Mark the session `archived`.
4. Retain per the retention policy (e.g., 90 days) then delete or
   anonymize.

## Session Persistence Backends

| Backend | Use case |
|---|---|
| In-process (dict) | Dev only; dies with the process |
| SQLite | Single-host production; zero-ops |
| Postgres | Multi-host production; transactional |
| Redis | High-throughput; TTL-native |
| S3 / blob | Archive; cold storage |

The harness abstracts the backend behind a session store interface.
Switching backends is a config change, not a code change.

## Session-Level vs Run-Level

The distinction matters:

- A **run** is one invocation of the agent loop (one user message → one
  agent response, possibly with many tool calls in between).
- A **session** is the container of many runs over time.

Run-level state (the active context window, the current tool dispatch)
lives in memory. Session-level state (the message history, the metadata)
lives in durable storage. The harness writes run-level state to
session-level storage at every turn boundary.

## Cross-References

- `agent-loop.md` — what a run looks like inside a session.
- `context-management.md` — how the context window is managed within
  and across runs.
- `harness-observability.md` — session-level spans and trace export.
- `memory-rag` skill — long-term memory that persists across sessions
  (longer-lived than session state).

## Pitfalls

1. **In-process-only sessions in production.** The process crashes; the
   user loses their conversation. Fix: durable persistence at turn
   boundaries.
2. **No status field.** The harness cannot tell whether a session was
   active or idle when a crash happened. Fix: explicit `status` field,
   updated before each run starts and after it ends.
3. **Double-execution on resume.** A tool call was dispatched; the
   crash happened; the resume retries the tool. Fix: check-then-act
   idempotency for every side-effecting tool.
4. **Secrets in the shared view.** The transcript contains an API key;
   the share recipient sees it. Fix: redact before sharing; audit the
   redaction.
5. **No fork-parent tracking.** Forked sessions lose the link to their
   parent; lineage is gone. Fix: record `fork_parent` at fork time.
6. **Export without trajectory.** The export has the visible text but
   not the tool calls; it cannot be replayed. Fix: export the full
   trajectory, not just the messages.
