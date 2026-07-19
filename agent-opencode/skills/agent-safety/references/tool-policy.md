> Last verified: 2026-07. OpenCode permission-rule syntax and plugin hook semantics continue to evolve; verify the current config schema at https://opencode.ai/config.json before committing policy.

# Tool Policy

Tool policy is the enforced layer that decides what an agent can call. Prompt safety guidance is advisory; permission rules, hooks, and sandbox settings are code paths.

## OpenCode Permission Model

OpenCode uses `permission` blocks in `opencode.json` at the global level and per-agent. Each rule maps a tool (or `*` for all) to an action: `allow`, `ask`, or `deny`. Bash and several other tools accept pattern objects that are evaluated last-match-wins.

```json
{
  "permission": {
    "bash": {
      "rm -rf /": "deny",
      "rm -rf /*": "deny",
      "git push *": "ask",
      "npm run test *": "allow",
      "*": "ask"
    },
    "edit": {
      "/etc/passwd*": "deny",
      "~/.ssh/*": "deny",
      "./.env": "deny",
      "*": "ask"
    },
    "external_directory": {
      "~/secrets/**": "deny",
      "*": "ask"
    }
  }
}
```

Per-agent `permission:` blocks override the global block. Use a default-deny posture (`"*": "deny"`) with narrow allows for read-only subagents.

## Posture Ladder

| Posture | Tool Surface | Use For |
|---|---|---|
| Chat-only | Conversation and status only | Public or low-trust agents |
| Read-only | Read/search/fetch, no writes or shell mutation | Research and audit agents |
| Scoped operator | Workspace writes, test commands, selected tools | Coding agents |
| Full operator | Broad tools with approvals, hooks, sandbox, logs | Trusted single-user operational agents only |

Default to the lowest posture that can complete the job.

### Worked Per-Agent Scoping Example

Consider one project with four agents: a research assistant, a coding agent, a deploy agent, and a background worker. Each gets a different slice of the same tool surface, scoped to its role.

**Research assistant (read-only):**

```json
{
  "permissions": {
    "allow": ["Read(./**)", "Grep", "Glob", "WebFetch"],
    "deny": ["Bash", "Write", "Edit", "Read(./.env)", "Read(./secrets/**)"]
  }
}
```

No shell, no writes, no secrets. It can read the workspace and fetch public URLs.

**Coding agent (scoped operator):**

```json
{
  "permissions": {
    "allow": ["Read(./**)", "Edit(./src/**)", "Write(./src/**)", "Bash(npm run lint)", "Bash(npm run test *)", "Bash(pytest *)"],
    "ask": ["Bash(npm install *)", "Bash(git push *)"],
    "deny": ["Read(./.env)", "Read(./secrets/**)", "Bash(curl *)", "Bash(rm -rf /)"]
  }
}
```

Workspace writes and test commands are allowed; installs and pushes ask; secrets and destructive primitives are denied.

**Deploy agent (scoped operator, narrow tools, approval-heavy):**

```json
{
  "permissions": {
    "allow": ["Bash(deploy payments staging)", "Bash(healthcheck payments staging)"],
    "ask": ["Bash(deploy payments *)"],
    "deny": ["Bash(deploy * production)", "Bash(*)"]
  }
}
```

Only the two task-named commands for the staging target. Production deploys are denied outright from this agent; they go through a different, more-approved path. Generic Bash is denied so a prompt-injected shell call cannot escape.

**Background worker (fixed surface):**

```json
{
  "permissions": {
    "allow": ["Bash(process_queue)"],
    "deny": ["Bash(*)", "Write", "Edit", "Read(./.env)", "Read(./secrets/**)"]
  }
}
```

One command, no writes, no secrets, no general shell.

The pattern: the parent project does not hand every subagent the parent surface. Each agent gets the smallest posture that completes its role, and the destructive or sensitive operations are explicitly denied even from agents that might plausibly need them.

## Design Rules

- Deny beats allow in policy intent: anything sensitive should have an explicit deny rule.
- Scope file access to the workspace unless the task truly needs more.
- Put package installs, deploys, pushes, migrations, and destructive commands behind `ask` or deny.
- Do not allow generic interpreter evals such as arbitrary `python -c` or `node -e` for untrusted contexts.
- Treat browser/computer-use tools as write-capable because they can click, submit, and purchase.
- Keep MCP server tools narrow and task-named; avoid generic shell/admin tools.

## Example Project Policy

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": [
      "Bash(npm run lint)",
      "Bash(npm run test *)",
      "Bash(pytest *)"
    ],
    "ask": [
      "Bash(git push *)",
      "Bash(docker compose up *)",
      "Bash(npm install *)"
    ],
    "deny": [
      "Bash(curl *)",
      "Bash(wget *)",
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)"
    ]
  }
}
```

Pair this with deterministic hooks for never-run primitives. Permission rules handle project judgment; hooks block the floor.

## Review Questions

- Which tools can mutate state?
- Which tools can reach the network?
- Which tools can read credentials or private data?
- Which rules are shared with the team versus local-only?
- What must always ask a human?
- What must never run even if the model asks persuasively?

## Pitfalls

- Allowlisting broad shell patterns because prompts became annoying.
- Forgetting that web and browser tools can exfiltrate read data.
- Giving a subagent the parent agent's full tool surface.
- Treating MCP server installation as a data-only config change.
- Shipping project allow rules without explaining why each one is safe.
