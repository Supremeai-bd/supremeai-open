# THIRD_PARTY_NOTICES — browser-automation

Provenance and license attribution for the vendored `browser-automation`
skill pack under `.agents/skills/browser-automation/`.

## Declared upstream (from SKILL.md frontmatter)

- `source: vibeship-spawner-skills (Apache 2.0)`
- `date_added: 2026-02-27`
- Upstream repository: <https://github.com/vibeforge1111/vibeship-spawner-skills>
  (repository URL additionally confirmed from the upstream root
  `package.json` `repository.url` field)

## License verification (live evidence, 2026-10-29)

- Upstream root `package.json` declares `"license": "Apache-2.0"`
  (v1.1.0, author `VibeForge`).
- Upstream `README.md` carries a `## License` section stating
  `Apache 2.0`.
- Upstream ships **no LICENSE text file** at the repository root
  (GitHub license-detection API returns 404; root file listing has no
  LICENSE/NOTICE entry). The canonical Apache License 2.0 text is
  therefore embedded verbatim in [`LICENSE`](LICENSE) — unmodified
  canonical text per the Apache Software Foundation — with the appendix
  copyright line filled from the upstream author declaration
  (`VibeForge`), the only copyright holder signal the upstream publishes.

## Redistribution compliance status

- Apache-2.0 §4(a): a copy of the license accompanies the pack
  (`LICENSE`, this directory).
- Apache-2.0 §4(b): the vendored `SKILL.md` content predates this file;
  no modifications to upstream-derived content were made in this change
  (attribution layer only).
- Apache-2.0 §4(c)/(d): upstream publishes no NOTICE file; attribution
  is preserved here and in the `LICENSE` appendix line.

## Scope

This attribution covers the `browser-automation` pack only. Packs whose
frontmatter declares `source: community` with no external repository are
in-house content under the repository root MIT LICENSE. The
`mcp-tool-developer` pack declares a purchase-gated upstream and carries
its own `THIRD_PARTY_NOTICES.md` documenting its distinct (unconfirmed)
license status. Filed under issue #1725.
