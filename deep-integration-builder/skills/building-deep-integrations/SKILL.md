---
name: building-deep-integrations
description: >-
  Methodology for building a comprehensive, deeply-tested control integration for
  any system that exposes an API — an MCP server plus a skill and workflow commands,
  packaged as a Claude Code plugin. Use this whenever the user wants to "fully
  control", "cover everything", or build a plugin / MCP server / integration for a
  device, appliance, SaaS, or service (NAS, router, home-automation hub, cloud
  console, ticketing system, database, etc.), and depth/completeness matters — not a
  thin wrapper around two endpoints. Trigger it even when the user just says "build
  me a plugin to manage X" or "make an MCP for Y": this sets the approach BEFORE any
  code, so invoke it first, then carry out its phases. It also applies when expanding
  an existing integration to close coverage gaps.
---

# Building deep integrations

A repeatable workflow for going from "control this system" to a genuinely complete,
honestly-scoped integration. It was distilled from building a plugin that reached all
~870 APIs of a Synology NAS — including reverse-engineering undocumented backup APIs.
Follow the phases in order; each de-risks the next.

## The one idea that creates the depth

**"Covered" means the operation actually works for the user — not that an API exists
for it.** A generic passthrough can *address* every endpoint, but real coverage needs
four things to line up: the **right method name**, the **right params**, the
**dependency running**, and **permission granted**. Every gap you'll hit is a failure
of one of these. Say "reaches the API" when that's what you mean, and reserve
"covered" for verified-working. This honesty is the whole game — it's what turns a
demo into something trustworthy.

## Phase 0 — Connect and prove the conventions (before ANY building)

Do not write a client until you've made real calls against the real system.

1. **Get reachability + credentials.** Confirm you can reach the host; keep secrets
   out of anything that will be committed (a git-ignored local config / env vars).
2. **Enumerate the whole surface from the system itself.** Most systems can tell you
   what they expose (an API-info/discovery endpoint, an OpenAPI/Swagger doc, a
   `/help`, a introspection query, a `--list` command). Pull the full list — it is
   your master checklist for "everything." Count and categorize it.
3. **Prove the call conventions with live calls:** auth/login, the session/token
   model (cookies, bearer, CSRF tokens), how params are encoded, one read, and note
   the error-code vocabulary. Capture the quirks now; they shape the client.

Only now do you understand the system well enough to design.

## Phase 1 — Two-layer architecture

Build both layers. They cover different needs:

- **Generic passthrough** — one tool that can call *any* endpoint (`call(api, method,
  params)`), plus discovery/search tools. This is how "everything" becomes true
  rather than aspirational, and it's your escape hatch for the long tail.
- **Curated tools** — ergonomic, single-purpose tools for the common jobs (health,
  the primary resources, the frequent actions). These make day-to-day use one clean
  call and encode the correct params/versions you discovered.

Package it as a plugin: an MCP server launched reproducibly (e.g. `uv run --script`
with inline deps so it self-provisions), a control **skill** teaching the model how to
drive it, and **slash-command workflows** for multi-step jobs. See
`references/plugin-scaffold.md` for the concrete structure.

## Phase 2 — Build iteratively, verify each tool against the live system

- Bring up the client and hit `status`/identity first.
- Add curated tools in small batches; **run each against the real system** and fix the
  params/version from the actual response. Do not trust a tool you haven't seen return
  real data.
- Prefer **reads** while building. For writes, verify the method *exists* and its
  param shape via safe probing (empty/fake params → distinguish "no such method" from
  "method exists, needs params") without mutating anything.

## Phase 3 — Systematic gap audit (this is where depth comes from)

After the obvious tools work, deliberately hunt for what's missing. For every major
domain, ask: does the **read** work, and do the key **write** methods exist? Probe them
safely and record the result. Then sort every finding into three honest buckets:

- **Works** — verified read (and write method present with right params).
- **Fixable** — the capability is reachable but something's off: wrong method name,
  wrong version, missing a token, or a stopped dependency. These are closeable.
- **Hard limit** — needs a license you won't buy, a permission that can't be granted,
  or simply isn't in the API (CLI/SSH-only). Name it plainly and stop over-promising.

Present this taxonomy to the user. It's more valuable than a green checkmark, and it's
what earns trust. See `references/gap-taxonomy.md` for a worked audit and the safe
probe pattern.

## Phase 4 — Close the fixable gaps

Work the "fixable" bucket. The recurring causes (check every one — this is a
**gotcha checklist**, not trivia):

- **Version-specific methods.** A `list`/`get` may exist at v1/v3 but NOT the API's max
  version. If a method 103s at max version, try lower versions before concluding it's
  absent. (Bit us repeatedly.)
- **CSRF / elevation tokens.** Sensitive writes may 403 until you attach a token — a
  CSRF token from login, or a re-confirmation token from a "confirm your password"
  endpoint. Fetch it and attach it; implement it once in the client.
- **Dependency-gated APIs.** A package/app's APIs may only register while it is
  *running*. If calls 102 ("not registered"), check whether the owning service is
  stopped and start it.
- **Hidden APIs.** Some endpoints don't appear in the global discovery list; query them
  by name directly.
- **Wrong entity name.** The list you want may live under a differently-named API than
  you'd guess (e.g. backups under `.Device`, not `.Task`).

## Phase 5 — Reverse-engineer the undocumented parts from real UI traffic

When an API is registered but no guessed method works, stop guessing and watch the
system's own UI make the call. This cracked the "impossible" backup APIs. The pattern:
open the vendor's web UI, inject a network interceptor, click the feature, read the
exact `api`/`method`/`version`/`params`, then replay from your client to confirm. Full
technique (including the XHR-interceptor snippet) is in
`references/reverse-engineering.md`.

## Phase 6 — Safety and honest verification

- **Confirm-gate destructive/disruptive writes** in code (`confirm=True`) and instruct
  the skill to confirm with the user before any write.
- **Never run live writes autonomously to "self-test."** Verify writes with the user's
  explicit go-ahead, and prefer **reversible** proofs — create a throwaway resource,
  confirm it appears, delete it, confirm the system is back to its original state.
- **Report faithfully.** If something wasn't verified, say so. Distinguish "built +
  method-verified" from "live-executed." Surface real findings you notice along the way
  (a full disk, a stopped service, a disabled firewall) — that observed truth is part
  of the value.

## Phase 7 — Publish to gh-tools (always)

Every finished integration is published to **`ghively/gh-tools`** — the standing home
for control-integration plugins (synology-nas, gitlab, emby, unifi, comfyui-control
live there). Do not put integrations in other repos or leave them local-only.

1. Working clone: `~/projects/gh-tools` (if absent: `gh repo clone ghively/gh-tools
   ~/projects/gh-tools`; set `git config user.email/user.name` on fresh clones — SSH
   remotes may lack agent keys, `gh` auth always works).
2. Plugin goes in its **own subdirectory** (`./<plugin-name>/`) with the scaffold from
   `references/plugin-scaffold.md`. Never commit `config.local.json` (gitignore it).
3. Append an entry to `.claude-plugin/marketplace.json` (`source: "./<plugin-name>"`,
   honest description noting what was live-verified).
4. Commit (conventional style) + push to main.
5. Make it installable NOW: `git -C ~/.claude/plugins/marketplaces/gh-tools pull`,
   then copy the local `config.local.json` into that clone's plugin dir (it is
   git-ignored, so it never arrives on its own — without this step the installed
   MCP server starts with defaults and host-side tools error).
6. Tell the user: `/plugin install <plugin-name>@gh-tools` → `/reload-plugins`.

Updating an existing integration = same flow: edit in `~/projects/gh-tools/<plugin>`,
bump the version in `.claude-plugin/plugin.json` AND the marketplace entry, commit,
push, pull the marketplace clone.

## Definition of done

You've reached the depth when: the full surface is enumerated and categorized; the
common jobs have verified curated tools; the generic layer reaches the rest; every
domain has been gap-audited into Works / Fixable / Hard-limit; the fixable gaps are
closed (or explicitly deferred with the reason); writes are confirm-gated and their
paths proven reversibly; the plugin is **published to ghively/gh-tools** (Phase 7)
and installable; and the user has an honest map of exactly what works and what
doesn't — no hand-waving.
