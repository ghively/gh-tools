# Tdarr integrations, authentication, and external hooks

How Tdarr talks to the outside world — and how the outside world talks to
Tdarr.

## Authentication (the model I previously got wrong)

Tdarr **does** have an authentication model — I incorrectly said "no auth"
in v0.1-0.2. Corrected:

### Unauthenticated mode (default)

If `auth=false` (default), the API is wide-open to anyone who can reach
port 8265/8266. **Tdarr trusts the LAN like the *arr stack.** Recommended
ONLY for isolated/home networks.

### Authenticated mode

1. Set `auth=true` env/config var on the **Tdarr Server** container.
2. A random `authSecretKey` is auto-generated on first start (you can also
   set it manually).
3. The web UI prompts you to set username + password on first visit.
4. Generate API keys via **Tools → API Keys** in the web UI.
5. Set `apiKey` env/config var on each **Node** so they can connect.
6. For this MCP plugin: set `api_key` + `api_key_header: "X-API-Key"` in
   `config.local.json`.

### Seeded API key (automation-friendly)

For automated/Docker deployments: `seededApiKey` env var auto-creates an
API key on first server start. Requirements:
- Must start with `tapi_`.
- At least 14 characters total.
- Alphanumeric + underscores only.

```bash
docker run -d \
  -e "auth=true" \
  -e "seededApiKey=tapi_my_secure_api_key_123" \
  ghcr.io/haveagitgat/tdarr
```

If the key already exists (re-deploys), it's not recreated. Safe for
re-runnable compose files.

### Securing unmapped-node traffic

If `enableUnmappedNodes=true`, Tdarr exposes library files over the network
API. **Always enable authentication when unmapped nodes are on.** Otherwise
anyone reaching port 8266 can download your library files.

## Webhooks (Discord)

Built-in Discord webhook integration. Set `notificationsDiscordWebhook` to
your Discord channel's webhook URL, then enable per-event toggles:

| Event | Field |
|---|---|
| Transcode succeeded | `notificationsTranscodeSuccess` |
| Transcode errored | `notificationsTranscodeError` |
| Transcode cancelled | `notificationsTranscodeCancelled` |
| Health check succeeded | `notificationsHealthcheckSuccess` |
| Health check errored | `notificationsHealthcheckError` |
| Health check cancelled | `notificationsHealthcheckCancelled` |
| Server started | `notificationsServerStarted` |
| Server update ready | `notificationsServerUpdateReady` |
| File entered review queue | `notificationsRequireReview` |

Plus `notificationsCustomText` prepends custom text to every notification.

**No native Slack/Pushover/Telegram/ntfy support.** For those, point a
Discord-to-X bridge at the Discord webhook, OR write a flow plugin using
the `Send Web Request` flow node (Tdarr 2.x) to hit any HTTP endpoint.

## Sonarr/Radarr/Whisparr integration: `tdarr_inform`

The community script **`tdarr_inform`** (<https://github.com/deathbybandaid/tdarr_inform>)
lets Sonarr/Radarr/Whisparr push "new file imported" / "file deleted"
events directly to Tdarr. This replaces relying on folder-watch polling.

Why use it:
- Lower disk I/O than the polling folder watcher.
- Real-time: Tdarr knows about a new file within seconds of import.
- Survives network-share folder-watch flakiness.

Install: hook it as a "Custom Script" in Sonarr/Radarr Settings → Connect.

## Alternative autoscan: `tdarr_autoscan`

**`tdarr_autoscan`** (<https://github.com/hollanbm/tdarr_autoscan>) — a
different scanner that focuses on triggering library rescans on Emby/Plex
after Tdarr finishes. Useful when the built-in `MC93_MigzPlex_Autoscan` /
`TD01_TOAD_Autoscan` plugins don't fit your trigger pattern.

## Plex/Emby/Jellyfin library-scan triggers

After Tdarr replaces a file, the media server's cached metadata is stale.
Trigger a rescan:

| Plugin | Target |
|---|---|
| `MC93_MigzPlex_Autoscan` | Plex via Autoscan |
| `TD01_TOAD_Autoscan` | Generic autoscan |
| `goof1_URL_Plex_Refresh` | Plex direct URL hit |

For Emby (which you have): there's no dedicated community plugin in the
catalog. Build a one-step flow using the `Send Web Request` flow node to
hit `POST http://emby:8096/Library/Refresh?api_key=<key>` after transcode.
Use `{{{args.userVariables.library.embyKey}}}` for the API key (per-library
variable, so it's not hardcoded in the flow).

## Heimdall / Homer dashboard integration

- **Heimdall Enhanced App:** <https://github.com/linuxserver/Heimdall-Apps/tree/master/Tdarr>
- **Homer custom service:** <https://github.com/bastienwirtz/homer/blob/main/docs/customservices.md#tdarr>

Both display Tdarr's stats directly on a dashboard tile. Useful for
at-a-glance library health.

## External API (this MCP plugin)

Tdarr's HTTP API (the 67 endpoints in `api-map.md`) is fully exposed
through this MCP server. Any external system that wants to integrate can
either:

1. Hit Tdarr's API directly (no auth on your LAN).
2. Drive Tdarr via this MCP server (gives you confirm-gating + ergonomic
   tool names + the codec/workflow knowledge base).
3. Hit the `tdarr_call` MCP tool from any MCP-aware client (Claude,
   Homelab, etc.).

## Auto-update controls

| Setting | Effect |
|---|---|
| `autoUpdateServer` | Update the Tdarr Server binary. |
| `autoUpdateServerVersion: "latest"` | Version track (`latest`, specific version, or `stable`). |
| `killAllProcessesDuringUpdate` | If true, kills active transcodes on update. If false, waits. |
| `autoUpdateNodes` | Push updates to nodes. |
| `pluginAutoUpdate` | Auto-update community plugins. |
| `pluginPinnedSha` | Pin to a specific plugin-repo commit (reproducibility). |
| `pluginCurrentSha` / `pluginLatestKnownSha` | Current vs latest commit hashes (visible state). |

For production stability on a real library, **pin `pluginPinnedSha`** once
you've verified your plugin stack works. This prevents upstream plugin
changes from silently changing transcode behavior.

## Custom plugin repo (air-gapped / fork)

`communityPluginRepo` (default `https://github.com/HaveAGitGat/Tdarr_Plugins/archive/master.zip`)
can be pointed at any zip URL matching the repo layout. Use cases:
- Air-gapped network with a mirror.
- Forked repo with custom plugins you don't want to publish.
- Frozen plugin set for production stability.

## Network topology notes

- **Tdarr Server** listens on:
  - **Port 8265** — web UI (HTTP).
  - **Port 8266** — internal server (Nodes + API).
- **Tdarr Node** makes outbound Socket.IO to server:8266. **No inbound port
  required** on the node.
- **API path:** `/api/v2/*` on port 8266 (NOT 8265).
  - ⚠️ The earlier doc-verified plugin used `:8265` because the web UI proxies
    API calls. Both work; `:8266` is canonical for direct API access.
- **UI path:** `/` on port 8265.

For Tdarr in Docker on unraid-host:
- `ports: 8265:8265, 8266:8266` exposes both.
- Nodes in separate containers connect via the docker network (`serverURL:
  http://tdarr:8266`) — confirmed live (your `kind-koi` node uses this).

## See also
- `advanced-features.md` — every other Tdarr capability.
- `library-and-nodes.md` — node + library config.
- `api-map.md` — full API reference.
