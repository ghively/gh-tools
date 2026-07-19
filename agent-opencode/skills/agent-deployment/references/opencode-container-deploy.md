# OpenCode Container Deployment

> Last verified: 2026-07 against OpenCode 1.18.3. OpenCode is a Bun-based
> agent runtime (TUI + headless + server). Running it in a container is
> the right shape for scheduled jobs, webhook workers, and shared
> dashboards. This reference covers the deploy path end-to-end.

OpenCode ships as a single binary (Bun-compiled) plus a config tree at
`~/.config/opencode/`. The container deploy shape is straightforward:
mount the config, expose the server port, inject provider keys via env.

## Why Containerize OpenCode?

| Use case | Why a container helps |
|---|---|
| **Scheduled jobs (cron gardener)** | Identical env every run; no "works on my laptop" drift |
| **Webhook worker** | Long-lived, restartable, isolated from the host |
| **Shared dashboard** | `opencode serve` exposed to a team; one install to update |
| **CI-resident agent** | Reproducible across CI runners |
| **Multi-tenant** | One container per tenant; isolated configs and state |
| **Air-gapped / on-prem** | Image promoted through environments without rebuild |

For interactive single-user TUI use, you usually do NOT containerize —
just install OpenCode on your machine. The container wins for unattended
and shared shapes.

## The Dockerfile

```dockerfile
# Dockerfile — OpenCode runtime
FROM oven/bun:1.1-debian AS base

# OpenCode ships as a single binary; install via the official installer
ARG OPENCODE_VERSION=1.18.3
RUN curl -fsSL https://opencode.ai/install.sh | BIN_DIR=/usr/local/bin sh

# Non-root user
RUN useradd --create-home --uid 1000 opencode
USER opencode
WORKDIR /home/opencode

# Default command: headless server
EXPOSE 4096
ENTRYPOINT ["opencode"]
CMD ["serve", "--hostname", "0.0.0.0", "--port", "4096"]
```

Notes:

- `oven/bun:1.1-debian` is the official Bun runtime image.
- OpenCode is a single binary; no `npm install` step in the image.
- Non-root user is mandatory — the safety floor assumes it.
- `opencode serve` is the headless server mode. The TUI does not work
  in a container (no TTY); use `serve` or `run` instead.

## Variants by Use Case

### Headless Server (Dashboard Backend)

```dockerfile
CMD ["serve", "--hostname", "0.0.0.0", "--port", "4096"]
```

Exposes the OpenCode HTTP/WS API; pair with the web UI or a custom
frontend. Long-lived; restart on crash.

### Scheduled Job Runner (Cron Gardener)

```dockerfile
CMD ["run", "--agent", "agent-foundry", "$(cat /workspace/prompt.md)"]
```

Runs a single prompt and exits. Pair with k8s `CronJob`, systemd timer,
or GitHub Actions `schedule:`. Idempotent — every run is from a clean
state.

### Webhook Worker

```dockerfile
CMD ["run", "--agent", "agent-foundry", "--listen", "0.0.0.0:4096"]
```

OpenCode listens for incoming prompts (POST to `/run`). Long-lived;
scale horizontally behind a load balancer.

### Batch Evaluator

```dockerfile
CMD ["run", "--agent", "agent-foundry-eval-runner", "--evals", "/evals/"]
```

Runs an eval suite and exits with status code. Pair with CI.

## Config and Skills

OpenCode reads config from `~/.config/opencode/opencode.json` and skills
from `~/.config/opencode/skills/` (or wherever `skills.paths` points).
In a container, mount these:

```yaml
# docker-compose.yml
services:
  opencode:
    build: .
    container_name: opencode
    restart: unless-stopped
    volumes:
      # The agent-opencode package (skills, agents, plugins)
      - ./agent-opencode:/home/opencode/.config/opencode/agent-opencode:ro
      # The commands (the 14 /agent-foundry-* workflows)
      - ./commands:/home/opencode/.config/opencode/commands:ro
      # The opencode.json (provider config + safety floor + agent defs)
      - ./opencode.json:/home/opencode/.config/opencode/opencode.json:ro
      # Persistent state (sessions, memory, traces)
      - opencode-state:/home/opencode/.local/share/opencode
      # Workspace (the code the agent works on)
      - ./workspace:/workspace
    working_dir: /workspace
    environment:
      ZAI_API_KEY: ${ZAI_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      TZ: ${TZ:-UTC}
      OPENCODE_LOG_LEVEL: ${LOG_LEVEL:-INFO}
    ports:
      - "4096:4096"
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:4096/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

volumes:
  opencode-state:
```

## The opencode.json for Container Deploy

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "zai-coding-plan": {
      "options": {
        "apiKey": "{env:ZAI_API_KEY}"
      }
    }
  },
  "model": "zai-coding-plan/glm-4.7",
  "small_model": "zai-coding-plan/glm-4.5-air",
  "default_agent": "agent-foundry",
  "skills": {
    "paths": [
      "/home/opencode/.config/opencode/agent-opencode/skills"
    ]
  },
  "permission": {
    "bash": {
      "curl * | *sh*": "deny",
      "rm -rf /": "deny",
      "*": "ask"
    },
    "edit": {
      "/etc/*": "deny",
      "~/.ssh/*": "deny",
      "*": "ask"
    }
  },
  "agent": {
    "agent-foundry": {
      "description": "Container-deployed agent-foundry workstation.",
      "mode": "primary",
      "permission": {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "edit": "ask",
        "bash": "ask",
        "webfetch": "allow",
        "websearch": "allow",
        "task": "allow"
      }
    }
  }
}
```

Notes for the container form:

- `{env:ZAI_API_KEY}` interpolation keeps the key out of the image.
- The skills path is absolute inside the container, matching the volume
  mount.
- `default_agent: agent-foundry` means `opencode run "..."` uses the
  agent-foundry workstation without needing `--agent`.
- `bash: ask` and `edit: ask` are intentional — the safety floor asks
  for human approval. For unattended jobs, set explicit `allow` rules
  for exactly the commands the job needs.

## ZAI-Specific Wiring

For a ZAI-only OpenCode container:

1. Set `ZAI_API_KEY` in `.env`.
2. Provider config uses `{env:ZAI_API_KEY}` interpolation (never inline).
3. Model IDs: `zai-coding-plan/glm-4.7` (frontier), `zai-coding-plan/glm-4.5-air` (small).
4. Test with: `docker compose run --rm opencode run "say ok"`.

See `zai-provider-config.md` for the full ZAI auth + model-ID reference.

## Unattended Mode (For Scheduled Jobs)

For a scheduled job (no human to approve `ask` prompts), use explicit
`allow` rules:

```json
{
  "permission": {
    "bash": {
      "git status": "allow",
      "git log *": "allow",
      "npm test": "allow",
      "npm run *": "allow",
      "curl * | *sh*": "deny",
      "rm -rf /": "deny",
      "*": "deny"
    },
    "edit": {
      "/etc/*": "deny",
      "~/.ssh/*": "deny",
      "/workspace/*": "allow",
      "*": "deny"
    }
  }
}
```

The principle: in unattended mode, default-deny everything except the
exact commands and paths the job needs. `ask` is for interactive; `deny`
is the unattended default; `allow` only for the vetted allowlist.

## The Local-Plugin Bug Workaround

OpenCode 1.18.3 has a known bug where local TypeScript plugins fail to
load (`plugin config hook failed: null is not an object`). Until the
upstream fix lands:

1. Do NOT register the agent-foundry-safety plugin in `opencode.json`
   for container deploys — it will throw on every startup.
2. Rely on the native `permission` rules for the safety floor.
3. Keep the plugin code and tests in the image for when the bug is
   fixed; just leave the `plugin` array empty.

```json
{
  "plugin": []
}
```

Once 1.18.4 or later ships with the fix, re-add:

```json
{
  "plugin": [
    ["./agent-opencode/plugins/agent-foundry-safety/index.ts",
     { "enableSecretCheck": false, "enableAuditTrail": false }]
  ]
}
```

## Persistent State

OpenCode writes state to `~/.local/share/opencode/`:

- Sessions (conversation history)
- Memory (durable across sessions)
- Traces (observability spans)
- Project snapshots (for undo/revert)

Mount this as a named volume or host path. Losing it loses all session
history and memory.

For production:

```yaml
volumes:
  opencode-state:
    driver: local
    driver_opts:
      type: nfs
      device: ":/path/on/nas"
      o: addr=nas.local,rw
```

Or back it up via restic (see `hermes-container-deploy.md` for the
restic pattern; the same shape applies here).

## Deploy

```bash
# First-time setup
git clone https://github.com/ghively/gh-tools.git
cd gh-tools/agent-opencode
./install.sh                          # installs to ~/.config/opencode/

# Container deploy
mkdir -p ~/opencode-deploy/{workspace,commands}
cd ~/opencode-deploy
cp -r ~/.config/opencode/agent-opencode .
cp ~/.config/opencode/opencode.json .
cp ~/.config/opencode/commands/agent-foundry-*.md commands/
cat > Dockerfile <<'EOF'
FROM oven/bun:1.1-debian
RUN curl -fsSL https://opencode.ai/install.sh | BIN_DIR=/usr/local/bin sh
RUN useradd --create-home --uid 1000 opencode
USER opencode
WORKDIR /home/opencode
EXPOSE 4096
ENTRYPOINT ["opencode"]
CMD ["serve", "--hostname", "0.0.0.0", "--port", "4096"]
EOF
cp /path/to/docker-compose.yml .
cp /path/to/.env.example .env
$EDITOR .env                          # set ZAI_API_KEY

# Start
docker compose up -d --build
docker compose logs -f opencode

# Verify
curl -sf http://localhost:4096/health
docker compose run --rm opencode run "say ok"
```

## Health Check

OpenCode's server mode exposes `/health`:

```bash
curl -sf http://localhost:4096/health
```

Returns 200 when:

- The Bun runtime is up
- The config loaded successfully
- At least one provider is configured

It does NOT verify the provider key is valid (no billable call). For a
deeper check, run `opencode run "ping"` as a synthetic.

## Multi-Tenant

For multi-tenant OpenCode (one container per tenant):

```bash
# Per-tenant deploy
docker run -d \
  --name opencode-tenant-a \
  -v /tenants/a/opencode.json:/home/opencode/.config/opencode/opencode.json:ro \
  -v /tenants/a/state:/home/opencode/.local/share/opencode \
  -e ZAI_API_KEY=$TENANT_A_ZAI_KEY \
  -p 4101:4096 \
  opencode:latest

docker run -d \
  --name opencode-tenant-b \
  -v /tenants/b/opencode.json:/home/opencode/.config/opencode/opencode.json:ro \
  -v /tenants/b/state:/home/opencode/.local/share/opencode \
  -e ZAI_API_KEY=$TENANT_B_ZAI_KEY \
  -p 4102:4096 \
  opencode:latest
```

Each tenant gets isolated config, state, and keys. The container image
is identical; only the volume mounts and env differ.

For Kubernetes, use a `StatefulSet` with per-pod PVCs and per-tenant
`Secret`/`ConfigMap`.

## Kubernetes

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: opencode
spec:
  serviceName: opencode
  replicas: 1
  selector:
    matchLabels: {app: opencode}
  template:
    metadata:
      labels: {app: opencode}
    spec:
      containers:
      - name: opencode
        image: ghively/opencode:1.18.3
        ports: [{containerPort: 4096}]
        env:
        - name: ZAI_API_KEY
          valueFrom:
            secretKeyRef: {name: opencode-providers, key: zai-api-key}
        volumeMounts:
        - name: config
          mountPath: /home/opencode/.config/opencode/opencode.json
          subPath: opencode.json
        - name: state
          mountPath: /home/opencode/.local/share/opencode
        - name: workspace
          mountPath: /workspace
        readinessProbe:
          httpGet: {path: /health, port: 4096}
          initialDelaySeconds: 10
        livenessProbe:
          httpGet: {path: /health, port: 4096}
          initialDelaySeconds: 30
          periodSeconds: 30
  volumeClaimTemplates:
  - metadata: {name: state}
    spec:
      accessModes: [ReadWriteOnce]
      resources: {requests: {storage: 10Gi}}
```

The `StatefulSet` (not `Deployment`) is correct because OpenCode has
persistent state. Pair with a `Service` for cluster-internal access and
an `Ingress` for external.

## Upgrades

```bash
# Pull the new OpenCode image
docker compose pull

# Rolling restart
docker compose up -d

# Verify
docker compose logs --tail 50 opencode
curl -sf http://localhost:4096/health
```

For major version upgrades:

1. Read the release notes for breaking config changes.
2. Snapshot the state volume.
3. Test the upgrade on a staging container first.
4. Promote the new image through environments.

## Pitfalls

1. **TUI mode in a container.** `opencode` (default TUI) hangs because
   there is no TTY. Fix: use `opencode serve` (long-lived) or
   `opencode run` (one-shot).
2. **Plugin array populated with the broken plugin.** OpenCode 1.18.3
   fails to load any plugin; startup logs `plugin config hook failed`.
   Fix: leave `plugin: []` until 1.18.4+.
3. **Inline API key in opencode.json.** Bakes into the image; leaks on
   push. Fix: `{env:ZAI_API_KEY}` interpolation.
4. **No persistent state volume.** Container restart loses all
   sessions and memory. Fix: mount `~/.local/share/opencode/` to a
   named volume.
5. **Workspace mounted read-write with no permission floor.** The agent
   can overwrite the workspace. Fix: explicit `edit: allow` for the
   workspace path; `deny` for everything else.
6. **Asking for unattended jobs.** `bash: ask` blocks the run when no
   human is there. Fix: explicit allowlist + default deny for unattended.
7. **All traffic on the same port.** Health, API, and metrics on 4096.
   Fix: separate ports or paths; pair with proper ingress.
8. **Running as root.** The safety floor assumes non-root. Fix:
   `USER opencode` (uid 1000) in the Dockerfile.
9. **No log driver caps.** OpenCode can be verbose; logs fill disk.
   Fix: `logging.options.max-size` + `max-file`.
10. **Trusting `--auto` in unattended mode.** `--auto` approves all
    non-denied permissions — fine for trusted dev, dangerous in
    production. Fix: explicit denylist + scoped allowlist.

## See Also

- `zai-provider-config.md` — the auth + model-ID deep dive.
- `hermes-container-deploy.md` — the Hermes runtime in a container.
- `framework-deploy-matrix.md` — per-framework recipes for all 13
  harnesses.
- `packaging-serving.md` — the broader packaging doctrine.
- `agent-harness/references/harness-deploy-patterns.md` — how the
  harness concerns change in production container deploys.
- `agent-harness/references/harness-comparison.md` — the 13-harness
  comparison this runtime sits in.
