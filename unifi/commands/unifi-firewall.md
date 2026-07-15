---
description: Review firewall/security posture — zone policies, traffic rules, port forwards, exposure
argument-hint: (optional) focus, e.g. "port forwards" or a rule name
---

# UniFi firewall & security review

Review the security posture using the `unifi` MCP tools. **Read-only** — propose,
don't change.

1. **Firewall policies** — `unifi_firewall_policies` (this console uses the
   zone-based v2 firewall; classic `unifi_firewall_rules` is usually empty).
   Summarize by zone pair and action; highlight any **allow** rules from WAN/untrust
   into the LAN.
2. **Firewall groups** — `unifi_firewall_groups` for referenced address/port sets.
3. **Traffic rules** — `unifi_traffic_rules`: list block/allow rules (apps/domains),
   noting which are disabled.
4. **Port forwards** — `unifi_port_forwards`: every rule that exposes an internal
   host to the internet. Flag each with the WAN port, target, and whether it's
   enabled — this is the primary external attack surface.
5. **Exposure sanity** — from `unifi_status`, note the WAN IP and whether any admin
   service looks internet-exposed.
6. If `$ARGUMENTS` narrows the focus (e.g. "port forwards"), weight the report there.

## Output

Lead with a posture verdict (**Solid / Review recommended / Concerning**). List open
port-forwards and any WAN→LAN allows prominently, each with a recommendation. Keep
it factual — do not modify any rule without explicit user confirmation, and warn
that firewall/port-forward changes can lock out remote access.
