# Unraid GraphQL API conventions & quirks (this box)

Verified against **GH-Nvidia**, Unraid OS **7.3.2**, unraid-api **4.35.1+a9625ae2**.
The `unraid` MCP server implements the auth/error handling for you; this is
background for interpreting behavior and crafting `unraid_graphql` queries.

## Auth model (handled by the server)

- Every request carries an `x-api-key: <key>` header — no login step, no
  session/cookie, no CSRF token. Stateless, unlike REST-CGI NAS APIs.
- Create keys in the webGUI (Settings → Management Access → API Keys) or via
  SSH/Terminal: `unraid-api apikey add --name X --roles admin`.
- Roles: `ADMIN`, `CONNECT`, `GUEST`, `VIEWER` (`unraid_api_key_roles_catalog`
  for the full permission matrix). This plugin assumes an `ADMIN` key.
- WebSocket subscriptions authenticate the same way — `x-api-key` in the
  `connection_init` payload (confirmed working; the HTTP header alone during
  the handshake likely also works but the payload form is what's verified).

## Endpoint & transport

- Single endpoint: `http://<host>/graphql` for queries/mutations (plain HTTP
  POST, JSON body `{query, variables}`). HTTPS was not reachable on this box
  (port 443 closed) — plain HTTP only, on the LAN.
- Subscriptions use the **same path** over WebSocket with the
  `graphql-transport-ws` subprotocol (the `graphql-ws` npm package's
  protocol) — confirmed live. `unraid_subscribe_once` implements the
  connection_init → connection_ack → subscribe → next*  → complete handshake.
- Live **introspection is disabled by default** (`{"errors":[{"extensions":
  {"code":"INTROSPECTION_DISABLED"}}]}` — and the `/graphql` sandbox UI is
  separately disabled too, `SANDBOX_DISABLED`, though the API itself works
  fine over POST regardless). This plugin ships the schema offline instead
  (`references/schema.graphql`, pulled from the open-source
  github.com/unraid/api repo at the **exact tag matching this server's API
  version**, `v4.35.1`) and exposes it via `unraid_schema_search` /
  `unraid_schema_type`. Re-verify the tag against `unraid_status`'s
  `unraid_api_version` if you ever bump this plugin for a newer server.

## IDs

- Every `id` field is a `PrefixedID` scalar: an opaque string shaped
  `"<machineId>:<local-id>"`, e.g.
  `f0f72a5c...028382:WDC_WUH721818ALE6L4_4MGBR0GV`. **Always** pass back the
  exact string a query returned — never construct one by hand, and never
  assume the local part alone works.

## Error handling

GraphQL responses put failures in a top-level `errors` array (HTTP status is
usually still 200, except validation failures which come back as 400) with
`extensions.code`. The client (`UnraidError`) surfaces all of them with a
plain-English hint:

| Code | Meaning |
|------|---------|
| `UNAUTHENTICATED` | missing/invalid `x-api-key` |
| `FORBIDDEN` | the key's role(s)/permissions don't cover this field — check `unraid_me` |
| `GRAPHQL_VALIDATION_FAILED` | bad field/argument name — check `unraid_schema_type` |
| `BAD_USER_INPUT` | an argument value was rejected |
| `INTERNAL_SERVER_ERROR` | the resolver itself threw — message has the real reason (see quirks below; several of these are genuine box-side bugs, not your query being wrong) |

## GraphQL lets you batch reads for free

Unlike a REST/CGI API, one query can touch many resources in one round-trip —
prefer this over several separate `unraid_graphql` calls:
```graphql
{ array { state } docker { containers { id state } } notifications { overview { unread { total } } } }
```

## Confirmed server-side quirks / bugs (this API version)

These aren't query mistakes — they're genuine behavior on **unraid-api
4.35.1** worth knowing before you hit them:

- **`createNotification`'s returned `id` doesn't match the real file.** It
  returns a UUIDv7-suffixed id (`title_<uuid>.notify`) but the notification is
  actually persisted with a Unix-timestamp suffix (`title_<epoch>.notify`).
  Passing the returned id straight to `archiveNotification`/
  `unreadNotification`/`deleteNotification` 500s with "Could not find
  notification in unreads/archive". **`unraid_notification_create` works
  around this** by re-listing unread notifications right after creating and
  returning the real id (`id_corrected: true` in the response) — use that
  tool rather than raw `unraid_graphql` for create-then-act-on-it flows.
- **Several fields declared non-null in the schema return null for specific
  devices, crashing the whole query** (GraphQL null-propagation bubbles a
  null-violation up to the nearest nullable ancestor). Confirmed instances:
  - `Disk.bytesPerSector` (and likely the other geometry fields —
    `totalCylinders`/`totalHeads`/etc.) is null for the **USB flash boot
    device**. `unraid_disk` deliberately omits these fields.
  - `RCloneBackupSettings.drives` is null when no rclone remotes/drives are
    configured (should be `[]`). `unraid_rclone_settings` omits it.
  - `InfoPci.type` / `InfoGpu.type` are null for at least one PCI/GPU entry on
    this box. `unraid_info` omits the `devices` sub-query; use
    `unraid_graphql` with a minimal field set (e.g. just `vendorname`) if you
    need device listings.
  - **Lesson for custom `unraid_graphql` queries:** if a query on a
    `!`-typed field 500s with "Cannot return null for non-nullable field",
    it's very likely this class of bug, not a mistake in your query — retry
    with fewer/different sub-fields rather than assuming the field name is
    wrong.
- **`vars.sysCacheSlots`** 500s with "Int cannot represent non-integer value:
  NaN" on this box (no cache pool configured — the resolver likely divides by
  a zero pool count). `unraid_vars` omits it.
- **`parityHistory`** 500s with "Parity history file not found" if a parity
  check has never run (the log file doesn't exist yet) rather than returning
  `[]`. `unraid_parity_history` catches this and returns an empty list.
- **`vms`/`upsDevices` are absent-feature errors, not bugs**: `vms.domains`
  errors "VMs are not available" when the VM Manager isn't enabled, and
  `upsDevices` errors "No UPS data returned from apcaccess" when no UPS is
  connected. `unraid_vms`/`unraid_ups` catch these specific messages and
  return a friendly `available`/`connected: false` instead of an error.
- **`connect`, `cloud`, `remoteAccess`, `network` (the `Network` type with
  `accessUrls`) are absent from the live schema entirely** on this box
  (`GRAPHQL_VALIDATION_FAILED: Cannot query field`), even though they're in
  the SDL from the open-source repo. This server has **no Unraid Connect
  plugin installed** (`unraid_plugins` returns `[]`) — those resolvers only
  register when Connect is active. `servers` (plural, the local-server-list
  view) still works without Connect. See the "Hard limits" section in
  `api-map.md`.
- **This API version (4.35.1) has no `restart` mutation on `DockerMutations`**
  — only `start`/`stop` (a native `restart` field was added in a later
  release per the upstream repo's main branch). `unraid_docker_restart`
  composes stop-then-start client-side.
- **`dockerContainerStats` is Subscription-only** — there's no plain Query
  field for live container stats, and the stream emits ONE container's stats
  per event, rotating across all running containers (not scoped to an `id`
  argument — there isn't one). `unraid_docker_stats` opens a short-lived
  WebSocket subscription and filters client-side for your container's id.
  One event from this stream had a stray ANSI escape sequence (`\x1b[H`)
  embedded in the container id (apparently leaked from parsing raw `docker
  stats` terminal output server-side) — `strip_ansi()` normalizes both sides
  before comparing, so this is transparent to callers.

## Field-name gotchas (guessed-wrong during build, now fixed, listed so you
## don't repeat them in custom `unraid_graphql` calls)

- `info { memory { ... } }` only has `layout` (per-DIMM) — **not**
  `total`/`max`/`used`; those live under `metrics { memory { total used free
  percentTotal } }` instead.
- `metrics { temperature { ... } }` is `{ sensors { ... } summary { average
  hottest coolest warningCount criticalCount } }` — no `units` field, and the
  summary field is `average`, not `overall`.
- `metrics { network { ... } }` fields are `name operstate bytesReceived
  bytesSent rxSec txSec utilizationPercent` — not `interface`/
  `rxBytesPerSec`/`txBytesPerSec`.
- `UPSBattery` fields are `chargeLevel`/`estimatedRuntime`/`health` — not
  `chargePercentage`.
- `DockerContainer.ports` (and everywhere else `[ContainerPort!]!` appears)
  needs a subfield selection (`ports { privatePort publicPort type }`) — it's
  an object list, not a scalar.
