# supremeai-skills — Skill Spec & Marketplace Directory

The Dynamic Capability Registry for the SupremeAI federation: modular
skill packages with progressive disclosure, secure execution sandboxing,
and universal index compatibility.

## Skill package layout

    <skill-name>/
    ├── SKILL.md          # YAML frontmatter + markdown instructions (required)
    ├── scripts/          # executable entry points (optional)
    └── assets/           # static resources (optional)

## SKILL.md frontmatter contract

| field       | required | meaning                                   |
|-------------|----------|--------------------------------------------|
| name        | yes      | unique slug, lowercase with hyphens        |
| version     | yes      | semantic version string                    |
| description | yes      | one-line summary surfaced at discovery     |
| triggers    | no       | task keywords that map dispatch to skill   |
| entry       | no       | default script path inside scripts/        |

The markdown body below the frontmatter is the full instruction set and
is loaded only at dispatch time (progressive disclosure, stage 3).

## cursor/plugins compatibility

A `.cursor-plugin/plugin.json` manifest is normalized into the same
capability descriptor: `name`, `description`, and its `commands` map
become triggers so SupremeAI can run high-leverage workflows natively.

## Marketplace directory

| skill        | version | summary                                | source                 |
|--------------|---------|----------------------------------------|------------------------|
| echo-greeter | 0.1.0   | reference skill: greeting scripts demo | examples/echo-greeter  |

External sources resolve through `registry/index.json`:

    { "skills": { "<name>": { "git": "<clone-url>", "ref": "<optional>" } } }

## CLI

    supremeai-skill install <source>   # local path, git url, or index name
    supremeai-skill list               # installed + indexed skills
    supremeai-skill remove <name>      # uninstall from target root
    supremeai-skill pack <dir>         # build distributable .skill archive
