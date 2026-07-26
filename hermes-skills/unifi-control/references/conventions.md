# UniFi API conventions & quirks (verified on this console)

## Authentication

- **Login:** `POST /api/auth/login` with JSON `{"username","password"}`. A local
  admin account is required — Ubiquiti **cloud/SSO** accounts with MFA cannot use
  the local API. Success sets a `TOKEN` cookie (a JWT) and returns the account.
- **Session:** the `TOKEN` JWT cookie carries the session; the server holds it in an
  `httpx` cookie jar. On a `401` the server re-logs-in and retries once.
- **CSRF:** the JWT's `csrfToken` claim (also echoed as the `X-Updated-Csrf-Token`
  response header) must be sent as the **`X-Csrf-Token`** request header on every
  **POST/PUT/DELETE**. Without it, writes return **HTTP 403 Forbidden** with an
  empty body. The server attaches it automatically and refreshes it from each
  response.

## URL structure

```
https://<host>/proxy/network/api/s/<site>/<family>/<resource>     # v1
https://<host>/proxy/network/v2/api/site/<site>/<resource>        # v2
https://<host>/api/<resource>                                     # UniFi OS host
```
Site is `default` on single-site consoles. UniFi OS listens on **443** (not the
self-hosted controller's 8443).

## Response envelopes

- **v1 (classic):** `{"meta": {"rc": "ok"|"error", "msg": "api.err.X"}, "data": [...]}`.
  Success → `data` is a list (the server unwraps it). Failure → `rc="error"` with a
  symbolic `msg`.
- **v2:** returns the JSON object/array directly (no `meta` wrapper). Paged
  endpoints (like `system-log/all`) return
  `{data, page_number, total_element_count, total_page_count}`.
- **host:** plain JSON.

## Error vocabulary

| Signal | Meaning |
|--------|---------|
| HTTP 403, empty body | missing/blocked CSRF token, or account lacks write permission |
| HTTP 401 | session expired / not logged in (server retries once) |
| HTTP 404 | wrong path (endpoint/method doesn't exist there) |
| `api.err.LoginRequired` | not authenticated |
| `api.err.NoSiteContext` | site doesn't exist / not in context |
| `api.err.Invalid` / `api.err.InvalidObject` | method exists, body/params rejected |
| `api.err.IdInvalid` | the `_id` in the path doesn't exist |
| `api.err.*Required` / Spring `Validation failed …` | method exists, required fields missing (v2 returns verbose Spring validation errors) |
| `api.err.NoPermission` | account lacks permission for this operation |

A `400` / `api.err.*` / validation error on a **write** means the method **exists**
and simply rejected your input — that's how you confirm a write path safely (below).

## Object CRUD (rest/*)

Each `rest/*` object is a full document keyed by `_id`.

| Action | Request |
|--------|---------|
| list | `GET rest/<name>` |
| create | `POST rest/<name>` with the full object |
| update | `PUT rest/<name>/<_id>` with the (usually full) object |
| delete | `DELETE rest/<name>/<_id>` |

**Toggling one field:** a bare `PUT {"enabled": false}` works for simple flags on
some objects, but others validate the whole document. The safe pattern is
**read-modify-write**: GET the object, change the field, PUT it back. v2 objects
(`firewall-policies`, `trafficrules`) always require the full object on PUT.

## Safe write-probing (how to check a method exists WITHOUT mutating)

- ✅ `PUT rest/<name>/<fake_id>` → `IdInvalid`/404 means the method exists.
- ✅ Read the list first; infer the shape from an existing object.
- ❌ **Do NOT `POST` an empty/partial body to a `rest/*` create endpoint.** Several
  (`rest/networkconf`, `rest/portforward`) will happily create a **junk sparse
  object** instead of rejecting it. (Learned the hard way during this build — two
  empty objects were created and then deleted to restore state.) If you must, be
  ready to `DELETE` the returned `_id` immediately.

## Parameter & value notes

- Booleans are real JSON booleans in bodies.
- MACs are lowercase, colon-separated.
- Byte counters are raw bytes; `*-r` suffix = per-second rate. Convert for humans.
- Wi-Fi `signal`/`rssi` is dBm (−50 strong … −75 weak).
- `stat/report` needs a POST body: `{"attrs": ["bytes","wan-tx_bytes",...], ...}`
  and the path encodes granularity+scope: `stat/report/hourly.site`.
- Time fields are epoch (seconds or ms depending on endpoint).

## Box-specific quirks (UDR7 / UniFi OS 4.x / Network 10.4)

- **Firewall is zone-based.** `rest/firewallrule` is empty; the real firewall is
  the v2 `firewall-policies` API (85 policies). Report from there.
- **`/api/system` is large and occasionally times out** under load. `unifi_status`
  already extracts its key fields — prefer it over calling `/api/system` directly.
- **Events moved to v2** `system-log/all` (POST, paged). The old classic
  `stat/event` returns 404 here; `list/event` needs specific params. Use
  `unifi_events`.
- **Only the Network app is installed** — Protect/Access/Talk/Connect are not
  provisioned on this console.
- Single site: `default`.
