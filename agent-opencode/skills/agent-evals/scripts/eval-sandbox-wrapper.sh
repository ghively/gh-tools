#!/usr/bin/env bash
set -euo pipefail

# Safe wrapper for eval commands. It provides:
#   1. A wall-clock timeout.
#   2. PATH shims that block destructive commands.
#   3. A restricted working directory.
# Usage: eval-sandbox-wrapper.sh -- command arg...

TIMEOUT_SECONDS="${EVAL_TIMEOUT_SECONDS:-1200}"
TMP_ROOT="${TMPDIR:-/tmp}"
SANDBOX_DIR="$(mktemp -d "$TMP_ROOT/agent-eval-sandbox.XXXXXX")"

cleanup() {
    rm -rf "$SANDBOX_DIR"
}
trap cleanup EXIT

mkdir -p "$SANDBOX_DIR/bin" "$SANDBOX_DIR/work"
# Default to the sandbox work dir so the agent runs isolated unless EVAL_WORKDIR overrides it.
WORKDIR="${EVAL_WORKDIR:-$SANDBOX_DIR/work}"

make_shim() {
    local cmd="$1"
    cat > "$SANDBOX_DIR/bin/$cmd" <<SHIM
#!/usr/bin/env bash
REAL_CMD="\$(PATH="\${PATH#*:}" command -v "$cmd" 2>/dev/null || true)"
case "\$*" in
    *"system prune"*|*"rm -rf /"*|*"systemctl stop"*|*"systemctl restart"*|*"systemctl disable"*|*"mkfs"*|*"--privileged"*|*"--network=host"*|*"--pid=host"*)
        echo "BLOCKED by eval sandbox: $cmd \$*" >&2
        exit 126
        ;;
esac
if [ -z "\$REAL_CMD" ]; then
    echo "Command not found outside sandbox shim: $cmd" >&2
    exit 127
fi
exec "\$REAL_CMD" "\$@"
SHIM
    chmod +x "$SANDBOX_DIR/bin/$cmd"
}

for cmd in docker systemctl rm dd mkfs shred; do
    make_shim "$cmd"
done

cat > "$SANDBOX_DIR/bin/ansible-playbook" <<'SHIM'
#!/usr/bin/env bash
REAL_CMD="$(PATH="${PATH#*:}" command -v ansible-playbook 2>/dev/null || true)"
case "$*" in
    *"--syntax-check"*|*"--check"*|*"--list-tasks"*|*"--list-hosts"*) exec "$REAL_CMD" "$@" ;;
    *) echo "BLOCKED by eval sandbox: ansible-playbook without dry-run flag" >&2; exit 126 ;;
esac
SHIM
chmod +x "$SANDBOX_DIR/bin/ansible-playbook"

cat > "$SANDBOX_DIR/bin/git" <<'SHIM'
#!/usr/bin/env bash
REAL_CMD="$(PATH="${PATH#*:}" command -v git 2>/dev/null || true)"
case "${1:-}" in
    push|reset|rebase) echo "BLOCKED by eval sandbox: git $1" >&2; exit 126 ;;
esac
exec "$REAL_CMD" "$@"
SHIM
chmod +x "$SANDBOX_DIR/bin/git"

export PATH="$SANDBOX_DIR/bin:$PATH"
cd "$WORKDIR"

if [ "${1:-}" = "--" ]; then
    shift
fi
if [ "$#" -eq 0 ]; then
    echo "Usage: $0 -- command arg..." >&2
    exit 2
fi

timeout "$TIMEOUT_SECONDS" "$@"
