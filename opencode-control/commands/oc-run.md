---
description: Run a coding task through opencode (ACP by default) — $ARGUMENTS is the task
---

Run this task through opencode: **$ARGUMENTS**

Use the `opencode` MCP server. Default to the **ACP connector** (`oc_acp_prompt`) since it
needs no running server and returns a full transcript.

1. Determine the project directory (`cwd`). If the user didn't say, ask, or use the current
   project. `cwd` must be absolute.
2. If the task is **analysis/planning only** (explain, review, plan, summarize), run
   read-only: `oc_acp_prompt(prompt=<task>, cwd=<dir>)` — permission defaults to `reject`,
   no confirmation needed. For a design pass, add `mode="plan"`.
3. If the task requires **editing files or running commands**, first confirm with the user
   that opencode should make changes, then call
   `oc_acp_prompt(prompt=<task>, cwd=<dir>, permission="allow", confirm=true, timeout=600)`.
4. Report the transcript: reply text, any tool calls, files written, plan, and token usage.
   If files were changed, show the diff (`oc_vcs('diff')` or git) so the user can review.

If the user specifically wants the work to happen inside their **running** opencode server
(shared sessions/TUI) instead, use `oc_prompt` against a session instead of ACP.
