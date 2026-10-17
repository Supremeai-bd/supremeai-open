# SupremeAI Infrastructure Guardian — AGENTS.md

> **Target Repository:** `Supremeai-bd/supremeai-infrastructure`
> **SSOT Domain:** Cloud & Deployment Platform, Multi-Satellite Health Watchdog, Docker Sandbox Profiles, Actions Quota Monitor, Disaster Recovery Automations.
> **Constitutional Reference:** [`AGENT_RULES.md`](../AGENT_RULES.md)

## Operational Boundaries

1. **Zero Secret Leaks:** Never commit master vault keys, production SSH credentials, or live database connection strings. All automation scripts rely strictly on environment variable injection and secure parameter vaults.
2. **Fail-Closed Disaster Recovery:** DR rollback routines must abort immediately if checksum verification or health probing fails.
3. **Actions Runner Quota Conservation:** Adhere strictly to the Free-org 2,000 min/month quota policy (`docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`). Never allow unchecked parallel matrix explosions or hanging daemon jobs.
4. **Hardened Execution Sandboxes:** Community pull request validations and bridge patch evaluations must execute within isolated, non-root, read-only rootfs containers.
