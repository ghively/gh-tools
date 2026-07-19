# Multi-Agent Routing

Multi-agent routing decides which agent, persona, role, or workspace should handle an incoming task. Routing should be deterministic enough to explain and restrictive enough to preserve isolation.

## When to Add Another Agent

Add another agent only when there is a durable difference in role, authority, workspace, memory, user group, model, or tool policy. Do not add agents just because a prompt could be phrased as a persona.

### Good vs bad reasons to add an agent

| Add an agent when... | Do not add an agent when... |
|---|---|
| A regulated dataset needs read-only access only | You want a friendlier tone |
| A destructive operation needs a gated path | You want a "persona" for flavor |
| A different team owns a workspace boundary | The task is just a different prompt for the same role |
| A cheap model can handle 90% of inbound traffic | You want parallelism for one tiny task |
| Untrusted external content needs an isolated worker | A skill or instruction set would cover it |

The test is durable difference, not narrative convenience. If two "agents" share workspace, tools, credentials, model, and authority, they are one agent with two prompts — and routing between them adds complexity for no isolation benefit.

## Routing Inputs

| Signal | Example use |
|---|---|
| User or tenant | Separate customer/team context. |
| Channel or surface | Chat support vs code review vs background job. |
| Task type | Research, implementation, QA, security, operations. |
| Risk | Read-only analysis vs destructive action. |
| Data boundary | Workspace, repository, project, or regulated dataset. |
| Model need | Cheap chat vs frontier review. |

## Precedence Rules

Document precedence explicitly. A typical order is exact task override, risk boundary, data/workspace boundary, user/team boundary, channel/surface, then default agent. If two rules match at the same tier, first configured or most specific wins; make that rule visible.

### Worked Conflict Resolution

Consider an inbound task: "delete the staging rows for customer Acme." Multiple signals fire:

| Signal | Matched value | Implied agent |
|---|---|---|
| Risk | destructive | ops (gated) |
| Data boundary | `staging` dataset | ops-staging |
| User/team | Acme → team B | team-B agent |
| Task type | row deletion | ops |

Applying precedence: risk (destructive) outranks user/team, so the task routes to **ops (gated)**, not the team-B agent — even though team B "owns" Acme. The destructive signal forces the gated path with preview and approval. Recording this decision in routing logs ("routed to ops: destructive override of team-B match") makes the precedence auditable instead of mysterious.

If precedence is implicit, two operators will disagree about why a task landed somewhere, and the destructive path will silently drift to a less-guarded agent. Write the order down; make every override visible.

## Isolation

Agents with different risk profiles should not share unrestricted tools, credentials, or scratch memory. Shared durable memory must record provenance. Per-agent workspaces reduce accidental cross-contamination.

Isolation has three layers, each independently enforceable:

| Layer | What it isolates | Typical mechanism |
|---|---|---|
| Workspace | Files, repos, datasets the agent can read/write | Per-agent working directory or scoped path allowlist |
| Credentials | API keys, tokens, cloud roles | Per-agent secret scope; never one shared god-token |
| Memory / scratch | Conversation, board, intermediate state | Per-agent scratch with provenance on any shared record |

Shared durable memory is acceptable only when every record carries provenance (which agent wrote it, when, from what source). Without provenance, cross-contamination is silent: agent B acts on agent A's stale scratch and neither knows it was not fresh.

## Claude Code Equivalents

Claude Code has explicit subagent definitions and task invocation, but not every gateway-style inbound routing feature exists in every host. Use concrete Claude Code mechanisms where available: `agents/*.md` for role definitions, skills for reusable workflows, hooks for deterministic gates, and MCP/tool permissions for capability boundaries.

Mapping routing concepts onto Claude Code surfaces:

| Routing concept | Claude Code surface |
|---|---|
| Role / persona definition | `agents/*.md` |
| Reusable workflow | Skill |
| Deterministic gate (e.g. block destructive) | Hook |
| Capability boundary (read-only vs write) | MCP / tool permissions |
| Workspace boundary | Working directory + path scoping |

Where a gateway-style feature (tenant-aware inbound dispatch, multi-channel fan-in) does not exist natively in a host, do not fake it inside agent prompts — put that routing in the layer that actually sees the inbound request (a gateway, a queue consumer, or the host's own dispatch), and let the agent layer stay focused on the task it receives.

## Anti-Patterns

- Splitting one coherent job across agents with no verifier.
- Giving all agents identical tool policies.
- Routing by vague persona labels instead of task/risk/data boundaries.
- Sharing memory without provenance.
- Letting a worker spawn more workers when the architecture says it is a leaf.

## Routing Config Sketch (pseudocode, illustrative)

```
routes:
  - match: { task: "deploy", risk: "destructive" }
    agent: ops-gated
    precedence: 2                      # risk boundary
    note: "destructive always gates, overrides team match"
  - match: { dataset: "regulated-*" }
    agent: compliance-read-only
    precedence: 3                      # data boundary
  - match: { team: "*" }
    agent: team-default
    precedence: 4
  - default: general-assistant
```

Every rule carries an explicit precedence number and a human-readable note. When a request matches several rules, the lowest precedence number wins, and the chosen rule's note is logged so operators can explain any routing decision after the fact.

