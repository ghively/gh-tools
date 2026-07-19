# Conversion Framework Matrix

Reference matrix for converting a plugin into a standalone agent on a
non-OpenCode target. OpenCode is the current host, so this file is retained
for cross-host migrations only.

## Selection Criteria

When choosing a target framework, evaluate:

- **MCP support** — first-class, adapter, or absent.
- **Skills / SKILL.md support** — native, portable, or manual loader.
- **Subagents / isolated context** — supported, partial, or absent.
- **PreToolUse-equivalent** — deterministic hook available, prompt-only, or
  absent.
- **Vendor lock-in** — license, control plane, default telemetry, exit cost.
- **Model buckets** — strong / value / budget tier support per subagent.

## Hard-Deny vs Soft-Fail

When porting a safety floor, prefer frameworks that allow hard-deny (throw
or equivalent). Soft-fail frameworks (log and continue) do not preserve the
source's enforcement semantics and must be flagged in the conversion
report.

## Notes

For OpenCode-native work, the answer is direct translation into OpenCode's
surfaces (skills, commands, subagents, plugins, MCP). Do not route OpenCode
work through another framework unless there is a specific reason.
