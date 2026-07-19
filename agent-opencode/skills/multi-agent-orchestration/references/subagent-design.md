# Subagent Design

Subagents are separate agent runs with narrower context and narrower purpose. They are not miniature copies of the main agent.

## Challenge the Premise

Ask: why does this need a subagent instead of a skill, command, script, or inline work?

Good reasons: parallelizable research, context-heavy analysis, isolated review, long-running work, or risk isolation. Bad reasons: wanting a reusable instruction, wanting a persona, or avoiding clear task definition.

A subagent is the heaviest of the available delegation tools. Cheaper options, in order: inline work (no overhead), a skill or instruction set (reusable, no spawn), a script (deterministic, no model), a CLI wrapper (deterministic, reusable). A subagent only wins when you need an independent model run with its own context — for parallelism, isolation, or specialist reasoning. If the task is deterministic, a script beats a subagent every time because it has no token cost and no verification burden.

## Claude Code Mapping

Claude Code subagents are defined as `agents/*.md` files and invoked through the Task tool when available in the host environment. The subagent definition provides role instructions and tool policy; the spawn prompt still must carry task-specific context. Do not assume the subagent inherits the parent conversation, private reasoning, or all local assumptions.

Two layers carry different content:

| Layer | Lives in | Carries |
|---|---|---|
| Subagent definition (`agents/*.md`) | Plugin/repo | Stable role, standing instructions, tool policy |
| Spawn prompt (per invocation) | Task invocation | This specific task, inputs, output contract, verification |

A well-written `agents/*.md` file reduces the per-spawn prompt length because the role and constraints are already fixed. But it does **not** remove the need for a task-specific briefing: the definition cannot know which files, branch, or stop condition this particular run needs.

## Spawn Prompt Structure

1. Context: why this task exists and what the parent is trying to achieve.
2. Task: bounded, specific, and independently executable.
3. Inputs: files, URLs, commands, constraints, and assumptions.
4. Output: exact artifact format and path if a file should be written.
5. Verification: what evidence proves completion.
6. Constraints: what not to modify, what not to access, and stop conditions.

### Filled-In Anatomy

```
[Context] You are a security reviewer spawned by the lead for mission
"ship-feature-x". The lead needs an independent read on authz risk before merge.
You do NOT inherit the parent conversation.

[Task] Review the diff on branch feature-x for authorization-bypass risks.

[Inputs] Files: repo/branches/feature-x.diff, repo/src/auth/*.ts.
Read-only. No network access.

[Output] Write findings to review/feature-x.md. Return a 5-line manifest:
severity histogram + top 3 findings with file:line.

[Constraints] Do not modify any file. Stop after 12 turns or when the diff is covered.

[Verification] Completion is proven by: review/feature-x.md exists with cited
file:line findings and a severity per finding. "done" alone is not accepted.
```

### Before / After

Bad (ambient assumptions, no contract):

> Review the feature branch for issues. Let me know what you find.

Good (self-contained, bounded, proof-bearing):

> Review `feature-x.diff` for authorization-bypass risks. Read-only, no network. Write cited findings with severity to `review/feature-x.md` and return a 5-line manifest. Stop after 12 turns. Completion is proven by the cited findings file existing.

The bad version assumes the subagent knows which branch, what "issues" means, where to write, and how the parent will judge success — none of which transfer from the parent conversation.

## Scope and Cost

Every subagent has its own context and token bill. Default to narrow scope and cheaper capable models. Fan-out multiplies cost and review burden; cap concurrency and require artifacts.

Cost is roughly multiplicative across fan-out: N subagents each reading the same large inputs cost roughly N × (input tokens + work tokens), plus the parent's verification pass over each artifact. A panel of five reviewers over a 20k-token diff is not "one review × 5" — it is five full passes plus consolidation. Before spawning, estimate:

```
total ≈ N × (spawn_prompt + inputs + work) + consolidation_pass
```

If that total dwarfs doing the work once with one focused agent, the fan-out is not justified. Cap concurrency explicitly (e.g., max 3 in flight), and require each subagent to write an artifact rather than returning prose, so the parent's verification pass reads bounded output.

## Tool Policy

Give each subagent the minimum tools for its job. A read-only reviewer should not inherit write or network privileges. A worker that handles untrusted content should not receive send/publish tools. Tool policy belongs to the role and risk profile, not to convenience.

A useful default policy matrix:

| Role | Read | Write | Network | Send/Publish |
|---|---|---|---|---|
| Reviewer | yes | no | no | no |
| Implementer | yes | scoped to branch | as needed | no |
| Untrusted-content worker | yes | scratch only | no | no |
| Deployer | yes | scoped | as needed | gated by approval |

Inheriting the parent's full tool set by default is the most common privilege leak. Narrow first; widen only with a stated reason recorded in the subagent definition.

## Subagent Design Checklist

- One role, one mission type.
- Narrow tool surface.
- Spawn prompt includes all needed context.
- Output is a verifiable artifact.
- Timeout and max-turn budget are defined.
- Parent verifies results before acting.

Run the checklist as a gate, not a wish list. If any item is missing, the spawn is not ready: a subagent without a max-turn budget can hang silently; a subagent without a stated artifact format will return prose the parent cannot verify; a subagent that inherits the parent's full tool set has already leaked privilege. The cheapest moment to fix these is before dispatch — after dispatch, you are debugging a run instead of designing one.

