#!/usr/bin/env bash
set -euo pipefail

# Generic eval runner for JSONL cases.
# Configure with environment variables or flags:
#   EVALS_DIR: directory containing category/*.jsonl files (default: ./evals)
#   EVAL_RUNNER: executable or script that accepts --dataset-file and --run-name
#   EVAL_RUNNER_ARGS: extra arguments passed to the runner

EVALS_DIR="${EVALS_DIR:-./evals}"
RUNS_DIR="${RUNS_DIR:-$EVALS_DIR/runs}"
BASELINE_DIR="${BASELINE_DIR:-$EVALS_DIR/baselines}"
RUN_NAME="${RUN_NAME:-eval-$(date +%Y%m%d-%H%M%S)}"
RUN_DIR="$RUNS_DIR/$RUN_NAME"
EVAL_RUNNER="${EVAL_RUNNER:-}"
EVAL_RUNNER_ARGS="${EVAL_RUNNER_ARGS:-}"

mkdir -p "$RUN_DIR" "$BASELINE_DIR"

shopt -s nullglob
ALL_PROMPTS=()
for category in governance capability behavioral regression; do
    for file in "$EVALS_DIR"/"$category"/*.jsonl; do
        ALL_PROMPTS+=("$file")
    done
done
shopt -u nullglob

if [ "${#ALL_PROMPTS[@]}" -eq 0 ]; then
    echo "ERROR: no eval prompts found under $EVALS_DIR" >&2
    exit 1
fi

python3 - "$RUN_DIR/prompts.jsonl" "${ALL_PROMPTS[@]}" <<'PY'
import json
import sys

out = sys.argv[1]
paths = sys.argv[2:]
with open(out, "w", encoding="utf-8") as dest:
    for path in paths:
        with open(path, encoding="utf-8") as src:
            for raw in src:
                raw = raw.strip()
                if not raw:
                    continue
                entry = json.loads(raw)
                if "prompt" not in entry:
                    task = (entry.get("input") or {}).get("task")
                    if task:
                        entry["prompt"] = task
                required = {"id", "category", "prompt"}
                missing = sorted(required - set(entry))
                if missing:
                    raise SystemExit(f"{path}: missing required fields {missing}")
                dest.write(json.dumps(entry, sort_keys=True) + "\n")
PY

COUNT=$(wc -l < "$RUN_DIR/prompts.jsonl")
echo "Running $COUNT evals: $RUN_NAME"
echo "Merged prompts: $RUN_DIR/prompts.jsonl"

if [ -n "$EVAL_RUNNER" ]; then
    # shellcheck disable=SC2086
    "$EVAL_RUNNER" --dataset-file "$RUN_DIR/prompts.jsonl" --run-name "$RUN_NAME" $EVAL_RUNNER_ARGS 2>&1 | tee "$RUN_DIR/output.log"
else
    echo "EVAL_RUNNER is unset; wrote merged dataset for manual or CI runner use."
    python3 - "$RUN_DIR/prompts.jsonl" <<'PY'
import json
import sys

for line in open(sys.argv[1], encoding="utf-8"):
    item = json.loads(line)
    print(f"[{item['id']}] {item['category']}: {item['prompt'][:90]}")
PY
fi

if ! compgen -G "$BASELINE_DIR/*.jsonl" > /dev/null; then
    cp "$RUN_DIR/prompts.jsonl" "$BASELINE_DIR/baseline-$(date +%Y%m%d).jsonl"
    echo "Recorded first baseline in $BASELINE_DIR"
fi

echo "Run complete: $RUN_DIR"
