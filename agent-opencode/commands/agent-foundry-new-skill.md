---
description: Author an OpenCode skill with trigger-focused frontmatter, concise procedures, linked references, and quality checks.
agent: build
---

Create an OpenCode skill for `$ARGUMENTS`. Load `opencode-authoring` only for
the portable surface-selection and quality principles. Check collisions, draft
the trigger description, and create `.opencode/skills/<name>/SKILL.md` or the
global `~/.config/opencode/skills/<name>/SKILL.md`. Use only OpenCode-supported
frontmatter: `name`, `description`, and optional `license`, `compatibility`, or
`metadata`. Keep the body concise, link references, test discovery in a fresh
session, and do not use Claude plugin variables.
