# Authoring OpenCode Skills

Skills are model-invoked procedural knowledge packets. Use one when the same
checklist, workflow, or reference set keeps getting pasted into chat.

## Mechanics

Verified against the OpenCode config schema
(`https://opencode.ai/config.json`) and the loader behavior in OpenCode 1.x.

- Skills live at `<skill-dir>/<name>/SKILL.md`.
- Default scan directories are `.opencode/skills/`, `.opencode/skill/`, and
  the global `~/.config/opencode/skills/` tree.
- Additional scan roots come from `skills.paths` in `opencode.json`. Each
  entry is scanned recursively for `**/SKILL.md`.
- The skill `name` is the directory's leaf name; frontmatter `name` must
  match it.
- A skill without a non-empty `description` is filtered out and never
  surfaced to the model. The description is the trigger API: front-load the
  concrete nouns and verbs the user will actually say.
- The body loads only when invoked, then stays in context. Keep `SKILL.md`
  short and link depth into `references/*.md`.

## Supported Frontmatter

| Field | Use |
|---|---|
| `name` | Required, must equal the directory leaf name, lowercase hyphen-separated, up to 64 chars |
| `description` | Required trigger text, third person, with what AND when to use |
| `license` | Optional SPDX identifier |
| `compatibility` | Optional compatibility note |
| `metadata` | Optional string-to-string map |

Any other field is rejected by stricter validators and should be avoided.

## Directory Layout

```text
skills/my-skill/
├── SKILL.md
├── references/
│   └── deep-dive.md
└── scripts/
    └── helper.py
```

Use relative links to `references/<file>.md` from the body. Link only files
that exist; dead links are a quality bug.

## Description Craft

- Third person: "Use when...", not "I help with...".
- Front-load the literal trigger words the user will say.
- Cover both what the skill does and when it fires.
- Gate with "Use ONLY when..." if it should stay quiet on adjacent topics.
- Name the sibling skill that owns the adjacent territory.

## Body Shape

```markdown
# <Skill Title>

One paragraph: the job and the mistake it prevents.

## When to Use
- bullets using the same vocabulary as the description

**Don't use for:** adjacent territory, naming the sibling skill.

## The Procedure
Numbered steps or a decision table.

## Examples
Two or three concrete input → output pairs.

## Pitfalls
The two or three mistakes people actually make.
```

## Verification

1. Frontmatter parses and `name` matches the directory.
2. Description is non-empty and trigger-focused.
3. Every relative link resolves.
4. A fresh OpenCode session loads the skill on the intended triggers and
   stays quiet on adjacent ones.
5. Restart OpenCode after changing config-time skill paths; runtime skill
   discovery does not hot reload.
