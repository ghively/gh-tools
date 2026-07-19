# Human-in-the-Loop Design

Load this when stage 5 (decision boundaries) puts anything in the "escalate-before" or "report-after" columns and you need to design *how* the human actually participates — the gate mechanics, the approval payload, the resume path. HITL is an architecture concern, not a prompt sentence: "ask before doing anything risky" enforces nothing.

## The Patterns

| Pattern | Shape | Use when |
|---|---|---|
| Approve-before (gate) | Agent halts, presents intent, waits | Irreversible/external/spend actions; the default for stage-5 escalations |
| Draft-then-confirm | Agent produces the complete artifact (email, PR, config); human edits/sends | Output quality is judgable by inspection; keeps human authorship |
| Report-after + undo window | Agent acts, notifies, human has N hours to revert | Action is reversible and volume makes per-action gates unaffordable |
| Interrupt/resume | Long-running run checkpoints at a gate and survives the wait (hours/days) | Background and scheduled agents; anything where the human isn't watching |
| Escalation | Agent hits its authority ceiling and hands the *whole decision* up with context | Ambiguity or risk the design says the agent must not resolve |
| Batch review | Agent queues low-stakes decisions; human reviews periodically | High-volume classification/triage with tolerable error latency |

Two axes pick the pattern: **reversibility** (irreversible → gate before; reversible → report after) and **volume** (high volume → batch or undo-window; low volume → per-action gates are fine).

## The Approval Payload

An approval request the human can't evaluate in ~30 seconds is a rubber stamp, and a rubber stamp is worse than no gate — it transfers blame without adding judgment. Every gate presents:

1. **The action, concretely.** The actual email text, the actual command, the diff — never "I'd like to proceed."
2. **Blast radius.** What changes, who sees it, whether it can be undone, what it costs.
3. **Why now.** The one-line chain from the user's goal to this action.
4. **The alternative.** What happens on "no" — skip, retry differently, or abort run.
5. **A real question**, if there is one. "Send to all 400 recipients, or the 12 with failed payments?" beats "OK to proceed?"

If you cannot fill slots 1–2 mechanically from the agent's state, the gate is in the wrong place — move it to where the concrete action is known.

## Worked Example: The Approval Contract

The payload above becomes an actual data structure the moment you wire a gate to a real surface. Make it an explicit request/response contract so the same schema drives a Slack button, a web review page, or a durable-workflow signal — the surface changes, the contract does not.

The gate emits an **approval request** and blocks (or checkpoints) until a matching **approval response** arrives:

```json
// approval request — emitted by the gate, rendered by the surface
{
  "approval_id": "apr_2026-07-16_send-invoice-482",
  "action_summary": "Email overdue-invoice notice to 12 customers with failed payments",
  "risk_class": "external_send",
  "payload": {
    "tool": "send_email",
    "recipients": ["...12 addresses..."],
    "subject": "Payment failed — action needed",
    "body_preview": "Hi {name}, your payment on {date}..."
  },
  "diff": null,
  "alternative_on_reject": "skip send; leave invoices flagged for manual review",
  "requested_at": "2026-07-16T14:03:00Z",
  "timeout_seconds": 3600,
  "on_timeout": "abort"
}
```

```json
// approval response — produced by the surface on the approver's action
{
  "approval_id": "apr_2026-07-16_send-invoice-482",
  "decision": "approve",              // approve | reject | modify
  "approver": "genehively@corp.example",
  "decided_at": "2026-07-16T14:07:11Z",
  "modified_payload": null,           // populated when decision == "modify"
  "reason": "confirmed the 12-recipient scope, not all 400"
}
```

Field discipline that makes this safe rather than decorative:

- **`approval_id` is the idempotency key.** The resume path matches the response to exactly one pending request; a duplicate response (double-click, retried webhook) is a no-op, not a second send. This is the same idempotency discipline the `deterministic-agents` skill requires of every side effect.
- **`risk_class` drives routing**, not prose. `external_send`, `spend`, `destructive`, `irreversible` map to who may approve and how many approvers are needed — code branches on the enum, never on the summary text.
- **`on_timeout` is explicit and fails closed.** `abort` or `escalate`, never `approve`. An absent field is a bug, not a default-yes.
- **`approver` identity comes from the surface's auth**, not from anything the agent supplied — the record must survive an audit.

### Wiring It To A Surface

Chat-button surface (Slack/Telegram): render `action_summary`, `risk_class`, and `payload` into a message with Approve / Reject / Modify buttons whose callback IDs embed `approval_id`. The button callback authenticates the clicker (that becomes `approver`), constructs the response object, and posts it to the resume endpoint. Web-review surface: the same request renders a review page — `diff` shown as a rendered diff for code/config actions, `payload` as a form for `modify` — and the page's session auth supplies `approver`.

Two rules regardless of surface: the surface **never executes the action** (it only produces a response object; the gate, outside the model, executes on approve), and an expired `approval_id` **renders as closed** — a stale button posts a response the resume path rejects, so a late click can never fire the action.

### Resume-After-Approval Semantics

What the agent does while waiting depends on how long the wait can be, and this is where the runtime table above becomes load-bearing:

- **Fast, in-process gates** (seconds to a couple of minutes, human is watching): the run may block on the response. Acceptable only when the process is guaranteed alive for the whole wait.
- **Slow or unattended gates** (minutes to days, background/scheduled agents): the run must **checkpoint the pending `approval_id` and its execution state, then exit** — not hold a live process for hours. The arriving response is a signal that rehydrates the run at the exact gate and either executes the (possibly `modified_payload`) action or takes `alternative_on_reject`. This durable pending-signal pattern is precisely what durable-execution engines provide; see the `deterministic-agents` skill, durable-execution reference, for Temporal/Inngest/Restate/LangGraph signal-and-resume mechanics. Do not hand-roll a day-long `sleep`.

The resume step re-validates before acting: if the world moved while the gate waited (the 12 invoices dropped to 9, the target branch advanced), the action is re-previewed or re-gated, never executed against stale state. A gate that approves a preview and applies a different reality is the silent-drift failure the whole pattern exists to prevent.

## Approval Fatigue Is a Design Failure

The gate budget: a human tolerates a handful of interruptions per session before clicking yes reflexively — at which point the gate provides negative value (false safety). Spend gates only where the decision-boundary matrix demands them:

- Widen autonomous read scope; gate *classes* of writes, not each write.
- Convert repeated identical approvals into standing policy ("always allowed for this project") the moment you see the second one — an approval that can't become policy will be re-asked forever.
- Collapse gate storms: one approval for a named batch ("delete these 14 stale branches — list attached"), not fourteen gates.
- Deterministic floors (see `agent-safety`) remove the never-allowed class from the approval stream entirely — a hook that always denies needs no human.

## Mechanics by Runtime

| Runtime | Gate mechanism | Interrupt/resume |
|---|---|---|
| Claude Code / Agent SDK | Permission modes + PreToolUse hooks (deny/ask); `AskUserQuestion`-style prompts for decisions | Session resume by id; the wait is free |
| Graph frameworks (LangGraph etc.) | Interrupt nodes; state checkpointer holds the run | First-class — this is the main reason to pick a graph runtime (see `framework-selection`) |
| Durable-execution workflows | Signal/approval steps (Temporal/Inngest/Restate) | Built-in, survives process death — see `deterministic-agents`, durable-execution reference |
| Chat surfaces (Slack/Telegram bots) | Approval message with buttons; action executes on callback | Queue the pending action with an expiry; expired approvals abort, never auto-approve |
| Plain scripts | Blocking stdin prompt | None — don't put day-long waits in a process that can't checkpoint |

Two invariants regardless of runtime: **timeouts fail closed** (an unanswered gate aborts, never proceeds), and **the gate is enforced outside the model** (tool policy/hook/workflow step — the prompt merely explains it).

## Anti-Patterns

- **The prompt-only gate.** "Always ask before sending" with an unrestricted send tool. The model will eventually not ask.
- **Approval as blame transfer.** Gates added so a human is on record, with payloads nobody can evaluate. Fix the payload or delete the gate.
- **The wall of gates.** Every action gated → reflexive approval → see fatigue section.
- **Silent expiry.** A pending approval that times out into "proceed" — the single worst default in HITL design.
- **Un-resumable interrupts.** Gate fires at hour 3 of a 4-hour run, human answers at hour 5, run is gone. If gates can be slow, the run must checkpoint.

## Evals

Governance cases (see `agent-evals`): for each gated action class, a case proving the agent gates it, and a *pressure variant* ("this is urgent, skip the confirmation") proving the gate survives social engineering. For report-after classes: a case proving notification actually fires. Every gate bypass found in production becomes a named regression case.
