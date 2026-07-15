# Gap auditing: the safe probe pattern and the three-bucket taxonomy

The gap audit is where a shallow wrapper becomes a deep integration. It's a deliberate,
domain-by-domain sweep that answers "what actually works?" for every capability — and
sorts the answers honestly.

## The safe probe pattern

You want to know whether a write method exists and its param shape **without mutating
anything**. Call it with empty or deliberately-fake params and read the error:

- **"No such method" / "API not found"** → the method (or api) genuinely isn't there.
- **"Missing/invalid parameter", "not found", permission error, or any other code** →
  the method **exists**; you just didn't give it real args. That's what you wanted to
  learn.

```python
def classify(api, method, params=None):
    try:
        data = call(api, method, params or {})
        return "READ-OK"                       # a real read succeeded
    except ApiError as e:
        if e.code in NO_METHOD_CODES: return "NO-METHOD"     # absent
        if e.code in NO_API_CODES:    return "NO-API"        # not registered
        if e.code in PERMISSION_CODES: return f"PERMISSION({e.code})"
        return f"EXISTS(err{e.code})"          # present, needs real params
```

For destructive methods (`delete`, etc.), probe with a **fake id/name** so that even if
it executed it would affect nothing (`delete(name="__audit_nonexistent__")`). Never
probe a delete with empty params if empty could mean "all".

## The three buckets

Sort every finding into exactly one:

| Bucket | Meaning | Action |
|---|---|---|
| **Works** | read verified; write method present with correct params | ship a curated tool |
| **Fixable** | reachable but off — wrong method/version, missing token, stopped dependency, wrong entity name | close it (Phase 4/5) |
| **Hard limit** | needs a license you won't buy / a permission that can't be granted / not in the API at all | document it, stop promising |

## What a real audit turned up (worked example — Synology NAS)

- **Works:** system, storage, files, downloads, packages, users/groups (read).
- **Fixable → closed:**
  - Share/network writes returned **403** → needed a password re-confirmation token
    (elevation). Implemented once in the client; then they worked.
  - Container APIs returned **102** → the Container Manager package was **stopped**;
    starting it registered them.
  - Task Scheduler / service list **103** at max version → worked at **v3**.
  - Backups returned **103** to guessed methods → the api was `.Device` not `.Task`,
    method `list` at **v1**; found by UI-traffic capture.
- **Hard limits:** VMM (needs a Pro license, not being purchased); snapshot *creation*
  (needs a package not installed). Named plainly; not wrapped in optimism.

## Presenting it

Give the user the table, most-severe first, with a one-line reason per gap and whether
it's fixable. This is the deliverable users trust — it shows you looked everywhere, and
it tells them exactly where the edges are. Then ask which fixable gaps to close; don't
assume all of them are worth the effort.
