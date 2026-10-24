# Security Policy

## Supported Versions

SupremeAI deploys continuously from `main` — every merged PR is built and released by CI. Security fixes land on `main` and roll out to the running deployment automatically, so only the latest revision is supported:

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `main` (latest deploy) | ✅ | All security fixes target this branch |
| Older revisions / tags | ❌ | Upgrade to the latest `main` deploy |

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

Report privately via **[GitHub Private Vulnerability Reporting](https://github.com/SaifulHaqueNiloy/supremeai/security/advisories/new)**. This notifies the maintainer directly and keeps the details confidential until a fix ships.

When reporting, please include (where applicable):

- Affected component and path (`backend/…`, `frontend/…`, `infrastructure/…`, workflow file, …)
- Impact assessment — especially anything crossing **tenant boundaries** (`tenant_id`) or exposing secrets
- Reproduction steps or a minimal proof of concept
- Suggested remediation, if you have one

## Response Targets (SLA)

| Severity | First response | Fix target |
| :--- | :--- | :--- |
| Critical (auth bypass, secret exposure, RCE) | ≤ 48 hours | ≤ 7 days |
| High (privilege escalation, injection, tenant isolation) | ≤ 72 hours | ≤ 14 days |
| Medium / Low | Best effort | Next regular cycle |

Maintainers may publish an advisory and credit reporters after the fix is deployed.

## Out of Scope

- Volumetric / application-level DoS without an identified root cause
- Social engineering of hosting providers (Render, Cloudflare, Supabase, Infisical, …)
- Issues in third-party services themselves — report those to the vendor
- Findings that require an already-compromised machine (local malware, root on user devices)
- Missing security headers on purely static documentation pages

## Security Engineering Baseline

For contributors — the repo enforces (and PR gates audit):

- **No Claim, No Code** (`AGENTS.md`) — every change lands via a claimed, referenced issue
- **Fail-closed secrets** — `ENCRYPTION_KEY`/`SUPREMEAI_JWT_SECRET` must be set in production; ephemeral keys are test/CI-only
- **Token transport** — JWTs ship as `httpOnly` cookies (`SameSite=Lax`, CSRF double-submit); JS-readable storage is being phased out
- **Tenant isolation** — every DB/API operation enforces `tenant_id`
- **Sandbox hardening** — AST validation before any sandboxed code execution; no network in sandboxed containers
