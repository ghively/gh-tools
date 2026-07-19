# Security Audit Record

<!-- Written by /agent-foundry-security-audit-agent (delegated to the
     agent-foundry-security-auditor subagent). Read by
     /agent-foundry-ship-check. The audit is read-only — the subagent
     never applies fixes; humans and pipelines do, after approval. -->

**Target:** <agent project path or repo>
**Audit type:** <my-agent-project | third-party-extension>
**Version audited:** <git SHA, plugin version, image digest>
**Date:** <YYYY-MM-DD HH:MM TZ>
**Auditor:** <subagent session ID; "agent-foundry-security-auditor">
**Verdict:** <SAFE | SAFE-WITH-CHANGES | DO-NOT-INSTALL | DO-NOT-SHIP>
**Open critical/high findings:** <count> (must be 0 for ship-check to pass)

## Threat Model

<One paragraph. Who can send input? What is the worst acceptable
outcome? Which content is untrusted? Stated assumptions go here.>

## Attack Surface

<Enumerate: tools, external connections, data flows an adversary could
reach. Reference the design.md Tools and Authority tables for a
first-party agent; enumerate extension surfaces for a third-party
extension.>

## Findings (ranked by severity)

For each finding: severity (CRITICAL / HIGH / MEDIUM / LOW), the fail
mode, the blast radius, the evidence (file:line), and the fail-closed
remediation.

| # | Severity | Finding | Blast radius | Evidence | Remediation |
|---|---|---|---|---|---|
| 1 | CRITICAL | <e.g., secret in commit history> | <e.g., key rotation required> | `path/file:line` | <the smallest change that closes it> |
| 2 | HIGH | ... | ... | ... | ... |

## Per-Domain Checklist

Mark each domain "CLEAN" or "FINDINGS" (cite the finding row above):

- [ ] **Secret handling** — credentials in env/vault only; no plaintext in code/config/logs
- [ ] **Prompt-injection paths** — untrusted content marked as data; tool results sanitized
- [ ] **Tool policy** — least-privilege allowlist; destructive tools gated by HITL
- [ ] **Safety floor** — never-run primitives blocked deterministically; audit log active
- [ ] **Permission rules** — default-deny; narrow allows; ask/deny on sensitive surfaces
- [ ] **Dependencies** — pinned versions; no known CVEs in the lockfile
- [ ] **Config posture** — secrets redacted in logs; debug modes off in production
- [ ] **Multi-tenant isolation** (if applicable) — per-tenant boundaries enforced
- [ ] **Audit trail** — every tool call logged with operator identity and timestamp
- [ ] **Supply chain** (third-party extensions) — vetted source; permissions match claims

## Remediation Plan (ordered by risk-reduction-per-effort)

For each open finding, the ordered plan. Do NOT apply fixes here — the
audit produces the plan; humans and pipelines apply, after approval.

1. **<finding #N>** — fix: <one-line>; verification: <eval case or smoke step>
2. **<finding #N>** — ...

## Re-audit Triggers

The audit is clean as of this version. Re-audit when:
- A dependency or tool-surface change lands (re-audit before ship-check).
- A new MCP server, plugin, or third-party tool is registered.
- The threat model shifts (new data source, new user population).
- Quarterly (the ceiling — even with no changes, re-audit on schedule).

## Run Record

- **Subagent session:** <ID>
- **Span export:** <OTel trace ID or artifact path>
- **Audit log reviewed:** <path to safety-audit.log entries for this session>
