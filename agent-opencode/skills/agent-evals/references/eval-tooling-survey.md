> Last verified: 2026-07. Eval tools, hosted platform features, benchmark coverage, and pricing change frequently; verify primary docs before standardizing on a tool.

# Agent Eval Tooling Survey

Start with JSONL cases, deterministic assertions, captured trajectories, and CI. Add a platform when the team needs shared datasets, trace review, online evals, annotation queues, or hosted reporting.

## Open And Local-First Tools

| Tool | Best Fit | Notes |
|---|---|---|
| [Inspect](https://inspect.aisi.org.uk/) | Agent, tool-use, benchmark, and sandboxed evals | UK AI Security Institute framework with datasets, solvers, scorers, agents, tools, MCP tools, and sandbox support. |
| [promptfoo](https://www.promptfoo.dev/docs/intro/) | Declarative prompt/app tests, red teaming, CI | Local CLI/library with assertions, providers, caching, concurrency, red-team workflows, and CI integrations. |
| [OpenAI Evals](https://github.com/openai/evals) | OpenAI-oriented benchmark registry and custom evals | Open-source framework and registry; dashboard evals also exist in the OpenAI platform. |
| [Ragas](https://docs.ragas.io/en/stable/) | RAG and AI-app eval loops | Strong fit for RAG metrics and experiments; for RAG-specific detail see the `memory-rag` skill. |
| [DeepEval](https://deepeval.com/docs/getting-started) | Pytest-like local evals plus optional hosted reporting | Supports test cases, LLM-as-judge metrics, tracing, datasets, and agent/component evaluation. |

### Choosing Between The Local-First Options

The local-first tools overlap but are not interchangeable. Pick by primary workflow:

- Heavy agent and tool-use evals with sandboxed task execution and benchmark reuse → Inspect.
- Declarative prompt and app tests with red-team coverage that drops into CI → promptfoo.
- Pytest-style local tests with optional LLM-as-judge metrics and a path to hosted reporting → DeepEval.
- RAG pipelines where chunking, retrieval, and grounded-answer metrics are the focus → Ragas (see `memory-rag`).
- OpenAI-ecosystem benchmark reuse and registry → OpenAI Evals.

Mixing two local-first tools is normal. The contract (stable case input, captured trajectory, machine-readable assertions, timeouts, baseline diff) is what makes them interoperate, not the tool name.

## Hosted And Observability-Integrated Platforms

| Platform | Best Fit | Notes |
|---|---|---|
| [Braintrust](https://www.braintrust.dev/docs) | Evals plus production traces and datasets | Structured workflow for instrumenting, observing, annotating, evaluating, and deploying AI apps. |
| [LangSmith](https://docs.smith.langchain.com/evaluation) | LangChain/LangGraph-heavy teams | Offline datasets, online trace evals, human/code/LLM evaluators, experiments, and production feedback loops. |
| [Langfuse](https://langfuse.com/docs/scores/overview) | Open-source observability plus eval scoring | Scores, datasets, experiments, annotation queues, LLM-as-judge, and CI/CD experiments. |

Choose the hosted platform by ecosystem fit and data-residency needs, not by feature-list length. LangSmith pays off when your stack is already LangChain/LangGraph-shaped; Braintrust fits when evals and production traces should live in one workflow; Langfuse fits when open-source self-hosting and eval scoring matter together. In every case, verify current pricing, data-residency, and access-control support against primary docs before standardizing.

## Benchmarks

Use benchmarks as comparability signals, not as release gates. SWE-bench-style coding tasks measure repository repair ability. Tau-bench-style tool/customer-service tasks measure tool-use policy and task completion. Neither replaces your golden suite because neither knows your production tools, permissions, data boundaries, or user workflows.

When benchmarks are useful: choosing between two foundation models on a comparable task family before you invest in integration; sanity-checking that a model change has not regressed a general capability your agent depends on; and communicating relative capability to stakeholders who do not share your eval harness. When they mislead: treating a benchmark rank as evidence your specific agent is safe to deploy, or skipping the golden suite because the benchmark score went up.

## LLM-As-Judge Patterns

LLM judges are useful for helpfulness, professionalism, reasoning quality, and rubric-based classification. They are weak for safety gates and exact tool-policy checks.

Known pitfalls:

- Position bias in pairwise judging.
- Verbosity bias toward longer answers.
- Self-preference when the judge resembles the evaluated model.
- Prompt sensitivity and rubric drift.
- Poor calibration on rare safety failures.

Mitigations:

- Calibrate with human-labeled examples before trusting scores.
- Use few-shot rubrics with positive and negative examples.
- Report agreement and disagreement, not only a mean score.
- Use judge panels for high-impact subjective decisions; see `multi-agent-orchestration/references/review-panels.md`.
- Keep deterministic assertions as the deployment gate for governance and schema behavior.

### Calibrating A Judge

A judge is not trusted until its decisions have been compared against human-labeled examples on your data, not on the provider's demo set. Minimum calibration loop:

1. Sample 50-200 cases that span the rubric range, including edge and adversarial cases.
2. Have at least two humans label each case independently; record inter-rater agreement.
3. Run the judge on the same cases; record judge-vs-human agreement and the specific disagreements.
4. Iterate the rubric and few-shot examples until judge agreement approaches human inter-rater agreement.
5. Re-calibrate on a cadence and after every model or rubric change.

Report agreement numbers alongside scores. A mean score with no agreement data is uncalibrated opinion.

## Adoption Stages

| Stage | Use |
|---|---|
| 1 | JSONL cases, deterministic assertions, local runner, CI failure on regressions |
| 2 | Captured trajectories, golden-suite baselines, canary model/prompt runs |
| 3 | Human annotation queues, LLM judges, online evals from production traces |
| 4 | Hosted platform with dataset versioning, dashboards, access control, and rollout gates |

Buy a hosted platform when coordination, annotation, auditability, or production trace mining costs more than the platform. Do not buy one to avoid defining what good behavior means.

### Stage 1 — Start Here

You need: JSONL cases under version control, deterministic assertions, a local runner, and CI that fails the build on any regression or governance failure. Acceptable runners include `pytest` driving the agent directly, `promptfoo` for declarative prompt and red-team tests, or a small custom script that captures the final answer and the tool-call trajectory. Do not adopt anything else until this loop runs on every change and blocks merge. Most teams underestimate Stage 1 and overpay for Stage 4 to compensate.

### Stage 2 — Add Trajectory And Baselines

Signals you have outgrown Stage 1: you cannot answer "did this prompt change regress?" because you have no captured baseline, or you cannot safely try a new model because there is no canary signal. Add: full trajectory capture, a frozen golden-suite baseline checked into the repo, and canary runs invoked before any model, provider, or tool-version swap. Diff current output against the baseline; review every delta before accepting a new baseline.

### Stage 3 — Add Humans And Judges

Signals you have outgrown Stage 2: subjective quality dimensions (helpfulness, tone, rubric fit) are being eyeballed inconsistently, or production traces contain failures that never reach your offline suite. Add: human annotation queues for the subjective calls, calibrated LLM judges with reported agreement, and online evals that score sampled production traces. Keep deterministic assertions as the merge gate; judges and humans inform, they do not replace, the gate.

### Stage 4 — When A Hosted Platform Earns Its Cost

Adopt a hosted platform (Braintrust, LangSmith, Langfuse, or comparable) only when one or more of these is true and the platform's cost is materially less than the team time it saves:

- Multiple teams need shared, versioned datasets with access control.
- Annotation queues need routing, review, and audit history beyond a spreadsheet.
- You need rollout gates wired into production traces, not only CI.
- Compliance or auditability requires queryable evidence of what was evaluated and when.
- Production-trace mining for failures has become a routine workflow, not an incident response.

Do not adopt a platform to skip defining what good behavior means. A hosted dashboard over an undefined rubric is a dashboard of opinions.

## Pitfalls

- Adopting a hosted platform before Stage 1 is wired. Fix: JSONL cases, deterministic assertions, and CI failure on regressions come first.
- Using an LLM judge to gate safety behavior. Fix: governance and schema gates stay deterministic; judges score subjective dimensions.
- Reporting a mean judge score without agreement data. Fix: report judge-vs-human agreement and the disagreements.
- Treating a benchmark rank as deployment readiness. Fix: the golden suite is the gate; benchmarks are comparability signals.
- Letting the platform's dataset drift from the shipped prompt and tool config. Fix: run evals from the same config path used in deployment.
- Picking a tool because it is well-known rather than because it fits the team's workflow. Fix: choose by fit (agent/tool-use vs RAG vs prompt/red-team) and re-check primary docs before standardizing.
