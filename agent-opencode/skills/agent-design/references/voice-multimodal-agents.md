# Voice & Multimodal Agents

Load this when the agent's surface is spoken audio (phone, assistant, in-app voice) or when non-text inputs — images, documents, screen captures, video — materially shape the design. The pillar doctrine holds; this reference covers what *changes* when the interface stops being text.

## Voice: What Actually Changes

Text-agent designs fail on voice for four structural reasons:

| Constraint | Design consequence |
|---|---|
| Latency is UX-fatal (>1s to first audio feels broken) | Streaming everywhere; small/fast models on the hot path; tool calls need masking (below) |
| No persistent display | The user can't re-read anything — confirmations must be spoken, state must be summarizable in one breath |
| Users interrupt (barge-in) | The loop must stop TTS mid-utterance, capture the interruption, and treat it as the new head of intent |
| Transcription is lossy | Names, numbers, addresses, amounts arrive corrupted; critical slots need read-back confirmation |

### Pipeline Shapes

| Shape | How | Trade-off |
|---|---|---|
| Cascade: STT → LLM → TTS | Three components, each swappable | Full control, easiest to debug and eval per stage; latency = sum of stages — needs aggressive streaming |
| Native speech-to-speech | One model consumes and produces audio | Lowest latency, natural prosody; less controllable, harder to intercept for tool policy, eval is murkier |
| Hybrid | Native S2S for chat; cascade path when tool calls / retrieval fire | Best product results today; two paths to maintain |

> Last verified: 2026-07. Which vendors offer competitive native speech-to-speech with tool calling changes quarterly; verify against provider pages before choosing a shape.

### Voice Doctrine

- **Budget latency like money.** Set an end-to-end target (commonly ≤800ms to first audio), assign per stage, and reject any design that spends it. Routing (see `model-selection`) matters more on voice than anywhere: the hot path takes the fast model, judgment moves off-turn. The "streaming everywhere" mandate below is the transport and progressive-disclosure discipline of `agent-deployment` (streaming-and-progressive-ux) taken to its limit — on voice, every rung of that UX ladder is mandatory, not optional.
- **Mask tool time.** Any tool call >300ms gets an acknowledgment utterance ("let me check that") generated *before* the call — silence reads as a dropped call.
- **Read back critical slots.** Anything transcription can corrupt AND an action depends on (recipient, amount, date, address) is confirmed by read-back before the action fires. This is the voice form of the approval payload (`human-in-the-loop.md`).
- **Design the interruption contract.** On barge-in: stop speaking, keep the abandoned utterance out of conversational state as "said," process the new input against prior context. Frameworks differ on how much of this you get free — it's a stage-3 selection criterion.
- **Keep turns short by contract.** Voice output that reads like your text output is a monologue. System prompt sets a hard sentence budget; anything longer becomes "want the details by text?"

### Voice Safety Notes

Caller identity is a design input: voice is spoofable and callers are unauthenticated by default, so authority (stage 5) must not key off "the caller sounds like the account owner." Sensitive actions need an out-of-band factor. On the output side: if you clone or synthesize a specific person's voice, disclosure and consent are non-negotiable requirements, not features.

## Multimodal Inputs (Vision, Documents, Audio Files)

Usually this is *multimodal input to a text agent*, not a new agent type. Design impacts:

- **Perception is a task-classification question (stage 2).** "Read the amount from this invoice image" is bounded extraction — a cheap vision call with a schema. "Look at this dashboard and tell me what's wrong" is open-ended reasoning. Don't pay open-ended prices for extraction work; see the task×model matrices.
- **Images are hostile input too.** Text inside an image (a screenshot of instructions, a QR code, an EXIF field) is the same injection channel as fetched web content — content, never command. The injection-defense reference applies unchanged.
- **Extract once, then work in text.** For pipelines, convert media to a verified textual/structured representation early (with confidence flags on corruptible fields) and let downstream steps consume that — cheaper, cacheable, and evaluable. Re-perceive only when a downstream step doubts the extraction.
- **Provenance beats vibes.** Outputs that cite where in the image/document a fact came from (region, page, cell) make verification and evals possible; "the invoice says X" without an anchor doesn't.

## Evals

Cascade stages get evaluated separately (STT word-error-rate on YOUR domain vocabulary — generic WER hides the product names and jargon you actually need) plus end-to-end task completion. The metrics that matter in production: task completion rate, p50/p95 latency to first audio, interruption-handling success, critical-slot accuracy *after* read-back, and escalation rate. For multimodal extraction: golden media fixtures with known ground truth, assertion per corruptible field. Latency is a first-class eval on voice — a suite that only checks correctness will happily ship an agent nobody can talk to.
