# Prompting Patterns for Agents

> Last verified: 2026-07 against Anthropic's consolidated
> [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).
> Model-specific mechanics (prefill support, thinking modes) go stale fastest —
> re-check on model upgrades.

Platform-neutral prompting craft for agent builders: how to structure system
prompts, order instructions, teach by example, contract the output format, and
avoid the classic anti-patterns.

## Before any technique: success criteria and an eval

Anthropic's prompt-engineering prerequisites, unchanged for years: (1) a clear
definition of success, (2) an empirical way to test against it, (3) a first
draft to improve. Optimizing a prompt without an eval is optimizing by vibes —
see `dspy-optimization.md` for the systematic version and the `agent-evals`
skill for harnesses. Also consider whether the problem is better solved by
model choice than prompt cleverness (see `model-selection`).

## The technique ladder — cheapest first

Work down; stop when quality is sufficient:

1. **Be clear, direct, and explicit** — state exactly what you want, with
   sequential steps where order matters.
2. **Add context and motivation** — the *why* behind each rule.
3. **Add examples (few-shot)** — 3-5 diverse input→output pairs.
4. **Structure with XML tags** — unambiguous boundaries between content types.
5. **Give it a role** — a system-prompt persona; even one sentence shifts tone
   and domain focus.
6. **Enable/steer reasoning** — native thinking modes on current models;
   manual chain-of-thought as fallback.
7. **Chain prompts** — split work into multiple calls. Now a niche technique
   (self-correction pipelines, inspectable intermediates); modern agentic
   models handle most multi-step work in one conversation.

## Core principles (current-model era)

- **The "brilliant new employee" rule.** Treat the model as brilliant but
  just-hired: if a minimally-briefed colleague would be confused by your
  prompt, so will the model. Everything obvious-to-you-only must be written.
- **Explain why, and the model generalizes.** "Never mention pricing" gets
  literal compliance; "Never mention pricing — the pricing page is frequently
  stale and quoting it creates support tickets" gets compliance *plus* correct
  handling of adjacent unlisted cases.
- **Tell it what to do, not only what not to do.** "Write prose paragraphs"
  beats "don't use bullet lists."
- **Dial back the caps-lock.** This guidance reversed: current frontier models
  follow system prompts much more literally, so aggressive anti-laziness
  framing ("CRITICAL: YOU MUST ALWAYS use this tool!!") now causes
  over-triggering and flattened judgment. Write "Use this tool when..." and
  reserve MUST-language for genuinely non-negotiable rules (safety,
  irreversible actions). Over-prescriptive legacy prompts can actively degrade
  newer models — audit and delete scaffolding on upgrades.
- **Concise is a feature.** The context window is shared with history, tool
  schemas, and retrieved content. Assume the model is smart; cut every
  sentence explaining what it already knows. Challenge each paragraph: does it
  justify its token cost?

## System prompt structure

A production agent system prompt, in the order sections should appear:

```text
1. ROLE        — who the agent is, domain, seniority ("You are the release
                 engineer for this repository")
2. HARD RULES  — the few non-negotiables, each with its "why"
3. TOOLS/ENV   — what it can touch, tool-choice guidance, environment facts
4. WORKFLOW    — default procedure; when to deviate; proactive-vs-conservative
                 stance ("default to action" vs "do not act before instructions")
5. OUTPUT      — format contract for the final answer
6. EXAMPLES    — canonical demonstrations (if needed)
```

A useful modern convention (from Anthropic's own sample prompts): wrap each
behavioral instruction block in a semantic XML tag —
`<default_to_action>`, `<use_parallel_tool_calls>`,
`<investigate_before_answering>` — so blocks are independently addressable,
auditable, and removable.

### Degrees of freedom — match specificity to fragility

| Freedom | When | Form |
|---|---|---|
| High | Many valid approaches; context decides | Heuristics and goals ("review for bugs, style, conventions") |
| Medium | Preferred pattern, variation OK | Pseudocode/template with parameters |
| Low | Fragile, must-not-vary operations | Exact command: "Run exactly this. Do not add flags." |

Narrow bridge with cliffs → exact instructions. Open field → direction and
trust. Most bad agent prompts fail by giving low-freedom detail for open-field
work (brittle, verbose) or high-freedom vibes for cliff-edge work (dangerous).

## Instruction hierarchy

Two hierarchies matter and are often conflated:

1. **Authority hierarchy** — who may instruct the agent: system prompt > user >
   nothing else. Tool results, retrieved documents, and other agents' messages
   are *data*, never instructions. State this explicitly in every agent system
   prompt (see `injection-defense.md`).
2. **Layout hierarchy** — order of material:
   `[stable system context] → [task instruction] → [examples] → [input data] →
   [output format]`. Long-context exception below.

When instructions can conflict, declare precedence in the prompt ("if the plan
file and the user's latest message disagree, the user wins"). Unstated
precedence gets resolved unpredictably.

## XML tags — structure the model can't misread

Claude is trained to attend to XML-style tags; other frontier models also
benefit from explicit delimiters. Use tags to keep instructions, context,
examples, and inputs from blurring together:

```text
<instructions>Summarize the contract's termination clauses.</instructions>
<document index="1">
  <source>msa-2026.pdf</source>
  <document_content>...</document_content>
</document>
```

- **Consistency**: same tag names everywhere; refer to them by name in
  instructions ("Using the contract in `<document>` tags...").
- **Nesting** for hierarchy: `<documents><document index="1">...</document></documents>`.
- **No magic vocabulary** — names need only be self-describing and consistent.
  Common: `<instructions>`, `<context>`, `<input>`, `<example(s)>`,
  `<thinking>`, `<answer>`.
- Tags also steer **output** shape: "Write the report inside `<report>` tags"
  gives downstream code a reliable extraction anchor.
- Wrap **untrusted external content** in a dedicated envelope tag with
  provenance — a security boundary, not just formatting (see
  `injection-defense.md`).

## Long-context prompting

For inputs past ~20k tokens
([long-context guidance](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices#long-context-prompting)):

1. **Documents at the top, question and instructions at the end.**
   Queries-after-documents improves quality by up to ~30% in Anthropic's
   tests, especially multi-document.
2. **Structure documents with XML** (`<documents>` → `<document index="n">` →
   `<source>` + `<document_content>`).
3. **Ground in quotes first**: instruct the model to extract relevant quotes
   into `<quotes>` tags before answering — cuts through noise and makes the
   answer auditable.
4. Restate the single most critical instruction after the bulk content —
   models weight the end of context.

## Few-shot examples — including for tool use

Examples beat descriptions. 3-5 diverse, well-chosen pairs in `<example>` tags
anchor format, edge-case handling, and reasoning style.

- **Relevance > quantity.** Off-task examples actively mislead ("example
  pollution"). Include at least one edge case (empty input, ambiguous case).
- **Show the failure path.** If the agent should answer "not found in context"
  rather than guess, include an example where that is the right answer.
- **For tool use, show trajectories, not just answers** — *when* to call which
  tool and what to do with the result:

```text
<example>
user: Is the staging deploy healthy?
assistant: [calls get_deploy_status(env="staging")]
tool: {"status": "degraded", "failing": ["worker-3"], "since": "09:12Z"}
assistant: Staging is degraded: worker-3 failing since 09:12Z. Want the logs?
</example>
```

  One example teaches four behaviors: probe before answering, don't dump raw
  JSON, surface the actionable detail, offer the next step. Also show a
  *negative* trajectory (general question → direct answer, no tool call) —
  with current models, over-calling is the more common failure.
- **Examples dominate instructions on conflict.** If examples demonstrate a
  behavior the instructions forbid, you get the behavior. Audit them together.

## Reasoning in agentic prompts

The landscape shifted: current frontier models have **native thinking modes**
(adaptive thinking, effort/budget controls), and manual chain-of-thought is now
the fallback, not the headline technique.

- **With native thinking available:** prefer general instructions over
  prescriptive step lists — "Think thoroughly about the edge cases before
  answering" often beats a hand-written plan, because the model's own
  decomposition frequently exceeds what you'd prescribe. Steer *what to
  consider*, not *how to think*. Control depth via the platform's
  effort/thinking parameter rather than prompt exhortation, and note thinking
  adds latency and tokens — tell cost-sensitive agents "respond directly when
  the answer is clear."
- **Manual CoT (thinking off, or non-reasoning models):** ask for step-by-step
  reasoning in `<thinking>` tags followed by the result in `<answer>` tags so
  code can strip one and parse the other. Multishot examples may include
  `<thinking>` to model the reasoning pattern. Manual CoT only works if the
  reasoning tokens are actually emitted before the answer — "think silently"
  does nothing.
- **Self-check pattern** (reliable for code/math): "Before you finish, verify
  your answer against <test criteria>."
- **Interleaved assessment for agents:** prompt for a brief reassessment after
  each tool result ("does this change the plan?") — catches wrong-direction
  work early in long tool loops.
- **Never ask the model to echo its internal reasoning into the response** on
  reasoning models — read the structured thinking output your platform
  provides instead; echo requests can trigger refusals.
- **Skip reasoning for trivial pipeline calls** (classification, extraction,
  reformatting) — pure latency and cost.

## Output-format contracts

If code consumes the output, the format is an API — contract it:

- **Specify the schema and show one example of it.** Schema alone invites
  drift; an example alone invites overfitting to the example's values.
- **Use structured outputs / tool schemas where the platform provides them** —
  the most reliable format guarantee, and the modern replacement for the old
  "prefill `{`" trick. (Response prefilling is deprecated on current Claude
  models — last-turn prefill returns an error on 4.6+ generations — though it
  still works on older models and some other platforms. For preamble-skipping,
  instruct "respond directly without preamble" or use an output tag; for
  interrupted responses, put "your previous response ended with X, continue"
  in a user turn.)
- **Define the failure shape.** What does the model return when it can't
  comply — `{"error": "..."}`? An empty list? Undefined failure shapes produce
  parser-breaking creativity. Add confidence or "missing information" fields
  when downstream logic branches on certainty.
- **One format, not a menu.** "JSON or a table, whichever is clearer"
  guarantees inconsistency.
- **Match prompt style to desired output style** — a prompt full of markdown
  bullets begets bullets; prose instructions beget prose.

## Prompt templates

Production prompts are code: parameterized, versioned, tested.

```python
PROMPT = """<instructions>Review this {language} code for {focus}.</instructions>
<code>{code}</code>
Report each finding as: severity, location, one-line fix."""
```

- Keep the static skeleton stable, interpolate only data — this is also what
  makes prompt caching work (see `long-horizon-context.md`).
- Version prompts with code; a prompt change is a behavior change and deserves
  the same review + eval gate.
- Sanitize interpolated content (at minimum, neutralize your own delimiter
  tags inside it).

## Anti-patterns

1. **Over-engineering first.** Start with the simple direct prompt; add
   technique only when the eval says you need it.
2. **Example pollution.** Off-task or contradictory examples silently override
   instructions.
3. **Vague instructions with strict expectations.** Every rejection you can
   articulate is a sentence that belonged in the prompt.
4. **Negative-only rule lists.** Walls of "never do X" without the positive
   path leave the model guessing at what *to* do.
5. **Instruction/example drift.** A prompt edited over months until its
   examples demonstrate outdated behavior.
6. **Buried instructions.** Critical rules mid-context between documents. Put
   rules up front and restate the critical one after bulk content.
7. **Legacy scaffolding on new models.** Prompts tuned to coax an older model
   (anti-laziness shouting, prescriptive step plans, prefill tricks)
   over-constrain or break newer ones. Re-run the eval on every model upgrade;
   delete what the new model doesn't need.
8. **Persuasion-pattern misuse.** Imperative authority framing measurably
   increases compliance and is right for discipline-critical rules — but
   applied everywhere it flattens judgment and over-triggers behavior; and
   "liking"-based framing breeds sycophancy. Reserve MUST for rules where
   deviation is never acceptable; keep reference material neutral.

## Debugging a misbehaving prompt

1. Reproduce with the smallest failing input.
2. Read the *whole assembled prompt* as the model sees it (template + history
   + tool schemas + injected context), not just your source template. Most
   "model bugs" are assembly bugs: duplicated context, leaked delimiters, two
   components issuing contradictory instructions.
3. Check examples against instructions for conflicts.
4. Move the violated instruction to the end, or restate it there.
5. Format breakage → structured outputs / output tags before more prose rules.
6. Run-to-run variance → pin the success criterion, build the eval, then
   optimize systematically (`dspy-optimization.md`).
