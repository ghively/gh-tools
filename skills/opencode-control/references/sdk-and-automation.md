# SDK, headless automation & forge CI

How to drive opencode programmatically — the `@opencode-ai/sdk`, raw HTTP from any
language, and running opencode in CI (GitHub, GitLab, other forges). Verified against
`@opencode-ai/sdk` 1.x source and live docs. This plugin's own MCP server *is* a raw-HTTP
client of exactly this API, so these patterns compose with the `oc_*` tools.

## The SDK: three entrypoints (`@opencode-ai/sdk`, JS/TS)

- **`createOpencodeServer({hostname, port, config, timeout, signal})`** — spawns
  `opencode serve` as a child process (via `cross-spawn`), so the **`opencode` binary must
  be on PATH**. Passes `config` to the child via the `OPENCODE_CONFIG_CONTENT` env var (not
  flags). Returns `{ url, close() }`. **Read `server.url`** — the requested port isn't
  guaranteed (port 0 → tries 4096 → any free port; it learns the real URL by parsing the
  "listening on …" stdout line).
- **`createOpencodeClient({baseUrl, directory, headers, fetch, responseStyle, throwOnError})`**
  — a typed client against a running server.
- **`createOpencode(options)`** — combined: starts a server + returns `{ client, server }`.

There's no embedded server — the SDK shells out to your installed CLI. For a persistent
service, run `opencode serve` yourself (systemd/container) and point `createOpencodeClient`
at it (or use this plugin's `oc_server`).

## Client method namespaces (ground truth from `sdk.gen.ts`)

`session` (list, create, get, delete, update, children, todo, init, fork, abort, share,
unshare, diff, summarize, messages, **prompt**, message, **promptAsync**, command, shell,
revert, unrevert), `event` (subscribe — SSE), `config` (get, update, providers), `provider`
(list, auth, oauth.*), `find` (text, files, symbols), `file` (list, read, status), `app`
(log, agents), `mcp` (status, add, connect, disconnect, auth.*), `tui` (appendPrompt,
submitPrompt, executeCommand, showToast, publish, control.*, …), `tool` (ids, list),
`command` (list), `project` (list, current), `path`, `vcs`, `lsp`, `formatter`, `pty`,
`instance`, `auth` (set), `global` (event), plus the loose
`postSessionIdPermissionsPermissionId(...)` for replying to a permission prompt.

`session.prompt` body: `{ parts:[TextPartInput|FilePartInput|AgentPartInput|SubtaskPartInput],
model?:{providerID,modelID}, agent?, system?, tools?, noReply?, messageID? }`.

## Event-driven automation — the correct pattern

`session.prompt()` **blocks** until the assistant turn finishes (`POST /session/{id}/message`).
`session.promptAsync()` **returns immediately** (`POST …/prompt_async`) — pair it with the
SSE event stream and wait for `session.idle`:

```js
import { createOpencode } from "@opencode-ai/sdk"
const { client, server } = await createOpencode({ config: { model: "anthropic/claude-sonnet-4-x" } })
const { data: session } = await client.session.create({ body: { title: "run" } })
await client.session.promptAsync({ path: { id: session.id },
  body: { parts: [{ type: "text", text: "Refactor foo.ts to async/await." }] } })
const events = await client.event.subscribe()
for await (const e of events.stream) {
  if (e.type === "message.part.updated" && e.properties.part.sessionID === session.id
      && e.properties.part.type === "text") process.stdout.write(e.properties.part.text ?? "")
  if (e.type === "session.error" && e.properties.sessionID === session.id) throw new Error(JSON.stringify(e.properties.error))
  if (e.type === "session.idle" && e.properties.sessionID === session.id) break
}
console.log((await client.session.messages({ path: { id: session.id } })).data)
server.close()
```

## Any language via raw HTTP (Python)

The server is plain HTTP+SSE — no JS needed. **Raw REST returns bare bodies** (the
`{data,error,request,response}` envelope is a JS-SDK-only convention — which is why this
plugin's tools read bare arrays/objects):

```python
import requests, json, sseclient        # pip install requests sseclient-py
B = "http://127.0.0.1:4096"
sid = requests.post(f"{B}/session", json={"title":"py"}).json()["id"]     # bare body, no envelope
requests.post(f"{B}/session/{sid}/prompt_async", json={"parts":[{"type":"text","text":"List repo files."}]})
for ev in sseclient.SSEClient(requests.get(f"{B}/event", stream=True, headers={"Accept":"text/event-stream"})).events():
    p = json.loads(ev.data)
    if p["type"] == "session.idle" and p["properties"].get("sessionID") == sid: break
print(requests.get(f"{B}/session/{sid}/message").json())
```

There's also an official **pre-release Stainless Python SDK**: `pip install --pre opencode-ai`
→ `from opencode_ai import Opencode; Opencode().session.list()` (you spawn `opencode serve`
yourself; no auto-spawn). Don't confuse it with the unofficial `opencode-agent-sdk` (a
different fork).

## One server, many projects

Don't run N servers for N repos. Pass `directory` per call: `createOpencodeClient({directory})`
sets `x-opencode-directory` (rewritten to `?directory=` on GET/HEAD). Server precedence:
`?directory=` → `x-opencode-directory` header → server's cwd.

## Real projects built on the SDK (patterns to steal)

- **kimaki** (Discord bot) — channels=projects, threads=sessions; queues follow-ups while a
  run is in flight; git-worktree isolation per fork.
- **portal** (mobile web UI), **OpenChamber** (web/desktop/VS Code GUI over HTTP+SSE),
  **CodeNomad** (desktop cockpit + password-authed remote server mode).
- **ai-sdk-provider-opencode-sdk** — routes Vercel AI SDK `generateText`/`streamText`
  through opencode; ideal for **model-comparison loops** (same prompt, N `provider/model`).

## Automation gotchas

- **Auth is HTTP Basic only** (`OPENCODE_SERVER_PASSWORD`, user `opencode`) — Bearer/token
  is not implemented (open issue). SSE clients that can't set headers use
  `?auth_token=<base64(user:pass)>` (same blob as `Basic`, in the query string).
- `opencode` must be on PATH for `createOpencodeServer` and for CI installs.
- Always read `server.url`; never assume the port you asked for.

---

# Forge CI — running opencode in pipelines

## GitHub (first-party, polished)

`opencode github install` sets up the **GitHub App** + workflow; the Action is
`anomalyco/opencode/github@latest`, which installs the binary and runs `opencode github run`.
Trigger on `/oc`/`/opencode` issue/PR comments (or a `schedule:` cron with a `prompt:`).
Auth defaults to **OIDC** (`permissions: id-token: write`; commits appear as the app) or set
`use_github_token: true` (needs `contents/pull-requests/issues: write`). Inline PR-review
comments pass file + line numbers + diff hunk.

## GitLab — NO first-party equivalent (verified)

There is **no `opencode gitlab` command, no `gitlab/` package, no anomalyco GitLab Action**.
Two things are often mistaken for it:
- The **`gitlab` provider** is a **model provider** (GitLab **Duo** hosted Claude models:
  `duo-chat-*`, `duo-workflow-*` via the `gitlab-ai-provider` npm pkg), NOT forge/CI
  integration. Picking `provider: gitlab` = "use Duo's models," like `anthropic`/`openai`.
- **GitLab's own Duo Agent Platform** embeds opencode as a supported CLI backend — but that's
  GitLab's product, GitLab-owned, configured via GitLab's docs, not an opencode artifact.

There *are* GitLab-engineer-authored **npm plugins** (ship separately): `opencode-gitlab-auth`
(OAuth/PAT) and `opencode-gitlab-plugin` (an **MCP server** for GitLab's REST/GraphQL —
MRs/issues/pipelines). Those enable an agentic MR reviewer, but they're auth/tool-access, not
CI orchestration. There's also a community CI/CD component, `nagyv/gitlab-opencode`.

### The DIY path (works on GitLab, Bitbucket, Gitea — anything)

`opencode run` is non-interactive; post results with the forge's CLI/API:

```yaml
# .gitlab-ci.yml
opencode-mr-review:
  image: node:22-slim
  rules: [{ if: '$CI_PIPELINE_SOURCE == "merge_request_event"' }]
  script:
    - apt-get update -qq && apt-get install -y -qq curl git jq
    - curl -fsSL https://opencode.ai/install | bash && export PATH="$HOME/.opencode/bin:$PATH"
    - export GITLAB_TOKEN="$GITLAB_TOKEN_OPENCODE"     # PAT w/ api scope — NOT CI_JOB_TOKEN
    - mkdir -p ~/.local/share/opencode
    - printf '{"anthropic":{"type":"api","key":"%s"}}' "$ANTHROPIC_API_KEY" > ~/.local/share/opencode/auth.json
    - git fetch origin "$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"
    - DIFF=$(git diff "origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME"...HEAD)
    - REVIEW=$(opencode run --model anthropic/claude-sonnet-4-x "Review this MR diff for bugs, security, and style. Bullet list, cite file:line.\n\n$DIFF")
    - glab mr note "$CI_MERGE_REQUEST_IID" --message "$REVIEW"
```

Auth gotcha: **`CI_JOB_TOKEN` generally can't post MR comments** — use a masked
Project/Personal Access Token with `api` scope. Bitbucket/Gitea/Forgejo have zero first-party
or community tooling — same `opencode run` + forge-API DIY pattern.

### Robust bot (better than one-shot per job)

Run a long-lived `opencode serve` with the `opencode-gitlab-plugin` MCP installed; a small
webhook receiver (verify `X-Gitlab-Token`) opens/continues a session per MR via the SDK,
feeds it the diff, and lets the agent post via the GitLab MCP tools or `glab`. Structurally
this is what `Schickli/agent-for-gitlab` does. See `oc_acp_prompt` / `oc_prompt` for the
headless run, and `oc_server` to manage the server.
