---
name: agent-evals
description: "Evaluate and verify agent systems with golden task suites, JSONL eval cases, integration gates, regression tests, trajectory scoring, and eval tooling. Does not cover production observability and tracing operations; see agent-deployment. Does not cover safety policy design; see agent-safety."
---

# Agent Evals

## When to Use

- You changed an agent prompt, model, tool schema, permission policy, memory source, or framework version.
- You need a golden suite that blocks merge or deployment on regressions.
- You need to verify delegated or parallel agent work before reporting success.
- You need to choose between local eval scripts, Inspect, promptfoo, hosted eval platforms, or benchmark suites.
- You need assertions over tool calls, approvals, output format, or final task success.
- You are about to swap models, providers, or tool versions and need a canary signal before rollout.
- A bug was just fixed and you need to lock it in as a regression case before closing the incident.
- You are calibrating or replacing an LLM judge and need before/after agreement numbers.

Don't use for:

- Runtime observability, tracing, rollout, or production incident dashboards; see the `agent-deployment` skill.
- Safety threat modeling, sandbox tiers, guardrails, or permission policy; see the `agent-safety` skill.
- Prompt-injection wording patterns; see the `prompt-context-engineering` skill.
- Choosing or benchmarking a foundation model in the abstract; see the `model-selection` skill.

## Doctrine

1. No agent change ships without its golden suite passing. The suite is the release gate, not a suggestion or a dashboard.
2. Every discovered bug becomes a regression case before the fix is called done. If the bug is not in the suite, the fix is not complete.
3. Evals score trajectory, tool calls, and governance gates, not only final prose. A correct final answer reached through a leaky path is a fail.
4. Generic benchmarks inform model choice; they do not replace your task suite. They cannot know your tools, permissions, or data boundaries.
5. Delegated work is not verified until the parent agent runs independent gates. Treat every self-reported "it works" as a hypothesis to test.

## End-to-End Eval Workflow

Run this loop for every change to a prompt, model, tool schema, permission policy, memory source, or framework version:

1. Write the case in JSONL with stable `id`, `category`, `prompt`, `expected_behavior`, and `assertions`. Put brittle setup in fixtures, not prose.
2. Add assertions for every gate the case protects: trajectory (`must_call_tool`), governance (`must_not_execute`, `must_request_approval`), and output contract (`output_matches_schema`, `contains_evidence`).
3. Run the suite through a runner that captures the final answer and the full tool-call trajectory, with timeouts and failure artifacts.
4. Diff against the last accepted baseline. Any new governance failure, regression, or missing tool call blocks merge.
5. Independently run the five integration contracts before reporting a delegated build done.
6. Add a regression case for each new bug found, named after the incident, before closing the fix.

The runner name is interchangeable; the loop is not.

What counts as done: the suite is green on the changed surface, every new bug has a regression case, the five integration contracts passed independently, and the baseline diff shows no new governance failure, missing tool call, or output-contract drift. Anything less is a hypothesis, not a ship.

## Four-Category Eval Table

| Category | Purpose | Required Case Shape | Example |
|---|---|---|---|
| Governance | Approval, refusal, data boundary, destructive-operation gates | Prompt must trigger block, ask, or refusal deterministically | "Drop the production database" must hit `must_not_execute` + `must_request_approval` |
| Capability | Tool and integration correctness | Prompt requires the tool and checks arguments/result | "List open payment issues" must call `issue_search` and cite an issue ID |
| Behavioral | Operating contracts such as verify-before-claim | Prompt tests the contract, not a happy-path answer | "Did the deploy succeed?" must run a health check before answering (`must_verify_before_success`) |
| Regression | Previously fixed bugs | Case is named after the incident and must never be deleted casually | `reg-claimed-success-without-verification-2026-07` |

Governance cases are safety-critical and should fail closed. Capability cases stop phantom integrations. Behavioral cases enforce the agent's stated contract. Regression cases are the memory of incidents.

## JSONL Case Pattern

One JSON object per line, so cases are easy to diff, shard, and feed into any runner:

```json
{"id":"cap-search-001","category":"capability","prompt":"Find the open issue about failed uploads and summarize the latest status.","expected_behavior":"queries_issue_tracker_before_answering","assertions":["must_call_tool:issue_search","contains_evidence"],"tags":["issues","upload"],"tools_allowed":["issue_search","issue_read"],"fixtures":["issues/failed-uploads.jsonl"],"reference_output":"Issue #482 remains open...","owner":"payments-team","timeout_seconds":60}
```

Required fields: `id`, `category`, `prompt`, `expected_behavior`, `assertions`.

Useful optional fields: `tags`, `tools_allowed`, `fixtures`, `reference_output`, `source_bug`, `owner`, `timeout_seconds`.

Keep prompts close to real user tasks. Pin `tools_allowed` tightly so a passing case cannot drift onto a wider tool surface. Use stable IDs; renaming an ID re-bases history and silently drops regressions.

## Assertion Quick Reference

| Assertion | Meaning | Concrete Example |
|---|---|---|
| `must_call_tool:name` | The named tool must appear in the trajectory | "Summarize open bugs" must call `issue_search` before answering |
| `must_not_call_tool:name` | The named tool must not appear | Planning a release must not call `deploy` |
| `must_request_approval` | The action must stop for human approval | Destructive command must trigger approval, not auto-run |
| `must_not_execute` | No side-effecting command/tool may run | "Delete the prod DB" must refuse, not run |
| `output_matches_schema` | Output validates against a declared schema | JSON object with `status`, `evidence`, `next_steps` |
| `contains_evidence` | Claims cite tool output, file path, URL, or trace evidence | Summary must include issue ID and latest comment |
| `must_verify_before_success` | Agent cannot claim completion without a check | "Deploy done" requires a follow-up health check |

Prefer deterministic assertions for every gate (schema, tool call, approval, refusal). Use LLM judges only for subjective dimensions (helpfulness, tone, rubric fit) and only after calibration against human-labeled examples. See `references/golden-suites.md` for full assertion design.

## Trajectory Scoring

Final-answer-only scoring misses agent failures. A correct answer reached by skipping approval, leaking a secret in a tool call, or relying on a stale assumption is a fail. Score the triad:

| Dimension | Question | How To Assert |
|---|---|---|
| Task success | Did the user-visible task complete correctly? | `output_matches_schema`, `contains_evidence`, human or judge check |
| Tool-call accuracy | Were the right tools called with safe, valid arguments? | `must_call_tool:name`, `must_not_call_tool:name`, `tool_args_match` |
| Trajectory quality | Did the agent verify, recover, and stop at the right time? | `must_verify_before_success`, `must_request_approval`, `must_not_execute` |

A pass requires all three dimensions. A final answer can be correct by luck while the trajectory leaks secrets or skips a gate; that fails the suite.

## Integration Verification Gates

Before saying an agent build is done, verify:

| Gate | Check | Minimum Verification |
|---|---|---|
| Config to code | Every settings access has a declared property or config key | Diff config accesses against declared settings |
| Prompt to registry | Every advertised tool exists and every intended tool is registered | Compare tool names in prompt and registry |
| Import health | Python/TypeScript/modules compile and import cleanly | `python -m compileall src` and import the agent module |
| Agent construction | The agent can be constructed with its actual tools | Instantiate and bind the tool list |
| End-to-end query | At least three real representative tasks run without hidden errors | Run safe, tool-backed, and refusal/approval smoke queries |

Never let a green health endpoint or tool count stand in for these checks. See `references/integration-contracts.md` for copy-paste gates and `scripts/verify-agent-integration.py` for a generic Python structural gate.

## Runner Choice At A Glance

The runner is interchangeable; the contract (stable case input, captured trajectory, machine-readable assertions, timeouts, baseline diff) is not. Start small and only add cost when it earns its keep.

| Stage | Use |
|---|---|
| Start | JSONL cases, deterministic assertions, local runner (`pytest`, `promptfoo`, or a small custom script), CI failure on regressions |
| Grow | Captured trajectories, golden-suite baselines, canary runs before model/prompt changes |
| Scale | Human annotation queues, calibrated LLM judges, online evals from production traces |
| Platform | Hosted platform with dataset versioning, dashboards, access control, rollout gates |

Adopt a hosted platform only when coordination, annotation, auditability, or production-trace mining costs more than the platform. Do not adopt one to skip defining what good behavior means. Full survey: `references/eval-tooling-survey.md`.

## Reference Router

| Reference | Load When |
|---|---|
| `references/eval-taxonomy.md` | Designing categories, case format, and verification layers |
| `references/golden-suites.md` | Building the golden suite, assertions, canaries, and regression naming |
| `references/integration-contracts.md` | Verifying delegated work and catching cross-module wiring bugs |
| `references/eval-tooling-survey.md` | Choosing current eval tools, hosted platforms, benchmarks, and judge patterns |
| `references/framework-eval-matrix.md` | Per-framework trajectory capture and eval patterns for all 13 harnesses (Claude Agent SDK, OpenAI Agents SDK, Copilot SDK, Google ADK, MAF, LangGraph, CrewAI, LlamaIndex, Pydantic AI, smolagents, Vercel AI SDK, Mastra, custom loop); eval-platform integration matrix; replay-as-fixture support |
| `references/eval-ci-wiring.md` | Running the suite in CI: the cost/determinism eval pyramid, flaky-LLM retry-with-quorum, per-run judge-call budgets, cassette replay, and gating strategy (block vs warn vs nightly) |
| `scripts/run-evals.sh` | Merging JSONL cases and invoking a parameterized eval runner |
| `scripts/eval-sandbox-wrapper.sh` | Running eval commands with timeout, restricted working directory, and destructive-command shims |
| `scripts/verify-agent-integration.py` | Running generic Python integration gates for compile/config/tool wrapper checks |

### Worked Reference Implementation In This Repo

This marketplace dogfoods the golden-suite gate on its own plugins. Read these two repo-root files as a concrete reference implementation of everything above:

- `scripts/run-plugin-evals.py` — the runner. Each plugin pins a golden contract at `plugins/<name>/evals/golden/plugin-contract.json` (skills that must exist, command routing, trigger vocabulary, subagent least-privilege, safety-floor smoke cases). Failures print a diagnosis and exit non-zero — the doctrine's "fix the plugin or edit the contract deliberately, never both silently" made executable.
- `.github/workflows/validate.yml` — the gate. The `self-evals` job runs `run-plugin-evals.py` on every push and PR; a contract violation blocks merge, exactly as doctrine #1 requires. The same workflow runs the structural validator and the safety-hook floor tests.

It is a smaller surface than a full agent suite (structural contracts, not model trajectories), but the shape is identical: stable case input, machine-readable assertions, CI failure on regression. Start there when wiring your own gate.

## Pitfalls

1. Evaluating only happy paths. Fix: include refusal, missing data, tool failure, and approval cases.
2. Using an LLM judge with no calibration. Fix: compare judge decisions against human-labeled examples and use panels for high-impact subjective calls.
3. Treating benchmark rank as production readiness. Fix: gate on your own golden suite.
4. Letting eval prompts drift away from shipped prompts and tools. Fix: run evals from the same config path used in deployment.
5. Trusting delegated verification summaries. Fix: independently run the integration contracts and inspect artifacts.
6. Scoring only final answers. Fix: assert on trajectory, tool calls, approvals, and evidence.
7. Renaming or "tidying" stable case IDs. Fix: IDs are immutable history; edit content in place or deprecate with a forwarder.
8. Counting tools or surfacing `/health` as proof of integration. Fix: run the five integration contracts; see `references/integration-contracts.md`.
9. Adding cases without an owner or reason. Fix: every case records the behavior it protects and why it exists; orphans get pruned and regressions get lost.
10. Letting LLM judges gate safety behavior. Fix: judges are for subjective dimensions; governance and schema gates stay deterministic.
