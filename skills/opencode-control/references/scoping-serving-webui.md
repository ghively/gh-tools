# Tool-scoping, agent modes, the persistent web server & web-UI routing

Operationally verified on opencode **1.x** (2026-07-17) while building a
multi-agent fleet with per-plugin MCP servers. These are the sharp edges.

## Restrict an agent's tools (scope it to one MCP server)

opencode tool ids are **`<mcpServerName>_<toolName>`** — so an MCP server named
`romm` exposing a `romm_status` tool appears as **`romm_romm_status`** (yes, the
prefix doubles when the tool is already server-named). To scope an agent to only its
own server's tools, disable the *other* servers with **wildcards**:

Legacy `tools` map (still works; removes the tools from the agent entirely):
```yaml
---
description: "..."
mode: all
tools:
  emby_*: false
  unifi_*: false
  searxng_*: false
---
```
Modern `permission` map (recommended; deny still lets the tool exist but blocks it):
```yaml
permission:
  romm_*: allow
  "*_*": deny        # or list the other servers explicitly
```
Wildcards match tool-id prefixes. Built-in tools (`bash`, `read`, `edit`, …) are
unaffected unless you name them. **Why it matters:** without scoping, every agent
sees *all* configured MCP servers' tools and will happily call the wrong one — and a
smaller model then throws "Model tried to call unavailable tool …".

## Agent modes & the `--agent` fallback (gotcha)

`mode:` is `primary` | `subagent` | `all`.
- **`opencode run --agent X` only works if X is `primary` or `all`.** If X is a
  `subagent`, opencode prints *"agent X is a subagent … Falling back to default
  agent"* and runs the **default** agent instead — which will have *its* tools, not
  X's. This silently masquerades and is a common "why is it using the wrong tools"
  cause.
- For a fleet where you both delegate to specialists (via the `task` tool) **and**
  invoke them directly, make specialists **`mode: all`**.
- A pure orchestrator that should only delegate: give it `mode: primary` and disable
  *all* MCP tools (`tools: {"*_*": false}`) so it can't call systems directly — it
  routes via `task` subagent delegations (which can run in parallel when the model
  batches them).

## Persistent web server (`opencode serve` / `opencode web`)

- **`opencode serve`** starts the HTTP API **and serves the web UI** at `/`
  (`opencode web` = serve + open a browser). Flags: `--port`, `--hostname`
  (default `127.0.0.1`), `--mdns`, `--cors`. There is **no `--dir`** — it roots at
  the process CWD, so run it from the project dir (e.g. a systemd `WorkingDirectory`).
- **Auth:** set `OPENCODE_SERVER_PASSWORD` → HTTP Basic, **username `opencode`**.
  Without it the server logs *"server is unsecured"* and is open. The Basic
  credentials also cover the `/event` SSE stream and the web UI's XHR.
- Persist it with a systemd unit (`ExecStart=opencode serve --port … --hostname …`,
  `EnvironmentFile` for the password, `WorkingDirectory` = project). Cap memory if
  the host is OOM-prone; all configured MCP servers start with it.

## Web-UI project routing (the "can't create a session / no project to add" trap)

The web UI is a SPA. Verified behavior:
- It **lands on the `global` project** (worktree `/`), whose directory list is empty
  → you see "add project" with **nothing to add**, and can't start.
- The server *does* know your real projects (`GET /project`), keyed by git worktree.
- Client routes: `/`, **`/:dir`**, `/:dir/session/:id`, `/new-session`. The `:dir`
  param is the **absolute path with `/` replaced by `_`** (decoded back via
  `replace(/_/g,"/")`). So to deep-link a project directly, open:
  ```
  http://<host>:<port>/_home_user_projects_myapp      # = /home/user/projects/myapp
  ```
  This bypasses the empty landing and opens straight into that project's agents.
  (The remote "select folder" browser uses `GET /project/{id}/directories`, which is
  empty for `global` — hence the dead end.)

## GLM tool-call reliability (zai-coding-plan)

Some GLM models (seen on **glm-4.7**) intermittently **leak their native tool-call
tags into the tool name** — e.g. it emits `romm_romm_platforms</arg_value>`, and
opencode rejects it as an unavailable tool. It's a model-format quirk, not your
config; the same agent usually succeeds on the next call. For tool-heavy agents,
prefer a model that emits clean tool calls (glm-5.x was more reliable in testing),
or keep the fast model and tolerate the occasional retry.
