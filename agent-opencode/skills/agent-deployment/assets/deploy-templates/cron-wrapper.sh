#!/usr/bin/env bash
# Scheduled-agent wrapper: overlap lock + heartbeat + budget, per the
# scheduled-event-driven-agents reference. Call from cron or a systemd timer:
#   ./cron-wrapper.sh python src/agent.py "the wake-up prompt"
set -euo pipefail

AGENT_NAME="${AGENT_NAME:-my-agent}"
STATE_DIR="${AGENT_STATE_DIR:-$HOME/.local/state/$AGENT_NAME}"
BUDGET_SECONDS="${AGENT_BUDGET_SECONDS:-900}"   # hard wall-clock cap
mkdir -p "$STATE_DIR"

# --- Overlap control: skip (don't queue) if the previous run still holds it.
# A backlog of stale runs firing at once is the classic scheduled-agent incident.
exec 9>"$STATE_DIR/run.lock"
if ! flock --nonblock 9; then
  echo "$(date -Is) SKIP overlap — previous run still active" >>"$STATE_DIR/runs.log"
  exit 0
fi

# --- Heartbeat: record EVERY firing, including no-ops, so "agent went quiet"
# is distinguishable from "agent had nothing to say". Alarm from the OUTSIDE
# on this file's age (e.g. a monitoring check on mtime > 2x the schedule).
date -Is >"$STATE_DIR/heartbeat"

START=$(date -Is)
set +e
timeout --signal=TERM "$BUDGET_SECONDS" "$@" >>"$STATE_DIR/last-run.out" 2>&1
CODE=$?
set -e

# Exit-path record: done / budget-killed / failed — the weekly ops review
# reads this distribution (operating-live-agents reference).
case $CODE in
  0)   OUTCOME=done ;;
  124) OUTCOME=budget-killed ;;
  *)   OUTCOME="failed($CODE)" ;;
esac
echo "$START -> $(date -Is) $OUTCOME" >>"$STATE_DIR/runs.log"

# Fail loudly to the scheduler (cron mail / systemd unit failure) on real
# errors; budget kills also count — a run that needs killing is a behavior
# change, not a fluke.
[ "$OUTCOME" = done ]
