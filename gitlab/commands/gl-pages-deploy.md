---
description: Configure GitLab Pages for a project — settings, custom domain, SSL, force-HTTPS
argument-hint: <project> [domain] [cert-path key-path]
---

Deploy/configure **$ARGUMENTS** Pages site. Read `references/projects-repo-mrs-issues.md` and
`references/admin-and-self-hosting.md`. Pages must be enabled at the instance level
(`admin_settings(action="get")` → `pages_domain_verification_enabled` etc.) — if 404s, that's
the cause, not a bug.

1. **Inspect current state (read-only)**: `pages(project, action="get")` — is Pages enabled for
   this project? What's the current URL (`https://<ns>.pages.example.io/<proj>` shape)? Is there
   a deploy? `pages(project, action="domains")` for existing custom domains.
2. **Enable Pages if needed**: `manage_project(action="update", project=..., params={
   pages_access_level: 30}, confirm=true)` (or `40`/`50` for restrict-to-members/owners; `20`
   for public-only). Note: actual deployment happens when a Pages-matching artifact is produced
   by a CI job (see `templates/ci/pages-static.yml`).
3. **Custom domain** (if `domain` given): `pages(project, action="domain_create", domain=...,
   params={domain: <domain>, auto_ssl_enabled: true}, confirm=true)` for Let's Encrypt auto-SSL
   (requires instance Pages SSL config); OR provide `certificate` + `key` params from the given
   cert/key file paths for a manual cert.
4. **Verify domain ownership**: GitLab returns a TXT verification record — output it and tell
   the user to add it to DNS. After DNS propagates, `pages(project, action="domain_get",
   domain=...)` shows `verified: true`.
5. **Force HTTPS** (instance-wide or project): `pages(project, action="update", params={
   https_only: true}, confirm=true)` if exposed at project level; otherwise it's
   `admin_settings(action="update", params={pages_https_only: ...}, confirm=true)` (instance-
   wide — confirm scope with the user first).
6. **Verify**: re-`pages(project, action="get")` + `pages(project, action="domains")` — confirm
   the site URL, domain verification status, SSL state. Visit the URL (or curl) to confirm 200.
7. **Report**: Pages URL, custom domain + verification/SSL status, access level, and the CI
   job/artifact that drives redeployment.

Pages quirks: unique-domain (`use_unique_domain`) is per-project; the instance domain must be
configured by an admin (in `admin_settings`); auto-SSL needs port 80 reachable for the ACME
challenge. If the deploy isn't appearing, the CI job is the usual culprit — check
`pipelines` + `jobs` for the `pages` job.
