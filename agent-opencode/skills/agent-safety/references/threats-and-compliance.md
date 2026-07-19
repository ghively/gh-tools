# Advanced Threats & Compliance

The core safety references (OWASP agentic threats, sandboxing, guardrails,
hooks, tool policy, multi-tenant isolation) cover the primary attack
surface. This reference fills the advanced gaps: model supply-chain
security, model poisoning, adversarial tools, PII handling at depth,
audit-logging standards, agent identity/authz, and data exfiltration
prevention.

## Model Supply-Chain Security

### Threat Surface

| Vector | What's at risk | Mitigation |
|---|---|---|
| **Base model provenance** | A model from an untrusted source may contain backdoors or tailored behaviors | Use models from vetted hubs (Hugging Face verified, provider APIs) |
| **Fine-tuning data corruption** | Poisoned datasets produce models that behave maliciously on specific triggers | Audit fine-tuning datasets; provenance chain from data source to weights |
| **Model-file format risks** (pickle, safetensors) | Deserialization can execute arbitrary code | Use safetensors exclusively; verify model weights with signed manifests |
| **Hugging Face hub trust** | A repo with a familiar name but different author; a model card that misrepresents capabilities | Verify author org, stars, downloads, and commit history before pulling |
| **Signed model integrity** | Weights replaced in transit or at rest | Use sigstore/cosign to verify model signatures; pin sha256 of weights |
| **Base-model card auditing** | The model card claims one thing; the model does another | Eval before trust — run the model against a golden safety suite before deploying |

### Defense in Depth

1. **Vetted source only.** Pull models from the official Hugging Face org
   (or the provider's API), not a random fork.
2. **safetensors over pickle.** Pickle loads can execute arbitrary code;
   safetensors is a pure data format. Most modern models ship safetensors
   by default — verify before loading.
3. **Digest pinning.** `model_id@sha256:abc123...` — pin the exact
   weight checkpoint, not the mutable tag. CI-reproducible model loading
   is also good for eval determinism.
4. **Golden-safety-suite gate.** Before a new model version enters
   production, run it against a suite of governance eval cases (the
   agent-safety skill's red-team output, encoded as eval cases). Fail
   CI on any regression.
5. **Provenance chain.** Model → fine-tuning dataset → source data →
   data-quality audit. Store this as the model's provenance manifest.
   Every link is a potential compromise point.

## Model Poisoning

Distinct from memory poisoning (the `owasp-agentic.md` coverage of
"Long-term bias on future work" via corrupted memory). Model poisoning
attacks the weights or tuning data directly.

### Types

| Type | How it works | Detection |
|---|---|---|
| **Backdoor weights** | Model behaves normally on clean inputs; triggers malicious behavior on specific patterns | Run the golden-safety-suite on every model version; include trigger patterns in the eval |
| **Fine-tuning data attack** | Tuning data contains crafted examples that change model behavior on targeted inputs | Audit the tuning dataset before training; provenance from source to tune |
| **Adversarial perturbation** | Injected noise into the model weights that causes specific outputs on specific inputs | Run the eval suite at inference time; hash-check weights |
| **Suppressed behavior** | Removes a safety refusal on a narrow pattern while keeping general refusals intact | Include targeted refusal probes in the golden safety suite |

### Multi-Provider Voting as Detection

For highly sensitive use cases, run the same prompt against multiple
models from different providers and compare. Disagreement on a safety-
critical decision means at least one model is wrong — treat the decision
as ambiguous and escalate.

```python
providers = [claude_opts, glm_opts, gemini_opts]
votes = [await ask_provider(ctg, "Should I approve this?") for ctg in providers]
if len(set(votes)) < len(votes):
    escalate_to_human("models disagree")
```

## Adversarial Tools & Tool-Result Poisoning

### Adversarial Tool Designs

A tool offered by a third-party MCP server, plugin, or skill can be
designed to:

- Exfiltrate data (tool arguments → external server).
- Escalate privileges (a "read" tool that also does a write under the
  covers).
- Obfuscate behavior (tool name says "search"; tool body does `deploy`).
- Poison the model via its result (indirect prompt injection through
  tool output).
- Return misrepresentative success/failure to manipulate agent state.

### Defenses

1. **Pre-install audit.** The `security-audit-checklist.md` reference
   covers this — read the tool source before installing. For MCP servers,
   run `tools/list` and inspect every tool's `description` and
   `inputSchema` for suspicious fields.
2. **Tool-result size caps.** Results over N bytes are truncated before
   entering the model context. Prevents result-based prompt injection
   via large payloads.
3. **Opaque tool results.** Mark external tool results as data. See
   `../../tool-mcp-engineering/references/mcp-security-and-primitives.md`
   for the opaque-envelope pattern.
4. **Tool-allowlist audit.** Automated check: every tool the agent can
   call is in the allowlist; every tool in the allowlist has been
   audited. CI gate.

## PII Handling

### Taxonomy

| PII category | Regulation reference | Agent concern |
|---|---|---|
| **Personal identifiers** (name, email, IP, phone) | GDPR Art 4(1), CCPA § 1798.140(o)(1) | Redact from logs; never surface to downstream systems without explicit consent |
| **Pseudonymized data** (token replaces identifier) | GDPR Recital 26 | Still PII — the mapping table re-identifies. Treat as PII for retention |
| **Sensitive personal data** (health, ethnicity, political, biometric) | GDPR Art 9, HIPAA PHI | Never enter model context under default policy; require explicit opt-in and auditing |
| **Financial identifiers** (PAN, account number) | PCI DSS Req 3 | Never in logs or model context; tokenize before indexing |
| **Children's data** | COPPA, GDPR-K | Never collect or process without verified parental consent |

### Redaction Pipeline

1. **Detect:** Classifier (presidio, regex, or an LLM gate) identifies
   PII in tool arguments, tool results, user messages, and model output.
2. **Redact or pseudonymize:** Replace PII with a type token (`[EMAIL]`,
   `[PHONE]`) for general-purpose contexts; or with a pseudonym (stable
   token that maps to the real value in a secure vault) for session-
   scoped use.
3. **Audit:** Record every redaction decision — what was redacted, when,
   from which field, by which rule. The audit log is itself subject to
   retention law.
4. **Never two-way:** Redacted data exits the redaction pipeline
   irreversibly. Pseudonymized data can map back via the vault, but the
   vault requires separate access control.

### PII in Agent-Specific Surfaces

| Surface | Risk | Defense |
|---|---|---|
| **Tool arguments** | User types PII in a prompt; the model passes it to a tool | Redact tool arguments before dispatch; the tool receives `[REDACTED]` |
| **Tool results** | An API returns a list of users with PII | Redact before the model reads the result |
| **Agent memory** | PII written to durable memory and recalled in later sessions | Redact before writing to memory; the memory store never holds PII in plaintext |
| **Audit logs** | The safety-audit.log captures command text with PII | Redact before logging; protect the log file with restricted permissions |
| **RAG corpus** | Document chunks containing PII enter the index | Preprocess the corpus: detect and redact PII before indexing |

## Audit-Logging Standards

### What a Production Audit Log Contains

Every auditable action (model call, tool call, permission verdict,
compaction, error, session lifecycle) logs:

| Field | Required? | Example |
|---|---|---|
| Timestamp | Yes | ISO 8601 with TZ |
| Session ID | Yes | Correlates actions within a session |
| Run ID | Yes | Correlates actions within a run |
| Actor | Yes | User or service account that authorized the session |
| Action | Yes | `model_call`, `tool_call`, `permission_verdict`, etc. |
| Resource | Yes | Tool name, model name, file path, session |
| Input summary | Yes | Truncated, redacted input fields |
| Output summary | Yes | Truncated, redacted output fields |
| Decision | Yes | `allow`, `deny`, `error`, `timeout` |
| Duration | Yes | Ms |
| Cost | Recommended | USD per model call |
| Trace ID | Recommended | OTel span link |

### Tamper-Evidence

- **Append-only.** The log is an append-only stream; no updates, no
  deletes.
- **Hash-chained.** Each log entry includes the hash of the previous
  entry. Verify the chain from end to start to detect tampering.
- **Signed segments.** Sign each N-entry segment with a private key;
  publish the public key. Verify segment signatures independently.
- **Write-once sink.** Export to S3 with object lock, GCS with retention
  policy, or a dedicated log platform (Datadog, Splunk). The sink
  guarantees immutability, not the agent.

### Retention

- **Minimum:** 90 days (match the shortest applicable regulation).
- **Standard:** 1 year (match typical SOC 2 / ISO 27001 auditing
  windows).
- **Maximum:** Per data-classification policy; PII-laden logs may need
  earlier deletion.

### OTEL / OCSF Alignment

Export audit events in OTel-compatible spans for real-time dashboards
and in OCSF (Open Cybersecurity Schema Framework) format for SIEM
ingestion. The two formats serve different consumers; emit both.

## Agent Identity & Authorization

### Agent-as-Principal

An agent is a principal, not a user proxy. It needs its own identity:

| Approach | Use case | Trade-off |
|---|---|---|
| **API key** | Simple; the agent authenticates as itself | Long-lived; must rotate on leak |
| **Workload Identity** (SPIFFE/SPIRE) | K8s-native; short-lived certs; auto-rotation | K8s-dependent |
| **OAuth client credentials** (`client_id` + `client_secret`) | The agent is a registered OAuth client; tokens short-lived | Token lifecycle management |
| **Machine-to-machine mTLS** | Zero-trust environments; agent presents a cert | PKI infrastructure required |
| **GitHub App / GitLab bot** | Platform-native identity for platform-resident agents | Platform-scoped; token per installation |

### Service-Account Discipline

- One service account per agent. Never share.
- Per-account scoping: the least privilege the agent's design requires.
- Rotate on schedule: every 90 days minimum; every 30 days for
  production.
- Audit: which agent used which account, when? The audit log answers.
- Deprovision on decommission: when the agent is retired, the service
  account is revoked immediately.

### Per-Tenant Identity

In multi-tenant deployments, each tenant's agent runs with its own
identity:

```
tenant-a:
  agent → service-account-a → secrets-a → resources-a
tenant-b:
  agent → service-account-b → secrets-b → resources-b
```

Auth decorrelation: a compromise of service-account-a does not grant
access to tenant-b's resources. See `multi-tenant-isolation.md`.

## Data Exfiltration Prevention

### Egress Taxonomy

| Vector | Defense |
|---|---|
| **Provider call** (the model's API call itself contains exfiltrated data — the model was tricked into including secret data in its output) | Content filters on output; tool-result scrutiny |
| **Tool-result exfiltration** (a tool sends data to an external URL as a side effect) | Egress allowlist: every outbound URL the agent may call; deny by default |
| **Memory exfiltration** (data written to memory in session A, read in session B by a different actor) | Per-session memory isolation; cross-session read requires explicit auth |
| **Log exfiltration** (secrets captured in audit logs and then the logs are exfiltrated) | Redact before logging; restrict log file permissions; ship logs with access control |
| **MCP server exfiltration** (a local MCP server that also phones home) | Per-server network policy; monitor egress from each MCP server process |
| **Multi-hop exfiltration** (data extracted through a permitted domain — e.g., DNS tunneling) | Monitor DNS and outbound traffic patterns; alert on anomalies |
| **Covert channels** (ICMP timing, connection-pooling side channels) | Network-level monitoring; treat agent containers as untrusted even inside the perimeter |

### Egress Allowlist Implementation

| Tier | Tools | Drops what |
|---|---|---|
| **DNS-level** (Pi-hole, CoreDNS) | Agent cannot resolve unauthorized domains | Bulk exfiltration via `curl` / `wget` |
| **IP/CIDR** (iptables, AWS security groups) | Agent can only reach specific IPs | Bypass at IP level |
| **SNI-level** (nginx, Envoy, TLS proxy) | Only allowed hostnames pass TLS handshake | Encrypted exfiltration to an allowed IP |
| **HTTP-proxy** (Squid, outbound proxy) | Inspect request URLs, headers, payloads | Hidden exfiltration via request body |

Layer all four. DNS is the cheapest first pass; HTTP-proxy is the most
sensitive but the most expensive. Start with DNS + allowlist; add
layers as trust erodes.

## Pitfalls

1. **The model supply chain as an afterthought.** "We pull from Hugging
   Face and trust it." Fix: vet, verify, pin digests.
2. **PII in memory that survives decommission.** Agent retired; memory
   store still has user data. Fix: retention policy; delete on
   decommission.
3. **Audit logs without tamper-evidence.** A compromised agent also
   deletes its audit trail. Fix: append-only + hash-chained + signed.
4. **Agent identity shared across tenants.** Tenant A's agent uses
   tenant B's service account. Fix: one identity per tenant; never
   share.
5. **Egress allowed by default.** Any URL works; exfiltration is easy.
   Fix: deny all; allowlist the exact URLs the agent needs.
6. **Tool-result injection not tested.** The red-team tests direct
   injection but not tool-result injection. Fix: include tool-result
   payloads in the red-team campaign.

## See Also

- `owasp-agentic.md` — the primary threat taxonomy.
- `sandboxing-tiers.md` — OS/container isolation.
- `deterministic-hooks.md` — the never-run safety floor.
- `multi-tenant-isolation.md` — per-tenant boundaries.
- `security-audit-checklist.md` — pre-deploy audit.
- `../../tool-mcp-engineering/references/mcp-security-and-primitives.md` — MCP-specific security.
- `incident-response.md` — what to do when a threat lands.
