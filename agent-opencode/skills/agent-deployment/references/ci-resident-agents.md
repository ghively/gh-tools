> Last verified: 2026-07. The claude-code-action input surface, headless CLI flags, the GitLab Duo platform, and the GitHub Copilot agent surface all move quickly — re-check [code.claude.com/docs/en/github-actions](https://code.claude.com/docs/en/github-actions), [gitlab-ci-cd](https://code.claude.com/docs/en/gitlab-ci-cd), [docs.gitlab.com/ee/user/duo_chat](https://docs.gitlab.com/ee/user/duo_chat/), and [docs.github.com/en/copilot](https://docs.github.com/en/copilot) before wiring a new pipeline.

# CI-Resident and Platform-Native Agents

Agents whose *runtime is the CI system itself* or *the platform's native AI runtime* — GitHub Actions, GitLab CI, GitHub Copilot cloud agent, GitLab Duo — give you the scheduler, sandbox, log store, and identity provider all at once. No service to host, no queue to run: the workflow file or platform config is the deployment.

Scope boundary: `scheduled-event-driven-agents.md` covers the *design* of unattended runs for any runtime; this file covers CI and platform-native runtimes specifically. `assets/deploy-templates/github-actions-scheduled.yml` is the copyable starting artifact for CI.

## Shape Taxonomy

Four tiers, ordered by authority the agent holds. Pick the lowest tier that does the job.

| Tier | Trigger | Authority | Examples | Key risk |
|---|---|---|---|---|
| **PR-triggered responder** | `issue_comment` / `pull_request_review_comment` with an `@claude` mention; `pull_request` events | Reads the PR, pushes to the PR branch, comments | Review on request, implement a fix from a comment, label/triage on mention | Untrusted PR/issue text becomes the prompt (see Security) |
| **Scheduled repo gardener** | `schedule:` cron + `workflow_dispatch` for manual test fires | Opens PRs/issues, edits files on a branch | Dependency triage, stale-issue sweeps, doc-freshness checks, link rot | Fires whether or not the world changed; cost drifts silently |
| **Event-driven worker** | Repo events: `issues: opened`, `workflow_run: completed` (CI failed), `release`, `push` | Diagnose and propose: comment a triage, open a patch PR | Issue-opened → classify + route; CI-failed → read logs, diagnose, draft fix PR | Event storms (one bad merge → N failed jobs → N agent runs) |
| **Merge-gate agent** | `pull_request` as a required status check | Pass/fail verdict only — never pushes | Policy review, migration-safety check, changelog-completeness gate | A probabilistic gate blocks humans; needs a bypass path and tight scope |

The merge-gate tier deserves suspicion: a deterministic linter that fails closed beats an LLM verdict wherever one exists (see the `deterministic-agents` skill — the LLM decides as little as possible). Use an agent gate only for judgments no linter can make, and make its verdict advisory-then-required only after weeks of shadow mode.

**Tier 0 — the deterministic substrate.** Before any agent tier, the repo should already have deterministic CI for everything checkable by a program. This marketplace repo's own `.github/workflows/validate.yml` is the worked example: structure validation, golden-contract evals, secret scan, and syntax lint on `push`/`pull_request`, plus a weekly `schedule:` re-run so drift not caused by a push (dependency or upstream change) still surfaces. That weekly cron *is* a minimal gardener — no model in the loop, exit code as verdict. An agent gardener earns its place only for the judgments that script cannot make (triage, prose review, diagnosis); it should sit *on top of* such a workflow, never replace it.

## GitHub Actions Wiring

The official action is [`anthropics/claude-code-action@v1`](https://github.com/anthropics/claude-code-action) (GA; `@beta` is the old input surface — `direct_prompt`, `mode`, and top-level `max_turns` are gone). Current inputs that matter:

| Input | Purpose |
|---|---|
| `prompt` | Instructions — plain text, GitHub context expressions, or a skill invocation (`/skill-name`, `/plugin:skill`). Omit it on comment events and the action runs in interactive mode, responding to the trigger phrase |
| `claude_args` | Passthrough of any Claude Code CLI args: `--max-turns 10 --model claude-sonnet-5 --allowedTools ... --mcp-config ...` |
| `anthropic_api_key` | `${{ secrets.ANTHROPIC_API_KEY }}` — required for direct API, not for Bedrock/Vertex |
| `github_token` | Token for GitHub API access (defaults to the Claude GitHub App's token; pass an app token for custom apps) |
| `trigger_phrase` | Mention that wakes it (default `@claude`) |
| `use_bedrock` / `use_vertex` | `"true"` to route through your cloud account instead of the direct API |
| `plugin_marketplaces` / `plugins` | Install plugins (newline-separated) before the run — how a plugin-packaged skill becomes the agent's procedure |

Mode is auto-detected: a `prompt` means automation mode (run immediately); no `prompt` on a comment event means interactive mode (respond to mentions).

### The four trigger wirings

```yaml
on:
  issue_comment:                     # PR-triggered responder
    types: [created]
  schedule:                          # gardener
    - cron: "0 6 * * 1"
  workflow_dispatch:                 # always: manual test fire
  issues:                            # event-driven worker
    types: [opened]
```

Gate mention-driven jobs so the workflow doesn't bill a runner for every comment:

```yaml
jobs:
  claude:
    if: contains(github.event.comment.body, '@claude')
    runs-on: ubuntu-latest
    permissions:
      contents: write        # push fix branches
      pull-requests: write   # open/comment PRs
      issues: write          # comment/label issues
      # nothing else — no packages, no deployments, no id-token unless OIDC below
    concurrency:
      group: claude-${{ github.event.issue.number || github.run_id }}
      cancel-in-progress: false   # skip-not-queue: let the active run finish
    timeout-minutes: 20           # the wall-clock budget
    steps:
      - uses: actions/checkout@v4
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          claude_args: "--max-turns 10"
```

The `permissions:` block is the least-privilege lever GitHub gives you: it downscopes the job's `GITHUB_TOKEN` regardless of repo defaults. Declare it explicitly in every agent workflow — the org-default may be `write-all`. The `concurrency.group` keyed per-issue prevents the classic pile-up: three quick comments spawning three agents that push to the same branch.

### Auth: API key vs cloud OIDC

Direct API is one secret. For Bedrock/Vertex, the documented pattern is workload identity — no long-lived cloud keys in GitHub at all:

```yaml
permissions:
  id-token: write          # REQUIRED for OIDC — plus the repo permissions above
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}   # IAM role trusting token.actions.githubusercontent.com, audience sts.amazonaws.com
      aws-region: us-west-2
  - uses: anthropics/claude-code-action@v1
    with:
      github_token: ${{ steps.app-token.outputs.token }}
      use_bedrock: "true"
      claude_args: "--model us.anthropic.claude-sonnet-4-6 --max-turns 10"
```

Vertex is the mirror image: `google-github-actions/auth@v2` with `workload_identity_provider` + `service_account` secrets, then `use_vertex: "true"` and env `ANTHROPIC_VERTEX_PROJECT_ID` / `CLOUD_ML_REGION`. Note the model-ID dialects — `us.anthropic.claude-sonnet-4-6` (Bedrock inference profile) vs `claude-sonnet-4-5@20250929` (Vertex `@`-date) vs `claude-sonnet-5` (direct API); a workflow copied across providers with the wrong dialect fails at the first model call. Restrict the IAM/WIF trust policy to the specific repo and ref — an OIDC provider trusted by "any repo in the org" hands Bedrock invoke rights to every workflow in the org. For cloud providers, Anthropic also recommends your own GitHub App (via `actions/create-github-app-token@v2`) rather than the default Actions identity, so the agent's commits have a distinct, auditable author that can also trigger CI.

## GitLab CI Equivalent

The GitLab integration is beta and GitLab-maintained; there is no `claude-code-action` equivalent component — the pattern is headless Claude Code (`claude -p`, verified current) inside a job:

```yaml
claude:
  stage: ai
  image: node:24-alpine3.21
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'              # gardener tier
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'   # responder tier
  timeout: 30m
  before_script:
    - apk add --no-cache git curl bash
    - curl -fsSL https://claude.ai/install.sh | bash
  script:
    - >
      claude -p "${AI_FLOW_INPUT:-$(cat prompts/gardener.md)}"
      --permission-mode acceptEdits
      --allowedTools "Bash Read Edit Write mcp__gitlab"
      --max-turns 25
      --output-format json | tee run-record.json
  artifacts:
    paths: [run-record.json]
    when: always
```

GitLab-specific mechanics:

- **Triggers**: scheduled pipelines (CI/CD → Schedules) for the gardener tier; `merge_request_event` rules for responders; mention-driven flows need a project webhook on "Comments (notes)" whose listener calls the pipeline-trigger API with `AI_FLOW_INPUT` / `AI_FLOW_CONTEXT` / `AI_FLOW_EVENT` variables — mentions are not native the way the GitHub App makes them.
- **Token scoping**: `CI_JOB_TOKEN` is the default identity for GitLab API writes and is already scoped to the project and job lifetime; harden further under Settings → CI/CD → Job token permissions (allowlist which projects accept it). Only mint a Project Access Token (`api` scope, stored masked as `GITLAB_ACCESS_TOKEN`) when the agent must touch other projects — that token is long-lived, so treat it as tier-up.
- **Auth**: `ANTHROPIC_API_KEY` as a masked (and protected-ref) CI/CD variable; or OIDC — exchange the job's ID token for AWS credentials via `aws sts assume-role-with-web-identity`, or GCP Workload Identity Federation with an external-account credential file. Same no-static-keys rule as GitHub.
- **Isolation**: every change flows through an MR, so approvals and protected branches apply to the agent exactly as to a human contributor.

## Platform-Native Agents

GitHub and GitLab both ship first-party AI agent runtimes that remove the
"bring your own harness" tax entirely. The platform IS the agent host: the
trigger surface, sandbox, identity, audit log, and approval gates are
built-in. Trade-off: you get the platform's opinionated workflow and you
cannot run a non-conforming agent inside that surface.

### GitHub Copilot Cloud Agent

The flagship GitHub-native runtime. Assign an issue, PR comment, schedule,
or API call to Copilot and it researches the repo, plans, edits on a
branch, and opens a PR — all on GitHub-hosted compute. The 2026 surface:

| Surface | Purpose |
|---|---|
| **Copilot cloud agent** | Autonomous repo-scoped task: assigned issue → branch → plan → diff → PR |
| **Copilot automations** | Schedule- or event-triggered runs of cloud agent (the direct equivalent of a CI-resident gardener — replaces hand-rolled cron + Actions for the same shape) |
| **Custom agents** | Tailored agents with their own skills, hooks, MCP servers, environment, and secrets; managed per org/enterprise |
| **Agent skills** | Reusable prompt modules loaded on demand (the same conceptual surface as OpenCode/Claude skills) |
| **Copilot hooks** | `pre-tool-use`, `post-tool-use`, session lifecycle — shell commands run at agent execution boundaries (the deterministic-enforcement surface) |
| **Copilot plugins** | Installable bundles of agents + skills + hooks + MCP + LSP config (the closest analogue to an OpenCode plugin) |
| **Copilot code review** | Automatic PR review separate from cloud agent; the dedicated Tier-1 merge-gate surface |
| **GitHub Agentic Workflows** | Natural-language instructions executed by AI coding agents in Actions — the meeting point of Actions and cloud agent |
| **Copilot Spaces** | Organized context bundles shared with collaborators |
| **Copilot Memory** | Long-term repo and preference memory — persists across sessions |
| **Sandbox (cloud + local)** | Isolated execution environment for filesystem, network, and tools |
| **BYOK / Bring your own model** | Route to a non-Copilot model via your own provider key |
| **Copilot SDK** (Node.js / .NET) | Build apps that drive Copilot programmatically; supports fleet mode, hooks, MCP, custom agents, session persistence |
| **Copilot CLI** | Headless CLI with autopilot, `/fleet` parallelism, `/research`, `/every` scheduling, plugins marketplace |
| **Third-party coding agents** | Anthropic Claude, OpenAI Codex, and others run as agent apps powered by the Copilot subscription |
| **Integrations** | Jira, Slack, Teams, Linear, Azure Boards, Raycast — start a session from a ticket or message |

Wiring a custom agent:

1. Org/enterprise admin enables Copilot and grants the agent repo access.
2. Define the agent in `.github/copilot/agents/<name>.copilot-agent.md` (or org-level) with: instructions, allowed tools, allowed MCP servers, model preference, hooks.
3. Add skills under `.github/copilot/skills/<name>/SKILL.md` — same shape as OpenCode skills (`name` + `description` frontmatter, body loads on trigger).
4. Optional hooks under `.github/copilot/hooks/` for pre/post-tool deterministic checks.
5. Optional MCP servers via `.github/copilot/mcp.json` or org policy.
6. Test in a single repo before promoting to the org; use the test-and-release workflow documented under "Testing and releasing custom agents."

**Copilot automations vs Actions-resident agents.** Automations are GitHub's
blessed replacement for hand-rolled `schedule:` + `claude-code-action`
workflows. Use automations when the trigger is repo-event or schedule and
the effect is a PR/comment/label; fall back to Actions + a headless CLI only
when you need the platform's full tool surface or a non-Copilot model.

### GitLab Duo

The GitLab-native AI surface. The 2026 shape:

| Surface | Purpose |
|---|---|
| **Duo Chat** | Conversational AI in the GitLab UI (Web IDE, MR, issue) — `/explain`, `/refactor`, `/tests`, `/troubleshoot` |
| **Duo Code Review (Duo Reviewer)** | Automated MR review with severity-tagged findings; the merge-gate equivalent |
| **Duo Workflow** | Autonomous task execution: triage, doc generation, refactoring; the closest analogue to Copilot cloud agent |
| **Duo Agent Platform (DAP)** | Build custom agents within GitLab using the platform's tools, context, and approval flow |
| **GitLab AI Context** | The indexing and retrieval layer Duo uses to ground responses in your repo, issues, and MRs |
| **Cloud Seed** | Provision cloud infrastructure (Terraform/Ansible) via Duo-driven templates |
| **Self-hosted models** | Route Duo to your own AWS Bedrock, Azure OpenAI, Vertex, or a self-hosted model gateway |
| **AI vendor routing** | GitLab-managed routing to Anthropic, OpenAI, Google, and Amazon models with per-workload choice |
| **Duo settings and policies** | Per-group, per-project, per-user controls; reject/allow lists for AI features |
| **MCP support** | Connect Duo Chat to external tools via Model Context Protocol servers |

Wiring a Duo Workflow:

1. Group owner enables Duo and selects a model vendor (or self-hosted).
2. Define the workflow under `.gitlab/duo/workflows/<name>.yml` (or via the UI) with: trigger (MR, schedule, manual, webhook), prompt, allowed tools, allowed namespaces.
3. Restrict the workflow's token scope via project settings → CI/CD → Job token permissions and Duo settings → allowed namespaces.
4. Approvals and protected branches apply to the agent's MRs exactly as to a human contributor's.
5. Run-records land in the MR conversation and in the audit log under Settings → Audit Logs.

**GitLab Duo Workflow vs CI-resident headless.** Duo Workflow is the
blessed replacement for hand-rolled `claude -p` inside `.gitlab-ci.yml`. Use
Duo Workflow when the trigger is GitLab-native (MR, scheduled pipeline,
webhook) and the model routing is acceptable. Fall back to a headless agent
CLI in CI only when you need a non-vendored model, a custom harness, or an
MCP server Duo Workflow cannot yet expose.

### Decision: Platform-Native vs Bring-Your-Own-Harness

| Criterion | Platform-native (Copilot / Duo) | Bring-your-own-harness in CI |
|---|---|---|
| Time to first PR | Minutes — UI configuration | Hours — workflow YAML + secrets + tokens |
| Vendor lock-in | High — skills and hooks are platform-shaped | Low — your harness is portable |
| Model choice | Vendor-curated, expanding; BYOK available on Copilot SDK | Any provider you can call |
| Audit and identity | Free and platform-native | You wire OIDC + tokens + audit |
| Cost model | Per-seat AI credits + usage | Per-run tokens + runner minutes |
| Tool surface | The platform's allowed tools + MCP servers you register | Whatever your agent framework supports |
| Environments | Platform sandbox (cloud or local) | Your runner image + sandbox config |
| Best for | Repo-scoped work where the platform already encodes the approval flow | Cross-system agents, custom harness, special-purpose models |

Pick platform-native when the trigger, effect, and approval flow all live
inside one platform. Pick bring-your-own-harness when you need portability,
a non-vendored model, or a tool surface the platform doesn't expose.

## Framework-Aware CI Wiring

The previous sections cover Claude-in-CI. The agent-foundry `framework-selection`
skill covers a wider landscape: LangGraph, CrewAI, LlamaIndex, Microsoft
Agent Framework, DSPy, Pydantic AI, smolagents, NeMo Agent Toolkit, and raw
provider-SDK loops. Each can be the resident agent in a CI job. The pattern
is the same — install, set secrets, run headless, capture output — but the
invocation differs.

### Universal CI Job Shape

```yaml
# Generic framework-resident agent job (GitHub Actions shown; GitLab mirror)
jobs:
  agent:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      id-token: write            # only if using OIDC for cloud model auth
    concurrency:
      group: agent-${{ github.event.issue.number || github.run_id }}
      cancel-in-progress: false
    timeout-minutes: 20
    env:
      PROVIDER_API_KEY: ${{ secrets.PROVIDER_API_KEY }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt          # your framework
      - run: python agents/gardener.py                 # the agent entrypoint
```

The GitLab equivalent substitutes `image: python:3.12-slim`, `script:`,
`rules:`, and `resource_group:` for the job skeleton.

### Per-Framework Entry Points

| Framework | Entrypoint shape | Notes |
|---|---|---|
| **Raw provider SDK loop** | `python agent.py` calling `client.chat.completions` in a tool-loop | Smallest surface; the reference pattern. No framework churn. |
| **OpenAI Agents SDK** | `python -m agents run agents/gardener.py` or `Agent().run()` | Native tool-calling loop with handoffs; pair with `set_trace_processor` for OTel audit |
| **LangGraph** | `python -m langgraph run graphs/gardener.json` or compile + invoke in-process | Use `MemorySaver` only within one run; CI has no durable checkpointer unless you wire one (see `deterministic-agents` skill) |
| **CrewAI** | `python -m crewai run crews/gardener.yaml` or `Crew(...).kickoff()` | Define crew in YAML for portability; pin `crewai` version explicitly |
| **LlamaIndex** | `python -m llama_index.agent.workflow` or `AgentWorkflow(...).run()` | Good when the agent reads from indexed repos or docs; pre-build the index in a separate step |
| **Microsoft Agent Framework (MAF)** | `python -m agent_framework run` or `AgentRuntime().run(...)`; .NET: `dotnet run` against `Microsoft.Agents.Hosting` | Cross-language; pairs with Azure Monitor for traces |
| **DSPy** | `python -m dspy.run pipelines/gardener.py` | Optimized programs; ship the compiled program, not the source |
| **Pydantic AI** | `python -m pydantic_ai run agents/gardener.py` or `Agent(...).run()` | Typed dependency injection; great for multi-model evaluation gates |
| **smolagents** | `python -m smolagents.run agents/gardener.py` | Code-action agent; sandbox aggressively — it writes and runs Python |
| **NeMo Agent Toolkit** | `python -m nat profile --workflow gardener.yaml` | Wraps/profiles an existing workflow; not a standalone runtime. Package is `nvidia-nat`, CLI is `nat` (formerly AgentIQ, NeMo Toolkit — three names, same API) |
| **Vercel AI SDK** | `node agents/gardener.ts` with `generateText` / `streamText` | The JavaScript-side equivalent of the raw provider loop; pair with OpenTelemetry for trace export |
| **Mastra** | `node -e "require('./agents/gardener').run()"` | JS/TS-native; ships its own workflow + agent primitives |
| **Google ADK** | `python -m google.adk.run agents/gardener` or `adk web` for interactive | Pairs with Vertex AI for model hosting; use Workload Identity for auth |
| **Claude Agent SDK** | `python -m claude_agent_sdk run` or `node agent.js` | The Claude harness as a library; the closest to headless Claude Code without the CLI |
| **Copilot SDK** (Node.js / .NET) | `npx copilot-sdk run` or `dotnet copilot run` | Drive Copilot sessions programmatically; supports fleet mode, hooks, MCP |

### Per-Framework Wiring Details

**LangGraph.** Compile the graph in-process and invoke it. Pin
`langgraph>=0.2` and `langchain-core` explicitly — the import paths moved
between 0.1 and 0.2. Use `MemorySaver` for single-run checkpointing; for
cross-run state, you need a durable checkpointer (Postgres, Redis) and the
accompanying connection secret — see `deterministic-agents` for the
durable-execution doctrine. Export OpenTelemetry spans to an OTLP collector
or Honeycomb/Tempo; LangGraph emits rich traces.

```python
from langgraph.checkpoint.memory import MemorySaver
from myapp.graphs import gardener

graph = gardener.build().compile(checkpointer=MemorySaver())
result = graph.invoke({"repo": "...", "issue_number": N},
                      {"configurable": {"thread_id": f"run-{run_id}"}})
```

**CrewAI.** Author the crew in YAML so the CI job only does `Crew(...).kickoff(inputs=...)`. Pin `crewai` and `crewai-tools` explicitly — both
have moved breaking changes between minor versions. CrewAI Flows (not Crews)
are the right shape for CI-resident work because they support stateful,
ordered execution.

**LlamaIndex.** Pre-build the index in an earlier step or store it in an
artifact; cold-loading on every run burns tokens and time.
`FunctionAgent` for single-agent work, `AgentWorkflow` for multi-agent.
Pin `llama-index>=0.11`; 0.10's agent surface is deprecated.

**Microsoft Agent Framework (MAF).** The successor to AutoGen + Semantic
Kernel. Use the `AgentRuntime` host for CI; it handles process lifetime,
observation, and termination. For .NET shops, the .NET surface mirrors the
Python one. Export telemetry to Azure Monitor or Application Insights
natively.

**DSPy.** Ship the *compiled* program (`teleprompter.compile(...)` output),
not the source — CI runs the optimized artifact. Pin `dspy` and the
underlying provider SDK explicitly; DSPy signatures break across versions.

**Pydantic AI.** Strong fit for CI-resident *gates* because the typed
dependency injection makes deterministic model swaps trivial — run the same
gate against three models and compare. Use `Agent(...).run_sync(...)` for CI
where async adds no value.

**smolagents.** Code-action agents that write and execute Python. Run them
inside a container with no secrets, no network egress except the model API,
and a read-only mount of the repo. Treat smolagents in CI the way you treat
`eval` in CI.

**NeMo Agent Toolkit.** Profile + evaluate an existing workflow; not a
production runtime. Use it in a *test* job that asserts the agent's quality
metrics held for this run, not as the agent itself.

**Vercel AI SDK.** The JavaScript entry point for a provider-loop agent.
Pin the SDK and provider packages; enable `experimental_telemetry` and
export to OTLP. Good when the rest of the codebase is TypeScript and you
want one language end-to-end.

**Mastra.** TypeScript-native workflow + agent framework. Pin `@mastra/core`
and `@mastra/memory`. Like CrewAI Flows, Mastra workflows support ordered
stateful execution — the right shape for multi-step CI-resident work.

**Google ADK.** First-party Google framework; pairs naturally with Vertex AI
models. Use Workload Identity Federation (no static keys) for auth; the ADK
reads `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` env vars. For CI
outside GCP, exchange the OIDC token for short-lived credentials in a
pre-step.

**Claude Agent SDK.** The harness Claude Code uses, as a library. Lower
friction than `claude -p` if your CI is already Python or TypeScript and you
want programmatic control over tool calls, hooks, and side effects. Pin the
SDK version exactly — the surface is still moving.

**Copilot SDK.** Build apps that drive Copilot sessions programmatically.
Supports fleet mode (parallel sub-agents), pre/post-tool hooks, MCP, custom
agents, and session persistence. Pair with GitHub App auth (not PAT) so the
agent's commits have a distinct, auditable author. The SDK is the right
choice when you want Copilot's capabilities but need to drive them from
your own runtime, queue, or UI.

### Universal Pitfalls Across Frameworks

1. **Unpinned versions.** A `requirements.txt` with `crewai` (no version) is
   a ticking bomb — frameworks churn and your agent breaks on a Tuesday.
   Fix: pin every framework dependency; treat the lockfile as a release
   artifact.
2. **In-process state across runs.** Frameworks default to in-process memory
   that dies with the job. If state must survive, use a durable checkpointer
   and wire the connection explicitly. See `deterministic-agents`.
3. **Tool-surface drift.** A framework upgrade silently renames or removes a
   tool your agent relies on. Fix: run the eval suite (`agent-evals` skill)
   on every framework version bump.
4. **Token blowout from logging.** Verbose frameworks log prompts and
   completions by default — that's a lot of tokens in a CI log that
   expires. Fix: set log level explicitly; export OTel to a collector
   instead of relying on stdout.
5. **Sandbox mismatch.** The runner image doesn't match your dev image; the
   agent works locally, fails in CI on a missing library or locale. Fix:
   pin a Docker image in `runs-on: ubuntu-latest` + `container:` block, or
   use GitLab's `image:` directly.
6. **No secrets redaction in framework output.** Frameworks that print
   intermediate steps can leak secret values into CI logs. Fix: register
   secrets with the CI system so the runner redacts them; never `print()`
   tool outputs in CI.
7. **Non-idempotent side effects.** A re-run after a runner death duplicates
   a real-world effect (a deployed change, an external API call). Fix: every
   side effect is gated by a check-then-act idempotency key. See
   runner-death discipline below.



## Operational Discipline

Every bound from the SKILL.md cost table must exist here, natively:

| Bound | GitHub Actions | GitLab CI | Copilot automations | Duo Workflow |
|---|---|---|---|---|
| Turn cap | `claude_args: "--max-turns N"` or framework arg | `--max-turns N` on `claude -p` or framework arg | Agent run-settings | Workflow config |
| Wall clock | `timeout-minutes:` on the job | `timeout:` on the job | Per-run timeout setting | Workflow timeout |
| Overlap | `concurrency.group` (skip-not-queue) | `resource_group:` | Per-agent concurrency | Per-workflow concurrency |
| Blast radius | `permissions:` + framework tool filter | Job token scoping + framework tool filter | Agent allowed-tools + sandbox | Allowed namespaces + sandbox |
| Spend visibility | `total_cost_usd` from `--output-format json` / OTel | JSON run-record / OTel | AI Credit usage report | Duo usage analytics |
| Audit trail | Run-record artifact + Actions log | Run-record artifact + pipeline log | Session history + webhook events | MR conversation + audit log |
| Identity | OIDC + scoped `GITHUB_TOKEN` or GitHub App | `CI_JOB_TOKEN` + optional PAT | GitHub App or user-bound | GitLab user or service account |

**Runner death mid-run.** A CI runner is preemptible: jobs get killed at timeout, on runner loss, on newer-commit cancellation. The agent's work must therefore be *harmless to lose and safe to re-fire*: every run either lands its effect atomically (one PR, one comment, one label) or checks durable state before acting (does the triage comment already exist? is there an open PR from branch `agent/dep-triage`?). That check-then-act key plus lock semantics is the idempotency doctrine of the `deterministic-agents` skill — CI gives you no journal, so the repo itself (branches, labels, comments) is your effect journal. If a job genuinely cannot be restarted from zero, it does not belong in CI; move it to a durable-execution worker.

**Audit trail.** The Actions/pipeline log is the transcript, but logs expire and are unreadable at incident speed. Persist a structured run record: `--output-format json | tee run-record.json` uploaded as an artifact (30-day retention), one line per run appended to a tracking issue for gardeners, and the PR/commit trail as the effect record. The agent's identity (GitHub App bot login, GitLab bot user) must be distinct from any human's so `git log --author` answers "what did the agent change this month?"

**Branch protection: propose, never self-merge.** The agent opens PRs; required status checks + required human review stand between its branch and `main`. Enforce structurally, not by prompt: protect `main` with required reviews, exclude the agent's identity from bypass lists, keep "Allow GitHub Actions to create and approve pull requests" disabled so a workflow-held token cannot approve PRs (GitLab: approval rules + protected branches). An agent that can merge its own PR has silently become tier-∞.

## Security

A public-repo CI agent reads attacker-controlled text (issue bodies, PR diffs, comments) while holding a token with repo write access. That is the prompt-injection worst case — treat it as such (defense catalogue: the `agent-safety` skill and `prompt-context-engineering`'s injection-defense reference).

1. **Restrict who can trigger.** claude-code-action requires write access to trigger by default — keep it that way. `allowed_non_write_users` is documented as a significant risk; bots enabled via `allowed_bots` skip the permission check entirely. In GitLab, gate the webhook listener on the commenter's role.
2. **Handle fork PRs as hostile.** Never check out the PR head ref to the workspace root under `pull_request_target` or `workflow_run` — those events run with secrets and a write token against attacker-controlled code. Check out the base ref (the action's default) or the head ref into a subdirectory exposed via `--add-dir`. Plain `pull_request` from forks gets a read-only token and no secrets — that default is your friend; don't "fix" it.
3. **Assume sanitization is partial.** The action strips HTML comments, invisible characters, image alt text, and hidden attributes from context — and its own docs warn new bypasses will emerge. Belt-and-suspenders: scope `--allowedTools` so a hijacked run *can't* do much (a triage agent needs comment/label writes, not `Bash`), and keep the merge gates from the previous section.
4. **Secrets hygiene in logs.** CI logs are broadly readable. The action keeps `show_full_output` off by default because tool output can contain tokens and file contents — leave it off (debug mode re-enables it; don't debug on public repos with real secrets). Register anything sensitive as a masked variable/secret so the runner redacts it, and remember the agent can `cat` a secret into a log unless tools are scoped.
5. **Deterministic context.** For scripted runs, `claude -p --bare` skips auto-discovery of hooks, skills, plugins, MCP servers, and CLAUDE.md — the run is exactly the flags you passed, immune to a poisoned `.mcp.json` landing in a PR. Pass what you need explicitly (`--plugin-dir`, `--mcp-config`, `--settings`).

## Decision Table: Platform-Native vs CI-Resident vs Webhook Service vs Human Session

| Criterion | Platform-native (Copilot / Duo) | CI-resident agent | Webhook service + worker | Human-run session |
|---|---|---|---|---|
| Latency to first action | Seconds–minutes (platform queue) | 30 s–2 min (runner spin-up) | Seconds | Whenever the human runs it |
| Run duration ceiling | Platform policy (typically minutes–tens of minutes) | Job timeout (hours max; runner is preemptible) | Unbounded; durable runtimes resume | Interactive patience |
| State between runs | Platform-managed (Copilot Memory, GitLab AI Context) | Only the repo + artifacts | Real session store, DB, queues | Full session context |
| Auth & audit | Free and platform-native (Webhook events, audit log) | Free: OIDC, scoped tokens, logs, artifact retention | You build all of it | The human's credentials |
| Ops burden | None beyond configuration | None beyond YAML | A service to host, monitor, page on | None |
| Cost model | AI credits / per-seat licenses | Runner minutes + tokens per run | Idle infrastructure + tokens | Tokens |
| Vendor lock-in | High (skills/hooks are platform-shaped) | Low (portable harness) | Low | None |
| Best for | Repo-scoped work where the platform encodes the approval flow | Repo-scoped, event/schedule-triggered, propose-don't-execute work with a custom harness or non-vendored model | Cross-repo/cross-system agents, sub-second triggers, long or stateful runs, non-Git side effects | One-offs, exploration, anything needing judgment mid-run |

Rules of thumb:

- **Platform-native wins** when the trigger, effect, and approval flow all
  live inside one platform. The platform gives you identity, secrets, logs,
  audit, and gates for free.
- **CI-resident wins** when you need a custom harness, a non-vendored model,
  or tool surface the platform doesn't expose. Still repo-scoped.
- **Webhook service wins** when you need memory across runs, sub-second
  triggers, runs beyond the timeout, or effects outside the repo.
- **Human-run session wins** when the task is rare enough that configuration
  overhead exceeds just doing it.

See `packaging-serving.md` for the webhook-service shape and
`scheduled-event-driven-agents.md` for the design doctrine either way.

## Pitfalls

1. **The gardener that spams.** A weekly cron opens a duplicate dependency-triage PR because nobody merged last week's. Fix: first step of the run checks for an existing open PR/issue from the agent's identity and updates it instead of creating (idempotency key = branch name).
2. **Concurrency pile-up.** Three `@claude` comments in two minutes → three runners fighting over one branch. Fix: `concurrency.group` keyed per PR/issue; skip-not-queue.
3. **Event storms from `workflow_run`.** One broken merge fails 12 jobs and wakes 12 diagnosis agents. Fix: trigger on the *workflow* completion (not per job), dedupe on head SHA, and cap with concurrency.
4. **The self-approving agent.** "Allow GitHub Actions to create and approve pull requests" left on, or the bot in a branch-protection bypass list — the propose-only design is now fiction. Fix: audit repo/org Actions settings; the gate must be structural.
5. **`pull_request_target` + checkout of the head ref.** The one-line YAML change that hands your secrets to any forker. Fix: base-ref checkout, or head ref in a subdirectory via `--add-dir`; review this in every agent workflow PR.
6. **Unpinned model in the workflow.** The workflow says `--model sonnet` and behavior shifts when the alias moves (on Bedrock/Vertex, pinning is also the `ANTHROPIC_DEFAULT_*_MODEL` env vars). Fix: pin full model IDs in the workflow file — it's a release artifact; version it like one (`versioning-rollout.md`).
7. **No manual trigger.** Debugging a cron agent by editing the cron. Fix: every scheduled workflow also declares `workflow_dispatch` and the wake-up prompt lives in the repo, testable before the schedule fires.
8. **Trusting the runner to survive.** A 25-turn run that writes three files, then the runner dies at turn 20 and the re-fire duplicates two of them. Fix: land effects atomically at the end (one push, one PR), or check-then-act per effect — see runner-death discipline above.
9. **Platform lock-in via skills.** A skill authored for Copilot's `.github/copilot/skills/` surface doesn't run anywhere else. Fix: keep the SKILL.md body portable (OpenCode shape), and treat platform-specific wrapper files as adapters. The `claude-code-authoring` skill's conversion references cover this.
10. **Copilot automations as a drop-in for an existing cron.** Behaviors differ: trigger surface, allowed tools, identity, sandbox model, and concurrency semantics are all platform-specific. Fix: read the current automation docs before porting a workflow; treat it as a port, not a copy.
11. **Duo Workflow in a regulated environment without self-hosted models.** Duo defaults to vendor-routed models; in PCI/HSA or similar zones, that's a violation. Fix: configure self-hosted model routing and verify the data-residency guarantees in your GitLab plan before enabling Duo Workflow.
12. **Two agents, one branch.** Copilot cloud agent AND a CI-resident agent both push to `agent/triage`. Fix: branch-naming convention per agent identity + branch protection rule that rejects conflicts; or pick one runtime and turn the other off for that trigger.
13. **Copilot Memory / Duo AI Context leaks across repos.** Memory and context persist across sessions and can leak into a fork PR or another project's session. Fix: scope memory per repo; disable cross-repo memory in org policy when working with sensitive repos.
14. **Framework version bump broke the silent assumption.** A `crewai` minor bump renamed an argument; the cron ran at 3 AM and failed on step 1. Fix: pin all framework versions; CI job that runs the eval suite on every framework bump before merge.
