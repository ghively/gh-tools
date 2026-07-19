# Framework Deploy Matrix

Every major agent framework can be deployed in a container. The shape
is similar across all of them (Python or Node base image, install deps,
inject provider key, run entrypoint) but the entrypoints, state
directories, and production concerns differ.

This reference gives one worked Docker recipe per harness for the 13
harnesses covered in `agent-harness/references/harness-comparison.md`.
Use it as a starting point; consult the framework's current docs for
breaking changes before shipping.

## The Universal Container Shape

```text
┌─────────────────────────────────────────────────┐
│  Container                                      │
│  ┌───────────────────────────────────────────┐  │
│  │  Base image (python / node / bun)         │  │
│  │  Framework deps (pinned)                  │  │
│  │  Agent code + config                      │  │
│  │  Non-root user                            │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  Env: PROVIDER_API_KEY (never in image)         │
│  Mounts: /data (persistent state), /workspace   │
│  Expose: HTTP port OR one-shot run              │
└─────────────────────────────────────────────────┘
```

The differences are: base image, install command, entrypoint command,
state directory, and any framework-specific supervision (LangGraph's
checkpointer, MAF's runtime host, etc.).

## Provider Config (All Frameworks)

Every recipe below uses ZAI as the provider. The pattern is identical
for Anthropic, OpenAI, Bedrock, Vertex — only the env var and base URL
change. See `zai-provider-config.md` for the per-framework provider
wiring code.

## Per-Framework Recipes

### 1. Claude Agent SDK

**Base:** Python 3.12 or Node 22
**State dir:** `/data/sessions`
**Entrypoint:** `python -m my_agent` or `node agent.js`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir claude-agent-sdk==0.4.*
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --create-home --uid 1000 agent && mkdir -p /data/sessions && chown agent /data/sessions
USER agent
ENV ANTHROPIC_API_KEY=""
CMD ["python", "-m", "my_agent"]
```

```yaml
# docker-compose.yml
services:
  agent:
    build: .
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      # For ZAI via the OpenAI-compatible endpoint:
      # OPENAI_BASE_URL: https://open.bigmodel.cn/api/paas/v4/
      # OPENAI_API_KEY: ${ZAI_API_KEY}
    volumes:
      - agent-data:/data/sessions
      - ./workspace:/workspace
    restart: unless-stopped
volumes: {agent-data: {}}
```

### 2. OpenAI Agents SDK

**Base:** Python 3.12
**State dir:** application-managed (no built-in session store)
**Entrypoint:** `python -m my_agents_app`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir openai-agents pydantic
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV OPENAI_API_KEY=""
# For ZAI: OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
CMD ["python", "-m", "my_agents_app"]
```

You must add a session store yourself — the SDK is stateless across
runs. Use SQLite/Postgres for production.

### 3. Copilot SDK

**Base:** Node 22 (LTS) or .NET 8
**State dir:** managed by Mission Control (GitHub-side)
**Entrypoint:** `node dist/index.js`

```dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY dist/ dist/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV GH_COPILOT_TOKEN=""
CMD ["node", "dist/index.js"]
```

Sessions live on GitHub's infrastructure; the container is stateless
from a session perspective. Auth via GitHub App token.

### 4. Google ADK

**Base:** Python 3.12
**State dir:** `/data`
**Entrypoint:** `python -m my_adk_agent`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir google-adk google-cloud-aiplatform
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && mkdir -p /data && chown agent /data
USER agent
# Auth via Workload Identity (recommended) or GOOGLE_APPLICATION_CREDENTIALS
ENV GOOGLE_CLOUD_PROJECT=my-project
ENV GOOGLE_CLOUD_LOCATION=us-central1
CMD ["python", "-m", "my_adk_agent"]
```

For GKE: use Workload Identity; no key in the image. For other
orchestrators: mount a service-account key as a secret.

### 5. Microsoft Agent Framework (MAF)

**Base:** Python 3.12 or .NET 8
**State dir:** managed by `AgentRuntime`
**Entrypoint:** `python -m my_maf_app`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir microsoft-agents-core microsoft-agents-hosting
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV AZURE_OPENAI_ENDPOINT=""
ENV AZURE_OPENAI_API_KEY=""
CMD ["python", "-m", "my_maf_app"]
```

For Azure: prefer Managed Identity over API keys. Pair with Application
Insights for native observability.

### 6. LangGraph

**Base:** Python 3.12
**State dir:** checkpointer DB (SQLite/Postgres)
**Entrypoint:** `python -m my_graph_agent`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "langgraph>=1.2,<2" \
    "langgraph-checkpoint-postgres>=2.0" \
    langchain-anthropic
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV ANTHROPIC_API_KEY=""
ENV CHECKPOINTER_DB=postgresql+psycopg://agent:***@db:5432/langgraph
CMD ["python", "-m", "my_graph_agent"]
```

For production: pair with a Postgres container for the checkpointer.
SQLite works for single-host dev only.

### 7. CrewAI

**Base:** Python 3.12
**State dir:** application-managed
**Entrypoint:** `python -m my_crew`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "crewai>=1.15,<2" \
    "crewai-tools>=0.40"
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV OPENAI_API_KEY=""
CMD ["python", "-m", "my_crew"]
```

CrewAI Flows give you ordered stateful execution; pair with Redis or
Postgres for cross-run state.

### 8. LlamaIndex

**Base:** Python 3.12
**State dir:** index storage (vector DB, docstore)
**Entrypoint:** `python -m my_agent_workflow`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
    "llama-index>=0.11" \
    "llama-index-llms-openai-like" \
    "llama-index-embeddings-openai"
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
COPY index/ /index/
RUN useradd --uid 1000 agent && chown -R agent /app /index
USER agent
ENV OPENAI_API_KEY=""
CMD ["python", "-m", "my_agent_workflow"]
```

The index is large — bake it into the image for immutable deploys, or
mount it from object storage for fast iteration.

### 9. Pydantic AI

**Base:** Python 3.12
**State dir:** application-managed
**Entrypoint:** `python -m my_pydantic_agent`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "pydantic-ai>=0.20" "logfire>=3"
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV OPENAI_API_KEY=""
ENV LOGFIRE_TOKEN=""
CMD ["python", "-m", "my_pydantic_agent"]
```

Pair with Logfire for native observability; OTel also works.

### 10. smolagents

**Base:** Python 3.12 (sandbox strongly recommended)
**State dir:** none (single-run by default)
**Entrypoint:** `python -m my_smolagents_app`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "smolagents>=0.4"
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV HF_TOKEN=""
CMD ["python", "-m", "my_smolagents_app"]
```

smolagents writes and executes Python — sandbox aggressively. Run with
`--security-opt no-new-privileges`, drop all capabilities, mount the
workspace read-only where possible. See `agent-safety/references/sandboxing-tiers.md`.

### 11. Vercel AI SDK

**Base:** Node 22 or Bun 1.1
**State dir:** application-managed
**Entrypoint:** `node dist/index.js` or `bun dist/index.js`

```dockerfile
FROM oven/bun:1.1-debian
WORKDIR /app
COPY package.json bun.lockb ./
RUN bun install --frozen-lockfile --production
COPY src/ src/
COPY tsconfig.json ./
RUN bun build src/index.ts --outdir dist --target bun
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV OPENAI_API_KEY=""
CMD ["bun", "dist/index.js"]
```

Bun compiles faster and uses less memory than Node for AI SDK apps.

### 12. Mastra

**Base:** Node 22 or Bun 1.1
**State dir:** Mastra Memory store
**Entrypoint:** `node dist/index.js`

```dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY dist/ dist/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV OPENAI_API_KEY=""
ENV MASTRA_MEMORY_BACKEND=postgresql
ENV DATABASE_URL=postgresql://agent:***@db:5432/mastra
CMD ["node", "dist/index.js"]
```

Pair with Postgres for cross-run memory.

### 13. Custom Provider-SDK Loop

**Base:** whatever language your loop is in
**State dir:** wherever you put it
**Entrypoint:** your loop entrypoint

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY src/ src/
RUN useradd --uid 1000 agent && chown -R agent /app
USER agent
ENV ZAI_API_KEY=""
ENV OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
CMD ["python", "-m", "my_agent"]
```

The custom loop is the easiest to containerize — there is no framework
machinery to wrangle. Add session persistence, observability, and HITL
as you need them (see `agent-harness` skill).

## Common docker-compose.yml

A reusable shape that works for any of the above:

```yaml
services:
  agent:
    build: .
    container_name: ${AGENT_NAME:-agent}
    restart: unless-stopped
    environment:
      # Provider (one or more)
      ZAI_API_KEY: ${ZAI_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      OPENAI_API_KEY: ${OPENAI_API_KEY:-}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-https://api.openai.com/v1/}
      # Observability
      OTEL_EXPORTER_OTLP_ENDPOINT: ${OTEL_ENDPOINT:-}
      OTEL_SERVICE_NAME: ${AGENT_NAME:-agent}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      TZ: ${TZ:-UTC}
    volumes:
      - agent-data:/data
      - ./workspace:/workspace
    working_dir: /workspace
    ports:
      - "${AGENT_PORT:-8000}:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
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
  agent-data:
```

## Universal .env

```bash
# .env — never commit
ZAI_API_KEY=ae697f95...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
AGENT_NAME=my-agent
AGENT_PORT=8000
LOG_LEVEL=INFO
TZ=UTC
OTEL_ENDPOINT=https://otlp-collector.example.com
```

## Universal .dockerignore

```
.git
.gitignore
.env
.env.*
.venv
venv
__pycache__
*.pyc
node_modules
dist
build
.DS_Store
.idea
.vscode
*.log
*.jsonl
```

## Universal .gitignore

```
.env
.env.*
*.log
*.jsonl
__pycache__/
node_modules/
dist/
.venv/
```

## Health Check Patterns

| Framework | Health endpoint | Synthetic alternative |
|---|---|---|
| Claude Agent SDK | your app's `/health` | `opencode run ping` style smoke |
| OpenAI Agents SDK | your app's `/health` | a no-op agent run |
| Copilot SDK | Mission Control | session list |
| LangGraph | `/health` (your server) | one graph invoke with a trivial input |
| CrewAI | your app's `/health` | one kickoff with a trivial task |
| LlamaIndex | `/health` | a 1-token completion |
| MAF | `/health` via runtime host | a single conversable ping |
| Custom loop | your app's `/health` | a `--smoke` flag on the entrypoint |

Always implement `/health` even if the framework does not require it.
Without it, the orchestrator cannot tell a wedged agent from a healthy
one.

## Multi-Container Topologies

For production, the single-container shape usually grows into:

```text
┌─────────────────────────────────────────────────────────┐
│  docker-compose / k8s                                   │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │  agent   │ ── │ postgres │    │  OTel collector  │   │
│  │          │    │  (state) │    │                  │   │
│  └──────────┘    └──────────┘    └──────────────────┘   │
│       │                                                │
│       │           ┌──────────┐    ┌──────────────────┐  │
│       └─────────► │  redis   │    │  vector db       │  │
│                   │ (cache)  │    │  (memory/RAG)    │  │
│                   └──────────┘    └──────────────────┘  │
│                                                         │
│  Env: ZAI_API_KEY from docker secret / k8s Secret       │
└─────────────────────────────────────────────────────────┘
```

- **Postgres** for session state and checkpointer (LangGraph, Mastra).
- **Redis** for tool-result cache and rate-limit state.
- **Vector DB** (Qdrant, Weaviate, Pinecone) for memory and RAG.
- **OTel collector** for trace export.

## Kubernetes Patterns

For each framework, the k8s shape is:

- **StatefulSet** for stateful agents (LangGraph, Mastra, MAF).
- **Deployment** for stateless agents (Copilot SDK, custom loop).
- **CronJob** for scheduled jobs (any framework, one-shot).
- **Job** for batch evals (any framework).

Pair with:

- `Secret` for provider keys.
- `ConfigMap` for non-secret config.
- `PersistentVolumeClaim` for `/data` and `/workspace`.
- `Service` + `Ingress` for HTTP entrypoints.
- `PodDisruptionBudget` for HA.
- `HorizontalPodAutoscaler` for stateless scaling.

See `opencode-container-deploy.md` for a worked OpenCode StatefulSet;
the same pattern applies to every framework.

## Framework-Specific Pitfalls

| Framework | Pitfall | Fix |
|---|---|---|
| Claude Agent SDK | Permission mode `bypassPermissions` in production | Default `acceptEdits` with explicit allowlist |
| OpenAI Agents SDK | No session store — sessions die with the process | Add Postgres-backed store |
| Copilot SDK | Per-user tokens in shared deployments | Use GitHub App auth, not user tokens |
| Google ADK | Static service-account key in the image | Workload Identity on GKE |
| MAF | Runtime host wedged but container healthy | Liveness probe on `/health` not just TCP |
| LangGraph | SQLite checkpointer in production | Postgres checkpointer + StatefulSet |
| CrewAI | Unbounded `max_iter` on tasks | Explicit `max_iter` per task |
| LlamaIndex | Cold index load every start | Pre-built index in image or object storage |
| Pydantic AI | Logfire export leaks PII | Redaction layer before export |
| smolagents | Unrestricted code execution | Drop capabilities; no-new-privileges; read-only mounts |
| Vercel AI SDK | Edge runtime quirks in container | Use `--target bun` for non-edge deploys |
| Mastra | Memory backend defaults to in-process | Set `MASTRA_MEMORY_BACKEND=postgresql` |
| Custom loop | No doom-loop detector | Add step cap + repetition detector (see `agent-harness/references/doom-loop-prevention.md`) |

## See Also

- `zai-provider-config.md` — per-framework provider wiring code.
- `hermes-container-deploy.md` — the Hermes runtime in a container.
- `opencode-container-deploy.md` — OpenCode in a container.
- `packaging-serving.md` — the broader packaging doctrine.
- `agent-harness/references/harness-comparison.md` — the 13-harness
  comparison this deploy matrix is based on.
- `agent-harness/references/harness-deploy-patterns.md` — how the
  harness concerns change in container deploys.
- `assets/deploy-templates/` — copy-paste Dockerfiles, compose files,
  and entrypoint scripts.
