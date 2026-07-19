# Conversion Runtime Matrix

Reference matrix for choosing where a converted agent runs. Retained for
cross-host migrations; OpenCode work runs inside OpenCode itself.

## Candidate Runtimes

AWS AgentCore, Google Vertex Agent Builder, Azure AI Foundry, LangSmith
Agent, Cloudflare Agents, Temporal, managed agent platforms, self-hosted,
and GitHub Actions are the common candidates.

For each, record:

- Hosting model (managed, self-hosted, ephemeral).
- Auth and secret handling (env, OAuth, vault).
- Observability surface (logs, traces, metrics).
- Cost model (per-invocation, per-hour, per-token).
- Lock-in ledger (exit cost: data export, rewrite effort, vendor-specific
  surfaces).

## Selection

Pick against:

1. The capability profile from `plugin-capability-audit.md`.
2. The lock-in tolerance of the owner.
3. The operational story required (alerts, rollback, on-call).

## OpenCode-Specific

If the target runtime is OpenCode, this matrix collapses: install the
plugin, register skills, and run. The interesting runtime question for
OpenCode is which provider and model tier backs each agent, which is covered
by the `model-selection` skill.
