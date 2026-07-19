# Security Policy

## Supported versions
<!-- List the versions / branches currently receiving security fixes. -->

| Version | Branch | Supported |
| ------- | ------ | --------- |
| latest  | main   | ✅         |
| <prev>  | <rel/x>| ✅ / ❌     |

## Reporting a vulnerability
**Do NOT open a public issue for a suspected vulnerability.** Instead:

1. Email **<security@example.invalid>** with a description, reproduction steps,
   and impact assessment.
2. You'll receive an acknowledgement within **<2 business days**.
3. We'll coordinate a fix + disclosure timeline with you. Valid reports are
   credited (with your permission) in the release notes.

Please **do not** run active exploits, scanners, or social-engineering against
the production instance. See the responsible-disclosure scope below.

## Scope
- This repository's source code and the deployed instance at
  `<https://example.invalid>`.
- The CI/CD pipeline configuration in this repo.

## Out of scope
- Third-party hosted services we depend on (report to them directly).
- Findings from automated scanners without a working exploit.
- Self-XSS, clickjacking on non-authenticated pages, missing security headers
  on marketing pages.
- Issues requiring physical access to a developer's machine.

## Disclosure
We follow coordinated disclosure: a fix lands first, then a public advisory
(with credit) after a reasonable window (typically 90 days or after a fix
release, whichever comes first).
