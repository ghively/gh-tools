# Skills Porting Cookbook

Recipes for porting SKILL.md content into non-OpenCode frameworks. Retained
for cross-host migrations; OpenCode consumes SKILL.md natively and does not
need a port.

## OpenCode-Native Path

For OpenCode, porting a Claude Code skill is direct:

1. Copy the skill directory into `.opencode/skills/<name>/` or
   `~/.config/opencode/skills/<name>/`.
2. Verify `name` frontmatter matches the directory leaf name.
3. Rewrite the `description` to be trigger-focused if it was vague.
4. Strip Claude-only frontmatter (`argument-hint`, `allowed-tools`,
   `disable-model-invocation`, etc.).
5. Replace Claude-specific body references (`${CLAUDE_*}`, `.claude/`,
   `claude --plugin-dir`) with OpenCode equivalents.
6. Test trigger behavior in a fresh OpenCode session.

## Cross-Host Recipes

For other frameworks (LangGraph, CrewAI, pydantic-ai-skills, Google ADK,
Mastra, Vercel AI SDK, deepagents, manual no-framework), the recipe shape
is:

1. Extract the procedural knowledge from `SKILL.md`.
2. Decide whether the target consumes it as a tool, a prompt section, or a
   retrievable document.
3. Implement the loader or adapter for that shape.
4. Port the supporting references and scripts as needed.
5. Verify trigger and content equivalence with golden tasks.

Always report fidelity gaps honestly: hard-deny hooks, prompt defense, and
tool scoping do not always have a 1:1 target equivalent.
