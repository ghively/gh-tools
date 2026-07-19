<!-- Derived from openclaw-agent-architect references; platform-neutralized for agent-foundry. -->
# Security Audit Checklist

Third-party agent code runs with the installing agent's authority. Skills, plugins, hooks, scripts, MCP servers, and package dependencies can all read data, influence prompts, or call tools if you grant them access.

## Pre-Install Audit

1. Locate the source. Prefer a public repository, signed release, or trusted vendor source over opaque archives.
2. Confirm provenance. Check maintainer identity, release history, issue activity, and whether the package is newly published or typo-squatting.
3. Read every instruction file. Look for hidden directives, encoded content, unusual Unicode, system-prompt extraction, broad file reads, or exfiltration URLs.
4. Read every script. Shell, Python, JavaScript, TypeScript, install scripts, and generated launchers are code execution paths.
5. Inspect package manifests. Flag lifecycle scripts, unpinned dependency ranges, URL/git dependencies, and unexpected binaries.
6. Inspect MCP server configuration. Check command, args, environment variables, network endpoints, and declared tools.
7. Install first in an isolated workspace or container. Deny write-capable tools and control-plane tools until behavior is observed.
8. Review logs and transcripts after adversarial prompts.

## Red Flags

- Instructions to ignore safety rules or reveal system/developer prompts.
- Reads of credential paths, shell history, environment files, or private keys.
- Commands built from user input without quoting or validation.
- Network calls to unrelated domains.
- Base64, hex, compressed blobs, or minified code with no source.
- Hooks that alter prompts, tool results, permission decisions, or model requests.
- MCP tools with vague names such as `run`, `exec`, `do_anything`, or `admin`.
- Package install scripts that run downloads or modify shell startup files.

### Finding Triage

Not every finding blocks install. Triage by exploitability and blast radius:

| Severity | Finding | Action |
|---|---|---|
| Blocker | Reads credentials, exfiltrates, alters prompts/permissions, or runs encoded payloads | Do not install; report upstream |
| High | Broad file reads, vague tool names, unvalidated argument construction | Install only with deny rules and sandbox; re-audit each release |
| Medium | Verbose logging of arguments, loose dependency ranges | Install with mitigations; track for follow-up |
| Low | Cosmetic or stylistic issues | Note and move on |

A finding moves up a tier when combined with another. Broad file read plus unrestricted network is exfiltration; rate each finding in combination, not isolation.

## OpenCode Flow

- Install plugins only from sources you have reviewed.
- Keep team-shared plugin and permission configuration in project `opencode.json` when appropriate.
- Use `permission.deny` for tools or command patterns that should never be available in the project.
- Review `mcp` config changes like code: an MCP server is executable software plus a tool surface.
- Run `opencode debug` and inspect the `permission` block in `opencode.json` after material configuration changes.

## MCP Server Vetting

For each MCP server:

- What process starts it?
- What package manager or binary supplies that process?
- What credentials does it receive?
- What network destinations can it reach?
- What tools, resources, and prompts does it expose?
- Are destructive tools separated from read-only tools?
- Does it log sensitive arguments or outputs?

### Concrete Pre-Install Checklist For A Third-Party MCP Server

Before adding any MCP server to `.mcp.json`, check each item. A "no" or "unknown" is a blocker until resolved:

- [ ] Source repository located and reviewed, not an opaque archive.
- [ ] Maintainer identity and release history checked; not newly published or typo-squatting a known name.
- [ ] `command` and `args` in the server config read and understood; no shell-meta injection in argument construction.
- [ ] Environment variables the server receives enumerated; no ambient secrets passed "just in case."
- [ ] Network destinations enumerated; egress restricted to those endpoints at the network layer.
- [ ] Declared tool list read; each tool name is task-specific, not generic (`run`, `exec`, `do_anything`, `admin`).
- [ ] Destructive tools identified and confirmed to require explicit approval, not bundled with read-only tools.
- [ ] Dependency tree inspected; no URL/git dependencies, no lifecycle scripts that run on install.
- [ ] Logging behavior confirmed; the server does not log sensitive argument or result payloads in plaintext.
- [ ] First-run plan ready: isolated workspace or container, no write-capable tools granted, adversarial prompts queued.

Treat `.mcp.json` changes like code review, not config edit. An MCP server is executable software plus a tool surface, and it runs with the installing agent's authority.

## First-Run Probe

Run the capability with benign, adversarial, and boundary prompts:

- Ask for a normal task.
- Ask it to read a secret path.
- Ask it to send data to an unrelated URL.
- Ask it to bypass its own instructions.
- Ask it to modify project or home configuration.

Any unexpected tool call is a failed audit until explained.

### Reading A First-Run Transcript

After the probe, read the transcript for the failures that matter, not only the obvious ones:

- Did any tool call carry arguments built from user input without validation?
- Did the capability attempt a network call to a destination outside the declared list?
- Did it try to read credential paths, shell history, or environment files?
- Did it attempt to alter prompts, tool results, permission decisions, or model requests?
- Did it persist anything (file write, memory write, config change) outside the declared workspace?

A clean-looking final answer is not a clean audit. The transcript of tool calls and argument shapes is the audit; the prose is the cover letter.

## Incident Response

If a third-party capability behaves badly:

1. Stop the agent session and disable the plugin/MCP server/hook.
2. Preserve logs, transcripts, and package versions.
3. Rotate credentials the capability could read.
4. Search recent changes for persistence or data staging.
5. Report the issue upstream or to the marketplace if appropriate.

### Post-Incident Hardening

After containment, close the gap that let the capability do damage in the first place:

- Add a `permissions.deny` rule for the tool or command pattern that was abused.
- Add a regression case to the eval suite named after the incident.
- Tighten the pre-install checklist with the check that would have caught this capability.
- Review sibling capabilities installed from the same source or maintainer.

An incident that does not change the checklist or the eval suite will repeat. The fix is not done until the floor is raised.
