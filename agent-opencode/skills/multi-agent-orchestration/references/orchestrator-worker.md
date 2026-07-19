# Orchestrator-Worker Pattern

An orchestrator decomposes a mission into proof-bearing phases, routes each phase to the right worker, carries artifacts between phases, and blocks unsafe operations until the required gate is satisfied. It should not do the worker's job unless the task is too small to delegate.

## Delegate or Do It Inline

Delegate when the task has a clear specialist role, produces a verifiable artifact, needs independent review, is long-running, or benefits from context isolation. Do it inline when it is a question, a tiny edit, or a short sequence where coordination overhead is larger than the work.

The orchestrator's temptation is to "help" by doing worker jobs directly. Resist it: every time the orchestrator executes a phase, it loses the verification property that makes the pattern valuable. The orchestrator decomposes, dispatches, verifies, and synthesizes — it does not implement. The exception is genuinely tiny steps (a one-line config tweak, a single lookup) where spawning a worker costs more than the work itself. When in doubt, ask: *does this step produce an artifact another phase depends on?* If yes, it is a delegated phase; if no, it may be inline.

## Decomposition Rules

1. Identify phases that each produce a verifiable artifact.
2. Assign exactly one owner per phase.
3. State the proof contract before dispatch.
4. Prefer fewer meaningful phases over many tiny tasks.
5. Carry forward artifacts, not vague summaries.

### Worked Sequence

Concretely, a mission moves through decompose → dispatch → verify → synthesize. Using "ship a migration with rollback and review" as the running example:

1. **Decompose.** The orchestrator splits the mission into proof-bearing phases and names one owner each: `schema_change` (owner: DB worker, proof: migration diff + dry-run output), `app_patch` (owner: app worker, proof: diff + test pass counts), `review` (owner: read-only reviewer, proof: cited findings + severity), `rollback_plan` (owner: ops worker, proof: decision artifact with kill criteria).
2. **Dispatch.** Each worker receives its inputs, constraints, tool policy, and budget. The DB worker gets write access only to the migration file; the reviewer gets read-only access and no network.
3. **Verify.** The orchestrator reads each artifact directly — the diff, the test output, the cited findings — rather than trusting "done." If `app_patch` reports success but no test counts, the phase is incomplete.
4. **Synthesize.** The orchestrator carries the verified artifacts forward, resolves conflicts (e.g., the reviewer flags a risk the rollback plan must cover), and records the final decision and gate status on the persisted board.

If any phase cannot state its proof contract up front, the decomposition is not finished. Go back and split further until every phase names its artifact.

## Proof Contract

Every delegated task returns at least one of:

| Artifact | Examples |
|---|---|
| `diff` | Patch, changed files, migration. |
| `tests` | Command, exit status, passed/failed counts, relevant log. |
| `evidence` | Screenshot, API response, log excerpt, benchmark output. |
| `report` | Findings with file:line citations or source links. |
| `decision` | Recommendation with alternatives, risks, and kill criteria. |

The full proof-contract discipline lives in `deterministic-agents/references/proof-contracts.md`.

## Greenlight Gates

Destructive, publishing, merge, external-send, credential, billing, or permission changes need a preview and explicit approval. Batch destructive operations require a classified preview list and exclusions before execution.

A gate has three parts: a **preview** (what will change, classified by risk), an **exclusion list** (what must not be touched), and an **approval signal** (explicit human or policy approval). The orchestrator blocks the apply step until approval is recorded. Example (pseudocode, illustrative):

```
gate = {
  phase: "apply_migration",
  preview: [{ action: "DROP COLUMN legacy_flag", risk: "high" }],
  exclusions: ["production_users", "billing_ledger"],
  approved: false,        # flips to true on explicit approval
  requires: ["human", "rollback_plan_present"]
}
# orchestrator refuses to dispatch apply_migration until gate.approved
```

## Large Output Handling

Ask workers to write large artifacts to files and return a short manifest. Output truncation corrupts conclusions; a truncated report is not evidence. Bound scope and split large research tasks into smaller artifacts.

The rule is mechanical: if a worker's output is large enough that the parent might only see a truncated tail, the worker must write the full artifact to a file and return a manifest (path, size, line count, top-N summary). The parent then reads the file when it needs detail and reads only the manifest for routing decisions. This is also what makes verification possible — you cannot reproduce a finding from a truncated log excerpt, but you can from a saved file with a cited line range.

## State

In-process orchestration state disappears on restart. Long missions need a persisted board, queue, issue tracker, or state file containing phase, owner, artifact path, verifier status, and next action. In Claude Code, persist this to a project file (e.g. a JSON state file under `.claude/` or the repo) rather than holding it only in conversation context.

A minimal board record (pseudocode, illustrative):

```
{
  "mission": "ship-feature-x-behind-flag",
  "phases": [
    {
      "name": "impl",
      "owner": "worker-A",
      "status": "verified",          # pending | running | verified | blocked | failed
      "artifact": "repo/branches/feature-x.diff",
      "proof": "diff",
      "next_action": "hand to reviewer"
    }
  ],
  "current_gate": "review",
  "updated_at": "2026-07-12T12:00:00Z"
}
```

The orchestrator reads and writes this board at every phase transition. If a process dies mid-mission, the next run resumes from the last recorded phase instead of restarting from scratch — provided every phase wrote its status and artifact path before yielding.

## Failure Modes

| Symptom | Root cause | Fix |
|---|---|---|
| Delegation overhead dominates | Task too small to delegate | Do it inline; fold the step into the parent |
| Worker says "done" with no artifact | Missing proof contract | Re-dispatch with an explicit `diff`/`tests`/`evidence`/`report`/`decision` requirement |
| Worker never returns | No timeout or retry policy | Set max-turns and wall-clock timeout; record on the board |
| Destructive batch applied unreviewed | No preview gate | Require classified preview + exclusions + approval before apply |
| Mission restarts from zero | State held only in conversation | Persist the board to a project file at every transition |
| Parent mis-summarizes a worker's report | Summaries substituted for artifacts | Carry the artifact path forward; the orchestrator reads the file, not a paraphrase |
| Two phases write the same artifact | Ambiguous ownership | Assign exactly one owner per phase; enforce in the board |

The last row is the most common silent failure: a parent paraphrases a worker's findings and the paraphrase is wrong, and every downstream phase acts on the paraphrase rather than the source. The rule is mechanical — if the parent did not read the artifact file, the synthesis step is not done.

