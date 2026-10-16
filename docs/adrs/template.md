# ADR Template

> Copy this file to `ADR-NNN-<SLUG>.md` (zero-padded, uppercase slug) and fill
> every section. An ADR records a **decision that is hard to reverse** —
> architecture, governance, boundary, or contract-level choices. Operational
> bug fixes and routine features do not get ADRs.

```markdown
---
id: adr-NNN-<slug>
title: "<short decision title>"
document_role: adr
status: proposed | accepted | superseded-by-ADR-MMM | rejected
canonical: false
decided: YYYY-MM-DD
deciders: "<who/which lane had authority>"
governing_issue: <issue number>
related_docs:
  - <relative paths>
---

# ADR-NNN: <title>

## Status

<proposed | accepted | superseded-by-ADR-MMM | rejected> — <date>, <deciders>.

## Context

What forces are in play — technical, political, organizational? What problem
were we solving, and what made it hard? State facts with evidence pointers
(issues, audits, measurements). No solution talk here.

## Decision Drivers

- <driver 1 — e.g. quota, security boundary, determinism, zero-admin budget>
- <driver 2>

## Considered Options

1. **<Option A>** — <pros / cons>
2. **<Option B>** — <pros / cons>
3. **<Option C (CHOSEN)>** — <pros / cons, and why it beat the others>

## Decision

<The decision itself, stated in one or two unambiguous sentences.>

## Consequences

**Positive:** <what becomes easier/possible>

**Negative / accepted costs:** <what becomes harder, and why it is acceptable>

**Neutral:** <follow-up work this obligates>

## Validation Evidence

<How we know the decision works: guard names, verification tiers, measured
results, live PR evidence. Fail-closed doctrine applies — an ADR that cannot
be validated should say so honestly (U2).>

## Related Documents

- [<doc>](<relative link>) — <one-line role>
```

## Rules for this repository's ADRs

1. **Numbering:** sequential `ADR-001`, `ADR-002`, … — never reused, never renumbered. Superseding creates a new ADR that flips the old one's `status` to `superseded-by-ADR-MMM` (both stay).
2. **Immutability:** an accepted ADR is a historical record. Corrections land as new ADRs, not edits (except front-matter `status` flips and typo fixes that do not change meaning).
3. **Evidence:** every ADR must cite its enforcement/validation surfaces — the guards, gates, or measurements that keep the decision true over time.
4. **Scope:** boundary/governance decisions ultimately belong to the admin (AGENTS.md §1.3/§4). Agent-authored ADRs document decisions already enacted by a governing issue or an admin directive — they record and cross-reference authority, they do not invent it.
5. **Index:** every new ADR is added to the [README index](./README.md) in the same PR.
