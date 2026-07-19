# When to Build What

This file answers one narrow question: what surface should a new agent capability take?

Read the decision tree top to bottom and stop at the first "yes." Most over-engineering in this area comes from starting in the middle — assuming "I need an MCP server" before checking whether a built-in tool plus a skill already covers it. The tree is ordered cheapest-first on purpose: the earlier you stop, the less you maintain.

## Decision Tree

```
Does the built-in toolset already cover it?
├─ yes -> write instructions or a skill, not a new tool
└─ no
   Does an existing CLI/API client already do it?
   ├─ yes -> skill + CLI/script wrapper
   └─ no
      Does an existing MCP server cover it?
      ├─ yes -> connect that server
      └─ no
         Does multiple-agent/client reuse justify protocol/server work?
         ├─ yes -> build a new MCP server
         └─ no -> write a script/CLI and wrap it with a skill
```

Each question is a real filter, not a formality. "Does the built-in toolset cover it?" rules out the majority of requests — most "new tool" needs are really "teach the agent to invoke an existing tool correctly." "Does an existing CLI/API client do it?" rules out most of the rest, because wrapping a working CLI in a skill is far cheaper than building a server. Only after both are genuinely "no" does the MCP layer even enter consideration.

## Surfaces

| Surface | Build when | Avoid when |
|---|---|---|
| Built-in tools | Existing read/write/search/shell/web tools are enough | You need reusable task knowledge. |
| Skill with scripts | Logic is small, deterministic, and local to this agent/plugin | Multiple MCP clients need it. |
| Existing MCP server | A maintained server already covers the service | Server is unaudited or overprivileged. |
| New MCP server | You need typed tools reusable across clients | One local agent could call a script. |
| Full plugin | You need commands, skills, hooks, agents, and assets together | It is just one capability. |

### Escalation cost

Each rung up the ladder costs more to build and, crucially, more to *maintain*. A skill is a markdown file plus optional scripts — cheap to fix. An MCP server is a running process with a schema, auth, and a protocol version to track — every consumer depends on its stability. A plugin is the heaviest: it bundles multiple surface types and ships as a unit. That maintenance cost is the real reason to start low and escalate only when forced, not when a higher surface sounds more impressive.

## Anti-Pattern Router

- "I need an MCP server" often means "I need the agent to call this existing CLI with good instructions."
- "I need one tool per API endpoint" often means "I need task-level tools over an API."
- "I need a new integration" often means "I need to connect an existing maintained MCP server."
- "I need a plugin" often means "I need a skill plus a script."

Pick the lowest surface that gives the model the right affordance and the operator the right audit boundary.

Each anti-pattern is a request stated at the wrong layer. When you hear "I need an MCP server," translate it back down the tree: *what is the agent trying to do, and is there already a tool or CLI for it?* More than half the time the answer collapses two or three rungs. The remaining cases that genuinely need a server are the ones where multiple clients reuse the same typed capability, or where no existing tool/CLI/server exists at all — those are the only requests that survive the translation intact.

## Worked Cases

Each case walks the decision tree to its lowest viable surface.

| # | Need | Walks to | Surface |
|---|---|---|---|
| 1 | Agent must run `pytest -x --lf` on a branch | Built-in shell covers it; just needs the right invocation | Skill (instructions) |
| 2 | Deterministic CSV → JSON transform the model botches | Logic is local and deterministic | Skill + script |
| 3 | Agent must read from a tracker with no current tool | A maintained MCP server already exists | Existing MCP server (audit first) |
| 4 | Three different MCP clients all need the same typed tool | Cross-client reuse justifies the work | New MCP server |
| 5 | One local agent needs a niche internal API | Single client, no reuse | Script-backed skill |
| 6 | Ship skills + hooks + agents + assets together | Multiple surface types must co-ship | Full plugin |

The pattern across all six: each need has a lowest surface that fully satisfies it, and escalating past it adds maintenance burden without adding capability. Case 4 is the only one that genuinely earns a new MCP server — and only because three clients will reuse it. If only one client needed it, it would collapse to case 5 (a script-backed skill).

## Cost by Surface

A rough sense of what each surface costs to build and to keep running, ordered cheapest to heaviest:

| Surface | Build cost | Maintenance cost | Failure surface |
|---|---|---|---|
| Skill (instructions) | Very low — markdown | Very low | Instruction quality |
| Skill + script | Low — markdown + a script | Low — keep script correct | Script logic |
| Existing MCP server | Low to connect, but audit cost is real | Track upstream releases | Upstream changes |
| New MCP server | High — schema, auth, transport, tests | High — protocol version + consumers depend on you | Startup, handshake, auth |
| Full plugin | Highest — multiple surface types co-shipped | Highest — version the whole bundle | Any component can break |

The asymmetry that matters: build cost is paid once, maintenance cost is paid forever. A surface that is cheap to build but expensive to maintain (an ad-hoc MCP server with one consumer) is a worse deal than a surface that is slightly more work now but trivial to maintain (a script-backed skill). When two surfaces could solve a need, pick the one with the lower maintenance column, not the lower build column.



