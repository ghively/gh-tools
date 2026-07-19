# Harness Deploy Patterns

The harness concerns (loop, context, sessions, error recovery, streaming,
HITL, observability, cache, doom-loop) all have production-deploy shapes
that differ from their dev shapes. This reference maps each concern to
its container-deployed form and is the bridge between the `agent-harness`
references (what the harness does) and the `agent-deployment` references
(where the harness runs).

## The Concern-by-Concern Deploy Shape

### 1. Loop → Multi-Replica Safety

In dev, one process runs the loop. In production:

- **Step caps must be enforced per-replica AND per-session.** A user
  who triggers 5 replicas should not get 5× the step budget.
- **The loop's stop conditions live in the harness, not the load
  balancer.** The LB terminates slow requests; the harness terminates
  looping agents. Both are needed.
- **Idempotent turn boundaries.** Every turn writes session state
  before the next model call, so a killed replica resumes cleanly.

See `agent-loop.md` for the loop; `session-lifecycle.md` for the
turn-boundary discipline.

### 2. Context Management → Compaction in a Constrained Box

In dev, the context window is the only constraint. In production:

- **Compaction must survive replica death.** The compacted summary is
  part of session state, written to the durable store.
- **Compaction should not run mid-request.** A long HTTP request that
  triggers mid-turn compaction risks client timeouts. Compact between
  turns, before the next request.
- **Compaction cost is real.** Summarizing 100K tokens is a 100K-token
  model call. Budget for it.

See `context-management.md` for the doctrine.

### 3. Sessions → Durable Store Choice

| Session store | When |
|---|---|
| In-process dict | Never in production |
| SQLite | Single-host; < 100 sessions |
| Postgres | Multi-host; transactional |
| Redis | High-throughput; TTL-native |
| S3 / blob | Archive only |

Production rules:

- The store is **outside** the agent container (separate container or
  managed service).
- The store is **backed up** (Postgres: WAL archiving; Redis: RDB +
  AOF; S3: versioning).
- The store is **shared** across replicas when the agent scales
  horizontally.

See `session-lifecycle.md` for the session contract.

### 4. Error Recovery → Circuit Breakers and DLQs

In dev, retry with backoff is enough. In production:

- **Per-replica circuit breaker.** If a replica hits N consecutive
  provider errors, it stops accepting new requests and reports
  unhealthy. The LB drains it.
- **Dead-letter queue.** Failed runs go to a DLQ (SQS, Kafka topic)
  for inspection and replay, not into `/dev/null`.
- **Provider diversification.** A single provider going down should
  not take the agent down. Configure fallback providers in routing.

See `error-recovery.md` for the recovery doctrine.

### 5. Streaming → Edge and Load Balancer Coexistence

In dev, the harness streams directly to stdout. In production:

- **Reverse proxy must support SSE / WebSocket.** nginx, Envoy, and
  ALB do; some load balancers buffer responses and break streaming.
- **Idle timeout matters.** A model that takes 30s to first token
  needs a proxy with a ≥ 60s idle timeout, not the 60-second default.
- **Backpressure must propagate.** If the client disconnects, the
  proxy must cancel the upstream request, not consume the whole
  response.

See `streaming.md` for the streaming doctrine.

### 6. HITL → Async Approval Surface

In dev, HITL is a TTY prompt. In production:

- **Asynchronous approval surface.** The harness pauses the run,
  writes the approval request to a queue, and waits. The user approves
  via a web UI, Slack, email — not the terminal.
- **Approval timeout.** If no verdict arrives within N minutes, the
  harness denies by default (fail-closed) or surfaces to operator
  (fail-open with alert). Pick one and document it.
- **Approval audit trail.** Every verdict is recorded with approver
  identity, timestamp, and reason.

See `hitl-interrupts.md` for the interrupt doctrine.

### 7. Observability → Sampling and Cost

In dev, emit every span. In production:

- **Sampling.** At 1000 req/s, emitting every span overwhelms the
  collector. Sample at 1-10% for traces; keep 100% for metrics and
  logs.
- **Cost of observability.** OTel export is not free — at high
  throughput, the export itself is a non-trivial CPU/network cost.
  Measure and budget for it.
- **PII redaction at the source.** The harness redacts before export;
  do not rely on the collector to redact.

See `harness-observability.md` for the span taxonomy.

### 8. Cache → Distributed Cache Layer

In dev, in-process cache is fine. In production:

- **Cache must be shared across replicas.** Otherwise each replica
  rebuilds its own cache, multiplying cost.
- **Cache invalidation must be coordinated.** Redis pub/sub or a
  shared invalidation signal prevents one replica from serving stale
  cached results after another invalidates them.
- **Cache TTL must match the data's staleness budget.** Tool results
  that go stale in 5 minutes need a 5-minute TTL, not 24 hours.

See `harness-cache.md` for the cache hierarchy.

### 9. Doom-Loop Prevention → Cross-Replica Detection

In dev, single-process doom-loop detection is enough. In production:

- **Detection must be per-session, not per-replica.** A user who
  loops across 5 replicas triggers detection based on the session's
  tool-call history, not the replica's.
- **Shared doom-loop state.** Recent tool-call signatures live in the
  session store, not in replica memory.
- **Doom-loop span is a real alert.** A doom-loop detection is a
  signal that something is wrong — alert on it, not just log it.

See `doom-loop-prevention.md` for the detector.

## Topology Patterns

### Single-Host

```text
┌────────────────────────────────────┐
│  Host                              │
│  ┌──────────┐  ┌──────────────┐    │
│  │  agent   │─►│   postgres   │    │
│  └──────────┘  └──────────────┘    │
│       │                            │
│       │       ┌──────────────┐     │
│       └─────► │    redis     │     │
│               └──────────────┘     │
└────────────────────────────────────┘
```

Simplest production shape. Works for low-traffic agents (one tenant,
< 100 concurrent sessions). docker-compose is sufficient.

### Multi-Host (HA)

```text
┌──────────────┐   ┌──────────────┐
│   Host A     │   │   Host B     │
│  ┌────────┐  │   │  ┌────────┐  │
│  │ agent  │  │   │  │ agent  │  │
│  └────────┘  │   │  └────────┘  │
└──────┬───────┘   └──────┬───────┘
       │                  │
       └────────┬─────────┘
                │
       ┌────────┴─────────┐
       │  managed postgres │
       │  managed redis    │
       │  managed OTel     │
       └──────────────────┘
```

For agents that need uptime. State in managed services; replicas
stateless. Requires the session store and cache to be shared.

### Multi-Tenant

```text
┌──────────────────────────────────────────────────┐
│  Orchestrator                                    │
│                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ │
│  │ tenant- │ │ tenant- │ │ tenant- │ │ tenant-│ │
│  │   a     │ │   b     │ │   c     │ │   d    │ │
│  │ agent   │ │ agent   │ │ agent   │ │ agent  │ │
│  └─────────┘ └─────────┘ └─────────┘ └────────┘ │
│       │         │         │          │          │
│       └─────────┴─────────┴──────────┘          │
│                     │                            │
│            per-tenant secrets                    │
└──────────────────────────────────────────────────┘
```

One container (or pod) per tenant. Each tenant has its own:

- Provider key (Secret per tenant)
- Session store (namespace in shared Postgres, or per-tenant DB)
- Permission policy (per-tenant opencode.json)
- Audit trail (per-tenant log group)

### Sidecar Patterns

For specific harness concerns, sidecars help:

- **OTel collector sidecar** — buffers spans before export; survives
  agent restarts without dropping spans.
- **Vault agent sidecar** — fetches secrets from Vault and writes them
  to a file the agent reads; rotates short-lived credentials.
- **Proxy sidecar** — intercepts egress for audit; the agent's only
  outbound path.

## Common Production Bugs

1. **Sticky sessions on a stateless backend.** The LB pins sessions to
   a replica that then dies. Fix: store sessions externally; LB does
   not need to be sticky.
2. **Streaming through a buffering proxy.** nginx default buffers;
   users see nothing for 30 seconds. Fix: `proxy_buffering off` for
   the streaming endpoint.
3. **Replica-scale cache invalidation missed.** Replica A invalidates
   a cached tool result; Replica B still serves it. Fix: shared cache
   (Redis) or pub/sub invalidation.
4. **Doom-loop detection per-replica.** A loop bounces across
   replicas and is never detected. Fix: per-session detection against
   the shared session store.
5. **Step cap drift across replicas.** Replica A's step count and
   Replica B's step count for the same session are both 25; the user
   gets 50 steps. Fix: step count is in the session store, not the
   replica.
6. **Approval timeout in async HITL.** The user takes 10 minutes to
   approve; the HTTP request timed out at 60s; the harness is waiting
   for a verdict that has nowhere to land. Fix: separate the
   approval queue from the HTTP request lifecycle.

## Deploy Checklist

Before promoting an agent harness to production:

- [ ] Sessions stored externally (Postgres / Redis)
- [ ] Step cap and doom-loop detector read from session state
- [ ] Compaction writes summary to session store before next turn
- [ ] Streaming-compatible reverse proxy
- [ ] Per-replica circuit breaker
- [ ] Dead-letter queue for failed runs
- [ ] HITL approvals are async with timeout and audit
- [ ] OTel export with PII redaction
- [ ] Shared cache (Redis) for prompt-cache and tool results
- [ ] Provider fallback chain configured
- [ ] Health check exercises a real model call, not just `/health`
- [ ] Backups tested with restore drill
- [ ] Secrets from env / vault, never in image
- [ ] Non-root user in the image
- [ ] Log driver size caps

Each unchecked box is a production incident waiting to happen.

## See Also

- The nine `agent-harness/references/*.md` files for each concern's
  doctrine.
- `agent-deployment/references/framework-deploy-matrix.md` — the
  per-framework Docker recipes.
- `agent-deployment/references/packaging-serving.md` — the broader
  packaging doctrine.
- `agent-deployment/references/observability.md` — production
  observability.
- `agent-deployment/references/versioning-rollout.md` — rolling out
  harness changes safely.
