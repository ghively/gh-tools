---
description: Full health check of the Synology NAS (system, storage, disks, security, updates, logs)
argument-hint: (optional) an area to focus on, e.g. "storage" or "security"
---

# Synology health check

Produce a concise health report for the Synology NAS using the `synology` MCP tools.
If `$ARGUMENTS` names a focus area, weight the report toward it, but always cover
the safety-critical basics (storage + disks).

Gather the data efficiently, then summarize. Prefer `synology_batch` to pull several
reads in one round-trip where possible.

1. **Identity & uptime** — `synology_status` (model, DSM version, uptime, temperature).
2. **Storage** — `synology_storage`. Flag any volume whose status is not `normal`
   (e.g. `attention`/`degraded`) and report % used per volume. Convert bytes to TB/GB.
3. **Disks / SMART** — from the same call, list any disk not `normal` and note the
   hottest disk temperature.
4. **Load** — `synology_utilization` for current CPU load and memory usage.
5. **Packages/services** — `synology_packages_list`; flag any expected package that
   is **not** `running`.
6. **Security** — `synology_firewall_status` for firewall state, and
   `synology_call(api="SYNO.Core.SecurityScan.Status", method="system_get")` for the
   last security scan status.
7. **DSM updates** — `synology_dsm_update_check`; report if an update is available.
8. **Recent errors** — `synology_logs(limit=30)`; summarize error/warning counts and
   the most recent notable entries.

## Output

Lead with an overall verdict: **Healthy / Needs attention / Critical**. Then a short
bulleted summary grouped by the sections above. Put anything abnormal at the top with
a concrete recommended action. Do not make any changes — this is read-only.
