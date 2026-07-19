# Domain Patterns: Support, RPA, Research

Three common agent domains that benefit from explicit patterns: customer
support, robotic process automation (RPA), and deep research. The
agent-foundry doctrine transfers; the shape of tools, authority, and
evals differs.

## Customer Support

### Shape

| Aspect | Pattern |
|---|---|
| **Job** | Triage incoming tickets; classify; route; draft responses; escalate ambiguity |
| **Trigger** | Webhook on ticket creation OR polling the ticketing system |
| **Tools** | Ticket system API (read + comment + label); user DB lookup; product docs RAG; escalation queue |
| **Authority** | `comment-only` by default: comment with draft, label, never close, never modify the user account |
| **Authority escalation** | Hand off to human agent when confidence is low, sentiment is high, or the request is out of scope |
| **Memory** | Per-user conversation history; product-team playbook; FAQ corpus |
| **Eval categories** | Governance (don't close tickets, don't leak other users' data); capability (each tool works); behavioral (empathy tone, escalation timing); regression (per past mistake) |

### Tool Surface (Typical)

- `search_tickets` — find related tickets and resolutions
- `get_user_history` — read the user's prior interactions
- `search_docs` — RAG over product documentation
- `comment_draft` — post a draft response for human review
- `label` — apply a routing label
- `escalate_to_human` — hand off to a queue

### Authority Floor

- Never close a ticket.
- Never modify the user account (refund, password reset, account
  deletion — all escalate).
- Never quote one user's data in another user's ticket.
- Never promise SLAs or compensation.

These belong in the permission rules, not the prompt. The prompt
guides; the permission rules enforce.

### Eval Emphasis

Behavioral evals dominate: tone, empathy, escalation timing,
de-escalation of hostile input. LLM-as-judge is well-suited but
calibrate against human-labeled gold; "empathy" drifts without it.

### Common Pitfalls

1. **Closing tickets to clear the queue.** The agent learns to close
   to reduce backlog. Fix: `comment-only` authority.
2. **Promising compensation.** The agent offers a refund to defuse.
   Fix: explicit deny on compensation actions.
3. **Quoting other users' PII.** RAG surfaces a related ticket with
   someone else's data. Fix: per-user filtering at retrieval time.
4. **Tone-deaf responses to hostile input.** Fix: behavioral evals
   with hostile-user fixtures.

### Framework Fit

- **Copilot cloud agent** if the support system lives in GitHub
  (rare).
- **LangGraph** for the routing + HITL gate shape.
- **Pydantic AI** for typed ticket schemas.

## Robotic Process Automation (RPA)

### Shape

| Aspect | Pattern |
|---|---|
| **Job** | Replace deterministic human clicks across N systems with an LLM-driven workflow that handles the messy 5% |
| **Trigger** | Schedule, queue, or event |
| **Tools** | UI automation (Playwright, Selenium); API clients; legacy system connectors; OCR for scanned docs |
| **Authority** | `scoped-operator` per process: exact operations on exact systems, nothing else |
| **Authority escalation** | HITL when the LLM hits the messy 5% — unrecognized field, ambiguous doc, system error |
| **Memory** | Process state; idempotency keys per record |
| **Eval categories** | Governance (never operate outside the scoped system); capability (each step); behavioral (idempotency, recovery); regression (per past workflow break) |

### Tool Surface (Typical)

- `navigate(system, page)` — UI automation
- `read_field(page, selector)` — extract data from a UI
- `fill_field(page, selector, value)` — write data
- `click(page, selector)` — action
- `call_api(system, endpoint, payload)` — API alternative
- `ocr(document)` — extract text from a scan
- `human_approval(action)` — HITL gate

### Authority Floor

- Operate ONLY on the scoped system (allowlist of URLs / API endpoints).
- NEVER submit a financial transaction without HITL.
- NEVER modify user identity records without HITL.
- NEVER exceed the per-run record budget (idempotency + cap).

### Idempotency is Everything

RPA agents touch real systems. A re-run after a crash must not double-
submit. Every action carries an idempotency key (record ID + step ID);
the harness checks the key before dispatching. See
`deterministic-agents/references/idempotency-and-replay.md`.

### Eval Emphasis

Regression evals dominate: every past workflow break is a regression
case. Capability evals per tool per system under test. Governance
evals for the never-do list (no off-system navigation, no
unsanctioned submits).

### Common Pitfalls

1. **UI drift breaks the agent.** The target system changes its UI;
   selectors fail. Fix: pair UI automation with API calls where
   possible; alert on selector failure.
2. **Double-submit on retry.** Crash mid-flow; retry; record created
   twice. Fix: idempotency keys checked before every write.
3. **Unbounded LLM judgment.** The LLM starts "improving" the workflow.
   Fix: tight system prompt; deterministic flow with the LLM only at
   named decision points.
4. **Silent failure on legacy systems.** Old systems return
   success-codes for failures. Fix: verify state after every write;
   treat unverifiable state as failure.

### Framework Fit

- **LangGraph** — the graph shape maps naturally to multi-step RPA
  flows with HITL interrupts.
- **Microsoft Agent Framework** — strong fit for Microsoft-stack RPA
  (Power Automate, Office).
- **Mastra** — TypeScript-native workflow shape.

## Deep Research

### Shape

| Aspect | Pattern |
|---|---|
| **Job** | Answer a hard question by gathering, cross-referencing, and synthesizing sources with citations |
| **Trigger** | User question |
| **Tools** | Web search (multi-source); web fetch (with extraction); academic search (Semantic Scholar, arXiv); RAG over a curated corpus; citation manager |
| **Authority** | `read-only` strictly: fetch, read, summarize, cite. Never write, never call APIs that mutate state |
| **Authority escalation** | Ask the user when sources disagree irreconcilably or when the question is ambiguous |
| **Memory** | Per-topic accumulation: prior findings, source trust, cited-URL cache |
| **Eval categories** | Governance (cite every claim, never fabricate); capability (each source type works); behavioral (cross-reference, calibrate confidence); regression (per past fabrication) |

### Tool Surface (Typical)

- `web_search(query)` — search the open web
- `web_fetch(url)` — fetch and extract content from a page
- `academic_search(query)` — Semantic Scholar / arXiv / Google Scholar
- `corp_corpus_search(query)` — RAG over a curated internal corpus
- `cite(source_id, claim)` — record a citation
- `ask_user(question)` — disambiguate

### Authority Floor

- NEVER fabricate a citation. Every claim must trace to a fetched
  source.
- NEVER modify the corpus during a research run (read-only).
- NEVER submit forms, log in, or interact with sites beyond fetching.
- ALWAYS label inferred conclusions vs. cited facts.

### Citation Discipline

Every non-trivial claim carries a citation. The agent's final output
is a structured document:

```
1. <claim> [source: title, URL, accessed-date]
2. <claim> [source: ...]
...
Synthesis: <reasoned conclusion> (labeled as inference)
```

Citations are checked: every cited URL was actually fetched during
the run (provenance audit). Fabricated citations are a SEV1 governance
failure.

### Eval Emphasis

Governance evals dominate: citation provenance (every cite fetched),
no-fabrication tests, calibration-of-confidence. Behavioral evals for
cross-referencing (does the agent spot when sources disagree?).
Regression per past fabrication incident.

### Common Pitfalls

1. **Fabricated citations.** The LLM invents plausible-looking URLs.
   Fix: provenance audit; cite only fetched URLs.
2. **Single-source bias.** The agent finds one source and stops.
   Fix: require cross-referencing; minimum N distinct sources per
   non-trivial claim.
3. **Stale information.** The cited source is from 2019 on a
   fast-moving topic. Fix: prefer recent sources; flag when the
   freshest source is old.
4. **Inference presented as fact.** Fix: explicit `Synthesis` section
   labeled as inference.

### Framework Fit

- **Custom loop** — research agents benefit from tight control over
  the search-fetch-cite loop; frameworks add little.
- **LangGraph** — for the multi-step search-and-cross-reference flow.
- **LlamaIndex** — when the corpus side (RAG over indexed sources)
  dominates.

## Cross-Domain Patterns

These three domains illustrate the meta-pattern: **the authority
floor differs, the eval emphasis differs, but the harness and
deploy shape are the same.** Read each domain's "Authority Floor"
section as a worked example of the agent-safety doctrine; read each
"Eval Emphasis" as a worked example of the agent-evals doctrine.

For any new domain (legal-research agent, finance-analysis agent,
coding-copilot agent), work through:

1. What is the job? (One sentence.)
2. What is the trigger?
3. What tools? (And critically, what is the read/write split?)
4. What is the authority floor? (The never-do list.)
5. What does the eval suite emphasize? (Which of the four categories
   dominates?)
6. What is the framework fit? (Does the workflow shape call for a
   graph, a handoff chain, a workflow, or a custom loop?)

Answer those six and you have a first-draft design.

## See Also

- `../../agent-design/SKILL.md` — the design doctrine these patterns instantiate.
- `../../agent-evals/references/eval-taxonomy.md` — the four-category taxonomy.
- `../../agent-safety/references/framework-safety-matrix.md` — the safety primitives.
- `../../agent-deployment/references/packaging-serving.md` — the deploy shapes.
