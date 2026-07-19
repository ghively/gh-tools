---
description: Build a golden governance, capability, behavioral, and regression eval suite for an agent.
agent: build
---

Build evals for `$ARGUMENTS`. Load `agent-evals`, inventory tools, authority,
contracts, and known bugs, then create 10 to 20 high-value cases with
machine-checkable assertions. Include governance cases for every dangerous or
escalated capability, capability cases per tool, behavioral contracts, and
named regressions. Wire the runner, sandbox side effects, run the baseline,
and require a green run before behavioral changes ship.
