---
description: Storage & capacity report for the Unraid array (disks, parity, shares)
argument-hint: (optional) a focus, e.g. "parity" or "shares"
---

# Unraid storage report

Give a clear picture of array health and capacity using the `unraid` MCP
tools. Read-only unless the user explicitly asks to change something.

1. **Array state** — `unraid_array`: overall `state` (STARTED/STOPPED/...),
   total capacity used vs free (convert `capacity.kilobytes` to human units —
   despite the field name being "kilobytes" it holds the numbers documented
   as such), parity disk(s), data disks, cache disk(s), and current
   `parityCheckStatus` (report `running`/`paused` state and `progress` % if
   a check is in flight).
2. **Disk health** — `unraid_disks` for the full physical inventory
   (including unassigned/spare disks): flag any `smartStatus` that isn't
   `OK`, and report the hottest disk's temperature. Cross-reference against
   `unraid_array`'s per-disk `status` (anything other than `DISK_OK` needs a
   note).
3. **Assignable disks** — `unraid_assignable_disks` if the user is asking
   about expanding the array or adding a cache disk — these are the
   disks currently eligible to be added.
4. **Parity history** — `unraid_parity_history` for past check results
   (duration, errors, whether correcting). An empty list just means no check
   has run yet — say that plainly, don't call it an error.
5. **Shares** — `unraid_shares` for per-share free/used and cache setting.

## Changing the array

Only if the user explicitly asks:
- **Starting/stopping the array** (`unraid_array_set_state`) is the most
  disruptive action this plugin exposes — stopping unmounts every disk,
  taking every array-backed share/container/VM offline. Confirm the specific
  intent (not just "yes, do it") before calling with `confirm=True`.
- **Adding/removing a disk** (`unraid_array_disk_add`/`_remove`) changes the
  array layout and generally requires the array to be stopped first — check
  `unraid_array`'s `state` and tell the user if it needs stopping first
  rather than trying to force it.
- **Starting a parity check** (`unraid_parity_check(action="start", confirm=True)`)
  is a multi-hour, I/O-intensive operation — confirm the user actually wants
  it now, not just that they're curious about parity checks.

## Output

Lead with a verdict: **Healthy / Needs attention / Critical**, then the
sections above. Put anything abnormal (degraded disk, low free space, failed
parity check) at the top with a concrete next step.
