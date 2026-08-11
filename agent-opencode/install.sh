#!/usr/bin/env bash
# Install agent-opencode into ~/.config/opencode/
# Idempotent: re-running updates in place.
set -euo pipefail
shopt -s nullglob   # empty globs expand to nothing, not a literal pattern

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${HOME}/.config/opencode"

echo "Installing agent-opencode from $SRC → $DEST"

mkdir -p "$DEST/agent-opencode" "$DEST/commands" "$DEST/agents"

# 1. Skills + plugin (the bulk of the package)
# --include before --exclude: keep the eval-suite template's cases.jsonl
# while still excluding runtime *.jsonl audit logs.
rsync -a --delete \
  --include='cases.jsonl' \
  --exclude='node_modules' --exclude='dist' --exclude='*.log' --exclude='*.jsonl' \
  "$SRC/skills" "$SRC/plugins" "$DEST/agent-opencode/"

# 2. Commands (20 agent-foundry workflows)
for f in "$SRC"/commands/agent-foundry-*.md; do
  cp "$f" "$DEST/commands/"
done
echo "  commands: $(ls "$DEST/commands"/agent-foundry-*.md | wc -l)"

# 3. Agents (4 subagents — primary agent-foundry comes from opencode.json)
for f in "$SRC"/agents/agent-foundry-*.md; do
  cp "$f" "$DEST/agents/"
done
echo "  subagents: $(ls "$DEST/agents"/agent-foundry-*.md 2>/dev/null | wc -l)"

# 4. Merge opencode.example.json into the user's opencode.json
if [ ! -f "$DEST/opencode.json" ]; then
  echo "  creating $DEST/opencode.json from example"
  cp "$SRC/opencode.example.json" "$DEST/opencode.json"
else
  echo "  opencode.json already exists — merge these keys manually:"
  echo "    - skills.paths (add $DEST/agent-opencode/skills)"
  echo "    - permission (the bash/edit safety floor)"
  echo "    - agent (the 5 agent-foundry agents)"
  echo "  See $SRC/opencode.example.json for the canonical shape."
fi

# 5. Build the safety plugin (optional — only if local plugin bug is fixed upstream)
if [ -d "$DEST/agent-opencode/plugins/agent-foundry-safety" ] && command -v npm >/dev/null 2>&1; then
  echo "  building safety plugin..."
  (cd "$DEST/agent-opencode/plugins/agent-foundry-safety" && npm ci --silent && npm run build && npm test)
  echo "  plugin built and tested"
  echo ""
  echo "  NOTE: OpenCode 1.18.3 has a bug where local TypeScript plugins fail to load."
  echo "  The safety floor is provided by native permission rules until the bug is fixed."
  echo "  See README.md for details."
fi

echo ""
echo "Done. Restart OpenCode to activate."
echo ""
echo "Quick verification:"
echo "  opencode run 'say ok'"
echo "  # should print 'ok' with no plugin errors"
