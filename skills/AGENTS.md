# AGENTS.md — supremeai-skills Governing Constitution

## Scope

This satellite is the SSOT for the SupremeAI Dynamic Capability Registry,
Skill Marketplace, and Skill Execution Sandbox. It owns skill package
layout, manifest specifications, progressive disclosure loading, the
skills.sh-compatible CLI importer, and cursor/plugins manifest
compatibility.

## Governance

1. The Superadmin directive chain is the only authority for spec changes
   to SKILL.md frontmatter, plugin manifest mapping, or sandbox policy.
2. External agents contribute exclusively through the bridge lane with
   new-files-only payloads; existing files require an admin-lane order.
3. Every skill ships `SKILL.md` (YAML frontmatter + markdown body),
   optional `scripts/`, and optional `assets/`. Nothing else is indexed.
4. Progressive disclosure is binding: boot-time discovery reads
   frontmatter only; full instructions load when a task dispatches
   against the skill. Never eager-load bodies into agent context.
5. The execution sandbox is fail-closed: timeouts, sanitized
   environment, ephemeral workspace. A script that outlives its budget
   is terminated and reported, never retried silently.
6. Zero hardcoded credentials. Registry sources resolve through
   `registry/index.json`; secrets never enter manifests or code.

## Conventions

- Python code is stdlib-only, unittest-tested, colocated under `tests/`.
- Manifest schema errors are data errors: report them, never guess.
- Package manager verbs: `install`, `list`, `remove`, `pack`.
- All module imports stay relative to the satellite root.
