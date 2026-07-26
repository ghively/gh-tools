---
description: Storage & capacity report for the Synology NAS (volumes, disks, shares, snapshots)
argument-hint: (optional) a share or volume name to drill into
---

# Synology storage report

Use the `synology` MCP tools to report on storage. Read-only.

1. **Volumes & pools** — `synology_storage`. For each volume: filesystem, status,
   total/used/free in TB, and % used. Call out anything over 85% full and any volume
   whose status is not `normal`.
2. **Physical disks** — from the same result: per disk model, status, temperature.
   Highlight any disk that is not healthy.
3. **Shared folders** — `synology_shares_list`; list shares with their volume and note
   any that are encrypted or hidden.
4. **Snapshots (optional)** — if `$ARGUMENTS` names a share, list its snapshots via
   `synology_call(api="SYNO.Core.Share.Snapshot", method="list", params={"name":"$ARGUMENTS"})`.

If the user wants to free space, offer to run `/syno-find-large` to locate big files.

## Output
A compact table of volumes (with a used/free bar in text), a disk health line, and a
share list. Flag risks first.
