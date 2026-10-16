# Architecture Decision Records (ADR) — Index

> ADRs record the federation's **hard-to-reverse decisions**: what lives on the
> public boundary, how work lands autonomously, which contracts are frozen.
> Template and rules: [`template.md`](./template.md).

| ADR | Title | Status | Decided |
|---|---|---|---|
| [ADR-001](./ADR-001-OPEN_FOUNDATION_BOUNDARY.md) | Open Foundation Boundary — Public-First SSOT split | accepted | 2026-10-15 |

## Lifecycle

```
proposed ──> accepted ──> superseded-by-ADR-MMM
    │
    └──> rejected
```

- **proposed:** under discussion (a governing issue or admin directive exists).
- **accepted:** enacted — enforcement surfaces (guards/gates) are live or land with the ADR.
- **superseded / rejected:** never deleted; the record remains for provenance (U2 — history is immutable, the pre-push hook enforces it literally).

## Authoring quick-start

1. Copy [`template.md`](./template.md) → `ADR-NNN-<SLUG>.md` with the next free number.
2. Fill every section; cite evidence (U2) and the governing issue.
3. Add the row to the table above (same PR).
4. Run the link resolver + `python scripts/agents/continuous_agent_loop.py --verify-only` before opening the PR.

## Related Documents

- [AGENTS.md](../../AGENTS.md) — constitution; §2.3 Public-First SSOT doctrine (the decision ADR-001 records)
- [AGENT_RULES.md](../../AGENT_RULES.md) — policy contracts; U2 evidence, U6 safety
- [docs/INGRESS_SECURITY_POLICY.md](../INGRESS_SECURITY_POLICY.md) — enforcement surface of the boundary decision
- [docs/AGENT_PORTAL_SPEC.md](../AGENT_PORTAL_SPEC.md) — the machinery that executes the boundary
- [docs/ZERO_ADMIN_GUIDE.md](../ZERO_ADMIN_GUIDE.md) — how ADR PRs land autonomously
