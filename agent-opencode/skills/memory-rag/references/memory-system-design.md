# Memory System Design

Agent memory should start small, explicit, and auditable. The durable core is not a transcript dump; it is the minimum set of facts and preferences that should influence future behavior.

## Layered Memory

| Layer | Contents | Loading pattern | Failure mode |
|---|---|---|---|
| Durable core | Stable facts, preferences, commitments, long-lived decisions | Injected or deliberately loaded at session start | Grows until every turn pays irrelevant token cost. |
| Working/daily memory | Current project state, recent decisions, transient tasks | Retrieved on demand | Agent forgets if it never searches. |
| Knowledge base/wiki | Structured notes with sources and contradictions | Search/read by task | Stale claims become invisible assumptions. |
| Consolidation output | Candidate promotions from recent work | Human or verifier reviews before promotion | Automatic promotion stores wrong facts. |

### Layer Boundaries (Concrete)

The four layers are separated by **how they are loaded, who writes them, and how stale they are allowed to become**. Mixing the layers is the most common memory-system bug:

| Layer | Loaded by | Written by | Allowed staleness | Token budget |
|---|---|---|---|---|
| Durable core | Session-start injection | Consolidation only | Months; reviewed weekly | Small and capped (e.g., < 2k tokens). |
| Working/daily | On-demand retrieval | The agent, during a run | Hours to days | Medium; discarded at run end. |
| Knowledge base/wiki | Task-driven search/read | Humans + cited agents | Days to weeks; versioned | Not injected wholesale; retrieved per query. |
| Consolidation output | Promotion review | Verifier or human | Never stale (it is the gate) | N/A (control plane, not prompt context). |

Anti-patterns this table prevents:

- **Injecting the knowledge base into every prompt.** It floods the token budget with content most queries do not need. Retrieve on demand instead.
- **Letting the agent write the durable core directly.** Working memory and durable memory collapse into one growing transcript. Route all durable writes through consolidation.
- **Treating consolidation output as prompt context.** It is a *control plane* (what gets promoted), not context the model reads. Confusing the two causes the model to "see" candidate facts before they are verified.

## What Belongs in Durable Memory

- Stable user/team preferences.
- Durable constraints and commitments.
- Long-lived domain facts needed often.
- Pointers to canonical project docs.

What does not belong: today-only context, full chat logs, large reference material, unverified claims, or anything cheaper to retrieve on demand.

### Decision Test for Durable Storage

Before promoting anything to the durable core, it should pass all of these:

| Test | Question | Fail action |
|---|---|---|
| **Stability** | Will this still be true in a month? | If no → working memory, not durable. |
| **Reuse** | Will it influence multiple future runs? | If no → keep in the run scratchpad. |
| **Cost of retrieval** | Is it cheaper to inject than to retrieve on demand? | If no → put in the knowledge base and retrieve. |
| **Verifiability** | Can a human or verifier confirm it with evidence? | If no → stays a candidate, never durable. |
| **Not a rule** | Is it a *fact* or *preference*, not an operating rule? | If it is a rule → project instructions or skills, not memory. |
| **No contradiction** | Does it conflict with an existing durable fact? | If yes → resolve the conflict before promoting. |

A fact that fails any test does not get promoted. The test that fails most often is **Not a rule** — teams try to encode operating policy in memory, which decays silently because no agent re-reads it the way it re-reads instructions.

## Write Policy

Memory should have explicit policy: what to remember, when to ask, when to overwrite, and how to cite provenance. For personal or user-model memory, err toward asking before storing sensitive facts. For project memory, require source links or file references.

### Write Policy Decisions (Concrete)

| Decision | Default rule | Exception |
|---|---|---|
| What to remember | Facts and preferences only, with evidence | Never rules, never today-only context. |
| When to ask before storing | Sensitive, personal, or user-identifying facts | Low-risk preferences may be stored as candidates without asking. |
| When to overwrite | Only with stronger evidence and a logged reason | Never silently; keep the prior value in history. |
| How to cite provenance | Source link, file reference, or run+turn ID | No provenance → no promotion to durable. |
| When to forget | Weekly audit demotes facts not referenced in N days | Archive, do not delete; keep the rollback path. |
| Who can write durable | Consolidation only (verifier or human) | Never an agent writing directly to durable in-run. |

## Consolidation

Periodic consolidation turns short-term notes into durable memory. The safest workflow is candidate extraction -> review -> promotion. Fully automatic promotion is appropriate only for low-risk facts with strong evidence and a rollback path.

### Sample Consolidation Schedule

Consolidation should be **scheduled and bounded**, not triggered whenever an agent feels like writing. A defensible cadence:

| Cadence | Scope | Action | Risk tolerance |
|---|---|---|---|
| Per turn (in-run) | Working/daily memory only | Append observation to a per-run scratchpad; never promote to durable in-run. | High (scratchpad is disposable). |
| End of run | Run scratchpad → candidate list | Extract candidate facts (preference, decision, commitment); tag with evidence + source. | Medium (candidates are not yet durable). |
| Daily (or every N runs) | Candidates → reviewed promotions | Verifier or human reviews candidates; promote low-risk facts with strong evidence. | Low; high-risk facts stay candidates. |
| Weekly | Durable core audit | Demote or archive facts not referenced in N days; resolve contradictions. | Low; archive, do not delete. |
| On source change | Facts depending on that source | Re-verify or invalidate; never silently keep a stale fact pointing at a moved doc. | Low; prefer invalidate over wrong. |

### Consolidation Candidate Format

Every candidate should carry enough to be reviewed without re-reading the run:

```
candidate_fact:    "User prefers tab-indented YAML."
evidence:          ["run_4821:turn_7", "run_4821:turn_19"]
conflicts_with:    "durable/fmt.md:line_4 says spaces"   # if any
risk:              low                                    # low | medium | high
proposed_action:   promote_to: durable/preferences.md
reviewer:          human | verifier_model
status:            candidate                             # candidate | promoted | rejected | archived
```

The `conflicts_with` field is the one teams skip. Promoting a fact that contradicts an existing durable fact without resolving the conflict is how memory becomes self-contradictory.

### Auto-Promotion Policy (When It Is Safe)

Auto-promotion is appropriate only when **all** of the following hold:

| Condition | Why |
|---|---|
| Risk is low (preference, format, naming) | Wrong facts are cheap to notice and fix. |
| Evidence is strong (≥ 2 independent observations) | Single observations are noise. |
| No conflict with existing durable memory | Conflicts require a human, not a vote. |
| Rollback path exists (versioned durable store) | You can undo the promotion if it was wrong. |
| The fact is not a rule or policy | Rules belong in instructions/skills, never memory. |

If any condition fails, the candidate stays in the review queue. High-risk facts (security, money, identity, commitments to other people) never auto-promote.

## Multi-Agent Memory

Shared memory is useful when agents collaborate, but it creates contamination risk. Keep role-specific scratchpads separate from shared durable facts. Record which agent wrote a memory and what evidence supported it.

### Multi-Agent Memory Layout

| Store | Scope | Who writes | Who reads | Contamination control |
|---|---|---|---|---|
| Per-agent scratchpad | One agent, one run | That agent only | That agent only | Discarded or archived at run end; never shared live. |
| Shared working memory | One task/session | Agents on that task | Agents on that task | Cleared when the task closes. |
| Shared durable core | Project/team | Promotion via consolidation only | All agents | Every entry has author + evidence + version. |
| User-model memory | One user | User-scoped agents + consolidation | User-scoped agents | Tenant isolation enforced; never cross-user. |

The rule: **write access narrows as you go up the ladder.** Any agent can write its scratchpad; only consolidation can write the durable core. Letting agents write directly to durable memory is how contamination, contradiction, and hallucinated facts enter the system.

### Provenance and Contamination Controls

- Every durable entry records: author agent, source evidence, ingested timestamp, version.
- Contradictions are surfaced at consolidation time, not silently overwritten.
- A fact extracted by an agent running on a value-tier model is treated as untrusted until a verifier or human checks it — model tier is a provenance field, not a trust grant.
- Cross-agent reads of user-model memory are scoped to the same user; never allow an agent to read another user's memory.

## Start Minimal

Begin with files or a small database. Add vector or graph memory only after you can name the retrieval failures a simpler system could not solve.
