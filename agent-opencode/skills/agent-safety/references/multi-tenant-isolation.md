# Multi-Tenant Agent Isolation

Load this when one agent deployment serves more than one customer, workspace, or org and a request from tenant A must never see, spend, or act on tenant B's data, credentials, or budget. Single-tenant agents skip this file; the moment a shared process, shared index, or shared credential touches two tenants, isolation becomes a security boundary, not a feature.

The governing principle: **tenancy is a boundary the code enforces, not a field the model is trusted to respect.** A `tenant_id` in the prompt is a hint; a `tenant_id` that scopes every credential lookup, every retrieval filter, and every audit record is a boundary. This file is the least-agency doctrine (see the parent SKILL) applied to the tenant axis: the smallest data, credential, and budget surface per request, enforced outside the model.

## The Four Isolation Axes

Every multi-tenant agent leaks along one of four axes. Each needs its own enforced control; a system that closes three and leaves one open is a system with a cross-tenant incident waiting on the open one.

| Axis | Leak looks like | Primary control |
|---|---|---|
| Credentials | Agent uses tenant A's token while serving tenant B; ambient service creds act on any tenant | Per-tenant credential brokering; no ambient creds in shared context |
| Memory / RAG | Tenant B's query retrieves tenant A's chunks; poisoned memory crosses tenants | Index-per-tenant, or a filtered shared index with the filter enforced server-side |
| Rate / cost | One tenant's burst starves or bankrupts the others (noisy neighbor) | Per-tenant quotas, budgets, and concurrency caps |
| Audit | An incident cannot be attributed to a tenant; logs mix tenants | Tenant-stamped, tenant-partitioned audit trail |

The axes are a conjunction, not a menu — the same way least-agency is. Scoped credentials with a shared unfiltered index still leak documents. A per-tenant index with an ambient admin token still lets a prompt-injected agent act across tenants.

## Credential Brokering

The failure to design out first: an agent process holds a broad service credential (a platform API key, a database superuser, a cloud role) and *chooses* which tenant to act as based on request context. One prompt injection or one routing bug and the agent acts as the wrong tenant with full authority.

Doctrine:

1. **No ambient tenant credentials in shared context.** The long-lived platform credential, if it exists at all, lives in a broker the agent cannot read — never in the agent's environment, prompt, memory, or tool-visible config. The agent asks the broker for a token; it never holds the master.
2. **Mint per-request, per-tenant, least-scope tokens.** The broker exchanges the authenticated tenant identity for a short-TTL token scoped to that tenant's resources and only the operations this request needs. The token expires in minutes, not the session.
3. **The tenant identity comes from the authenticated request, not the model.** Derive `tenant_id` from the session/auth layer before the agent runs. If the model can name the tenant it acts as, injection can rename it.
4. **Tokens are request-scoped, not agent-scoped.** A sub-agent or tool spawned for tenant A's request inherits A's token and cannot widen it. Crossing to tenant B requires a new broker exchange that the authenticated identity would have to authorize — which, mid-request, it cannot.

```
authenticated request (tenant_id from session)
   -> broker.mint(tenant_id, scopes=[needed_ops], ttl=5m)   # master cred stays in broker
   -> agent runs with the scoped token only
   -> token expires; nothing to leak into memory or logs
```

Brokering shape by platform is out of scope here; the invariant is platform-independent — **the agent never holds a credential broader than the current tenant + current task.** For the credential *storage* and rotation mechanics behind the broker, see the `agent-deployment` skill.

## Memory and RAG Index Isolation

A shared retrieval corpus is the most common quiet cross-tenant leak: it does not throw an error, it just returns another tenant's chunk as a plausible answer. Two designs, and the tradeoff between them:

| Design | Isolation strength | Cost | Use when |
|---|---|---|---|
| Index-per-tenant | Strongest — physical separation, no filter to forget | Higher storage/ops; many small indexes; cross-tenant analytics need a separate path | High-sensitivity data; regulated tenants; few large tenants |
| Filtered shared index | Weaker — one forgotten filter leaks everything | Cheap, one index, easy analytics | Many small low-sensitivity tenants; cost-dominated |

If you choose the filtered shared index, the filter is a security control and must behave like one:

1. **Enforce the tenant filter server-side, at the index boundary** — not as a query parameter the agent assembles. An agent-assembled filter is one prompt injection away from `tenant_id: *`. Bind the filter from the authenticated identity in the retrieval service, below the layer the model can influence.
2. **Fail closed.** A query with no resolved `tenant_id` returns nothing, never the unfiltered corpus. Default-open metadata filters are the classic breach.
3. **Stamp every chunk with its owning tenant at ingestion** and re-check tenant on the way out; a chunk whose tenant does not match the request tenant is dropped even if the filter "should" have excluded it. Belt and suspenders, because a single bad filter is a full-corpus leak.
4. **Isolate memory writes too.** Long-term memory is a tenant-scoped store; a summary written during tenant A's session must be unreachable from tenant B's. Poisoned memory that crosses tenants is both a leak and an integrity attack.

For chunk provenance metadata, embedding-model versioning, and the retrieval-eval methodology that proves the filter actually holds, see the `memory-rag` skill — this file governs the *tenant boundary*; that skill governs the pipeline it rides on. A cross-tenant retrieval case belongs in the golden suite (see the `agent-evals` skill): a query issued as tenant B that must return zero of tenant A's known chunks.

## Rate, Cost, and Noisy-Neighbor Control

Isolation is not only confidentiality; availability and budget are tenant boundaries too. Without per-tenant limits, one tenant's runaway loop or traffic spike degrades or bankrupts every other tenant on the shared deployment.

| Control | Bounds | Failure if missing |
|---|---|---|
| Per-tenant request rate limit | Requests/min per tenant | One tenant's burst starves the pool |
| Per-tenant concurrency cap | In-flight agent runs per tenant | One tenant monopolizes workers |
| Per-tenant token/cost budget | Model spend per tenant per window | One tenant's loop runs up the shared bill |
| Per-tenant tool-call quota | Calls to expensive/rate-limited downstreams | One tenant exhausts a shared third-party quota for all |

Enforce limits keyed on the authenticated `tenant_id`, in the layer in front of the agent, not inside the prompt. A global rate limit protects the platform from the outside world; it does nothing to stop tenant A from consuming tenant B's share. The two are different controls — keep both. Meter to the tenant so cost is attributable and a runaway is contained to the tenant that caused it. Model-side budget mechanics (per-run token caps, escalation ladders) are the `model-selection` skill; this file adds the requirement that the budget be *keyed per tenant*.

## Tenant-Aware Audit Logging

An audit trail that cannot answer "which tenant did this touch?" fails exactly when you need it — during a suspected cross-tenant breach. Requirements:

1. **Every audit record carries the authenticated `tenant_id`** (plus request id, principal, tool, and decision), stamped from the auth layer, never from model output.
2. **Partition or scope the logs so one tenant's audit export cannot include another tenant's records.** A tenant requesting their own audit trail (a common compliance right) must not receive a neighbor's entries.
3. **Redact secrets before write, as everywhere** (see the parent SKILL's audit-log discipline) — and additionally never let tenant A's payload land in a shared log line that tenant B's investigation reads.
4. **Make cross-tenant access attempts loud.** A resolved-then-mismatched tenant on a retrieval or a broker exchange is a high-signal event; log it as a security alert, not a debug line.

## Blast-Radius Design

Assume one tenant boundary will eventually be crossed — a filter bug, a leaked token, an injection. Design so the crossing is contained:

- **Isolate the highest-sensitivity tenants harder.** Regulated or high-value tenants get index-per-tenant and dedicated credential scopes even when the cost model would prefer sharing. Match the isolation tier to the impact of a breach, the same way the parent SKILL matches layer count to impact.
- **Size the shared surface to the acceptable blast radius.** A single shared unfiltered index is a full-fleet blast radius; per-tenant indexes cap a breach to one tenant. Choose the sharing granularity by what a single failure exposes.
- **Kill by tenant.** Operators must be able to suspend, throttle, or revoke one tenant — freeze its tokens, drain its runs — without taking down the others. A containment control that only works fleet-wide is not containment.
- **Test the boundary, don't assert it.** Each axis gets an eval (see the `agent-evals` skill): a cross-tenant retrieval attempt, a token-scope-escape attempt, a noisy-neighbor budget-exhaustion case, and an audit-attribution check. A boundary that is configured but never probed fails silently the first time it matters.

## Pitfalls

1. **Trusting `tenant_id` from the model or the prompt.** A prompt-supplied tenant is an injection target; the model will eventually echo an attacker-supplied one. *Fix:* derive `tenant_id` in the auth layer before the agent runs; the model never selects the tenant it acts as.
2. **Ambient platform credentials in shared context.** A broad service token in the agent's env or config lets one routing bug act as any tenant. *Fix:* keep the master in a broker the agent cannot read; mint short-TTL, tenant-scoped tokens per request.
3. **Agent-assembled retrieval filters.** A tenant filter the model builds into the query is one injection from `*`. *Fix:* bind the filter server-side from the authenticated identity, below the model's influence, and fail closed on a missing tenant.
4. **Default-open metadata filters.** A query with no resolved tenant that returns the unfiltered corpus is a full-index leak. *Fix:* no `tenant_id`, no results; re-check the owning tenant on every returned chunk.
5. **Global rate limit mistaken for tenant isolation.** A platform-wide limit stops the outside world, not tenant A starving tenant B. *Fix:* add per-tenant rate, concurrency, cost, and tool-quota limits keyed on the authenticated tenant.
6. **Shared long-term memory across tenants.** A summary written for tenant A that tenant B can retrieve is both a leak and a poisoning vector. *Fix:* scope the memory store per tenant; isolate writes as strictly as reads.
7. **Tenant-blind audit logs.** Logs that mix tenants cannot attribute an incident or safely satisfy a per-tenant audit export. *Fix:* stamp every record with the authenticated tenant and partition so exports never cross tenants.
8. **One isolation axis closed, the rest assumed.** Scoped credentials with a shared unfiltered index still leak documents; a per-tenant index with an ambient admin token still acts across tenants. *Fix:* treat the four axes as a conjunction and test each one.
9. **Uniform isolation regardless of sensitivity.** Sharing an index across a regulated tenant and a free-tier tenant sets the blast radius to the weakest link. *Fix:* isolate high-sensitivity tenants harder; match the tier to the breach impact.
10. **Asserting the boundary instead of probing it.** A tenant filter that is "obviously correct" is the one that breaks silently. *Fix:* a cross-tenant eval per axis, run before every retrieval, credential, or routing change.
