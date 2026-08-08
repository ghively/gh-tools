---
description: Request a game the right way — scored interactive search, review the reasoning, grab only with the user's explicit go-ahead.
argument-hint: <game title> [platform]
allowed-tools: mcp__romarr__romarr_release, mcp__romarr__romarr_platforms, mcp__romarr__romarr_release_grab, mcp__romarr__romarr_request, mcp__romarr__romarr_queue
---

Get a game into the library via ROMarr's scored path, not the quick/raw one.

1. Parse `$ARGUMENTS` for a title and (optionally) a platform. If no
   platform was given and the title is ambiguous across systems, call
   `mcp__romarr__romarr_platforms` and ask the user which one.
2. `mcp__romarr__romarr_release(game=<title>, platform=<platform>)` — the
   scored interactive search. This is read-only; always do this first
   rather than jumping straight to `romarr_request`.
3. Present the top few candidates with their score and reasoning
   (`reasons` field) — seeders, region match, size sanity, and any
   hack/beta/demo rejection. Recommend the top `accepted` one, but show the
   user what's available.
4. Ask the user to confirm which release to grab (or confirm the top pick).
5. `mcp__romarr__romarr_release_grab(release_id=<id>, confirm=true)` only
   after that explicit approval — never pass `confirm=true` on your own
   judgment.
6. `mcp__romarr__romarr_queue()` to confirm it's now in flight, and report
   back queue position / status.

If `romarr_release` finds nothing (`found: 0` or all candidates rejected),
say so plainly — do not fall back to `romarr_search` (the legacy endpoint)
without telling the user it returns a download URL with Prowlarr's API key
embedded in it (see the romarr-control skill's security note).
