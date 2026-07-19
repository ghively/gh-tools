# Deterministic Safety Hooks

The agent-foundry plugin ships a narrow OpenCode safety floor implemented as
a TypeScript plugin registered via `opencode.json`'s `plugin` array. It is a
code-enforced layer the model cannot talk its way around.

> Note: OpenCode 1.18.3 has a known bug where local TypeScript plugins fail
> to load (`plugin config hook failed: null is not an object`). Until the
> upstream fix lands, the safety floor is delivered through OpenCode's
> native `permission` rules in `opencode.json`. The TypeScript plugin and
> its tests are retained for when the bug is fixed; both layers share the
> same block catalog and audit-log semantics.

## Shipped Plugin

Location: `agent-foundry/plugins/agent-foundry-safety/index.ts`
Registered in: `opencode.json` under `plugin`

| Hook event | Tool matchers | Purpose |
|---|---|---|
| `tool.execute.before` | `bash`, `write`, `edit`, `apply_patch` | Deny known never-run shell operations and privileged writes to protected paths |
| `tool.execute.after` | all tools (opt-in via `enableAuditTrail`) | Append bounded JSONL audit line per tool call |

OpenCode's deny mechanism is to `throw new Error("safety floor: ...")`
inside `tool.execute.before`. There is no Claude-style
`hookSpecificOutput.permissionDecision` object; a thrown error fails the
tool call deterministically.

## Safety-Floor Doctrine

- The pattern list is deliberately narrow.
- It targets operations that should never run, not judgment calls.
- It complements, not replaces, OpenCode permission rules and sandboxing.
- It fail-opens on parse or shape errors with audit logging so a broken
  hook does not silently brick normal agent operation.
- The normal OpenCode permission system (`ask`/`deny`/`allow` per tool and
  per pattern) still gates everything above this floor.

## Block Catalog

The TypeScript function `isDestructiveCommand` denies:

| Category | Rationale |
|---|---|
| Remote fetch piped to interpreter | Common RCE and exfiltration primitive |
| Remote download then execution of the downloaded file | Two-statement `curl … -o x.sh; bash x.sh` — the pipe-only rule's sibling |
| Command substitution executing a fetch | `eval $(curl…)`, `sh -c "$(wget…)"`, bare `$(curl…)` run fetched bytes as code |
| Encoded payload decoded into interpreter | Obfuscated command execution |
| `dd`, `mkfs`, block-device redirects, device `shred` | Disk and filesystem destruction |
| Root `rm -rf` and `--no-preserve-root` | Host wipe primitives |
| Fork bomb | Resource exhaustion |
| Privileged container and host namespace flags | Container escape or host-root equivalence |
| `docker run --cap-add` of an escape capability | SYS_ADMIN/SYS_MODULE/SYS_PTRACE/DAC_*/… grant container escape |
| `nsenter` into PID 1 and risky `unshare` | Host namespace escape primitives |
| Account/password modification | Identity and persistence tampering |
| Firewall flush/disable | Defense removal and exposure |
| Shutdown/reboot/poweroff/halt | Host availability impact |
| Writes to critical identity/system files | Persistence and lockout |
| SSH key/config writes | Backdoor persistence |
| `crontab` install/edit/remove | Scheduled-task persistence via the `crontab` command |
| Broad chmod on system directories | Permission weakening |
| Git `core.sshCommand` tampering | Code execution on future pulls |

The TypeScript function `isProtectedPath` denies file writes (via `write`,
`edit`, or `apply_patch`) to:

- `/etc/sudoers` and `/etc/sudoers.d/`
- `/etc/passwd`, `/etc/shadow`, `/etc/group`, `/etc/gshadow`
- `/boot/`, `/proc/`, `/sys/`
- `/etc/cron.d/`, `/etc/cron.daily/`, `/etc/cron.hourly/`, `/etc/cron.weekly/`, `/etc/cron.monthly/`
- `/etc/systemd/system/`
- `~/.ssh/`

`apply_patch` paths are parsed from the `*** Add File:`, `*** Update File:`,
`*** Delete File:`, and `*** Move to:` markers so a native patch tool
cannot bypass the write floor.

### Why Each Category Is A Never-Run Primitive

The catalog is deliberately narrow. Each category is a primitive that no
legitimate agent task should ever need; that is what makes it safe to deny
deterministically, without judgment calls.

- Remote fetch piped to interpreter and encoded-payload execution: these
  are the standard shapes of "download and run attacker code." Legitimate
  package install uses package managers, not `curl | sh`.
- Remote download then execution of the downloaded file: the pipe
  (`curl | sh`) is only the inline shape of "run attacker code." The same
  primitive split across two statements — `curl … -o /tmp/x.sh; bash
  /tmp/x.sh` — is identical in effect, so the floor ties the download path
  to the execution with a backreference.
- Command substitution executing a fetch: `eval $(curl…)`, `sh -c
  "$(wget…)"`, and a bare command-position `$(curl…)`/backtick all execute
  the fetched bytes as shell. The floor blocks exactly the executing
  contexts and deliberately leaves `V=$(curl…)` and `echo $(curl…)` alone.
- `docker run --cap-add` of an escape capability: adding `SYS_ADMIN`,
  `SYS_MODULE`, `SYS_PTRACE`/`DAC_READ_SEARCH`/`DAC_OVERRIDE`,
  `SYS_RAWIO`, `SYS_BOOT`, `BPF`, or `ALL` to a container is a host-escape
  grant, the same class as `--privileged`. Deliberately does not match
  `--cap-drop` or ordinary caps such as `NET_ADMIN`.
- `crontab` install/edit/remove: the write floor guards cron *files*
  under `/etc`, but the `crontab` command edits the user's own crontab
  without touching those paths — a persistence vector. The floor blocks
  the mutating forms and deliberately allows the read-only listing
  `crontab -l`.
- Disk and filesystem destruction: no coding task requires wiping a block
  device or the root filesystem.
- Privileged container flags, `nsenter` into PID 1, risky `unshare`:
  host-escape or host-root-equivalence primitives.
- Account/password modification, firewall disable, host power state,
  critical-file writes, SSH key writes, broad system chmod, git
  `core.sshCommand`: persistence, backdoor, or defense-removal primitives.

Anything that is sometimes legitimate — `rm` inside a workspace, package
install, deployment commands, ordinary file edits — belongs to OpenCode
permission rules and human approval, not to this floor.

## Audit Log

By default the plugin logs to
`~/.config/opencode/agent-foundry/safety-audit.log`. Override with the
`AGENT_FOUNDRY_AUDIT_LOG` environment variable for tests or managed
deployments.

Log rows include timestamp, decision, tool, and a truncated payload.
Review `BLOCK` rows for enforcement and `PARSE_ERROR_ALLOW` rows for hook
input compatibility problems. The Bash floor also logs an `allow` row for
every permitted Bash command (not just blocks) — useful for post-incident
forensics. The write floor logs only blocks.

### Using The Log In Incident Review

After an incident, the audit log is the timeline of what the agent tried:

- `BLOCK` rows show the never-run primitives the agent attempted — each
  one is a real signal of intent or compromise.
- `allow` rows reconstruct the sequence of permitted Bash commands.
- `PARSE_ERROR_ALLOW` rows show where hook input changed shape (a CLI
  upgrade, a new tool matcher); investigate clusters after version bumps.

Restrict file permissions on the log: it captures command text, which may
include secrets passed on the command line. Rotate or ship it to a central
collector if local retention is a risk.

## Safe Extension Discipline

Add a pattern only when:

- It describes a never-run primitive, not a risky operation that sometimes
  is valid.
- It has concrete test vectors.
- It does not match routine development commands.
- The deny reason tells the operator exactly what happened.

Broad patterns erode trust. If the floor blocks normal work, users disable
it and lose the real protection.

### Extension Workflow

1. Name the primitive in concrete terms (the exact command shape).
2. Confirm it is never legitimate for any agent task in this environment.
3. Write the test vector first: the exact input that should be denied,
   and a benign neighbor command that must still pass.
4. Check the pattern against a corpus of normal agent commands for false
   positives.
5. Write the deny reason so the operator can act on it without reading
   the source.
6. Land the pattern and the test vector together in `index.ts` and
   `tests/safety.test.ts`.

If step 2 fails — the operation is sometimes legitimate — it belongs in
OpenCode's `permission.ask` or `permission.deny` policy, not in this floor.

## Test Vectors

The TypeScript test suite runs against the pure decision functions
directly, then exercises the hooks via a mock client. Run with:

```bash
cd agent-foundry/plugins/agent-foundry-safety
npm test
```

The suite (`tests/safety.test.ts`) covers:

- Block vectors: `curl … | bash`, `dd of=/dev/sd*`, `rm -rf /`, `docker
  run --privileged`, `crontab -e`, `git config core.sshCommand`
- Allow vectors: `ls -la`, `git status`, `curl -o /tmp/a.tar URL`,
  `crontab -l`, `rm -rf /tmp/work`
- Protected-path denials: `/etc/sudoers`, `/etc/passwd`, `~/.ssh/…`,
  `/tmp/../etc/passwd` (normalization check)
- OpenCode-specific tools: `write`, `edit`, `apply_patch` with protected
  paths parsed from patch markers
- Optional secret check (off by default) and audit trail (off by default)
  remain opt-in

If you add a block pattern, add a paired test vector in the same change.

## The Opt-In Tier

Two more behaviors ship with this plugin but are deliberately NOT enabled
by default — the auto-loaded floor stays deny-only and minimal so nobody
is ever tempted to disable it. Enable either via the plugin options in
`opencode.json`:

```json
{
  "plugin": [
    [
      "./agent-foundry/plugins/agent-foundry-safety/index.ts",
      {
        "enableSecretCheck": true,
        "enableAuditTrail": true
      }
    ]
  ]
}
```

| Option | What it does |
|---|---|
| `enableSecretCheck: true` | Denies `write`/`edit` content containing high-confidence secret material: private key blocks, vendor-prefixed tokens (AWS/GitHub/Slack/`sk-`/Google), signed JWTs, DB URLs with passwords. Placeholder-aware — `AKIA...EXAMPLE`, `${VAR}`, `<redacted>`, truncated `...` samples pass through. |
| `enableAuditTrail: true` | Appends one bounded JSONL line per tool call (timestamp, session, tool, args) to `~/.config/opencode/agent-foundry/tool-audit.jsonl` (`AGENT_FOUNDRY_TOOL_AUDIT_LOG` to override) AND emits structured logs via `client.app.log`. Forensic trail, never blocks. |

Both follow the floor's contract: fail-open, narrow by design, tested in
the same suite. The secret scanner is opt-in rather than floor because
"looks like a credential" is a judgment call with a real false-positive
rate — the floor only holds never-legitimate operations.

## Versus Claude Code's PreToolUse Hooks

If you are porting from Claude Code:

| Claude Code | OpenCode |
|---|---|
| `hooks/hooks.json` manifest | `opencode.json` `plugin` array entry |
| `PreToolUse` event | `tool.execute.before` hook |
| `PostToolUse` event | `tool.execute.after` hook |
| `hookSpecificOutput.permissionDecision: "deny"` | `throw new Error(...)` from `tool.execute.before` |
| `matcher: "Bash"` | lowercase `input.tool === "bash"` |
| `matcher: "Write\|Edit\|MultiEdit\|NotebookEdit"` | `input.tool === "write"` / `"edit"` / `"apply_patch"` (no `MultiEdit`/`NotebookEdit` in OpenCode) |
| `${CLAUDE_PLUGIN_ROOT}` path | plugin directory is self-contained |
| `~/.claude/agent-foundry/safety-audit.log` | `~/.config/opencode/agent-foundry/safety-audit.log` |
| Python script via stdin/stdout JSON | TypeScript function with `(input, output)` arguments |
| `settings.json` permission rules | `opencode.json` `permission` block |

The doctrine (narrow, never-legitimate primitives, fail-open on parser
errors, audit everything) carries over unchanged.
