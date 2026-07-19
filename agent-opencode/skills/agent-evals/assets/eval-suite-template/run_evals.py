#!/usr/bin/env python3
"""Golden eval runner — stdlib only, agent-agnostic.

    python run_evals.py --agent-cmd 'claude -p {prompt} --max-turns 10'
    python run_evals.py --set-baseline
    python run_evals.py --only regression-issue-42

Reads cases.jsonl, invokes the agent command once per case ({prompt} is
substituted, safely quoted), evaluates assertions against the agent's stdout,
writes a dated snapshot to runs/, and gates against baseline.json:

  - a case that passed in the baseline and fails now  -> REGRESSION, exit 1
  - a case failing with no baseline entry             -> reported, exit 1
  - --set-baseline pins the current outcome set

Supported assertions per case (all optional, all must hold):
  output_contains      [str] — every string must appear
  output_contains_any  [str] — at least one must appear
  output_not_contains  [str] — none may appear
  output_regex         str   — must match (re.search)
  must_exit_zero       bool  — agent process exit code must be 0
"""
import argparse
import datetime
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases.jsonl")
BASELINE = os.path.join(HERE, "baseline.json")
RUNS = os.path.join(HERE, "runs")
TIMEOUT = int(os.environ.get("EVAL_TIMEOUT_SECONDS", "300"))


def load_cases(only=None):
    cases = []
    with open(CASES, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("//"):
                case = json.loads(line)
                if only is None or case["id"] == only:
                    cases.append(case)
    return cases


def invoke(agent_cmd, prompt):
    parts = [p.replace("{prompt}", prompt) for p in shlex.split(agent_cmd)]
    try:
        proc = subprocess.run(parts, capture_output=True, text=True,
                              timeout=TIMEOUT)
        return proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        return -1, f"<timeout after {TIMEOUT}s>"


def check(assertions, exit_code, output):
    """Evaluate assertions against agent output.

    Supports two formats:
    1. Dict format (legacy): {"output_contains": [...], "output_not_contains": [...], ...}
    2. Array format (doctrine): ["must_call_tool:search", "contains_evidence", "not_contains:error", "must_exit_zero", "must_request_approval"]

    Array assertions are parsed by prefix:
    - must_call_tool:<name> — the trajectory must contain this tool (requires trajectory capture; warns if unsupported)
    - must_not_execute:<name> — the trajectory must NOT contain this tool (warns if unsupported)
    - must_request_approval — the trajectory must show an approval pause (warns if unsupported)
    - contains:<text> / contains_evidence — the output must contain this text
    - not_contains:<text> — the output must NOT contain this text
    - must_exit_zero — the agent must exit 0
    - output_regex:<pattern> — the output must match this regex
    """
    problems = []
    low = output.lower()

    # Dict format (legacy, backward compatible)
    if isinstance(assertions, dict):
        for s in assertions.get("output_contains", []):
            if s.lower() not in low:
                problems.append(f"missing required string: {s!r}")
        anys = assertions.get("output_contains_any", [])
        if anys and not any(s.lower() in low for s in anys):
            problems.append(f"none of the accepted strings present: {anys}")
        for s in assertions.get("output_not_contains", []):
            if s.lower() in low:
                problems.append(f"forbidden string present: {s!r}")
        pattern = assertions.get("output_regex")
        if pattern and not re.search(pattern, output):
            problems.append(f"regex did not match: {pattern!r}")
        if assertions.get("must_exit_zero") and exit_code != 0:
            problems.append(f"agent exited {exit_code}")
        return problems

    # Array format (doctrine — each assertion is a string)
    if isinstance(assertions, list):
        for assertion in assertions:
            # Trajectory assertions (require framework-specific capture)
            if assertion.startswith("must_call_tool:"):
                problems.append(f"WARNING: 'must_call_tool' requires trajectory capture — not supported by text-only runner. Wire trajectory per framework-eval-matrix.md. Assertion: {assertion}")
            elif assertion.startswith("must_not_execute:"):
                problems.append(f"WARNING: 'must_not_execute' requires trajectory capture — not supported by text-only runner. Wire trajectory per framework-eval-matrix.md. Assertion: {assertion}")
            elif assertion == "must_request_approval":
                problems.append(f"WARNING: 'must_request_approval' requires HITL trajectory capture — not supported by text-only runner. Wire per framework-eval-matrix.md.")
            # Output-content assertions
            elif assertion.startswith("contains:"):
                s = assertion[len("contains:"):]
                if s.lower() not in low:
                    problems.append(f"missing required string: {s!r}")
            elif assertion == "contains_evidence":
                if "evidence" not in low and "source" not in low and "citation" not in low:
                    problems.append("output lacks evidence/citation")
            elif assertion.startswith("not_contains:"):
                s = assertion[len("not_contains:"):]
                if s.lower() in low:
                    problems.append(f"forbidden string present: {s!r}")
            elif assertion.startswith("output_regex:"):
                pattern = assertion[len("output_regex:"):]
                if not re.search(pattern, output):
                    problems.append(f"regex did not match: {pattern!r}")
            elif assertion == "must_exit_zero":
                if exit_code != 0:
                    problems.append(f"agent exited {exit_code}")
            else:
                # Unrecognized format — treat as contains for backward compat
                if assertion.lower() not in low:
                    problems.append(f"missing required string: {assertion!r}")
        return problems

    problems.append(f"unrecognized assertions format: {type(assertions).__name__} — use dict or list")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-cmd", default=os.environ.get("EVAL_AGENT_CMD"),
                    help="command template; {prompt} is substituted per case")
    ap.add_argument("--set-baseline", action="store_true")
    ap.add_argument("--only", help="run a single case id")
    args = ap.parse_args()
    if not args.agent_cmd:
        sys.exit("no agent command: pass --agent-cmd or set EVAL_AGENT_CMD")

    cases = load_cases(args.only)
    if not cases:
        sys.exit(f"no cases matched (looked in {CASES})")

    results = {}
    for case in cases:
        exit_code, output = invoke(args.agent_cmd, case["prompt"])
        problems = check(case.get("assertions", {}), exit_code, output)
        results[case["id"]] = {
            "category": case["category"],
            "passed": not problems,
            "problems": problems,
        }
        mark = "PASS" if not problems else "FAIL"
        print(f"  {mark}  [{case['category']}] {case['id']}")
        for p in problems:
            print(f"        - {p}")

    os.makedirs(RUNS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = os.path.join(RUNS, f"{stamp}.json")
    with open(snapshot, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    if args.set_baseline:
        with open(BASELINE, "w", encoding="utf-8") as fh:
            json.dump({cid: r["passed"] for cid, r in results.items()},
                      fh, indent=2)
        print(f"\nbaseline pinned ({len(results)} cases) -> {BASELINE}")
        return

    baseline = {}
    if os.path.isfile(BASELINE):
        with open(BASELINE, encoding="utf-8") as fh:
            baseline = json.load(fh)

    regressions = [cid for cid, r in results.items()
                   if not r["passed"] and baseline.get(cid, False)]
    new_failures = [cid for cid, r in results.items()
                    if not r["passed"] and cid not in baseline]
    passed = sum(r["passed"] for r in results.values())
    print(f"\n{passed}/{len(results)} passed — snapshot: "
          f"{os.path.relpath(snapshot)}")
    if regressions:
        print(f"REGRESSIONS vs baseline: {regressions}")
    if new_failures:
        print(f"failing cases with no baseline entry: {new_failures}")
    if regressions or new_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
