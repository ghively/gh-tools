# langgraph-starter

A minimal LangGraph project showing the two things you pick LangGraph *for*
(see the framework-landscape decision table): an explicit graph state machine
with checkpointing, and a human-in-the-loop interrupt that survives process
death. If you don't need those, the Claude Agent SDK starters next door are
less machinery.

The graph:

```
START ─► triage ─► (needs approval?) ─► approve [INTERRUPT] ─► act ─► END
                └─────────── no ─────────────────────────────► act ─► END
```

- **triage** classifies the request and drafts the action (LLM step).
- **approve** is an interrupt node: the graph checkpoints and STOPS; a human
  resumes it later — hours later, different process — with a verdict.
- **act** executes only what triage drafted and approval allowed.

## Run

```bash
pip install -U langgraph langchain-anthropic
export ANTHROPIC_API_KEY=...
python src/graph.py "archive all issues older than a year"
# prints the draft + thread id, then exits at the interrupt
python src/graph.py --resume <thread-id> --approve
```

## Where to go from here

- Swap `InMemorySaver` for a persistent checkpointer (SQLite/Postgres) before
  relying on cross-process resume — InMemorySaver dies with the process.
- The approval payload printed at the interrupt follows the 30-second rule
  from `agent-design`'s human-in-the-loop reference: action, blast radius,
  why, and what "no" does.
- Evals: the eval-suite template in `agent-evals` assets; governance case #1
  is "the gate holds under pressure."

API surface last verified: 2026-07 against langgraph 1.2.x (1.0 GA since
Oct 2025; pre-1.0 lines are no longer supported). Check the
langgraph-quickstart reference's banner if imports fail.
