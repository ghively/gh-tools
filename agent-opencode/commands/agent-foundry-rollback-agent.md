---
description: Roll back a deployed agent — restore code, prompt, model, tool, memory, and config to the last known-good manifest; verify.
agent: build
---

Roll back the agent at `$ARGUMENTS`. Active incident or strongly
suspected regression — restore known-good behavior first, diagnose
later.

Load `agent-deployment` (especially `versioning-rollout.md`,
`operating-live-agents.md`). Process:

1. **Confirm rollback is the right move.** Roll back when:
   - The agent is failing live user requests.
   - A safety event is in progress (BLOCK storm, prompt-injection
     landing, data exfil suspected).
   - The failure is high-severity and the fix is not 15 minutes away.

   Do NOT roll back for:
   - A flaky eval (route to debug).
   - A user complaint about tone (route to tweak).
   - Planned maintenance (use versioning-rollout's canary).

2. **Identify the last known-good version.** From the versioning
   manifest (see `versioning-rollout.md`), the last green ship-check
   is the target. Record:
   - Git SHA of the code.
   - Model IDs (frontier + small).
   - Tool versions (especially MCP servers).
   - Prompt hash.
   - Memory snapshot (if applicable).

3. **Restore the manifest atomically.** A partial rollback is a new
   failure mode. Restore:
   - Code: redeploy the previous image / checkout the previous SHA.
   - Config: previous `opencode.json` / `config.yaml`.
   - Model IDs: explicit pin (not aliases).
   - Tools: previous MCP server versions; previous tool schemas.
   - Memory: roll back the memory store to the snapshot if memory
     corruption is the suspect.

4. **Verify.** Run `/agent-foundry-smoke-test` against the rolled-back
   version. If smoke passes, the system is back to known-good.

5. **Communicate.** The incident report needs:
   - What was rolled back (version A → version B).
   - Why (the symptom that triggered rollback).
   - When (timestamp).
   - Who authorized.
   - Follow-up (debug + fix + re-release timeline).

6. **Reserve diagnosis for after stability.** The rolled-back system
   is now serving users correctly. Diagnosis of the failed version
   happens in staging against a captured reproduction — see
   `/agent-foundry-debug-agent`.

7. **Re-release with canary.** When the fix is ready, do NOT
   roll-forward to the previously-failed version. Cut a new release
   with the fix; canary it; watch the eval suite; ship-check the
   canaried version.

Report: the rollback manifest (from / to), smoke-test verdict on the
rolled-back version, and the next-step timeline for diagnosis and
re-release.