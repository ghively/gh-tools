# Hermes Agent Container Deployment

> Last verified: 2026-07. Hermes is a separate Python-based agent runtime
> (CLI, `config.yaml`, s6-overlay supervision, swarm profiles). It is
> distinct from OpenCode. The agent-foundry knowledge library covers both;
> this reference is Hermes-specific. For OpenCode-in-a-container, see
> `opencode-container-deploy.md`.

Hermes is built to run as a long-lived agent host: a daemon, a swarm of
worker profiles, a gateway, and optional dashboard. The canonical
deployment shape is a Docker container using s6-overlay as the
supervision tree, with all configuration driven by environment variables
and `config.yaml`. This reference covers the complete deploy path.

## What Hermes Needs

A production Hermes install assumes:

| Component | Purpose |
|---|---|
| `hermes` CLI | The Python entry point (PyPI package or git checkout) |
| `~/.hermes/` state tree | Sessions, memory, MCP server configs, skills |
| `config.yaml` | Model routing, swarm profiles, tool allowlists |
| `AGENTS-system-prompt.md` | The system-prompt baseline |
| Model API keys | ZAI / Anthropic / OpenAI / Bedrock / Vertex |
| Optional: gateway | HTTP/WebSocket entry point for the dashboard |
| Optional: dashboard | The browser UI (Electron desktop app or web) |
| Optional: MCP servers | External tools registered in `mcp-config-template.yaml` |
| Optional: Telegram bot | For mobile-driven operation |

The minimal install is the CLI + `config.yaml` + one provider key. The
full install adds the gateway, dashboard, and bot.

## Container Shape

```text
┌──────────────────────────────────────────────────────────┐
│  hermes container (s6-overlay supervision tree)          │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  s6-overlay (init)                                 │  │
│  │   ├── hermes-gateway    (HTTP/WS entry)            │  │
│  │   ├── hermes-agent      (the Python daemon)        │  │
│  │   ├── hermes-bot        (Telegram bot, optional)   │  │
│  │   ├── hermes-dashboard  (web UI, optional)         │  │
│  │   ├── restic-backup     (scheduled backup)         │  │
│  │   └── nightly-distillation (4 AM cron)             │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  /data (persistent volume)                         │  │
│  │   ├── state/         sessions, memory, traces      │  │
│  │   ├── skills/        the Hermes skills library     │  │
│  │   ├── config.yaml    model routing + swarm         │  │
│  │   └── wiki/          the LLM wiki / RAG corpus     │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Env vars: ZAI_API_KEY, ANTHROPIC_API_KEY, ...          │
└──────────────────────────────────────────────────────────┘
```

The s6-overlay supervision tree is what makes Hermes production-grade
in a container: each service restarts independently, logs are captured,
and the whole tree shuts down cleanly on `SIGTERM`.

## The Dockerfile

```dockerfile
# Dockerfile
FROM python:3.12-slim AS base

# s6-overlay brings the supervision tree
ARG S6_VERSION=v3.2.0.0
ADD https://github.com/just-containers/s6-overlay/releases/download/${S6_VERSION}/s6-overlay-noarch.tar.xz /tmp/
ADD https://github.com/just-containers/s6-overlay/releases/download/${S6_VERSION}/s6-overlay-x86_64.tar.xz /tmp/
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz && \
    tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz && \
    rm /tmp/s6-overlay-*.tar.xz

# Hermes + Python deps
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Skills + system prompt baseline (the knowledge layer)
COPY skills/         /hermes/skills/
COPY AGENTS-system-prompt.md /hermes/

# s6 service definitions (one per long-lived service)
COPY services/       /etc/s6-overlay/s6-rc.d/

# Entry: s6-overlay as init
ENTRYPOINT ["/init"]
```

The image contains the Hermes code, the skills library, and the s6
service definitions. It contains **no secrets** — those come from the
runtime env.

## s6 Service Definitions

Each long-lived Hermes component is an s6 service. The pattern is one
directory per service under `/etc/s6-overlay/s6-rc.d/`:

```text
services/
├── hermes-agent/
│   ├── run              # exec hermes --serve --config /data/config.yaml
│   ├── type             # "longlive"
│   └── dependencies.d/  # hermes-gateway (if you want gateway first)
├── hermes-gateway/
│   ├── run              # exec hermes gateway --port 8000
│   └── type             # "longlive"
├── hermes-bot/
│   ├── run              # exec hermes bot
│   ├── type             # "longlive"
│   └── dependencies.d/  # hermes-agent
├── restic-backup/
│   ├── run              # exec /usr/local/bin/hermes-backup.sh
│   ├── type             # "longlive"
│   └── dependencies.d/  # hermes-agent
└── nightly-distillation/
    ├── run              # exec cron-driven distillation loop
    └── type             # "longlive"
```

Each `run` script ends with `exec` so s6 owns the PID and can restart
it. A typical `hermes-agent/run`:

```bash
#!/command/execlineb -P
s6-setuidgid hermes
backtick -i HERMES_CONFIG { echo /data/config.yaml }
importas HERMES_CONFIG HERMES_CONFIG
exec hermes --serve --config ${HERMES_CONFIG}
```

The full s6 authoring pattern lives in the Hermes runtime skill's
`hermes-s6-container-supervision` reference; the above is the deploy
shape.

## config.yaml (The Routing Layer)

The Hermes config lives at `/data/config.yaml` (mounted from the host
or generated on first run). The minimal ZAI-only config:

```yaml
llm:
  backends:
    - name: zai
      kind: openai
      base_url: "https://open.bigmodel.cn/api/paas/v4/"
      api_key_env: ZAI_API_KEY
      default_model: glm-4.7
      models:
        - glm-5.2
        - glm-4.7
        - glm-4.7-flashx
        - glm-4.5-air
        - glm-5v-turbo

  routing:
    orchestrator: zai/glm-5.2
    builder:      zai/glm-4.7
    reviewer:     zai/glm-4.7
    researcher:   zai/glm-4.7
    title:        zai/glm-4.5-air
    summary:      zai/glm-4.5-air

swarm:
  profiles:
    - name: default
      workers: [orchestrator, builder, reviewer, qa, researcher, ops]
      nightly: [distillation]

gateway:
  enabled: true
  port: 8000
  auth:
    mode: token
    token_env: HERMES_GATEWAY_TOKEN

bot:
  enabled: true
  telegram_token_env: HERMES_TELEGRAM_TOKEN

backup:
  restic:
    repo_env: RESTIC_REPOSITORY
    password_env: RESTIC_PASSWORD
    schedule: "0 4 * * *"            # 4 AM daily
    keep_daily: 7
    keep_weekly: 4

paths:
  state: /data/state
  skills: /hermes/skills
  wiki: /data/wiki
  system_prompt: /hermes/AGENTS-system-prompt.md
```

See `zai-provider-config.md` for the full ZAI auth flow and per-tier
model placement.

## docker-compose.yml

```yaml
services:
  hermes:
    build: .
    container_name: hermes
    restart: unless-stopped
    volumes:
      - hermes-data:/data
      - ./config.yaml:/data/config.yaml:ro
      - ./skills:/hermes/skills:ro
    environment:
      # Provider keys (from .env, never committed)
      ZAI_API_KEY: ${ZAI_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      # Gateway
      HERMES_GATEWAY_TOKEN: ${HERMES_GATEWAY_TOKEN}
      # Optional bot
      HERMES_TELEGRAM_TOKEN: ${HERMES_TELEGRAM_TOKEN:-}
      # Backup
      RESTIC_REPOSITORY: ${RESTIC_REPOSITORY:-}
      RESTIC_PASSWORD: ${RESTIC_PASSWORD:-}
      # Ops
      TZ: ${TZ:-UTC}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    ports:
      - "8000:8000"        # gateway
    healthcheck:
      test: ["CMD", "curl", "-sf", "-H", "Authorization: Bearer ${HERMES_GATEWAY_TOKEN}", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"

volumes:
  hermes-data:
```

## .env (gitignored)

```bash
# .env — never commit
ZAI_API_KEY=ae697f95...Tib8Fbw...
ANTHROPIC_API_KEY=sk-ant-...
HERMES_GATEWAY_TOKEN=...
HERMES_TELEGRAM_TOKEN=...
RESTIC_REPOSITORY=...
RESTIC_PASSWORD=...
TZ=America/Chicago
LOG_LEVEL=INFO
```

## Deploy

```bash
# First-time setup
git clone https://github.com/ghively/hermes-agent.git hermes
cd hermes
cp .env.example .env
$EDITOR .env                 # fill in keys
cp config.example.yaml config.yaml
$EDITOR config.yaml          # tune routing for your models

# Build + start
docker compose up -d --build
docker compose logs -f hermes

# Verify
curl -sf -H "Authorization: Bearer $HERMES_GATEWAY_TOKEN" \
  http://localhost:8000/health
```

## ZAI-Specific Wiring

For a ZAI-only deployment (the user's stated case):

1. Set `ZAI_API_KEY` in `.env`.
2. In `config.yaml`, configure the `zai` backend as shown above.
3. Set `routing` to use `zai/glm-*` for every role.
4. Leave `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc. unset (or empty).
5. Test with: `docker compose exec hermes hermes --prompt "say ok"`.

The minimal model routing for cost-conscious operation:

```yaml
routing:
  orchestrator: zai/glm-5.2          # frontier, judgment-heavy
  builder:      zai/glm-4.7          # strong general
  reviewer:     zai/glm-4.7
  researcher:   zai/glm-4.7
  qa:           zai/glm-4.7
  title:        zai/glm-4.5-air      # cheap, fast
  summary:      zai/glm-4.5-air      # cheap, fast
  # Free tier (glm-4.7-flash) is for dev only — rate-limited
```

## Multi-Provider Routing

For production with provider diversity (ZAI + Anthropic + Bedrock):

```yaml
llm:
  backends:
    - name: zai
      kind: openai
      base_url: "https://open.bigmodel.cn/api/paas/v4/"
      api_key_env: ZAI_API_KEY
      default_model: glm-4.7
    - name: anthropic
      kind: anthropic
      api_key_env: ANTHROPIC_API_KEY
      default_model: claude-sonnet-5
    - name: bedrock
      kind: bedrock
      aws_region_env: AWS_REGION
      default_model: us.anthropic.claude-sonnet-4-6

  routing:
    orchestrator: anthropic/claude-sonnet-5      # strongest reasoning
    builder:      zai/glm-4.7                    # value tier
    reviewer:     anthropic/claude-sonnet-5
    researcher:   zai/glm-4.7
    title:        zai/glm-4.5-air
    summary:      zai/glm-4.5-air
    fallback:
      - anthropic/claude-sonnet-5
      - zai/glm-4.7
      - bedrock/us.anthropic.claude-sonnet-4-6
```

The `fallback` chain is consulted in order on rate-limit or error.

## Volume and Backup

The `/data` volume is the durable state: sessions, memory, the wiki, the
audit trail. Lose it and the agent forgets everything.

Hermes ships a restic backup script (`scripts/hermes-vault-backup.sh`
in the source). Schedule it via s6 (the `restic-backup` service above)
to run nightly. Verify restore quarterly — an untested backup is not a
backup.

The backup includes:

- `/data/state/` — sessions, memory
- `/data/wiki/` — the knowledge corpus
- `/data/skills/` — your custom skills
- `/data/config.yaml` — the routing layer

The backup excludes:

- `/data/cache/` — regenerable
- `/data/logs/` — already in docker logs

## Health Check

The gateway's `/health` endpoint returns 200 when the agent is ready to
serve. Use it for:

- Docker `healthcheck`
- Kubernetes readiness/liveness probes
- Load balancer health

```bash
# Container health
curl -sf -H "Authorization: Bearer $HERMES_GATEWAY_TOKEN" \
  http://localhost:8000/health
```

The health check verifies:

- The Python daemon is running
- The gateway can reach it
- At least one LLM backend is configured

It does **not** verify the LLM key is valid (that requires a billable
call). Wire a synthetic check separately if you need that signal.

## Observability

Hermes emits structured logs to stdout (captured by docker json-file
driver). For production:

- Ship logs to a central collector (Vector, Fluent Bit, Promtail).
- Export metrics to Prometheus via the gateway's `/metrics` endpoint.
- For OpenTelemetry traces, set `OTEL_EXPORTER_OTLP_ENDPOINT` and
  `OTEL_SERVICE_NAME=hermes` — Hermes emits GenAI-compliant spans.

See `observability.md` for the broader agent-observability doctrine.

## Upgrades

```bash
# Pull latest Hermes
docker compose pull
# OR rebuild from source
docker compose build --pull

# Rolling restart (s6 keeps serving during the restart window)
docker compose up -d

# Verify
docker compose logs --tail 50 hermes
curl -sf -H "Authorization: Bearer $HERMES_GATEWAY_TOKEN" \
  http://localhost:8000/health
```

For major version upgrades, snapshot the volume first:

```bash
docker run --rm -v hermes-data:/data -v $(pwd):/backup \
  alpine tar czf /backup/hermes-data-$(date +%Y%m%d).tar.gz /data
```

## Multi-Host (Fleet)

For a fleet of Hermes instances (one per host, each with its own bot
token and swarm profile):

```bash
# Per-host env
HERMES_HOST_ID=lab-01
HERMES_BOT_TOKEN=...

# Bootstrap from a reference install
hermes-instance-deploy \
  --host lab-01 \
  --bot-token $HERMES_BOT_TOKEN \
  --config reference-config.yaml \
  --tags lab,prod
```

The `hermes-instance-deployment` skill covers fleet topology in depth.
The container shape is identical per host; only the env vars differ.

## Pitfalls

1. **Secrets in the image.** `ENV ZAI_API_KEY=...` in the Dockerfile.
   Fix: env vars at runtime; `.dockerignore` for `.env`.
2. **No persistent volume.** Container restart wipes the agent's
   memory. Fix: mount `/data` to a named volume or host path.
3. **`config.yaml` in the image.** Edit-deploy cycle for every routing
   change. Fix: mount `config.yaml` from the host; image stays stable.
4. **s6 service without `exec`.** The `run` script does
   `hermes --serve` without `exec`; s6 cannot track the PID; restart
   does not work. Fix: every `run` ends with `exec`.
5. **Gateway port exposed without auth.** Anyone on the network can
   drive your agent. Fix: `gateway.auth.mode: token` + a strong
   `HERMES_GATEWAY_TOKEN`.
6. **Unhealthy health check that always passes.** The check just
   verifies the port is open; the daemon may be wedged. Fix: check
   `/health` which verifies the agent can serve.
7. **Backup that has never been restored.** Quietly failing for months.
   Fix: quarterly restore drill to a scratch volume.
8. **All providers pointing to one key.** The single key hits rate
   limits; everything fails. Fix: per-provider keys; fallback chain.
9. **Free-tier model in production routing.** `glm-4.7-flash` rate-
   limits after ~100 calls/hour. Fix: use `glm-4.5-air` or `glm-4.7`
   for production; reserve Flash for dev.
10. **No log driver caps.** Docker logs fill the disk; the container
    wedges. Fix: `logging.options.max-size` + `max-file`.

## See Also

- `zai-provider-config.md` — the ZAI auth + model-ID deep dive.
- `opencode-container-deploy.md` — running OpenCode itself in a container.
- `framework-deploy-matrix.md` — per-framework container recipes for all
  13 harnesses.
- `packaging-serving.md` — the broader packaging doctrine Hermes fits in.
- `scheduled-event-driven-agents.md` — the design layer for the cron /
  nightly-distillation service.
- `observability.md` — Prometheus metrics, OTel traces, log shipping.
- The source `hermes-runtime` plugin in `ghively/agent-marketplace` —
  the Hermes-specific skills (swarm role manuals, s6 authoring, backup,
  instance deployment) in their original form.
