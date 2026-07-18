---
description: Full health & orientation check of the opencode install (server, ACP, config, agents, providers)
---

Run a complete health and orientation check of the user's opencode install using the
`opencode` MCP server. Report concisely.

1. `oc_status` — reachability, health, version, paths, current project, default
   model/agent, session count, configured providers. If the server is **unreachable**,
   say so and offer `oc_server(action='start')` (or `opencode serve --port 4096`).
2. `oc_acp_probe` — prove the ACP channel works (handshake only, safe): report protocol
   version, agent version, advertised capabilities, and auth methods.
3. `oc_agents` and `oc_commands` and `oc_skills` — summarize what's defined (built-in vs custom).
4. `oc_providers` — which providers are configured and how they authenticate.
5. `oc_mcp('status')` — any MCP servers opencode itself has wired up.

Then give a short verdict: what's working, anything unreachable or misconfigured, and one
or two concrete suggestions (e.g. "server not running", "plaintext API key in config",
"no small_model set"). Do not make changes — this is read-only.
