# Project Instructions (`AGENTS.md`)

OpenCode reads `AGENTS.md` as standing project guidance. Use it for rules
that should always be in context.

## Locations

- `AGENTS.md` at the project root is loaded automatically.
- Additional paths can be added via the `instructions` field in
  `opencode.json`:

```json
{
  "instructions": ["AGENTS.md", "docs/style.md", "docs/security.md"]
}
```

## What Belongs Here

- Toolchain and test commands (`npm test`, `pytest`, `ruff`).
- Repo conventions (branching, commit format, code style).
- Persistent guardrails (never commit secrets, run lint before push).
- Cross-cutting agent guidance that applies to every session.

## What Does NOT Belong Here

- Procedural workflows that fire on specific triggers → use a skill.
- User-invoked workflows with arguments → use a command.
- Deterministic enforcement → use a plugin hook or permission rule.

## Size Discipline

`AGENTS.md` is always in context. Keep it short and high-signal. Link out to
longer docs from `instructions` rather than inlining them.

## Versus Claude's `CLAUDE.md`

OpenCode reads `AGENTS.md`, not `CLAUDE.md`. Do not create `CLAUDE.md` in an
OpenCode project. The semantics are similar — always-loaded project guidance
— but the filename and loader differ.
