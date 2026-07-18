---
description: Run SAST/Secret-Detection on a CE project and surface findings from the raw artifact
argument-hint: <project> [ref]
---

Run security scanning on **$ARGUMENTS** and report findings. On GitLab **CE/Free** the scan
jobs run for free but findings never appear in the MR widget or a dashboard (those are
Ultimate) — so the recipe is: run the template, then **parse the raw job artifact**. Read
`references/ce-vs-ee-and-security.md` first.

1. Check the CI config: `read_file(project, ".gitlab-ci.yml", ref)`. Confirm it includes
   `Security/SAST.gitlab-ci.yml` and/or `Security/Secret-Detection.gitlab-ci.yml`
   (`include: - template: ...`). If missing, propose adding them (show the diff, get approval,
   then `write_files(..., confirm=true)`) — note Dependency-Scanning/DAST are NOT available on CE.
2. Trigger a pipeline on the ref: `pipelines(project, action="create", params={"ref": <ref>})`
   (confirm=true), or use the latest: `pipelines(project, action="latest", params={"ref": <ref>})`.
3. Wait for the scan jobs: `jobs(project, action="list_pipeline", ...)` — find the `sast` /
   `secret_detection` jobs; poll until `success`.
4. Pull the findings artifact: `jobs(project, action="artifacts", ...)` for that job (the SAST
   report is `gl-sast-report.json`, secret detection `gl-secret-detection-report.json` — SARIF/
   JSON). If the curated tool can't fetch the single file, use `gitlab_rest("GET",
   "/projects/:id/jobs/:job_id/artifacts/gl-sast-report.json")`.
5. Parse the report's `vulnerabilities[]` (severity, name, location.file/line, identifiers) and
   present a ranked summary. Offer to open issues for the high-severity findings
   (`manage_issue(..., action="create", confirm=true)`) — with approval.

Be explicit that this is the CE path (artifact parsing), not the Ultimate vulnerability dashboard.
