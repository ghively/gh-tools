# Production Infrastructure: K8s, Security, Scaling & FinOps

The `packaging-serving.md` reference covers shapes (CLI/service/worker)
and container basics. The `framework-deploy-matrix.md` covers per-
framework Dockerfiles. This reference fills the infrastructure layer
those references stop at.

## Kubernetes Deploy Patterns

### When K8s

- More than one replica (HA).
- More than one tenant (per-tenant isolation via namespaces).
- You already operate K8s (and the ops burden is amortized).
- You need rolling updates, canary deploys, HPA, PDB, and pod-level
  health that docker-compose cannot give you.

### The Basic Shape

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: agent
spec:
  serviceName: agent
  replicas: 2
  selector: {matchLabels: {app: agent}}
  template:
    metadata: {labels: {app: agent}}
    spec:
      serviceAccountName: agent-sa
      containers:
      - name: agent
        image: registry.example.com/agent:1.2.3
        ports: [{containerPort: 8000}]
        envFrom:
        - secretRef: {name: agent-provider-keys}
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
        - name: state
          mountPath: /data
        resources:
          requests: {cpu: "500m", memory: "512Mi"}
          limits: {cpu: "2", memory: "2Gi"}
        readinessProbe: {httpGet: {path: /health, port: 8000}, initialDelaySeconds: 10}
        livenessProbe: {httpGet: {path: /health, port: 8000}, initialDelaySeconds: 30}
  volumeClaimTemplates:
  - metadata: {name: state}
    spec: {accessModes: [ReadWriteOnce], resources: {requests: {storage: 10Gi}}}
```

### StatefulSet vs Deployment

| Shape | When to use | Because |
|---|---|---|
| **StatefulSet** | The agent has persistent state (sessions, memory) | StatefulSet preserves identity + PVC across restarts |
| **Deployment** | The agent is stateless (session state external; cache external) | Deployment scales horizontally with no per-replica state |
| **CronJob** | Scheduled one-shot (gardener, eval runner, freshness sweep) | Job lifecycle: run, exit, record |
| **Job** | Batch (one eval suite; one migration) | Exit code is the verdict |

### Multi-Replica Considerations

- **Session affinity.** If sessions are NOT externalized, the LB must
  pin sessions to a replica. Use cookie-based affinity (not IP hash —
  IPs change behind NATs).
- **Session externalization.** If sessions live in Postgres, any replica
  can handle any request. This is the simpler shape.
- **Cache coherence.** Tool-result cache lives in Redis, not replica
  memory. Invalidate via Redis pub/sub.
- **Doom-loop detection across replicas.** Detection state lives in the
  shared store, not replica memory.

### Autoscaling (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: agent-hpa}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: agent}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource: {name: cpu, target: {type: Utilization, averageUtilization: 70}}
  - type: Pods
    pods:
      metric: {name: agent_active_sessions}
      target: {type: AverageValue, averageValue: 50}
```

Custom metrics (active sessions, tool-call queue depth) guide scaling
better than CPU. A low-CPU agent with a long queue is under-provisioned
but won't trigger a CPU-targeted HPA.

## Multi-Region & DR

### Multi-Region

For global agents (user-facing, multi-region latency budget):

| Layer | Multi-region pattern |
|---|---|
| **Compute** | K8s cluster per region; identical image, different config |
| **Session state** | Per-region Postgres with cross-region async replication |
| **Cache** | Per-region Redis; no cross-region replication (latency kills) |
| **Provider** | Per-region provider endpoint (Bedrock in us-west-2, ZAI in Singapore) |
| **DNS** | Latency-based routing (Route 53, Cloud DNS) |
| **Config** | One config repo; per-region overlay files |

Active-active is the goal; active-passive is the fallback. Active-passive
means cold start on the passive region when the active fails — budget for
the worst-case failover time (warm DB, cold model cache).

### Disaster Recovery

| RPO (Recovery Point Objective) | What you lose | How |
|---|---|---|
| < 1 hour | Sessions from the last hour | Continuous WAL archiving to the secondary region |
| < 24 hours | The last daily backup | Daily pg_dump + restic to multi-region object store |
| Manual | Whatever you can reconstruct | Export session JSON; re-import manually |

**Backup scope:**
- Postgres (session state).
- Redis (RDB dump — cache is disposable, but the cost of a cold cache
  is real).
- The config repo (git is your backup; verify you can clone from cold).
- The skills library (git).
- Provider keys (in a vault, not in the backup).

**Restore drill:** Quarterly, restore the full system from backup to a
staging environment. Verify the agent boots, loads sessions from the
restored DB, and responds. An untested backup is not a backup.

## Container Security

Beyond the non-root user in the Dockerfile:

| Layer | Tool | What it protects against |
|---|---|---|
| **Image scanning** | Trivy, Snyk, Grype | Known CVEs in base image and dependencies |
| **SBOM generation** | Syft, CycloneDX | Supply-chain audit; what's in the image? |
| **Seccomp profile** | Docker seccomp, K8s `seccompProfile` | System-call filtering; the agent cannot `mount`, `ptrace`, etc. |
| **AppArmor / SELinux** | Per-container profile | Filesystem access restrictions |
| **Read-only root** | `readOnlyRootFilesystem: true` | Agent cannot write to the image; must use mounted volumes |
| **Capability dropping** | `capabilities: {drop: [ALL]}` | Container has no root capabilities; add back only what's needed |
| **User namespace remap** | `userns-remap` | UID 0 in the container ≠ UID 0 on the host |
| **Admission control** | OPA/Gatekeeper, Kyverno | Reject pods that violate policy (no-image-scan, root-user, privileged) |
| **Network policy** | K8s `NetworkPolicy` | Default-deny all egress; allowlist only provider APIs + state store |

### Minimal K8s Security Policy

```yaml
apiVersion: v1
kind: Pod
spec:
  securityContext:
    runAsNonRoot: true
    seccompProfile: {type: RuntimeDefault}
  containers:
  - securityContext:
      capabilities: {drop: [ALL]}
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
```

These five directives (non-root, seccomp, no capabilities, read-only
root, no priv esc) are the minimum viable security posture for any
agent container.

## Sidecar Patterns

### OTel Collector Sidecar

```yaml
containers:
- name: otel-collector
  image: otel/opentelemetry-collector-contrib
  args: [--config, /etc/otel/config.yaml]
  volumeMounts:
  - name: otel-config
    mountPath: /etc/otel
```

The agent emits spans to localhost (the sidecar); the sidecar buffers
and exports to the upstream collector. If the upstream is down, the
sidecar buffers in memory (or disk). If the agent crashes, the sidecar
still flushes buffered spans.

### Vault Agent Sidecar

```yaml
containers:
- name: vault-agent
  image: hashicorp/vault:latest
  args: ["agent", "-config", "/etc/vault/agent.hcl"]
```

The Vault agent fetches secrets, writes them to a shared volume, and
rotates them before expiry. The agent reads from the volume. No secrets
in env.

### Egress Proxy Sidecar (Envoy)

All agent egress flows through the Envoy sidecar. Envoy enforces the
URL allowlist, monitors for anomalies, and provides egress audit.

## Queue-Based Scaling

### Queue Depth as the Scaling Signal

```python
queue_depth = redis.llen("agent:inbox")
hpa_target = min(10, max(2, queue_depth // 50))
```

Queue depth (not CPU) drives scaling. When the agent pool processes
requests from a queue:

| Queue depth | Replicas | Reason |
|---|---|---|
| < 50 | 2 (min) | Idle |
| 50-200 | 2-4 | Moderate |
| 200-500 | 4-8 | Busy |
| 500+ | 8-10 (max) | Overloaded; alert; check provider rate limits |

### Queue Backend Choice

| Backend | Best for |
|---|---|
| SQS | AWS-native; exactly-once (FIFO); dead-letter queue |
| RabbitMQ | Complex routing; per-tenant queues; ACK semantics |
| Kafka | Event replay; long retention; multi-consumer |
| Redis Streams | Lightweight; same infra as cache; consumer groups |
| NATS JetStream | Ultra-low latency; edge/fog |

### Provider Rate Limiting

Every provider has RPM/TPM quotas. The agent harness must:

1. **Track per-provider call rate.** In Redis, a sliding-window counter
   of provider calls in the last 60 seconds.
2. **Throttle before the limit.** At 80% of quota, queue new requests
   (not reject). At 95%, reject with a 429 to the upstream.
3. **Back-off on provider 429.** Exponential backoff with jitter; the
   queue absorbs the delay.
4. **Circuit-break on persistent failures.** If the provider returns
   429 or 5xx for > 5 consecutive calls, stop sending. Alert.

```python
RATE_LIMIT = 600  # RPM from provider dashboard
current = redis.get("provider:calls:last-60s") or 0
if current > RATE_LIMIT * 0.95:
    raise RateLimitExceeded("Provider quota — retry later")
redis.incr("provider:calls:last-60s")
redis.expire("provider:calls:last-60s", 60)
```

## FinOps for Agents

### Cost-Tracking Platform Options

| Platform | Features | Use for |
|---|---|---|
| **Helicone** | API proxy; per-model cost tracking; prompt caching analytics; rate-limit monitoring | Open-source; self-hostable; multi-provider proxy |
| **Lunar.dev** | AI gateway; rate limiting; quota management; provider abstraction | Enterprise AI gateway |
| **Vercel AI Gateway** | Built-in cost tracking for Vercel AI SDK apps | Vercel-hosted agents only |
| **Cloudflare AI Gateway** | Caching; rate limiting; cost attribution | Edge-proxied agents |
| **Portkey** | 200+ models; config-based routing; cost analytics; guardrails | Multi-provider with central config |
| **OpenRouter** | Aggregated provider; single API key; cost analytics per request | POC / low-volume multi-provider |

### Per-Tenant Cost Attribution

In multi-tenant deployments, cost follows the tenant:

```python
# Tag every model call with the tenant ID
response = client.chat.completions.create(
    model="glm-4.7",
    messages=[...],
    user=f"tenant:{tenant_id}",   # Anthropic/OpenAI user field
)
# Record in cost-tracking DB
cost_tracker.record(
    tenant_id=tenant_id,
    model="glm-4.7",
    input_tokens=response.usage.prompt_tokens,
    output_tokens=response.usage.completion_tokens,
    cost=compute_cost(response.usage, model_prices),
)
```

### Spend Alert Ladder

| Level | Trigger | Action |
|---|---|---|
| Daily budget (soft) | Today's spend > 80% of daily budget | Log warning; continue |
| Daily budget (hard) | Today's spend > 100% of daily budget | Stop accepting new sessions; finish in-flight |
| Per-run ceiling | Current run's cost > 2× historical average | Pause the run; alert operator; await decision |
| Provider billing anomaly | Current hour's cost > 3× the 7-day hourly average | Alert; investigate API key compromise |

### Chargeback/Showback

For multi-team or multi-tenant deployments:

- **Showback**: Report cost per team/tenant without enforcing budgets.
  Good for awareness; no blocking behavior.
- **Chargeback**: Pre-allocated budget per team/tenant; hard cap with
  alert and cut-off. Blocks new sessions when budget exhausted.
- **Cost-centers**: In org-level deployments, tag with cost-center IDs
  that map to accounting codes.

## Pitfalls

1. **HPA on CPU for agent workloads.** Agents spike CPU on model calls
   (the provider does the work; the agent waits). CPU-targeted HPA
   mis-scales. Fix: custom metrics (queue depth, active sessions).
2. **CronJob without `concurrencyPolicy: Forbid`.** Two gardener runs
   collide. Fix: `concurrencyPolicy: Forbid` + `startingDeadlineSeconds`.
3. **PDB without min replicas.** A drain kills all replicas. Fix:
   `PodDisruptionBudget: minAvailable: 1` when `replicas ≥ 2`.
4. **Read-only root without granting write access to /tmp.** Some
   frameworks write temp files. Fix: mount an `emptyDir` at `/tmp`.
5. **OIDC provider trusted by "any repo in the org."** Every workflow
   gets cloud credentials. Fix: restrict the trust policy to the
   specific repo and ref.
6. **Vault agent writes key; agent reads; key rotated mid-read.** The
   key file changes between the read and the use. Fix: the agent reads
   the key into memory at startup; hot-reloads on SIGHUP.
7. **HPA with no `minReplicas`.** The service scales to zero; no agent
   is running to handle the next request. Fix: `minReplicas: 2`.
8. **Queue-based scaling without dead-letter.** Failed requests
   disappear. Fix: DLQ with retention and alerting.

## See Also

- `packaging-serving.md` — container shapes and rules.
- `framework-deploy-matrix.md` — per-framework Dockerfiles.
- `ci-resident-agents.md` — GitHub Actions, GitLab CI, Copilot, Duo.
- `observability.md` — monitoring and alerting.
- `../../agent-safety/references/sandboxing-tiers.md` — container
  isolation.
- `../../agent-safety/references/multi-tenant-isolation.md` — per-
  tenant boundaries.
- `../../agent-harness/references/harness-deploy-patterns.md` — the
  harness concerns in production.
