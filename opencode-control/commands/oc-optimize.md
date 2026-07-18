---
description: Audit and optimize the opencode config (models, cost, permissions, agents, rules)
---

Audit the user's opencode configuration and propose an optimization pass. Read
`references/configuring-opencode.md` and `references/agents-and-workflows.md` first.

1. Gather: `oc_config_get('merged')`, `oc_providers`, `oc_models`, `oc_agents`.
2. Evaluate against the optimization playbook:
   - **Cost/models**: is `small_model` set to something cheap? Are unused providers trimmed
     via `disabled_providers`/`enabled_providers` (e.g. openrouter's 340 models)? Do cheap
     read-only agents use a small model while `build` gets the capable one?
   - **Secrets**: any plaintext API keys in `provider.*.options.apiKey` that should become
     `{env:...}`?
   - **Permissions**: are safe commands (`git *`, `npm run *`) `allow` and dangerous ones
     (`rm *`, `git push *`) `deny`, so routine work isn't interrupted?
   - **Rules**: is there an `AGENTS.md`? Useful `instructions` globs?
   - **Context hygiene**: `compaction`, `tool_output` limits for long sessions.
3. Present findings as a short table (issue → suggested change).
4. Build a single deep-merge `patch` and **show it to the user**. On approval,
   `oc_config_update(patch, confirm=true, scope='global')`. For key **removals** (merge
   can't delete), edit the config file directly instead.
5. Confirm with `oc_config_get` and summarize what changed. Never apply without approval.
