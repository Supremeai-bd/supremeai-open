# SupremeAI Skill Contract (repository inspection snapshot)

**Purpose:** Help an author choose the correct SupremeAI skill path. This reference records source observations from `Supremeai-bd/supremeai` (main, inspected 2026-10-31); recheck repository sources before relying on details for a live publishing action.

## Skill package example

`skills/examples/echo-greeter/SKILL.md` demonstrates this YAML frontmatter:

```yaml
---
name: echo-greeter
version: 0.1.0
description: Reference skill demonstrating the SKILL.md contract with a script entry point.
triggers: [greet, hello, greeter]
entry: scripts/greet.py
---
```

Its body describes what the skill does and gives the caller concrete execution and failure-handling instructions. The example entry script is ordinary Python with an argument parser, stdout result, and non-zero exit behavior. This example is evidence of a package convention, not proof that every runtime or account supports direct user upload/activation.

## Separate runtime blueprint

`core/skill_manager.py` exposes `synthesize_skill_schema(task_description)`, which requests a JSON object shaped like:

```json
{
  "skill_name": "UniqueCamelCaseName",
  "description": "Reusable task summary",
  "parameters": [
    {"name": "url", "type": "string", "description": "Target URL"}
  ],
  "execution_steps": [
    {"action": "navigate", "url": "target_url"},
    {"action": "click", "selector": ".btn"}
  ]
}
```

Treat this as an automation blueprint schema, not as the same thing as a `SKILL.md` package or the governed `SkillManifest`. Respect whichever caller/API is actually consuming the result; do not wrap it in Markdown when the consumer requires raw JSON.

## Governed manifest and ingestion

`core/schemas/skill_manifest.py` defines a Pydantic `SkillManifest` with required `skill_id`, `name`, `description`, `source_url` (HTTP URL), and `checksum`; `version` defaults to `1.0.0`, and `status` defaults to `staging`. `permissions` defaults to denied capabilities (`allow_network: false`, `allow_filesystem_write: false`) and empty allowed domains/environment-variable lists. Optional `governance` can declare owner, allowed data/roles/tools, human approval points, success metrics, evaluation tests, budget, and audit logging. Statuses include staging, quarantine, approved, ephemeral, rejected, and deprecation_pending. Do not claim a submitted skill is approved just because it validates.

`core/schemas/skill_index.py` currently lists verified source prefixes: `https://github.com/modelcontextprotocol/servers` and `https://github.com/paykaribazaronline/supreme-verified-skills`. `core/agents/skill_ingestor.py` checks both manifest source and zip download URL against that allowlist, verifies SHA-256, blocks unsafe zip paths, checks entry code statically, runs adaptation, and tests in a sandbox before moving a package into quarantine. A skill author should never work around provenance, checksum, static checks, sandboxing, or review. Confirm current server policy before suggesting a source or ingestion action.

## Important execution security boundary

`core/skill_manager.py` queries active skill rows from the `skills` database table, but fetched Python code is blocked by default unless the in-process code-generation gate is explicitly enabled. Its source contains AST checks and restricted builtins as additional safeguards, while explicitly warning those are not a security boundary. Do not suggest enabling in-process code execution as a user-level shortcut. Prefer the governed sandbox/approval lifecycle and verify current deployment settings with maintainers.

## Authoring checklist

- Keep `name`/`skill_id` stable, descriptive, and valid for the target consumer; use simple lowercase hyphenated IDs for directory/package names unless a stricter schema says otherwise.
- Write a task-specific `description` and meaningful `triggers`; avoid broad triggers that cause accidental activation.
- Declare `entry` only when the target package loader expects an executable entry file, and ensure the relative path exists.
- Make parameters, output, error behavior, and side effects explicit. Keep generated behavior bounded and testable.
- Default network, filesystem writes, external tools, and environment variables to none. List only the minimum required access in the actual manifest/permission mechanism.
- Use synthetic test inputs; never embed secrets or real user records in source, examples, or test fixtures.
- Compute checksums from the exact archive bytes only at packaging time; never fabricate or reuse a stale checksum.
- Treat quarantine, review, approval, and activation as separate states/operations. Need an authorized workflow result before reporting any as complete.

## Source files referenced

- `skills/examples/echo-greeter/SKILL.md`
- `skills/examples/echo-greeter/scripts/greet.py`
- `core/skill_manager.py`
- `core/schemas/skill_manifest.py`
- `core/schemas/skill_index.py`
- `core/agents/skill_ingestor.py`
