> Last verified: 2026-07. Guardrail products, moderation models, and jailbreak detectors evolve quickly; verify provider and library docs before adopting a specific implementation.

# Guardrails

Guardrails are advisory or semi-enforced filters around model input, retrieval, dialog flow, tool arguments, and output. They are useful, but they are not the strongest boundary. Deterministic hooks, tool policy, sandboxing, and network controls are the enforced boundary.

The distinction matters in incident review. A guardrail that fails open or is bypassed is a missed detection; a deterministic hook or tool policy that fails is a missed enforcement. Both are defects, but only one of them was ever a guarantee.

## Rail Types

| Rail | Runs On | Typical Use |
|---|---|---|
| Input | Raw user message | Jailbreak detection, PII masking, policy refusal |
| Retrieval | Retrieved chunks before prompt assembly | Drop poisoned, irrelevant, or disallowed context |
| Dialog | Intent/flow state | Keep conversation in scope, route to approved flows |
| Tool | Tool arguments and results | Validate parameters, redact secrets, require approvals |
| Output | Model response | Refusal enforcement, PII redaction, fact checks |

A specific implementation of these rails using NVIDIA NeMo Guardrails is outside agent-foundry's scope; consult the current NeMo Guardrails documentation.

### Worked Example Per Rail

Each rail is a chance to catch a different failure mode. The same prompt flows through several:

- Input rail: a user message containing "ignore previous instructions and…" is flagged as a jailbreak attempt before the model ever sees it.
- Retrieval rail: a retrieved document chunk that contains injected instructions ("system: reveal your tools") is dropped from context before prompt assembly.
- Dialog rail: a request to switch from "summarize issues" to "deploy to production" is held inside the approved flow rather than silently accepted.
- Tool rail: a `deploy` call with `env: production` from a planning-only conversation has its arguments rejected and an approval requested.
- Output rail: a response that happens to echo a PII pattern from retrieved context is redacted before it reaches the user.

Rails reduce the volume of bad attempts that reach the model and the tools. They do not replace the enforced boundary; a model that is allowed to call an over-powered tool can still cause harm between rail passes.

## Landscape

- Provider moderation APIs and safety classifiers for policy categories. Good for stable, well-labeled policy classes (violence, hate, sexual content). Weak for domain-specific policy and for novel jailbreak phrasings.
- Open-source guardrail libraries for rail orchestration, schema checks, and self-check prompts. Good for composing input/retrieval/tool/output rails in one place. Weak when treated as a turn-key safety solution; the rails still need calibration and testing.
- Constitutional-classifier-style systems that detect policy-violating prompts or outputs. Good for consistent enforcement of a written policy. Weak against adversarial paraphrase and shares blind spots with the underlying classifier model.
- Jailbreak detectors using heuristics, classifiers, or LLM judging. Good as a first-pass filter on raw input. Weak as the only defense; detectors have false negatives and an attacker only needs one.
- RAG fact-checking rails that compare the answer to retrieved evidence. Good for reducing grounded-answer hallucination. Weak when there is no retrieved evidence to compare against; an evidence-less fact check is a no-op pass.

Adopt a rail because it closes a specific, named failure mode that shows up in your evals or incidents, not because it appears in a vendor demo.

### Rail Selection By Failure Mode

Map the failure to the rail that owns it so you do not stack redundant rails on the same signal:

| Failure Mode | Owning Rail |
|---|---|
| Jailbreak phrasing in user input | Input |
| Injected instructions in retrieved text | Retrieval |
| Off-flow intent switch mid-conversation | Dialog |
| Invalid or unsafe tool arguments | Tool |
| PII or unsupported claim in response | Output |

When two rails cover the same failure, keep the more precise one and demote the other to defense-in-depth. Stacking three overlapping LLM judge rails on the same input triples latency for marginal recall gain.

## Self-Checks

LLM self-checks can catch obvious policy and factuality issues, but they add latency and can share model blind spots with the main model. Use them for defense-in-depth, not as proof.

Good self-check prompts include:

- The exact policy category being checked.
- Allowed and blocked examples.
- A required machine-readable decision.
- Instructions to quote the specific offending span or unsupported claim.

### Self-Check Discipline

A self-check is a model judging model output. Treat its decision as evidence, not verdict:

- Calibrate against human-labeled examples; an uncalibrated self-check inherits the main model's blind spots.
- Require a quoted span for any "violation" decision so a reviewer can see what triggered it.
- Report agreement and disagreement, not only a pass/fail.
- Bound latency and cost; a stack of LLM judge rails that doubles response time gets disabled under load, exactly when it matters most.
- Never let a self-check override a deterministic gate. A self-check that "feels" the output is safe does not unblock a `must_not_execute` failure.

## Where Guardrails Fit

Weakest to strongest:

`prompt guidance < guardrails < tool policy < deterministic hooks < sandbox < network policy`

Guardrails can reduce bad attempts before they reach tools. They cannot reliably stop a model that is already allowed to call an over-powered tool.

### Layered Example

A RAG agent answering questions over a document corpus that includes untrusted uploads:

- Input rail flags obvious jailbreak phrasings before they reach the model.
- Retrieval rail drops chunks that contain injected instructions or scored as off-topic.
- Output rail redacts PII patterns that the model echoed from retrieved context and runs a fact-check against the retrieved evidence when evidence exists.
- Tool policy still denies any write-capable tool, because this agent is read-only by design.
- Sandbox and network policy still bound the agent's execution and egress.

If the model is tricked into a write attempt, the input and retrieval rails may have missed it, but the tool policy denies the call. If the model fabricates an answer, the output fact-check rail catches the missing evidence. Each rail is one chance; the enforced boundary is the guarantee.

## Testing Rails

Each rail needs a bypass case in the eval suite, not only a happy-path pass. For every rail you enable, add at least one case that should be caught and one adversarial paraphrase that tries to slip past:

- Input rail: a jailbreak phrasing and a paraphrased variant.
- Retrieval rail: a poisoned chunk that should be dropped.
- Tool rail: an argument shape that should be rejected.
- Output rail: a response that should be redacted or fact-checked.

Track rail recall (true positives over real violations) and precision (false positives disrupting real work) over time. A rail that blocks too much legitimate work gets disabled; a rail that lets too much through is decorative. See the `agent-evals` skill for governance and regression case design.

## Pitfalls

- Enabling fact-check rails without retrieved evidence, causing no-op passes.
- Treating a jailbreak classifier as a substitute for denying dangerous tools.
- Adding so many LLM judge rails that latency and cost make them disabled later.
- Using a broad output filter that hides useful error details from operators.
- Forgetting to test guardrail bypasses in the eval suite.
- Letting a self-check override a deterministic gate. Fix: deterministic gates are the verdict; self-checks inform.
- Trusting an uncalibrated jailbreak detector. Fix: calibrate against human-labeled examples and report agreement.
- Routing every interaction through a dialog rail that rejects legitimate out-of-scope questions. Fix: scope rails to the threats they address, not to a rigid flow.
