---
description: Operate a deployed agent — verify health, review the audit trail, surface anomalies, decide on tweaks vs incidents.
agent: build
---

Operate the agent at `$ARGUMENTS`. Daily / weekly operating discipline
for a live agent that has passed ship-check.

Load `agent-deployment` (especially `operating-live-agents.md`,
`tweaking-live-agents.md`, `observability.md`). Process:

1. **Health verification.**
   - Hit `/health`; confirm 200 with no recent restarts.
   - Check provider quotas (ZAI console, etc.) for spend against budget.
   - Check container stats: CPU, memory, disk for the state volume.
   - Check the safety-audit.log for recent `BLOCK` rows — each is a
     real signal of intent or compromise.

2. **Trajectory review.** Pull the last N runs from the trace system
   (Langfuse / Phoenix / LangSmith / OTel collector). Spot-check:
   - Did any run hit the step cap? (Doom-loop symptom.)
   - Did any run hit the cost cap? (Runaway symptom.)
   - Did any run execute a destructive tool? (Permission drift.)
   - Did any run produce an unverified-success claim? (Hallucination.)

3. **Audit-trail review.** The safety-audit.log is the incident
   timeline. Look for:
   - Clusters of `PARSE_ERROR_ALLOW` after a version bump (input shape
     drift).
   - New `BLOCK` patterns not seen before (new attack vectors or new
     model behaviors).
   - `allow` rows with commands that look wrong (the model tried
     something it should not have).

4. **User-feedback triage.** Review any user complaints, support
   tickets, or session replays. Cluster by symptom; rank by frequency
   × severity.

5. **Decide: tweak, incident, or no-change.**
   - **Tweak** — small targeted fix; route to `/agent-foundry-extend-agent`
     or `/agent-foundry-debug-agent` if a behavioral change is needed.
     Use `tweaking-live-agents.md` doctrine.
   - **Incident** — active failure or safety event; route to
     `/agent-foundry-rollback-agent` and the incident-response
     playbook (`agent-safety/references/incident-response.md`).
   - **No-change** — log the review and move on. Most operating
     sessions end here.

6. **Report.** One-paragraph verdict: agent is healthy / degraded /
   broken; what was reviewed; what action (if any) was taken; what
   should be re-checked next time.

Operating discipline is the boring 90% of agent engineering. The
pipeline got the agent shipped; this command keeps it trustworthy.