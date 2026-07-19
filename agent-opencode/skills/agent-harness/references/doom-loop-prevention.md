# Doom-Loop Prevention

A doom loop is when the agent repeats the same actions turn after turn
without making progress. The model is not always able to detect its own
looping — the harness must catch it structurally.

## Doom-Loop Taxonomy

| Pattern | Signature | Example |
|---|---|---|
| **Exact repeat** | Same tool call, same args, consecutive turns | `search("x")` → `search("x")` → `search("x")` |
| **Argument cycle** | Same tool, args cycle through a small set | `search("a")` → `search("b")` → `search("a")` → `search("b")` |
| **Tool-pair cycle** | Two tools alternate without progress | `read(file)` → `edit(file)` → `read(file)` → `edit(file)` (same file, same content) |
| **Apology loop** | Model apologizes and retries the same failed approach | "Sorry, let me try again" → same call → same failure → "Sorry..." |
| **Refinement spiral** | Model keeps refining without ever finishing | edit → undo → edit differently → undo → ... |
| **Step-cap grazing** | Model always "almost done" at the step cap | Never converges; always one step away |

## Detection

The harness tracks recent tool-call signatures and detects repetition:

```python
def is_doom_loop(messages, window=5):
    recent = extract_tool_calls(messages[-window:])
    if len(recent) < 3:
        return False

    # Exact repeat: same call 3+ times
    signatures = [hash(tc.tool, json.dumps(tc.args, sort_keys=True))
                  for tc in recent]
    if len(set(signatures)) == 1 and len(signatures) >= 3:
        return True

    # Argument cycle: 2-arg cycle repeated
    if len(signatures) >= 4:
        unique = list(dict.fromkeys(signatures))
        if (len(unique) == 2
            and signatures[-4:] == [unique[0], unique[1],
                                     unique[0], unique[1]]):
            return True

    # Apology loop: text-only turns with "sorry"/"try again" language
    recent_text = extract_text(messages[-window:])
    if (all(t.strip() for t in recent_text)
        and len(recent_text) >= 3
        and any(re.search(r"\b(sorry|apolog|try again|let me)\b",
                          t, re.I) for t in recent_text[-3:])):
        return True

    return False
```

The window (default 5 turns) and the thresholds (3 for exact repeat, 4
for cycle) are the tuning knobs. Tighter thresholds catch loops sooner
but risk false positives on legitimate retry patterns.

## Detection Spans

When the detector fires, emit a span:

```json
{
  "type": "doom_loop_detected",
  "pattern": "exact_repeat",
  "window": 5,
  "repeated_tool": "search",
  "repeated_args_hash": "abc123",
  "step": 12
}
```

## Response

When a doom loop is detected, the harness:

1. **Stops the loop.** Does not dispatch the next repeated tool call.
2. **Surfaces to the model.** Appends a system message: "You appear to
   be in a loop: <description>. Try a different approach or stop."
3. **Gives the model one more turn.** If the model adjusts, continue.
   If it repeats, stop the run.
4. **Emits the span.** The operator sees the detection and the model's
   response.

The harness does not silently kill the run on first detection. It
intervenes, gives the model a chance to recover, and stops only if the
loop persists.

## Cost and Step Caps as Backstops

Even without doom-loop detection, the harness's step cap and cost cap
will eventually stop a looping agent. The doom-loop detector's value
is **early detection** — stopping the loop after 5 turns instead of
after the 25-turn step cap.

| Defense | Catches | Latency to detection |
|---|---|---|
| Step cap | Everything (eventually) | Slow (up to the cap) |
| Cost cap | Expensive loops | Medium (depends on per-turn cost) |
| Doom-loop detector | Repetitive loops | Fast (within the window) |
| User interrupt | Anything the user notices | Manual |

Layer all four. The doom-loop detector is the early-warning system; the
caps are the backstops.

## Legitimate Retry vs Doom Loop

Not every repeated tool call is a doom loop. The detector must
distinguish:

| Legitimate retry | Doom loop |
|---|---|
| Same tool, same args, but the tool was retried after a transient failure | Same tool, same args, the tool succeeded, the model calls it again |
| Same tool, slightly different args (the model is searching) | Same tool, identical args, in a tight cycle |
| Two tools alternating but each call makes progress (read → edit → read shows the edit worked) | Two tools alternating with no progress (read → edit → read shows the edit did nothing) |

The detector checks **progress**, not just repetition. For the tool-pair
case, the harness compares the tool results between cycles: if they are
identical, it is a doom loop; if they differ, the agent is making
progress.

## Worked Example: The Apology Loop

A common failure mode:

```
Turn 1: model calls tool X (fails)
Turn 2: "Sorry, let me try again." → calls tool X (same args, fails)
Turn 3: "I apologize for the confusion." → calls tool X (same args, fails)
Turn 4: "Let me try a different approach." → calls tool X (same args, fails)
Turn 5: step cap
```

The apology text changes each turn, but the tool call is identical. The
detector catches this on turn 3 (3 identical tool signatures), surfaces
to the model ("you have called X with the same arguments 3 times and
it has failed each time; try a different tool or args"), and either
the model adjusts or the harness stops.

## Tuning

| Parameter | Default | Tighten to | Loosen to |
|---|---|---|---|
| Window size | 5 turns | 3 (aggressive) | 10 (conservative) |
| Exact-repeat threshold | 3 | 2 | 5 |
| Cycle threshold | 4 | 4 (already tight) | 6 |
| Apology-text detection | On | On (always) | Off (risky) |

Tightening catches loops sooner but risks false positives on legitimate
retry patterns (e.g., a search agent that legitimately issues the same
query across multiple sources). Loosen for exploratory agents;
tighten for execution agents.

## Pitfalls

1. **No detector.** The agent loops until the step cap; tokens wasted.
   Fix: enable the detector with the default window.
2. **Silent kill.** The detector fires; the run stops; the user does
   not know why. Fix: surface the detection to the model first; stop
   only if the loop persists.
3. **False positives on exploratory agents.** The detector flags a
   search agent's repeated queries. Fix: loosen the window or tune the
   progress check.
4. **No progress check on tool-pair cycles.** The detector flags
   read → edit → read even though the edit changed the file. Fix:
   compare tool results between cycles before flagging.
5. **Apology text not detected.** The model apologizes but the tool
   call differs slightly; the detector misses it. Fix: also check for
   apology language in the text-only turns, not just tool-call
   signatures.
6. **Detector that never fires.** Thresholds too loose; the agent
   loops until the step cap anyway. Fix: monitor how often the
   detector fires; tune if it never does.
