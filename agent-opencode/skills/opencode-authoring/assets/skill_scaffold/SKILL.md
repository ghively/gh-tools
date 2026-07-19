---
name: my-skill-name
description: "REPLACE — this line is the skill's API. Pattern: <what it does> + <the trigger nouns/verbs a user would actually say> + <what it does NOT cover, naming the sibling skill that does>. It is the ONLY text the model sees when deciding to load this skill."
---

# My Skill Name

One paragraph: the job this skill does and the mistake it prevents. If you
can't name the mistake it prevents, it's documentation, not a skill.

## When to Use

- The user asks to ... (use the same vocabulary as the description)
- ... (2-4 bullets)

**Don't use for:** adjacent territory, naming the skill/command that covers it.

## The Procedure

Numbered steps or a decision table — actionable, not encyclopedic. The body
must earn its context-window cost: every line should change what the model
does next.

| Situation | Do |
|---|---|
| ... | ... |

## Examples

Two or three concrete input → output pairs. These are the highest-leverage
content in the file — a good example teaches more than three paragraphs.

**Input:** "..."
**Output:** ...

## Pitfalls

- The 2-3 mistakes people actually make, each with the fix.

<!--
Authoring rules (delete this comment when done — enforced by the
skill-quality-checklist reference in claude-code-authoring):
- name matches the directory leaf name exactly, lowercase hyphenated
- description is trigger-focused and third person
- SKILL.md under 500 lines; depth goes to references/*.md
- link references like: see [deep dive](references/deep-dive.md)
- only OpenCode-supported frontmatter: name, description, license,
  compatibility, metadata
- test triggering in a fresh session: 2-3 phrases that should load it,
  1-2 that shouldn't
-->
