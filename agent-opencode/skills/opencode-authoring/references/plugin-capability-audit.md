# Plugin Capability Audit

Before converting any plugin into another host, inventory its six component
axes and derive a capability profile. Then map the profile to a target agent
type — or honestly recommend "don't convert".

## The Six Axes

1. **Skills.** Procedural knowledge triggered by description. Count, depth,
   and trigger quality.
2. **Commands.** User-invoked workflows. Argument shape, side effects,
   dependencies on other commands.
3. **Subagents.** Isolated specialists. Tool grants, model tiers, prompt
   defense, output contracts.
4. **Hooks.** Deterministic enforcement. Event types, decision logic,
   failure modes.
5. **MCP servers.** External tools. Tool schemas, auth, transport.
6. **Plugin manifest and config.** Packaging, versioning, dependencies.

## Capability Profile

For each axis, record:

- What the component does.
- What host-specific behavior it depends on.
- The fidelity cost of porting it (low / medium / high).

## Target Mapping

- Profile fits OpenCode's native surfaces → Strategy C translation.
- Profile is mostly skills and references → Strategy B portable rehost is
  viable.
- Profile is heavily host-specific (plugin manifest, hook wire protocol,
  path placeholders) → Strategy A SDK-native rewrite or "don't convert".

## Honest "Don't Convert" Verdict

Recommend not converting when:

- An existing OpenCode built-in or MCP server covers the capability.
- The capability is a single `AGENTS.md` rule or a small skill.
- The cost of porting exceeds the cost of rebuilding from the doctrine.
- The plugin's value is tightly coupled to the source host's UX (slash
  namespaces, managed settings, permission UI).

State the verdict explicitly with evidence; do not soft-pedal it.
