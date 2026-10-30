#!/usr/bin/env python3
"""DEPRECATED tombstone (#3573) — the loop's rotation API lives in continuous_agent_loop.py.

This module previously duplicated the loop's 12h/24h `cadences_hours` role-gate
SSOT (DEFAULT_CADENCE_HOURS / load_cadence_config / role_is_due / due_roles /
mark_role_run) plus an empty-board audit-issue creator. #3573 removed the
artificial hour-gate regime from the loop (event-driven rotation: one scheduled
role per idle cycle, re-armed by work events, zero timer locks) and destroyed
this executable duplicate with it: zero importers (git grep verified at
landing), the exact dual-SSOT drift class #57 documents.

The bridge lane cannot express file deletions (live landing receipt 2026-10-31:
"deletion diff (+++ /dev/null) is not supported by the bridge lane"), so this
file remains as a docstring-only tombstone. Any future re-introduction of a
time-based role gate must go through AGENT_LOOP_SPEC §4c review first.
Deleting this tombstone is an owner/maintainer-lane follow-up with direct git
access; keeping or re-growing executable content here is prohibited by the
zero-recurrence pins in tests/test_agent_cadence.py.
"""
