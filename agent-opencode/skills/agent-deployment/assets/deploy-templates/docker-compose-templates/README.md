# docker-compose-templates

Worked docker-compose examples for the common agent deploy shapes.
Pair with the corresponding Dockerfile from the parent directory.

## Files

| Template | Shape | When to use |
|---|---|---|
| `single-agent.yml` | One agent container + Postgres + Redis | Single-host production; one agent, one tenant |
| `multi-tenant.yml` | N agent containers (one per tenant) + shared Postgres | Multi-tenant SaaS shape |
| `langgraph-checkpointer.yml` | LangGraph agent + Postgres checkpointer | LangGraph with durable resume |
| `hermes-s6.yml` | Hermes container with s6-overlay supervision tree | Long-lived Hermes agent (gateway + agent + bot + backup) |
| `opencode-serve.yml` | OpenCode in `serve` mode (headless server) | Shared dashboard backend, scheduled jobs |
| `cron-gardener.yml` | One-shot agent run on a schedule | Repo gardener, eval runner, freshness sweep |
| `eval-runner.yml` | Batch evaluator that runs an eval suite and exits | CI gate; nightly regression sweep |

## Usage

```bash
cp docker-compose-templates/<shape>.yml ./docker-compose.yml
cp docker-compose-templates/.env.example ./.env
$EDITOR .env                          # set ZAI_API_KEY + others
docker compose up -d --build
```

See `references/framework-deploy-matrix.md` for the per-framework
Dockerfiles that pair with these compose files, and
`references/zai-provider-config.md` for the ZAI auth and model-ID
reference.
