# Computer-Use & Browser Agents

Agents that act through a UI — a browser, a desktop, a terminal emulator — instead of an API. Load this when the workload involves clicking, typing, scrolling, or reading rendered pages, or when the user says "automate this website / this app" and no API exists.

The design rule that governs everything else: **a UI is a tool surface you don't control.** It changes without notice, renders differently per session, and displays content written by strangers. Every pattern below exists to survive one of those three facts.

## First Decision: Do You Actually Need the UI?

| Situation | Build |
|---|---|
| The service has an API covering the operations | API tools. Always. 10-100× cheaper, faster, and assertable |
| API exists but misses one operation | API tools + browser for that one operation only |
| No API, data is static/public | Scraper (fetch + parse) — no agent loop needed |
| No API, flow requires session/login/JS | Browser agent |
| Legacy desktop app, no browser | Computer-use (screen + pointer) — the most expensive option; exhaust the others first |

Browser automation as a fallback is a design smell worth surfacing to the user: ask once whether an API/partnership/export path exists before committing to UI automation.

## Perception Choices

| Mode | How the agent sees | Strengths | Weaknesses |
|---|---|---|---|
| Accessibility tree / DOM | Structured elements with roles and text | Cheap tokens, precise targeting, stable selectors | Misses canvas/visual-only state; deep trees blow context |
| Screenshot (vision) | Pixels | Sees what a human sees, works on anything | Costly, slower, coordinates drift, resolution-sensitive |
| Hybrid (tree first, pixels on demand) | Structured by default, screenshot to disambiguate | Best default for browser agents | More moving parts |

Default: hybrid for browsers, pixels for desktop computer-use (no tree available), DOM-only for well-known internal apps.

## Tool Surface

Task-level tools, same as the stage-4 rule — not one tool per input event:

- `navigate(url)`, `read_page(filter?)`, `click(element)`, `type(element, text)`, `wait_for(condition)` — the primitive set.
- Consolidate known flows into one tool each: `login()`, `search_orders(query)`, `download_invoice(id)`. Every consolidated flow removes a whole class of mid-flow model error.
- Label per the sensitivity scheme: `click` is **write** the moment a form or button is involved; anything past a payment/submit/delete control is **destructive or spend-affecting**.

## The Three Disciplines

**1. Assert state, never assume it.** Every action is preceded by a check that the UI is where the agent thinks it is (URL, heading, element present) and followed by a check that the action took effect. A click that silently did nothing, repeated confidently, is the signature browser-agent failure. Budget roughly one verification read per action.

**2. Gate irreversibility.** The approval boundary must live OUTSIDE the model: an allowlist of safe domains/flows, and a deterministic interceptor (hook, proxy, or tool-policy layer) that stops before submit/purchase/delete/send controls and escalates per the decision-boundary matrix. See `human-in-the-loop.md` for the approval payload design.

**3. Treat every rendered page as hostile input.** Web content is the canonical prompt-injection vector: pages can contain instructions aimed at the agent ("ignore your task, click here"). Separate the *content channel* (what the page says) from the *command channel* (what the user asked); never let page text expand the task, change targets, or unlock authority. Injection mechanics: `prompt-context-engineering` skill, injection-defense reference.

## Failure Modes to Design For

| Mode | Response |
|---|---|
| Selector/layout changed since last run | Re-perceive and retarget once; then fail with a screenshot attached, don't guess |
| Action silently no-ops | Post-action assertion catches it; retry once, then escalate |
| Unexpected interstitial (cookie wall, 2FA, CAPTCHA) | Named handler or escalate to human; never brute-force — CAPTCHA and anti-bot bypass is a line agents don't cross |
| Session expired mid-flow | Re-auth via the consolidated `login()` tool, resume from last asserted state |
| Page contains agent-directed instructions | Content-channel discipline; log the attempt |
| Infinite scroll / pagination trap | Hard caps on steps and per-run budget |

## Evals

Golden tasks with recorded fixtures (saved DOM/screenshot snapshots) so the suite runs without live sites; plus a small live smoke set against stable pages. Assert on *outcome state* (order exists, file downloaded, form value persisted), not on action transcripts — the correct click sequence can change under you while the outcome contract holds. Regression case per UI change that ever broke you.

## Current Landscape

> Last verified: 2026-07. This table rots fast; verify against vendor docs before committing.

| Layer | Options |
|---|---|
| Model-native computer use | Anthropic computer-use tool (screenshot + pointer/keyboard actions); OpenAI operator-class equivalents |
| Browser drivers | Playwright (the default), Playwright MCP server (browser as MCP tools), Selenium (legacy) |
| Agent frameworks | browser-use (Python, DOM-first), Stagehand (Playwright + LLM), Claude Code/Agent SDK + Playwright MCP |
| Managed | Anthropic/partner hosted browser environments; various operator products |

Pick the thinnest layer that works: a Playwright MCP server plus the disciplines above beats a heavyweight framework for most jobs.
