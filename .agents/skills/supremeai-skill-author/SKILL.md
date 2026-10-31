---
name: supremeai-skill-author
description: Help users design and package reusable skills for SupremeAI. Use when a user wants to create, refine, validate, or prepare a skill for SupremeAI, including instruction-based SKILL.md packages, executable entry-point packages, or runtime skill blueprints.
---

# SupremeAI Skill Author

Help the user turn a recurring task into a clear, reusable, safe skill that matches the intended SupremeAI execution path. Do not assume every SupremeAI skill format is interchangeable: first identify the target runtime and deliverable.

## Workflow

1. **Clarify the use case.** Ask what repeatable task the skill should perform, who will use it, what inputs it receives, what a successful result looks like, and which tools/data it may access. Gather one or two realistic example requests. Ask only for missing information that changes the design.
2. **Choose the target format.** Distinguish among:
   - An instruction-only skill package with `SKILL.md` and metadata such as `name`, `version`, `description`, `triggers`, and optional `entry`.
   - A Python executable-entry package, with a declared script entry point and explicit input/output behavior.
   - A runtime-generated automation blueprint using the JSON schema exposed by `SkillManager.synthesize_skill_schema` (`skill_name`, `description`, `parameters`, `execution_steps`).
   - A governed/publishable skill requiring a `SkillManifest`, source provenance, checksum, permission declarations, testing, and review.

   If the user's destination is unclear, explain these choices and recommend the smallest format that meets their use case. Do not promise that a Markdown package can be directly installed or executed by a runtime expecting Python code or a JSON blueprint.
3. **Design the behavior.** Write concise, imperative instructions. Specify triggers, inputs, steps, output shape, error handling, and boundaries. Set the skill's degrees of freedom to the task: use judgment-based guidance when the task varies; use explicit parameters and deterministic steps when execution is fragile.
4. **Apply least privilege.** Request only the tools, data, network domains, filesystem writes, and environment variables essential for the skill. Treat all permissions as denied unless the target contract explicitly grants them. Never place secrets, credentials, or private user data in a skill file. Require confirmation before consequential external actions.
5. **Create the package.** Produce the files the selected format requires. For an instruction-based package, use a short `SKILL.md` with YAML frontmatter, concrete instructions, and optional `scripts/`, `references/`, and `templates/` only when they add reusable value. For runtime blueprints, emit valid JSON only if requested by the calling workflow; otherwise show it as a clearly labeled draft. For manifest-based publishing, do not invent a checksum, trusted source, or approval status.
6. **Validate.** Check frontmatter and required fields, unique and descriptive triggers, entry paths, script syntax, parameter names, output/error behavior, permission scope, and consistency between description and actual behavior. Run relevant tests when available. Report what was checked and any remaining assumptions.
7. **Deliver honestly.** Provide the complete package or files and concise usage instructions. Distinguish a drafted or locally validated skill from one uploaded, approved, enabled, or published. Never claim those lifecycle actions happened without an authorized tool and a successful result.

## Working with SupremeAI

Read `references/supremeai-skill-contract.md` before creating a project-native skill. The repository contains several skill-related paths and lifecycle models; use the reference to avoid conflating them. When implementation details are uncertain or may have changed, inspect current project documentation/source or ask the user rather than guessing.

## Interaction style

Collaborate with the user: propose a first draft early, make assumptions visible, then revise from feedback. Avoid making the user fill out a long form. Favor a small, useful skill over unnecessary code or extra files.
