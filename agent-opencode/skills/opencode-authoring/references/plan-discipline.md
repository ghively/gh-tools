# Plan Discipline

Plan before build. Explicit approval gates keep the user in control of file
creation and side effects.

## Approval Levels

- **Thinking and reading** are free. Search, read, and analyze without
  asking.
- **Proposing** is free. Recommend a design, draft pseudocode, or sketch a
  diff in chat without asking.
- **Writing files** requires explicit approval. State what will be created
  or modified and wait for a clear yes.
- **Side effects** (deploy, publish, commit, send, delete) require explicit
  approval per action.

## Approval Recognition

Only treat the following as approval:

- "Yes", "approved", "go ahead", "do it", "build it", "ship it", or similar
  unambiguous affirmative.
- A specific yes to a specific proposal ("yes, create the AGENTS.md", not a
  generic "looks good").

Do not treat the following as approval:

- "Makes sense", "looks good", "reasonable", "ok so far", "continue
  exploring", "interesting", or other acknowledgments.
- Silence after a proposal.
- A question about the proposal.

When ambiguous, ask: "Approved to build this?"

## Failure Modes

- **Surprise files.** Files appeared without a green light. Fix: ask before
  writing.
- **Scope creep.** Approval for one file became approval for ten. Fix:
  restate scope explicitly and confirm.
- **Soft approval.** Interpreting "ok" as "yes". Fix: ask the explicit
  approval question.
- **Endless planning.** Never moving to build. Fix: when the design is
  clear, ask for approval and proceed on yes.

## In Commands and Skills

Authoring commands and skills should bake plan discipline in:

- Read-and-analyze steps proceed without asking.
- File-writing steps end with "stop and ask for approval".
- Side-effectful steps end with "wait for explicit approval".
- The template should name the approval gate, not leave it implicit.
