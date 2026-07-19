# Authoring OpenCode Commands

Use a command when a workflow is user-invoked and takes arguments. Use a
skill when the model should load contextual knowledge automatically.

## Mechanics

Verified against the OpenCode config schema
(`https://opencode.ai/config.json`) and the `command` definition.

- Commands live at `.opencode/commands/<name>.md`,
  `.opencode/command/<name>.md`, or the global
  `~/.config/opencode/commands/<name>.md` tree.
- A command creates a `/name` slash invocation. Names are flat; plugin-style
  `ns:name` prefixes are not expanded.
- `template` is the command body — everything below the frontmatter — and is
  required; do not put a `template:` key in frontmatter.
- `$ARGUMENTS` expands to everything the user typed after the command.
- `$1`, `$2`, ... expand to individual positional arguments.

## Supported Frontmatter

| Field | Use |
|---|---|
| `description` | Required, what the command does |
| `agent` | Name of the agent to run the template against |
| `model` | Optional `provider/model-id` override |
| `variant` | Optional model variant |
| `subtask` | Optional boolean, runs as a subtask |

`argument-hint`, `arguments`, `allowed-tools`, `disable-model-invocation`,
`user-invocable`, `context`, `hooks`, `paths`, and `shell` are Claude-only
and have no effect in OpenCode. Drop them.

## When to Use a Command

- The user explicitly invokes a workflow: `/release-notes 1.2.3`.
- The workflow takes positional or named arguments.
- The body needs a specific agent or model.

Keep side-effectful commands explicit. The body is run as a prompt, so state
changes (deploy, publish, commit, delete) should be gated by an explicit
approval step in the template, not implied.

## Body Shape

```markdown
---
description: Draft release notes for $VERSION from merged PRs since the last tag.
agent: plan
---

Draft release notes for $ARGUMENTS.

1. Read the changelog and merged PRs since the last tag.
2. Group changes into Added / Changed / Fixed / Removed.
3. Propose the next version bump and the notes draft.
4. Stop for approval before writing anything.
```

## Referencing Other Commands

OpenCode does not expand one command inside another. If a workflow depends
on another command's procedure, either inline the shared procedure into the
template or move it into a skill the command loads.

## Verification

1. Frontmatter parses and `description` is non-empty.
2. `$ARGUMENTS` and positional substitutions expand as expected.
3. The slash invocation appears after a restart.
4. Side effects are gated by explicit approval in the template.
