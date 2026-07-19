# DSPy — Systematic Prompt Optimization

> Last verified: 2026-07 against [dspy.ai](https://dspy.ai) and PyPI (dspy
> 3.2.1 stable, May 2026). API names and optimizer recommendations go stale
> fastest; check [choosing an optimizer](https://dspy.ai/diving-deeper/choosing-an-optimizer/)
> before committing.

DSPy (Stanford NLP, ~36k GitHub stars) is the framework for *programming*
language models instead of hand-tuning prompts: you declare task signatures,
compose modules, define a metric, and let an optimizer search for the
instructions and few-shot demos that maximize the metric. Use it when a prompt
matters enough to deserve an eval — the alternative is optimizing by vibes.

**When DSPy is the right tool:**
- You have (or can label) 10+ examples and a checkable success criterion.
- A prompt is load-bearing in production and hand-tuning has plateaued.
- A multi-stage pipeline (retrieve → reason → answer) needs joint tuning.
- You want prompts that port across models (re-compile instead of re-tune).

**When it isn't:** one-off prompts, tasks with no measurable metric, or simple
chains where a direct prompt already hits the bar. Eval harness design itself
is the `agent-evals` skill; retrieval pipelines are `memory-rag`.

## Setup (current API)

The old `dspy.OpenAI` / `dspy.Claude` clients are gone. One LM class,
LiteLLM-style `provider/model` strings:

```python
import dspy

lm = dspy.LM("anthropic/claude-sonnet-4-5", max_tokens=2000)
dspy.configure(lm=lm)

# Scoped override — e.g., a cheap model for one sub-step:
with dspy.context(lm=dspy.LM("anthropic/claude-haiku-4-5")):
    ...
```

## Signatures — declare the task, not the prompt

```python
# Inline: quick prototyping
qa = dspy.Predict("question -> answer")

# Class: docstring = task description; fields carry types and hints
class TicketTriage(dspy.Signature):
    """Classify a support ticket and extract the error code."""
    ticket: str = dspy.InputField()
    category: str = dspy.OutputField(desc="one of: auth, billing, bug, feature")
    error_code: str | None = dspy.OutputField()
```

Signatures accept Python/Pydantic types directly — `dspy.Predict` handles
structured output natively (the old `TypedPredictor` was removed in 3.0).
The docstring and field descriptions are *starting points*: optimizers rewrite
the instructions, so describe the task honestly rather than prompt-golfing.

## Modules — composable, optimizable units

| Module | What it does | Use when |
|---|---|---|
| `dspy.Predict` | Direct signature → completion | Simple classification/extraction; default starting point |
| `dspy.ChainOfThought` | Adds a `reasoning` output field before the answer | Multi-step logic; quality > latency |
| `dspy.ReAct(sig, tools=[...], max_iters=20)` | Tool-calling agent loop; tools are plain Python callables; returns a `trajectory` | Multi-step research/action tasks |
| `dspy.ProgramOfThought` / `dspy.CodeAct` | Generates and executes code to compute the answer | Arithmetic, data transforms — code beats text-math |
| `dspy.BestOfN(module, N, reward_fn, threshold)` | N rollouts, keep the best per your reward | Output-quality floor; validation without retraining |
| `dspy.Refine(module, N, reward_fn, threshold)` | Like BestOfN plus LM feedback between attempts | Iterative self-correction |
| `dspy.MultiChainComparison` | Generates M candidates, compares, picks | High-stakes/ambiguous answers (self-consistency) |

Note: `dspy.Assert`/`dspy.Suggest` (assertion-driven backtracking) were
**removed in 2.6** — `Refine`/`BestOfN` are the replacements.

Compose modules with ordinary Python:

```python
class RAG(dspy.Module):
    def __init__(self, retriever, k=3):
        super().__init__()
        self.retriever = retriever
        self.generate = dspy.ChainOfThought("context, question -> answer")

    def forward(self, question):
        context = self.retriever(question, k=3)
        return self.generate(context=context, question=question)
```

Every `Predict`/`ChainOfThought` inside becomes an optimization target — the
optimizer tunes each stage's instructions and demos jointly against your
end-to-end metric.

## Metric design — the part that decides everything

A metric is a function the optimizer maximizes. Signature:

```python
def metric(example, pred, trace=None):   # full form adds pred_name, pred_trace
    ...
    return score   # bool or float
```

Design rules:

1. **Graded beats binary for nuanced tasks.** Exact-match gives the optimizer
   no gradient; partial credit (F1, rubric points) lets it climb.
2. **Use `trace` to be stricter during bootstrapping.** `trace is not None`
   during optimizer compilation — return a hard bool there (only flawless
   demos get bootstrapped) and a graded float during evaluation.
3. **Encode all the things you actually care about** — correctness AND
   format AND length AND citation — as a weighted score. The optimizer will
   exploit anything you forgot to measure.
4. **LLM-as-judge metrics are allowed** (a `dspy.Predict` inside the metric)
   — calibrate the judge first (see `agent-evals`).
5. **For GEPA, return feedback, not just a score:**

```python
def gepa_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    score = grade(gold, pred)
    return dspy.Prediction(
        score=score,
        feedback=f"Answer was {'correct' if score else 'wrong: expected ' + gold.answer}. "
                 f"Format {'ok' if is_json(pred.answer) else 'broken — not valid JSON'}.")
```

GEPA's reflection model reads the feedback text to propose better prompts;
richer feedback → better search. Other optimizers ignore the feedback field.

## Optimizer selection

| Optimizer | Mechanism | Data needed | When to use |
|---|---|---|---|
| `BootstrapFewShot` | Runs your program, keeps traces that pass the metric as few-shot demos | 10-50 | **Safe first try** — almost always beats zero-shot when the metric is reliable |
| `BootstrapFewShotWithRandomSearch` (`BootstrapRS`) | Bootstrap + random search over demo subsets | 50+ | Demo quality varies run-to-run |
| `MIPROv2` | Bayesian search over the joint instruction + demo space | 50-200 + valset | Both instructions and demos need tuning; the workhorse |
| `GEPA` | Reflective prompt evolution: a strong reflection LM reads metric feedback and rewrites instructions; Pareto candidate pool | 50+ with feedback-shaped metric | Current state of the art when you can write textual feedback; instruction-heavy tasks |
| `SIMBA` | Mini-batch introspection of failure patterns | 50+ | Failure cases share a diagnosable pattern |
| `KNNFewShot` | Per-input demo selection by embedding similarity | 10+ (larger better) | Cheap baseline; diverse trainset at inference |
| `BootstrapFinetune` | Distills the program into model weight updates | 100+ | Prompt-only has plateaued; latency/cost demands a smaller tuned model |
| `BetterTogether` | Chains prompt- and weight-optimizers (e.g. prompt→finetune→prompt) | 100+ | Squeezing the last points |
| `COPRO` | Instruction-only coordinate search | 20-100 | Legacy-tier; demos already fixed; prefer MIPROv2/GEPA |

Key parameters (verified 3.2.x):

```python
# MIPROv2 — auto presets size the search
opt = dspy.MIPROv2(metric=metric, auto="medium")      # light | medium | heavy
compiled = opt.compile(program, trainset=trainset, valset=valset)

# GEPA — budget is exactly one of auto / max_full_evals / max_metric_calls,
# and it needs a strong reflection model
opt = dspy.GEPA(metric=gepa_metric, auto="light",
                reflection_lm=dspy.LM("anthropic/claude-opus-4-6"))
compiled = opt.compile(program, trainset=trainset, valset=valset)
```

## Worked example — optimize a triage prompt end to end

```python
import dspy

dspy.configure(lm=dspy.LM("anthropic/claude-sonnet-4-5"))

# 1. Program
triage = dspy.ChainOfThought(TicketTriage)          # signature from above

# 2. Data — dspy.Example with declared inputs; split BEFORE optimizing
data = [dspy.Example(ticket=t, category=c, error_code=e).with_inputs("ticket")
        for t, c, e in labeled_rows]                 # aim for 50-200
train, val, test = data[:120], data[120:160], data[160:]

# 3. Metric — graded, strict under trace
def metric(example, pred, trace=None):
    cat_ok = pred.category == example.category
    code_ok = pred.error_code == example.error_code
    if trace is not None:                            # bootstrapping: flawless only
        return cat_ok and code_ok
    return 0.7 * cat_ok + 0.3 * code_ok

# 4. Baseline — never skip this
evaluate = dspy.Evaluate(devset=test, metric=metric, num_threads=8,
                         display_progress=True)
baseline = evaluate(triage)                          # EvaluationResult; .score is a %

# 5. Cheap optimizer first
bs = dspy.BootstrapFewShot(metric=metric, max_bootstrapped_demos=4)
triage_bs = bs.compile(triage, trainset=train)
print(evaluate(triage_bs).score - baseline.score)

# 6. Escalate only if the gap justifies it
mipro = dspy.MIPROv2(metric=metric, auto="medium")
triage_mipro = mipro.compile(triage, trainset=train, valset=val)
print(evaluate(triage_mipro).score)

# 7. Ship the winner as an artifact; version it with your code
triage_mipro.save("prompts/triage_v2.json")          # demos + instructions, not weights
# Load: program = dspy.ChainOfThought(TicketTriage); program.load("prompts/triage_v2.json")
```

The workflow discipline — baseline, then cheapest optimizer, then escalate,
always scoring on a held-out test set — matters more than which optimizer you
pick. Typical progression: baseline 0.65 → BootstrapFewShot 0.78 → MIPROv2 or
GEPA 0.85+ (task-dependent; measure, don't assume).

The saved JSON is a **prompt artifact**: inspect it (it's the compiled
instructions + demos), diff it in code review, and re-compile — not re-tune by
hand — when you change models.

## Pitfalls

1. **Optimizing on the test set.** Train/val/test split first; report only
   test. Compiling against your test set is the LLM version of training on it.
2. **Binary metric on a nuanced task.** Exact match gives the search nothing
   to climb; add partial credit.
3. **Metric missing a dimension you care about.** The optimizer will happily
   sacrifice format for accuracy (or vice versa) if only one is scored.
4. **Too many demos.** `max_bootstrapped_demos` in the 3-5 range; 16+ demos
   overfit and bloat every production call's token cost.
5. **Skipping the baseline.** Without a pre-optimization score you can't tell
   whether 30 minutes of MIPROv2 bought anything.
6. **Tiny trainsets with heavyweight optimizers.** MIPROv2/GEPA on 10 examples
   mostly fits noise; use BootstrapFewShot until you have 50+.
7. **Stale API knowledge.** DSPy moves fast (assertions removed, TypedPredictor
   removed, LM clients unified, `reasoning` replaced `rationale` as the CoT
   field). Verify against dspy.ai for your installed version.
8. **Treating the compiled prompt as magic.** Read what the optimizer
   produced. Compiled instructions sometimes encode dataset quirks you don't
   want in production — that's a data problem to fix, not a prompt to ship.
