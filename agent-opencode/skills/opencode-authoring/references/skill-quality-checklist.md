# Skill Quality Checklist

Run this against every new or changed OpenCode skill before reporting done.
Each item has a concrete pass/fail test.

## Frontmatter

- [ ] `name` present, matches the directory leaf name, lowercase hyphenated,
  ≤ 64 chars.
- [ ] `description` present, non-empty, third person, trigger-focused.
- [ ] No unsupported frontmatter fields. Allowed: `name`, `description`,
  `license`, `compatibility`, `metadata`.
- [ ] YAML parses cleanly between `---` fences.

## Body

- [ ] Opens with a one-paragraph job statement.
- [ ] `## When to Use` section with concrete trigger phrases.
- [ ] `**Don't use for:**` line naming the sibling skill that owns adjacent
  territory.
- [ ] Procedure as numbered steps or a decision table, not prose paragraphs.
- [ ] At least two concrete input → output examples.
- [ ] A `## Pitfalls` section with the actual mistakes people make.
- [ ] Body under ~500 lines; depth linked out to `references/`.

## References and Assets

- [ ] Every relative link resolves to a real file inside the skill tree.
- [ ] Every referenced asset or script exists.
- [ ] No links escape the skill tree to non-installed paths.

## Triggers

- [ ] The trigger phrases a user would say appear in the description.
- [ ] At least two phrases that SHOULD load the skill tested in a fresh
  session.
- [ ] At least one phrase that should NOT load the skill tested in a fresh
  session.

## Portability

- [ ] No hardcoded user paths, hostnames, or owner names.
- [ ] No Claude-specific variables (`${CLAUDE_*}`) or paths (`.claude/`).
- [ ] No Claude-only frontmatter (`argument-hint`, `disable-model-invocation`,
  `allowed-tools`, etc.).

## Verification

- [ ] A fresh OpenCode session loads the skill on the intended triggers.
- [ ] Restart performed if config-time paths changed.
- [ ] Report state explicitly: which items passed, which were deferred with a
  reason.
