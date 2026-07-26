# Events & context/compaction management

The event system (observe opencode) and compaction/context tuning (control cost on long
sessions). Verified against `anomalyco/opencode` source. `oc_events(seconds)` tails the bus;
compaction is configured via `oc_config_update`.

## The three event streams — pick the right one

- **`GET /event`** (this plugin's `oc_events`) — **instance/directory-scoped**; the stable,
  fully-populated stream. Use this for normal automation. Emits `server.connected` on
  connect and `server.heartbeat` every **10s**; ends on `server.instance.disposed`.
- **`GET /global/event`** — cross-instance, **unfiltered**; use only to supervise multiple
  opencode instances from one process. Carries global-only events (e.g. `installation.updated`).
- **`GET /api/event`** — the newer **experimental** v2 stream; **incomplete** — it does NOT
  carry `session.idle`, `permission.asked`, `message.*`, or `command.executed` in current
  builds, and its heartbeat is a raw SSE comment every 15s. **Don't build on it yet.**

Every event is `{ id, type, properties }` (SSE) / `{ id, type, data }` (internal).

## Event catalog (the v1 stream the SDK/plugins actually see)

- **session**: `session.created`, `session.updated`, `session.deleted`, `session.diff`,
  `session.error` (tagged union: `AuthError`, `ContextOverflowError`, `APIError`,
  `ContentFilterError`, `AbortedError`, …), `session.status` (`{status: idle|busy|retry}`),
  `session.idle` (turn finished), `session.compacted`.
- **message**: `message.updated`, `message.removed`, `message.part.updated` (streams tool
  `pending→running→completed/error` + text/reasoning growth), `message.part.removed`.
- **permission**: `permission.asked`, `permission.replied`. **question**: `question.asked`,
  `question.replied`, `question.rejected`.
- **files**: `file.edited`, `file.watcher.updated` (`add|change|unlink`). **vcs**:
  `vcs.branch.updated`. **todo**: `todo.updated`. **command**: `command.executed`.
- **infra**: `mcp.tools.changed`, `lsp.updated`, `pty.created|updated|exited|deleted`,
  `project.updated`, `installation.updated|update-available`, `models-dev.refreshed`,
  `catalog.updated`, `reference.updated`, `plugin.added`, `tui.*`, `workspace.*`, `worktree.*`.

### Which events matter for automation
- **`session.idle`** — the turn is done; safe to read final messages / notify. (The wait
  signal for `promptAsync`.)
- **`message.part.updated`** — the only way to watch streaming tool activity; **de-dupe by
  `callID`** (it fires repeatedly as a part updates).
- **`permission.asked`** (observe) vs the synchronous **`permission.ask` hook** (a plugin can
  flip `output.status` to auto-allow/deny — this is the control point, not the event).
- **`session.error`** — provider/auth/context-overflow failures; a monitor should treat
  repeated `session.status: retry` as a leading indicator to compact before overflow.

## Compaction internals

Auto-compaction fires on a **token threshold, not a turn count**: when the last turn's total
tokens reach `model.limit.input − reserved`. Config block (`compaction` in opencode.json):

| Knob | Default | Effect |
|---|---|---|
| `auto` | `true` | master switch for automatic compaction (`/compact` still works if off) |
| `prune` | `false` | enable a **free, no-LLM** pass that marks old completed tool outputs as compacted |
| `tail_turns` | `2` | recent user turns (with their responses) kept **verbatim**, not summarized |
| `preserve_recent_tokens` | `clamp(0.25×usable, 2000, 8000)` | token budget for those tail turns |
| `reserved` | `min(20000, model max output)` | headroom subtracted before "usable" is computed (safety margin vs overflow) |

`prune` internals (not configurable): protects the newest ~40k tokens of tool output and the
`skill` tool's output, and only commits if it can reclaim ≥20k tokens. Manual `/compact` =
`POST /session/{id}/summarize` with `auto:false` — and manual compaction does **not** trigger
the synthetic continue turn (below).

## The two compaction hooks (plugins)

- **`experimental.session.compacting`** `(input, {context:[], prompt?})` — append strings to
  the summarization prompt, or replace it entirely. Use it to inject durable project memory
  (a living spec/`memory.md`) into every summary so critical facts survive indefinitely.
- **`experimental.compaction.autocontinue`** `(input, {enabled:true})` — **⚠️ cost gotcha**:
  after an auto-compaction opencode silently inserts a synthetic user "continue?" turn, which
  **spends one more model call**. In scripted/batch automation, return `{enabled:false}` to
  suppress it.

## Other context-cost levers

- **`tool_output`**: `max_lines` (default 2000), `max_bytes` (default 51200). When exceeded,
  the full output spills to a truncation dir (7-day retention) and the model sees a head/tail
  preview + a hint to `Read`/`Grep` the file. Lower these to shrink verbose tool contributions.
- **`attachment.image`**: `auto_resize` (true), `max_width`/`max_height` (2000),
  `max_base64_bytes` (5 MB).
- **`opencode-dynamic-context-pruning` (DCP)** — a third-party plugin that rewrites the
  model-facing request (replacing stale tool outputs with compressed summaries, dropping
  duplicate/errored-call inputs) while leaving on-disk history intact. Runs alongside core
  compaction at a different layer — if you run both, the model may see a request meaningfully
  smaller than core token telemetry reports.
- Note: `experimental.aggressive_truncation` is an **oh-my-openagent config flag, NOT core
  opencode** — it doesn't exist in core source. Don't set it expecting core to honor it.

## Tuning cookbook

**Minimize cost on long sessions:**
```json
{ "compaction": { "auto": true, "prune": true, "tail_turns": 1, "preserve_recent_tokens": 3000, "reserved": 12000 },
  "tool_output": { "max_lines": 400, "max_bytes": 16384 } }
```
Plus a plugin returning `{enabled:false}` from `experimental.compaction.autocontinue`.

**Preserve important context:**
```json
{ "compaction": { "auto": true, "prune": false, "tail_turns": 4, "preserve_recent_tokens": 8000 } }
```
Plus `experimental.session.compacting` injecting a durable memory doc.

**Avoid mid-task compaction surprises:** compaction triggers on tokens, so a single huge
un-truncated tool output can trip it mid-task — keep `tool_output` limits conservative, raise
`reserved` for big-context models, watch `session.status: retry` and `/compact` manually at
natural checkpoints (e.g. after `todo.updated` shows a phase done) rather than reacting.
