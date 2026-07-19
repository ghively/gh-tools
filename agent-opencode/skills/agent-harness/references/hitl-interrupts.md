# Human-in-the-Loop Interrupts at the Harness Layer

The harness owns the interrupt mechanism. The model proposes an action;
the harness decides whether to execute immediately, ask for approval,
or deny. This is distinct from prompt-level guidance ("ask before
deploying") — the harness enforces structurally.

## Interrupt Points

| Point | When | Mechanism |
|---|---|---|
| **Pre-tool** | Before a tool call dispatches | Harness checks the call against permission policy; pauses if needed |
| **Post-tool** | After a tool returns, before the model sees the result | Harness reviews the result; can redact or block |
| **On-signal** | When a specific condition is met (cost threshold, step count) | Harness pauses proactively |
| **User-initiated** | User sends a follow-up while the agent is working | Harness queues or steers |

The pre-tool interrupt is the primary safety mechanism. The harness
gates destructive tools here, independent of model judgment.

## The Pre-Tool Interrupt Flow

```
Model emits tool call
        │
        ▼
Harness checks permission policy
        │
        ├── allow ──► dispatch immediately
        │
        ├── ask ────► pause; surface to user; await verdict
        │                  │
        │                  ├── approve ──► dispatch
        │                  ├── deny ─────► append denial to context; model adjusts
        │                  └── modify ───► dispatch with modified args
        │
        └── deny ───► append denial to context; model adjusts
```

The interrupt is synchronous from the loop's perspective: the loop is
paused while awaiting the verdict. The harness does not spin; it yields
and resumes when the verdict arrives.

## Interrupt UX

When the harness interrupts, it shows the user:

1. **What** the model wants to do (the tool name and arguments).
2. **Why** (the model's stated reason, if any).
3. **Blast radius** (what happens if this executes).
4. **The decision** (approve / deny / modify).

The 30-second rule: the user should be able to decide in 30 seconds.
If the interrupt requires more research, the tool surface is too broad.

See `agent-design/references/human-in-the-loop.md` for the design
doctrine; this reference covers the harness implementation.

## Permission Policy at the Harness Layer

The harness's permission policy is layered:

1. **Global rules** (from `opencode.json`): always-on, apply to every
   session.
2. **Session rules** (from session metadata): per-session overrides.
3. **Tool-level rules** (from tool annotations): the tool declares its
   own destructiveness.
4. **Runtime rules** (from the deterministic safety floor): code-enforced
   denials the model cannot override.

Each layer can only tighten, never loosen, the layer above. A session
rule can deny a globally-allowed tool, but cannot allow a
globally-denied one.

## The Verdict Surface

When the user approves/denies, the harness:

1. Records the verdict in the transcript (audit trail).
2. Either dispatches the tool or appends a denial to context.
3. Emits a span for the interrupt and its resolution.

The denial message to the model is structured: "Tool X was denied by
the user. Reason: <provided reason>." The model can then adjust (try a
different approach, ask for clarification, or accept the constraint).

## Async Interrupts (Steering)

Some harnesses support async interrupts — the user sends a message
while the agent is mid-run:

| Mode | Behavior |
|---|---|
| **Queue** | The message waits; delivered after the current turn |
| **Steer** | The message interrupts the current turn; the model sees it before the next tool call |
| **Cancel** | The message cancels the current run; a new run starts |

Steer mode is the most powerful but the hardest to implement. The
harness must check for queued user messages at each loop step and
inject them.

## Cost and Step Interrupts

The harness can proactively interrupt when:

- The run exceeds a cost threshold.
- The run exceeds a step count.
- The doom-loop detector fires.

These interrupts surface to the user as "the harness paused this run
because <reason>." The user can resume, adjust, or abort.

## Session Resume with Pending Interrupts

If a session is saved with a pending interrupt (the harness was waiting
for user approval when the process died), the resume must:

1. Detect the pending interrupt.
2. Surface it to the user again.
3. Not auto-dispatch the tool (the user never approved).

## Pitfalls

1. **Prompt-level approval only.** "Always ask before deploying" in
   the system prompt; the model deploys anyway. Fix: harness-level
   pre-tool interrupt; the model cannot bypass.
2. **No audit trail for verdicts.** The user approved; no record.
   Fix: every verdict is a span in the transcript.
3. **Async interrupts that lose work.** The user steers mid-run; the
   current tool's work is discarded. Fix: steer mode checks for
   interrupts at turn boundaries, not mid-tool.
4. **Auto-dispatch on resume.** The session resumes; the pending
   approval is forgotten; the tool fires. Fix: pending interrupts
   are part of session state; resume re-surfaces them.
5. **Interrupt without context.** "Approve tool call?" with no detail.
   Fix: show what, why, blast radius.
6. **Modify mode that breaks invariants.** The user modifies the args;
   the modified args violate the tool's schema. Fix: validate modified
   args against the schema before dispatch.
