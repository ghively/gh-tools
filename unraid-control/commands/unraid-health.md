---
description: Full health check of the Unraid server (system, array, disks, Docker, notifications, UPS)
argument-hint: (optional) an area to focus on, e.g. "docker" or "array"
---

# Unraid health check

Produce a concise health report for the Unraid server using the `unraid` MCP
tools. If `$ARGUMENTS` names a focus area, weight the report toward it, but
always cover the safety-critical basics (array + disks).

Gather data efficiently — GraphQL lets you combine several reads in one
`unraid_graphql` call if you prefer, but the curated tools below are fine too.

1. **Identity & versions** — `unraid_status` (reachability, Unraid/API
   versions, array state, container counts, unread notifications).
2. **Array & disks** — `unraid_array`. Flag any disk whose `status` isn't
   `DISK_OK`, report capacity used %, and note the parity-check status if one
   is currently running. Cross-check `unraid_disks` for SMART status
   (anything not `OK`) and the hottest disk temperature.
3. **Load** — `unraid_metrics` for current CPU %, memory used %, and the
   temperature summary (flag `warningCount`/`criticalCount` > 0 and name the
   hot sensor(s)).
4. **Docker** — `unraid_docker_containers`; flag any container whose `state`
   isn't `RUNNING` when it looks like it should be (has `autoStart: true`),
   and note how many have `isUpdateAvailable: true`.
5. **VMs** — `unraid_vms`; report `available: false` plainly if the VM
   Manager is off rather than treating it as an error.
6. **UPS** — `unraid_ups`; report `connected: false` plainly if none is
   attached.
7. **Notifications** — `unraid_notifications(type="UNREAD")`; surface any
   `ALERT` importance ones verbatim (title + description), summarize
   `WARNING`/`INFO` counts.
8. **Registration** — `unraid_registration`; mention if `type` is `TRIAL`
   rather than a purchased tier.

## Output

Lead with an overall verdict: **Healthy / Needs attention / Critical**. Then
a short bulleted summary grouped by the sections above. Put anything abnormal
at the top with a concrete recommended action. Do not make any changes — this
is read-only.
