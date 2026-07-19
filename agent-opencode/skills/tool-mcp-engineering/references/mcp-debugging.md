# MCP Debugging

MCP failures are easiest to debug by isolating the server from the host and testing the protocol handshake directly.

The single most useful habit: never debug an MCP server *through the agent*. The agent hides the handshake, swallows startup errors, and reports everything as "the tool failed." Reproduce the failure against the bare server over stdio first, and most mysteries collapse into a missing package, a bad env var, or a duplicate tool name.

## Workflow

1. List configured servers in the host (`claude mcp list` where available).
2. Inspect one server's command/env/config (`claude mcp get <name>` where available).
3. Run the server command directly with the same environment.
4. Use MCP Inspector or a small stdio probe to run `initialize` and `tools/list`.
5. Disable unrelated servers while isolating startup failures.
6. Re-enable one at a time and verify tool calls, not just startup.

The discipline is **isolate before you interpret**. A symptom seen through the agent ("the tool is missing" / "the call hung") has many causes; the same symptom reproduced against the bare server over stdio has one. Step 3 — running the server command directly with the identical environment — eliminates half of all bugs before you even open Inspector, because it surfaces missing packages, bad Node/Python versions, and missing env vars as plain process errors.

## Failure Taxonomy

| Symptom | Likely cause | Fix |
|---|---|---|
| Process exits immediately | Missing package, bad command, wrong Node/Python version | Run binary directly; pin/install dependency. |
| Initialize times out | Cold start, bad env, server blocked on input | Increase timeout only after direct run is clean. |
| `tools/list` hangs | Duplicate tool names, server bug, deadlock | Test with Inspector; split mounted subservers or rename tools. |
| Tool missing | Server disabled, capability mismatch, registration bug | Check list output and server logs. |
| 401/403 from tool | Credential missing/expired/wrong location | Verify server's auth pattern; do not assume env vars are read. |
| 429/timeout | Upstream unavailable or rate limited | Add backoff, reduce calls, or disable broken server. |

## Debugging Decision Tree

Match the symptom to the diagnostic, in order. Each branch ends in a concrete next step rather than a guess.

```
Server not visible to the host at all?
├─ yes -> claude mcp list shows nothing? -> check config registration + scope
└─ no
   Server process exits immediately?
   ├─ yes -> run the command directly in the same env -> missing package / bad version?
   └─ no
      initialize times out?
      ├─ yes -> direct run clean? -> server blocked on input or cold start; raise timeout only then
      └─ no
         tools/list hangs or returns fewer tools?
         ├─ yes -> duplicate tool names? -> rename; or mounted subserver deadlock -> split
         └─ no
            A specific tool call fails?
            ├─ 401/403 -> credential missing/wrong location; verify the server's auth pattern
            ├─ 429/timeout -> upstream rate-limited or down; add backoff / disable
            └─ validation error -> schema mismatch; re-check tool input contract
```

The tree enforces the ordering that matters: registration → process startup → handshake → tool listing → individual call. Jumping straight to "the tool is broken" skips the four layers that fail more often.

 |

## Auth Patterns

MCP servers differ: static API key, bearer token, OAuth client credentials, local config file, browser/device auth, or no auth for local files. Before asking a user to "log in," verify which pattern the server actually implements.

The most common auth bug is assuming the server reads the env var you set. Some servers expect the token under a specific name, some read a config file, some require an OAuth dance that runs once and caches a token. The fix is always the same: read the server's documented auth pattern, set exactly what it expects, and reproduce a single tool call in Inspector to confirm the credential works *before* blaming the model or the host.

## Inspector

MCP Inspector remains the standard interactive debugging tool for local servers. Use it to see initialization, tool schemas, resources, prompts, and call results without involving the full agent host.

The Inspector workflow that catches the most bugs: connect to the server, watch the initialize handshake succeed, open `tools/list` and confirm every expected tool appears with the right schema, then call one read-only tool and read the raw response. If any of those four steps fails, you have a precise, reproducible problem — not "the agent can't use my server." Only after all four pass should you reattach the agent.

## Health Checks

The script in `scripts/mcp-health-check.py` performs a stdio initialize + `tools/list` probe against a simple YAML/JSON server list. It is useful for cron/CI checks and for catching broken package upgrades.

Because it runs the exact protocol handshake (`initialize` → `notifications/initialized` → `tools/list`) with the `2025-11-25` protocol version, a passing health check means the server answers the same exchange a real client performs. Wire it into CI so a dependency bump that breaks startup fails the build immediately, rather than failing silently the first time an agent tries to use the tool.

## Common Mistakes

| Mistake | What goes wrong | Fix |
|---|---|---|
| Debugging through the agent | Startup errors are hidden; everything reads as "tool failed" | Reproduce against bare server over stdio first |
| Assuming the env var name | Server reads a different token name or a config file | Read the server's documented auth pattern; test one call in Inspector |
| Relative paths in client config | Host launches subprocess from a different cwd; server not found | Use absolute paths in `args` |
| Raising timeout before fixing startup | A slow cold start masks a missing dependency | Get the direct run clean, then tune timeout |
| Trusting `tools/list` alone | A broken server can still list tools while `initialize` is flaky | Run the full handshake probe, not just listing |
| Enabling all servers at once during a regression | One bad server poisons the whole session | Disable all, re-enable one at a time, verify each |

The pattern uniting these: each mistake is an attempt to reason about the server *indirectly* (through the agent, through assumed env, through a partial handshake). The fix is always to make the failure reproducible against the smallest possible surface — the bare command, then the stdio handshake, then one tool call — and only then reattach the agent.


