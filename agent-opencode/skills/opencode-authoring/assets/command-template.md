---
description: REPLACE — one line, imperative, says what running this does and what comes out (shown in the command list; make it decide-able at a glance)
agent: build
---

<Do the thing> for: $ARGUMENTS

Load the `<skill-name>` skill. Process:

1. **<Gate or first step>** — <commands that can be run on the wrong target
   need a gate first: check preconditions, refuse with a pointer if unmet.>
2. **<Step>** — <numbered, imperative, each step names its output.>
3. **<Step>** — <route depth to skill references by name rather than
   restating their content here.>
4. **<Verification step>** — <how the command proves its work before
   reporting: run the thing, check the output, compare against X.>
5. **<Report step>** — <the exact shape of what the user gets back: verdict
   first, then supporting detail. If the command must NOT act without
   approval, say so here explicitly.>

<Closing constraint if any: what this command never does, and which command
covers the adjacent job.>

<!--
Authoring rules (delete this comment when done — see authoring-commands
reference in claude-code-authoring):
- 25-40 lines total; a command is a workflow contract, not an essay
- route to skills with backticked names ("Load the `x` skill")
- $ARGUMENTS appears exactly once, early
- OpenCode does not expand one command inside another; inline shared procedure
  or move it to a skill
- if it writes files, say where; if it must ask before acting, say when
-->
