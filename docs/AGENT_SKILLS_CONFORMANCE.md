# Agent Skills Metadata Conformance (issue #1672)

Three skill-metadata conventions coexist in this federation. This document is
the mapping contract that stops them drifting, plus the usage contract for the
guard that enforces the file plane's structure. It accompanies
`scripts/ci/skill_conformance_guard.py` (landed by issue #1672, scout radar
R17 / `SCOUT_RADAR_2026-10-28-III`).

## The three planes

1. **File plane (standard)** — `.agents/skills/<dir>/SKILL.md` with YAML
   frontmatter. Governed by the [Agent Skills open standard](https://agentskills.io/specification)
   — originally developed by Anthropic, released as an open standard
   (Apache-2.0 code, CC-BY-4.0 docs). A skill is a folder whose `SKILL.md`
   carries frontmatter with minimum `name` + `description`; progressive
   disclosure happens in three stages (discovery sees name+description only,
   activation loads the full SKILL.md on match, execution loads bundled
   scripts/references on demand).
2. **Registry plane (dynamic skills)** — `skills/schema.py`, the pydantic
   `SkillMetadata` model (name / version / description / author / tags) that
   powers dynamic-skill discovery and versioning.
3. **The standard itself** — the external specification, previously unused as
   a validation target.

## Field mapping: SKILL.md frontmatter <-> SkillMetadata

| Concept | SKILL.md (standard, file plane) | SkillMetadata (registry plane) | Drift notes |
|---|---|---|---|
| Identity | `name` — required, must equal the directory name (guard E4) | `name` — required, slugified (registry convention uses e.g. `data_cleaner`) | Same concept, different surface conventions; equality is enforced only inside the file plane |
| Purpose | `description` — required, 1–1024 chars (guard E5/E6) | `description` — required, "concise", **no length cap in the pydantic model** | The 1024 cap is enforced at the file plane only; the registry plane trusts its inputs |
| Version | *(none in the standard — spec evolution is not per-skill)* | `version` — defaults `"1.0.0"`, strict SemVer `model_validator` | developing-genkit-js smuggles a version through a nested `metadata:` map (guard W3 flags this convention-2 leakage) |
| Authorship | *(no first-class field)*; in-repo skills carry extension fields `author`, `source`, `source_repo`, `source_type` | `author` — defaults `"supremeai_agent_id"` | No sync exists in either direction; the guard inventories extension fields (W1) instead of pretending a schema exists |
| Discovery tags | *(none in the standard)* | `tags: list[str]` for semantic/tokenized discovery | Some in-repo skills carry top-level `tags`/`tools` extension fields (W1 inventory) |
| License | `license` — optional standard extension, recommended for attribution | *(no field)* | **No in-repo skill carries one** (guard W2 across all folders at seed time) |

The mapping is deliberately **asymmetric-enforcing**: the file plane gets hard
structural checks (errors E1–E6, ratcheted), while registry-plane semantics
stay advisory (warnings W1–W3, report-only). Nothing here changes runtime
behavior — skills load exactly as before; the guard only makes
discovery-breaking structure loud at push/CI time.

## Discovery semantics the guard protects

`.agents/skills/<dir>/SKILL.md` is the discovery entry. A folder without
`SKILL.md` advertises a skill no client can discover — the guard's E1. The
seed instance is `developing-genkit-python/` (ships `references/` only; its
entry file is absent), pinned in the dated baseline
`scripts/ci/skill_conformance_baseline.json` rather than silently ignored
(floors are real, never assumed empty — the #2081 lesson). The floor is
**shrink-only**: entries may be removed when fixed, never added by hand; new
or grown structural errors fail closed.

## Validator usage

```text
python scripts/ci/skill_conformance_guard.py             # scan + ratchet
python scripts/ci/skill_conformance_guard.py --check     # alias, explicit
python scripts/ci/skill_conformance_guard.py --root DIR  # custom skills root
python scripts/ci/skill_conformance_guard.py --baseline  # regenerate the dated seed
python scripts/ci/skill_conformance_guard.py --self-test # hermetic battery
```

Exit codes: `0` = clean or fully covered by the shrink-only baseline; `1` =
new/grown structural violations (or self-test failure). Warnings never affect
the exit code.

## Honest limitations

A structural validator cannot verify instruction quality, detect prompt
injection in skill bodies, or validate bundled scripts — content scanning is a
separate lane (the R17 field report says exactly this). The parser is a
minimal stdlib frontmatter reader covering the shapes this repo actually
ships (plain scalars, quoted scalars, plain-scalar continuation folding,
nested maps, block scalars, comments); it deliberately does not implement
full YAML, and it refuses to guess: an unparseable frontmatter is an error,
not a silent pass.
