#!/usr/bin/env bash
# One-command setup for gh-tools on a fresh machine.
#
# The entire fleet has exactly ONE system dependency: uv. Every MCP server is
# a PEP 723 single-file script whose deps (mcp<2.0.0, httpx, + per-plugin
# extras) resolve automatically from uv's shared package cache on first run.
# This script installs uv if missing, then pre-warms every server's script
# environment so plugin startup is instant and offline-safe afterwards.
#
# Usage: scripts/bootstrap.sh          # install uv + warm all envs
#        scripts/bootstrap.sh --test   # also run every plugin's smoke test
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "==> installing uv (the fleet's only system dependency)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "==> uv $(uv --version | awk '{print $2}')"

echo "==> pre-warming script environments"
warmed=0
for f in "$ROOT"/*/mcp/*.py; do
  # only PEP 723 scripts (helpers like comfy_graphs.py/acp_client.py have no header)
  head -5 "$f" | grep -q "^# /// script" || continue
  uv sync --script "$f" --quiet && warmed=$((warmed+1)) || echo "WARN: sync failed for $f"
done
echo "==> $warmed script environments ready"

if [[ "${1:-}" == "--test" ]]; then
  echo "==> running smoke tests (skip cleanly where no config.local.json exists)"
  pass=0; fail=0; skip=0
  for t in "$ROOT"/*/mcp/_smoketest.py; do
    plugin="$(basename "$(dirname "$(dirname "$t")")")"
    if [[ ! -f "$ROOT/$plugin/config.local.json" ]]; then
      echo "SKIP  $plugin (no config.local.json)"; skip=$((skip+1)); continue
    fi
    if (cd "$ROOT/$plugin" && uv run --script "$t" >/tmp/gh-tools-smoke-$plugin.log 2>&1); then
      echo "PASS  $plugin"; pass=$((pass+1))
    else
      echo "FAIL  $plugin (see /tmp/gh-tools-smoke-$plugin.log)"; fail=$((fail+1))
    fi
  done
  echo "==> smoke: $pass pass, $fail fail, $skip skipped"
  [[ $fail -eq 0 ]]
fi
