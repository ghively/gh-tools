# eval-suite-template

Copy this directory into your agent project (conventionally `evals/`) and you
have a runnable golden suite with baseline gating on day one. It is the
starting point the `/agent-foundry-new-eval-suite` command builds from.

```
evals/
├── cases.jsonl        # the golden cases — one JSON object per line
├── run_evals.py       # stdlib-only runner: invoke agent, assert, gate
├── baseline.json      # pinned expected results (created by --set-baseline)
└── runs/              # dated result snapshots (gitignore if noisy)
```

## Wire it to your agent

The runner shells out to whatever command runs one prompt against your agent,
via `--agent-cmd` (or the `EVAL_AGENT_CMD` env var). `{prompt}` is replaced
per case:

```bash
# Headless agent CLI (any vendor):
python run_evals.py --agent-cmd 'claude -p {prompt} --max-turns 10'
python run_evals.py --agent-cmd 'opencode run "{prompt}"'
# your own CLI:
python run_evals.py --agent-cmd 'python src/agent.py {prompt}'
```

## The loop

```bash
python run_evals.py                  # run all cases, compare to baseline
python run_evals.py --set-baseline   # pin current results as the baseline
python run_evals.py --only regression-issue-42
```

Rules that make this worth having (from the `agent-evals` pillar):

1. **Four categories, breadth first** — governance (never-do), capability
   (each tool works), behavioral (operating contracts), regression (one case
   per past bug, named after it).
2. **Assertions, not vibes** — every case must be machine-checkable. If you
   can't write the assertion, rewrite the case.
3. **The gate is the point** — no prompt/model/tool/config change ships
   without a green run. Wire `run_evals.py` into CI next to your tests.
4. **Sandbox side effects** — anything that can write or spend should run
   under the sandbox wrapper (see the skill's `scripts/eval-sandbox-wrapper.sh`).
