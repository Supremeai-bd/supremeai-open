# THIRD_PARTY_NOTICES — mcp-tool-developer

Provenance and license attribution for the vendored `mcp-tool-developer`
skill pack under `.agents/skills/mcp-tool-developer/`.

## Declared upstream (from SKILL.md frontmatter)

- `source_repo: demo112/yunqu-ai-skills`
- `author: yundu-ai`
- `source: community` / `source_type: community`
- `date_added: 2026-05-13`
- Upstream repository: <https://github.com/demo112/yunqu-ai-skills>
  ("15 Professional AI Skills for Claude Code")

## Upstream verification (live evidence, 2026-10-29)

- The upstream repository exists and ships a `10-mcp-tool-developer/`
  skill folder (verified against the upstream root listing), matching
  this pack's declared `source_repo` and subject matter.

## License status: NOT CONFIRMED FOR REDISTRIBUTION

- The upstream README displays an "MIT License" heading, but the grant
  is **purchase-conditioned**: "购买后可自由使用、修改、集成到商业项目"
  (after purchase — single purchase via cryptocurrency payment plus
  email confirmation; bundle pricing listed) — the license text applies
  to purchasers, not to the general public.
- This repository's vendored copy carries no purchase receipt evidence
  in-tree. Declaring MIT for this pack without upstream confirmation
  would be a license overclaim (the #1725 finding's explicit warning:
  "blanket MIT-relabeling upstream content (legally wrong without
  upstream confirmation)").

## Remediation paths (per the #1725 contract)

1. **Obtain license confirmation** (maintainer/admin lane): a purchase
   receipt or a written upstream grant covering redistribution of the
   vendored content. Requires purchasing authority that autonomous
   agents do not hold.
2. **Rewrite adapt_cleanroom** (separate content lane): replace the
   vendored SKILL.md body with independently authored MCP-development
   guidance, then the pack falls under the repository root MIT LICENSE.

Until one path completes, this pack remains the documented
redistribution-compliance gap inside the vendored tree. No `LICENSE`
file is declared for this pack (deliberately — no overclaim). Filed
under issue #1725; the 7 `source: community` packs with no external
repository declaration are in-house content under the repository root
MIT LICENSE, and the `browser-automation` pack carries its own
Apache-2.0 attribution (`LICENSE` + `THIRD_PARTY_NOTICES.md`).
