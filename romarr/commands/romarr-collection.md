---
description: Plan and run a DAT-based (No-Intro/Redump) set-completion batch for a platform, with the user's go-ahead before queueing anything.
argument-hint: (optional) platform or DAT name
allowed-tools: mcp__romarr__romarr_collections, mcp__romarr__romarr_collection_plan, mcp__romarr__romarr_collection_start, mcp__romarr__romarr_collection_step, mcp__romarr__romarr_collection_control
---

Run a guided collection (set-completion) job.

1. `mcp__romarr__romarr_collections` — see batches already in progress and
   which DATs are available to plan against. If `$ARGUMENTS` names a
   platform/DAT, match it against this list; if ambiguous or empty, ask.
2. `mcp__romarr__romarr_collection_plan` with the chosen DAT/platform —
   read-only comparison: expected vs. present vs. missing, with the reason
   each dump won its group. If this errors "no DAT loaded", tell the user
   plainly and stop (Settings, or point `DAT_PATH` at a No-Intro/Redump
   directory) — do not guess a workaround.
3. Summarize the plan: how many missing, a sample of titles, estimated
   scope. Ask the user to confirm before queueing — a full-platform DAT can
   mean dozens to hundreds of downloads.
4. Only after explicit approval: `mcp__romarr__romarr_collection_start`
   with `confirm=true` to queue the batch.
5. To advance an existing batch: `mcp__romarr__romarr_collection_step`
   (confirm=true) requests the next slice.
6. To manage a running batch: `mcp__romarr__romarr_collection_control`
   (confirm=true) with action pause/resume/retry/cancel — confirm which
   action and which batch with the user before calling.

Never call `romarr_collection_start` speculatively "to see what happens" —
it queues real downloads, potentially many.
