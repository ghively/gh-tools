# ZAI (GLM) Provider Configuration

> Last verified: 2026-07. ZAI is the operator alias for Zhipu AI's GLM
> platform (bigmodel.cn / open.bigmodel.cn). The API surface, model IDs,
> and pricing tiers move quickly — re-check
> [docs.bigmodel.cn](https://docs.bigmodel.cn/cn/guide/start/model-overview)
> and [open.bigmodel.cn/pricing](https://open.bigmodel.cn/pricing) before
> locking a deployment.

ZAI is the model provider behind the GLM family (GLM-5.2 flagship, GLM-4.7,
GLM-4.5-air, free Flash tier, GLM-5V-Turbo for vision). It is OpenAI-API-
compatible at the wire level, which means most agent harnesses can call it
with a base URL swap.

This reference covers ZAI auth, model IDs, and configuration across every
host that matters: OpenCode, Hermes, the major agent frameworks, and
container deployments.

## The Auth Model

ZAI uses a single API key per account, formatted as
`<numeric-id>.<base64-secret>` (e.g., `ae697f95...Tib8Fbw...`). Treat it
like any provider API key:

- **Never bake it into an image.** Inject via env var, secret, or vault.
- **Rotate on leak.** ZAI keys do not auto-expire; a leaked key is live
  until you rotate.
- **Scope per environment.** Production, staging, and dev should use
  different keys when the platform supports it (ZAI's per-key scoping is
  limited today — treat each key as account-scoped).
- **Set spend alerts.** ZAI billing is metered per token; a runaway agent
  burns cash. Configure alerts in the ZAI console.

The standard env var name is `ZAI_API_KEY`. Some harnesses use
`ZHIPU_API_KEY` or `GLM_API_KEY`; pick one and standardize.

## Model IDs (July 2026)

| Model | ID | Use |
|---|---|---|
| GLM-5.2 (flagship) | `glm-5.2` | 1M context, 128K output, SOTA coding |
| GLM-4.7 | `glm-4.7` | Strong general-purpose, 200K context |
| GLM-4.7-FlashX | `glm-4.7-flashx` | Fast value tier |
| GLM-4.7-Flash | `glm-4.7-flash` | **Free tier** |
| GLM-4.5-air | `glm-4.5-air` | Small/fast for titles, routing |
| GLM-5V-Turbo | `glm-5v-turbo` | Vision |

The `provider/model-id` form is used by OpenCode and frameworks that carry
a provider prefix (`zai-coding-plan/glm-4.7`). The bare form is used by
the OpenAI-compatible client (`model="glm-4.7"`).

ZAI is also available via Vertex AI as "GLM 5" / "GLM 4.7" (ZAI.org) —
different model IDs and a different auth flow (Google Workload Identity
instead of `ZAI_API_KEY`).

## OpenAI-Compatible Endpoint

ZAI exposes an OpenAI-compatible chat completions API:

```
Base URL:  https://open.bigmodel.cn/api/paas/v4/
Endpoint:  /chat/completions
Auth:      Bearer <ZAI_API_KEY>
```

Any OpenAI-compatible client (the `openai` SDK, LangChain's
`ChatOpenAI`, Vercel AI SDK's `openai` provider, etc.) works with this
base URL. Set:

```bash
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
OPENAI_API_KEY=$ZAI_API_KEY
```

…and call `model="glm-4.7"`. This is the easiest path for any framework
that does not have a native ZAI integration.

## In OpenCode

`opencode.json` provider config:

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
  "small_model": "zai-coding-plan/glm-4.5-air"
}
```

Notes:

- The `apiKey` value supports `{env:VAR}` interpolation. Never hardcode
  the key in `opencode.json`.
- `zai-coding-plan` is the provider ID OpenCode uses (it ships with
  ZAI support built in).
- `model` is the primary (frontier) model; `small_model` is used for
  titles, summaries, and compaction. The `glm-4.5-air` choice for
  `small_model` is the recommended value tier.
- For ZAI on Vertex, the provider config is different — see the Vertex
  section below.

## In Hermes (config.yaml)

Hermes uses OpenAI-compatible providers via its `llm.backends` block in
`config.yaml`:

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
```

Notes:

- `api_key_env: ZAI_API_KEY` — Hermes reads the key from env, never from
  the config file. Set `ZAI_API_KEY` in the container env.
- The `routing` block maps swarm roles to model tiers. The pattern above
  uses GLM-5.2 only for orchestration (judgment-heavy) and GLM-4.7 for
  everything else, with GLM-4.5-air for cheap fan-out.
- For self-hosted/air-gapped, see `self-hosted-models.md` in the
  Hermes runtime skill.

## In Each Major Framework

### LangChain / LangGraph

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="glm-4.7",
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
```

### CrewAI

```python
from crewai import LLM

llm = LLM(
    model="openai/glm-4.7",          # LiteLLM provider prefix
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
```

### OpenAI Agents SDK

```python
from openai import AsyncOpenAI
from agents import Agent, OpenAIChatCompletionsModel

client = AsyncOpenAI(
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
agent = Agent(
    name="my-agent",
    model=OpenAIChatCompletionsModel(model="glm-4.7", openai_client=client),
)
```

### Pydantic AI

```python
from pydantic_ai.models.openai import OpenAIModel
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
model = OpenAIModel("glm-4.7", openai_client=client)
```

### Vercel AI SDK (TypeScript)

```typescript
import { createOpenAI } from '@ai-sdk/openai';

const zai = createOpenAI({
  baseURL: 'https://open.bigmodel.cn/api/paas/v4/',
  apiKey: process.env.ZAI_API_KEY,
});

const result = await generateText({
  model: zai('glm-4.7'),
  prompt: 'Hello',
});
```

### smolagents

```python
from smolagents import HfApiModel  # or LiteLLMModel

# Via LiteLLM (OpenAI-compatible)
from smolagents import LiteLLMModel
model = LiteLLMModel(
    model_id="openai/glm-4.7",
    api_base="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
```

### Custom Provider-SDK Loop

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
)
response = client.chat.completions.create(
    model="glm-4.7",
    messages=[{"role": "user", "content": "Hello"}],
)
```

### Microsoft Agent Framework, Google ADK, Copilot SDK, Mastra

Same OpenAI-compatible pattern. MAF uses `AzureOpenAI`/`AsyncOpenAI` for
custom endpoints; Google ADK supports custom model backends; Copilot SDK
is GitHub-bound (ZAI is BYOK via the SDK's BYOK provider config); Mastra
uses the same `createOpenAI` pattern as Vercel AI SDK.

## In a Container

The pattern is the same regardless of host:

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
# ZAI key never in image
ENV ZAI_API_KEY=""
ENV OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
CMD ["python", "-m", "my_agent"]
```

```yaml
# docker-compose.yml
services:
  agent:
    build: .
    environment:
      ZAI_API_KEY: ${ZAI_API_KEY}     # from .env, never committed
      OPENAI_BASE_URL: https://open.bigmodel.cn/api/paas/v4/
      OPENAI_API_KEY: ${ZAI_API_KEY}  # frameworks that read OPENAI_* vars
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import os; assert os.environ.get('ZAI_API_KEY')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

```bash
# .env (gitignored)
ZAI_API_KEY=ae697f95...Tib8Fbw...
```

```bash
# deploy
docker compose up -d --build
docker compose logs -f agent
```

### Secret-Injection Alternatives

For production, inject the key via:

| Method | When |
|---|---|
| **Docker Swarm / Compose secret** | Single-host; `secrets:` block mounts the key as `/run/secrets/zai_key` |
| **Kubernetes Secret** | Multi-host; `envFrom: secretRef: name: zai-credentials` |
| **HashiCorp Vault Agent** | Enterprise; vault-agent sidecar writes the key to a file the agent reads |
| **AWS Secrets Manager / GCP Secret Manager** | Cloud-native; SDK fetch on startup, never in env |
| **GitHub Actions secret** | CI-resident agents; `${{ secrets.ZAI_API_KEY }}` |

The principle is the same: the key exists at runtime, never in the image,
never in the repo.

## ZAI on Vertex AI (ZAI.org)

ZAI is also available via Vertex AI as "GLM 5" / "GLM 4.7" (ZAI.org). The
auth flow is Google Workload Identity, not `ZAI_API_KEY`:

```python
import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(project="my-project", location="us-central1")
model = GenerativeModel("glm-4.7")  # ZAI.org model name on Vertex
```

Use this path when:

- You are already on Google Cloud and want unified billing.
- You need Vertex's regional data residency.
- You want Workload Identity instead of long-lived API keys.

Otherwise, the direct ZAI API is simpler.

## Tool Calling and Structured Outputs

ZAI / GLM supports OpenAI-style tool calling and JSON-mode structured
outputs. Most frameworks work without modification; the quality of
structured outputs is on par with GPT-4.x for English and stronger for
Chinese-language tasks.

For LangChain tool-calling:

```python
from langchain_core.tools import tool

@tool
def search_tickets(query: str) -> list[dict]:
    """Search the ticket system."""
    ...

llm = ChatOpenAI(
    model="glm-4.7",
    base_url="https://open.bigmodel.cn/api/paas/v4/",
    api_key=os.environ["ZAI_API_KEY"],
).bind_tools([search_tickets])
```

For OpenAI-style `response_format`:

```python
response = client.chat.completions.create(
    model="glm-4.7",
    messages=[...],
    response_format={"type": "json_object"},
)
```

## Pitfalls

1. **Key in the image.** Baked into a `Dockerfile` `ENV` line; leaked on
   `docker push`. Fix: env var at runtime; `.dockerignore` for `.env`.
2. **Wrong base URL.** The chat completions path is `/api/paas/v4/`, not
   `/v1/`. A wrong base URL gives a 404 on the first call.
3. **Hardcoded model alias.** `glm-4.7` is an alias; the underlying
   snapshot moves. Fix: pin exact versions for production
   (`glm-4.7-2026-07-15` style).
4. **Treating GLM-4.7-Flash as production-grade.** The free Flash tier
   is great for dev and titles; rate limits and quality make it wrong
   for production loops. Use `glm-4.5-air` or `glm-4.7` for production.
5. **No spend alert.** A loop bug burns through credits. Fix: set
   per-day spend alerts in the ZAI console; use the harness's cost cap.
6. **Mixing ZAI direct + Vertex in one codebase.** Two auth flows, two
   model ID dialects. Pick one per environment.

## See Also

- `agent-deployment/references/ci-resident-agents.md` — running ZAI-backed
  agents in CI.
- `agent-deployment/references/hermes-container-deploy.md` — full Hermes
  container deploy with ZAI.
- `agent-deployment/references/opencode-container-deploy.md` — running
  OpenCode itself in a container with ZAI.
- `agent-deployment/references/framework-deploy-matrix.md` — per-framework
  Docker recipes for all 13 harnesses.
- `model-selection/references/task-model-matrix-cloud.md` — the broader
  cloud provider matrix ZAI sits in.
