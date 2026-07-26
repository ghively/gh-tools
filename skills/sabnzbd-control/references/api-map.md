# SABnzbd API map

Verified live on SABnzbd 5.0.4 (2026-07-19). Hand-enumerated from the
official SABnzbd API wiki + live probes — SABnzbd has no OpenAPI.

## 1Password

- Vault: `Gregory`
- Item: `SABnzbd API Key` (id `vgghtwb3lj7etzjpoqdarnhtay`)
- Field: `credential` (API key)
- Read with: `op item get vgghtwb3lj7etzjpoqdarnhtay --vault Gregory --field credential --reveal`
- (No URL on the item — the URL is non-secret config: `http://192.168.0.133:8080`)

## Auth

`?apikey=<32-char hex>` query parameter on every request, plus
`output=json`. Created under Config > General > API Key. Acts with full
control.

## Conventions

- All actions are GET-or-POST `/api?mode=<name>&output=json&apikey=<key>&<params>`.
- Modes that change state accept inputs as query params.
- Server returns `{"error": "..."}` for most failures with HTTP 200 — the
  client raises an exception when it sees this.
- `{"status": true}` is the simple success acknowledgement.

## Live-verified modes (2026-07-19)

(Catalog also exposed via `sabnzbd_list_modes`.)

### Read
- `mode=version` → `{"version": "..."}`
- `mode=fullstatus` → `{"status": {...}}` (paused, speed, sessions, etc.)
- `mode=queue&limit=&start=&search=` → `{"queue": {...}}` (slots, speed, timeleft)
- `mode=history&limit=&search=` → `{"history": {...}}` (completed/failed)
- `mode=server_stats` → `{"total": ..., "month": ..., "week": ..., "day": ..., "servers": [...]}`
- `mode=warnings` → `{"warnings": [...]}`
- `mode=get_config&section=&keyword=` → `{"config": {...}}`

### Write (confirm-gated in tools)
- `mode=pause&value=<minutes>` → pause (omit value for indefinite)
- `mode=resume`
- `mode=speedlimit&value=<Kbps or %>`
- `mode=addurl&name=<url>&pp=&cat=&priority=` → returns nzo_ids
- `mode=addlocalfile&name=<path>` (server-side path)
- `mode=queue&name=delete&value=<id1,id2>&del_files=1` (delete from queue)
- `mode=history&name=delete&value=<id>` (delete from history)
- `mode=retry&value=<nzo_id>` (retry a failed job)
- `mode=set_config&section=&keyword=&value=`

### Modes that exist but NOT implemented in tools
- `mode=addfile` (multipart NZB upload — needs form-data; reachable via
  `sabnzbd_call` but the file body has to be supplied another way).
- `mode=pauseall` / `mode=resumeall` (pause/resume EVERYTHING incl.
  post-proc and scanner) — reachable via `sabnzbd_call`.
- `mode=change_opts&value=<nzo_id>&pp=` (change post-proc options on a job).

### Dangerous (double-gated)
- `mode=restart` — restart SABnzbd (kills active downloads)
- `mode=shutdown` — shut down (NO auto-restart on this homelab — DSM
  Container Manager has restart=no per the 2026-07-19 incident)

## Quirks (verified live)

- Deleting queue/history jobs is done via `mode=queue&name=delete&value=<ids>`
  or `mode=history&name=delete&value=<ids>` — the same `delete` semantics
  depend on which mode hosts it.
- `mode=pause&value=60` = pause for 60 minutes; `mode=pause` alone = indefinite.
- `toggle_pause` and `rpc_stats` are NOT implemented on SABnzbd 5.x (the
  server returns "not implemented"). Use `pause`/`resume` instead.
- `mode=options` returns non-JSON (an HTML error) on 5.x — avoid.
- `addurl` validates the URL — invalid URLs return `{"error": "expects one parameter"}`.

## Hard limits

- `shutdown` is honored literally and does NOT auto-restart on this homelab.
- `addfile` (multipart upload) is not exposed as a curated tool — use
  `addurl` (URL-based) instead.
