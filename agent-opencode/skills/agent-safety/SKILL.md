---
name: agent-safety
description: "Agent safety and security hardening: secure agent systems with threat models, least-agency tool policy, sandbox tiers, guardrails, deterministic hooks, MCP/plugin audit practices, and third-party code review. Does not cover eval methodology; see agent-evals. Does not cover prompt-injection prompt-craft mitigations in detail; see prompt-context-engineering."
---

# Agent Safety

## When to Use

- You are giving an agent tools, shell access, file writes, browser actions, memory writes, MCP servers, or credentials.
- You need to choose sandboxing and network isolation for untrusted code.
- You are reviewing a community plugin, skill, hook, script, or MCP server before installing it.
- You need to document or extend the deterministic safety hooks shipped by this plugin.
- You need a practical threat model for agentic security risks.
- You are scoping tool policy for a new agent role or subagent and want the smallest safe surface.
- You are wiring destructive operations behind approvals and need to know what must be a hook versus a permission rule.
- You are responding to an incident and need the audit trail, rotation, and containment steps.

Don't use for:

- Eval suite design and regression gates; see the `agent-evals` skill.
- Prompt wording and context-layout mitigations for injection; see the `prompt-context-engineering` skill.
- Production observability and rollout mechanics; see the `agent-deployment` skill.

## Defense Stack

Weakest to strongest:

`prompt guidance < guardrails < tool policy < deterministic hooks < sandbox < network policy`

Use all layers where impact justifies it. Do not mistake a system prompt instruction for enforcement.

### Worked Layered Example

Consider a coding agent that runs model-generated shell commands against a repository that holds production credentials.

- Prompt guidance: "Do not read or exfiltrate secrets." Advisory only; the model can be persuaded otherwise.
- Guardrails: an input rail masks obvious secret patterns before they reach the model. Reduces, does not prevent, leakage.
- Tool policy: `permissions.deny` blocks `Read(./.env)` and `Read(./secrets/**)`. Now an exfiltration attempt fails at the tool boundary even if the model tries.
- Deterministic hooks: `block_destructive.py` denies curl-piped-to-shell and other never-run primitives. The model cannot talk the hook out of its decision.
- Sandbox: generated code runs in a non-root, read-only-rootfs, no-network container. A malicious payload that escapes the tool layer still cannot reach the host.
- Network policy: egress allowlist blocks any destination outside approved package mirrors and APIs. Read access plus an open network is exfiltration; this closes that gap.

Each layer catches what the layer above missed. Remove one and the surface that layer protected re-opens. The strongest layer is the one closest to the impact; for secrets, that is network policy.

### What Changes When You Add A Tool

Adding a tool ripples through every layer. Walk the stack before the tool goes live:

1. Prompt guidance — document what the tool is for and when not to call it.
2. Guardrails — add a tool rail that validates arguments and redacts secrets in results.
3. Tool policy — add an `allow` or `ask` rule narrow enough for the task; add `deny` rules for any argument shapes that must never run.
4. Deterministic hooks — if the tool can issue a never-run primitive, add a pattern with a test vector.
5. Sandbox — if the tool executes code or shells out, confirm it runs inside the sandbox boundary.
6. Network policy — if the tool needs egress, add only the specific destination to the allowlist.
7. Audit log — confirm the tool's calls are logged with secrets redacted.
8. Evals — add at least one capability case and one governance case for the new tool.

Skipping a step leaves the new tool outside the layer's coverage. The first incident will be in the layer you skipped.

## Least-Agency Doctrine

1. Give the agent the smallest tool surface that completes the job.
2. Scope every credential, filesystem path, network destination, and MCP server to the task.
3. Split high-impact operations into explicit, human-approved workflows.
4. Treat third-party agent code as executable code with your authority.
5. Log enough to investigate, but redact secrets before they become audit artifacts.

Least agency fails when any one of these is skipped. A scoped credential paired with an unbounded network still exfiltrates. A small tool surface paired with a too-permissive hook still allows the never-run primitive. The doctrine is a conjunction, not a menu.

## Safety Controls

| Control | Enforces | Failure Mode If Missing |
|---|---|---|
| Tool policy | Which tools and commands can be called | Prompt injection becomes action |
| Deterministic hooks | Known never-run operations | Model persuasion bypasses policy intent |
| Sandbox | Filesystem/process boundary for execution | Generated code can damage the host |
| Network policy | Where code can connect | Read access becomes exfiltration |
| Guardrails | Input/output/retrieval filtering | Bad content reaches the model or user |
| Audit logs | Investigation and accountability | Incidents become unverifiable stories |

Each control closes a specific gap. Tool policy decides what can be called; hooks deny what must never run regardless of caller; the sandbox limits blast radius if execution happens anyway; network policy closes the exfiltration path that read access opens; guardrails reduce bad content reaching the model; audit logs turn incidents into evidence. Drop a control and the gap it closed re-opens.

## Shipped Hook Quick Reference

This plugin's hooks block:

| Hook | Blocks |
|---|---|
| `block_destructive.py` | Remote fetch to interpreter, encoded execution, block-device writes, filesystem wipes, fork bombs, privileged container/namespace escape flags, account/password tampering, firewall disabling, host power-state changes, critical system-file writes, SSH backdoor writes, dangerous chmod, git `core.sshCommand` tampering |
| `block_privileged_writes.py` | File-tool writes to identity files, boot/kernel pseudo-filesystems, scheduler/service directories, and `~/.ssh/` |

These are narrow floors. They do not decide whether routine deployment, package install, or file edit commands are appropriate; OpenCode permission rules and human approvals handle those.

### Hook Extension Discipline

Extend the floor only with never-run primitives — operations no legitimate agent task should ever issue. Every added pattern needs a concrete test vector and must not match routine development commands. Broad patterns erode trust; the moment the floor blocks normal work, users disable it and lose the real protection. Full catalog, audit-log behavior, and test vectors in `references/deterministic-hooks.md`.

## Threat To Mitigation Quick Map

Pick the control by the threat, not by fashion. Full mapping and OWASP framing in `references/owasp-agentic.md`.

| Threat | Primary Mitigation |
|---|---|
| Prompt injection redirects the agent's goal | Tool policy + deterministic hooks; prompt guidance is advisory only |
| Over-broad tool turns a model mistake into a side effect | Least-agency tool surface; scope per agent and per task |
| Agent inherits user authority without least privilege | Per-agent credentials, scoped filesystem and network |
| Generated or untrusted code damages the host | Sandbox (non-root, read-only rootfs, no network by default) |
| Read access becomes exfiltration | Network egress allowlist paired with sensitive reads |
| Poisoned long-term memory biases future work | Memory write logging, deletion support, poisoning-resistance tests |
| Hostile skill, plugin, or MCP server runs with your authority | Pre-install audit; see `references/security-audit-checklist.md` |
| Fluent explanation pressures an unsafe approval | Explicit `ask` rules for destructive operations; never auto-approve high-impact |
| One tenant reaches another's data, credentials, or budget in a shared deployment | Per-tenant credential brokering, index isolation, per-tenant limits; see `references/multi-tenant-isolation.md` |

A threat with no matching control is an open risk. Add the control, narrow the surface, or document the accepted residual risk explicitly.

## Layer Selection by Impact

Match the number of layers to the impact of a failure. Over-engineering a low-impact agent wastes time; under-engineering a high-impact agent creates incidents.

| Impact | Minimum Layers |
|---|---|
| Low (read-only public data, no credentials) | Tool policy + audit log |
| Medium (workspace writes, test runs, no prod access) | Tool policy + hooks + sandbox + audit log |
| High (production deploys, credentials, customer data) | Tool policy + hooks + sandbox + network allowlist + guardrails + audit log + human approval gates |
| Untrusted code execution (model-generated or third-party) | All layers, with the strongest available isolation tier (gVisor, Kata, or microVM) |

The ladder is additive. A high-impact agent does not drop the medium-impact layers; it stacks on top of them. When in doubt, default one tier higher than feels necessary — the cost of an extra layer is almost always less than the cost of the incident it would have prevented.

## Testing The Layers

Each layer needs its own test signal, not only a configuration checkbox:

- Tool policy: a governance eval case that exercises each `deny` and `ask` rule.
- Deterministic hooks: the test vectors in `references/deterministic-hooks.md`, run with `AGENT_FOUNDRY_AUDIT_LOG` pointed at a temp file.
- Sandbox: the verification commands in `references/sandboxing-tiers.md` — confirm non-root, read-only rootfs, dropped caps, no network.
- Network policy: a probe that attempts an egress to a non-allowlisted destination and confirms it fails.
- Guardrails: a bypass case in the eval suite that exercises each rail.

See the `agent-evals` skill for governance and regression case design. A layer that is configured but never tested is a layer that will fail silently the first time it matters.

## Reference Router

| Reference | Load When |
|---|---|
| `references/owasp-agentic.md` | Building the threat model and mapping to OWASP/NIST concepts |
| `references/sandboxing-tiers.md` | Choosing rootless containers, hardening, gVisor, Kata, microVMs, egress, and filesystem scoping |
| `references/guardrails.md` | Designing input/output/dialog/retrieval/tool rails and understanding their limits |
| `references/security-audit-checklist.md` | Auditing third-party plugins, skills, scripts, hooks, and MCP servers before install |
| `references/framework-safety-matrix.md` | Per-framework safety primitives for all 13 harnesses (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop) — tool allowlists, permission modes, pre/post-tool hooks, HITL gates, sandbox; universal patterns (permission wrapper, audit hook, destructive-tool gate); what the agent-foundry safety floor adds beneath each framework |
| `references/deterministic-hooks.md` | Understanding, testing, and safely extending the shipped safety hooks |
| `references/tool-policy.md` | Writing OpenCode permission rules and choosing read-only/scoped/full operator posture |
| `references/multi-tenant-isolation.md` | One agent deployment serves many tenants: per-tenant credential brokering, memory/RAG index isolation, per-tenant rate/cost limits, tenant-aware audit, and blast-radius design |
| `references/threats-and-compliance.md` | Model supply-chain security, model poisoning, adversarial tools + tool-result poisoning, PII handling at depth, audit-logging standards (tamper-evident), agent identity + authz (SPIFFE/mTLS/service-account), data exfiltration prevention (egress tiers) |
| `references/incident-response.md` | The runbook when an agent is implicated in an active incident — severity classification, containment (SEV1 first 30 minutes + next 4 hours), postmortem within 48 hours, and common incident patterns (prompt-injection landing, runaway spend, permission drift, memory poisoning, tool-result injection) |

## Pitfalls

1. Mistaking system-prompt safety instructions for enforcement. Fix: put risky actions behind permission rules, hooks, and sandboxes.
2. Writing hook patterns so broad they catch normal work. Fix: only block never-run primitives and add test vectors.
3. Running untrusted generated code with sandboxing off. Fix: use a non-root, read-only, no-network container at minimum.
4. Installing a community MCP server without auditing it. Fix: read source, manifest, dependencies, tool list, and first-run behavior.
5. Giving every subagent the parent tool surface. Fix: assign tool policy per role and task.
6. Allowing read plus unrestricted network. Fix: pair sensitive read access with egress controls.
7. Treating guardrails as the enforced boundary. Fix: guardrails advise; tool policy, hooks, sandbox, and network policy enforce.
8. Logging command text without protecting the log. Fix: the audit log captures payloads; redact secrets and restrict file permissions on the log.
9. Removing a layer to fix a false positive without replacing its coverage. Fix: each layer closes a gap; narrow the rule, do not delete the layer.
