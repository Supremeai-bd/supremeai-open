# Bridge Split-Brain Root-Duplicate Guard (2026-10-30)

**Part of #1676** — implements the requested *bridge post-check that fails when a
dispatched path creates a duplicate of an existing root file*. The satellite
cleanup halves (delete the 15 stale nested `studio/` copies + any unintended
`infrastructure/` residue in `Supremeai-bd/supremeai-studio`) are **not** done
here; see "Remaining work" below.

## Root cause (verified in `scripts/bridge/bridge_intake.py`)

`route_files()` routes `studio/<rest>` to the `Supremeai-bd/supremeai-studio`
satellite but keeps the namespace prefix (`canon = f`). Satellite mirrors carry
the monorepo namespace dir *content* at their root, so a dispatched
`studio/package.json` lands at `studio/package.json` **next to** the canonical
root `package.json` — a stale nested duplicate. Fifteen such copies accumulated
in the studio satellite (7 diverged → split-brain, per the #1676 audit). The
same shape applies to every prefix-routed satellite target.

## Guard semantics (fail-closed, evidence-based)

New in `bridge_intake.py`:

- `deletion_paths(diff)` — parses `deleted file mode` entries from the order
  diff (b/-side path set).
- `split_brain_duplicates(target_repo, target_dir, mapped)` — for **satellite**
  targets only (monorepo `PRIVATE_REPO` exempt: `studio/` is a legitimate
  workspace namespace there), flags every dispatched add/modify path
  `<ns>/<rest>` whose root twin `<rest>` **actually exists as a file** in the
  freshly cloned target main tree. Deletions are exempt: removing the stale
  copy is exactly the desired cleanup.
- Wiring: computed after `clone()` and before branch checkout / `git apply`;
  any hit → `reject("split-brain guard (#1676): …")` with the offending paths
  and the two sanctioned remedies (write the root path, or submit a deletion
  order for the stale copy).

The twin check strips exactly one namespace segment (`studio/x/y` ↔ `x/y`),
matching the observed mirror layout (satellite root mirrors monorepo
`studio/` content).

## Evidence

- `tests/test_bridge_splitbrain_guard.py` — 13 offline tests: 2 wiring pins,
  monorepo exemption, root-twin flag, no-twin pass, deletion exemption,
  root-level exemption, directory-twin non-file, mixed-order selection,
  `deletion_paths` detect/ignore/multi/empty, live monorepo namespace sanity.
- Full battery this branch: 13/13 new tests; `-k "intake or bridge"` 62 passed,
  3 skipped, 0 new failures; `continuous_agent_loop.py --verify-only` 8/8 PASS;
  `deploy_preflight_guard.py --self-test` PASS.

## Remaining work on #1676 (satellite state, admin/follow-up lane)

1. Delete the 15 stale nested `studio/` copies in `Supremeai-bd/supremeai-studio`.
2. Remove unintended `infrastructure/` nested residue there (verify intent of
   `infrastructure/cloudflare-studio-proxy` before removal).

A bridge deletion order can do both now that the guard exempts deletions, but
each deletion diff must byte-match the satellite preimage (fail-closed apply),
so it needs its own verification pass — deliberately not rushed into this order.

## Honest limitations

- The guard checks the **target clone's main tree** at intake time; a root twin
  created *after* intake but before merge is outside its view (same TOCTOU
  class as every intake gate; the apply is still fail-closed on conflict).
- Repos whose satellites do NOT mirror stripped content would false-positive;
  all current `BRIDGE_TARGET_REPOS` follow the root-mirror layout, and the
  check is evidence-based (twin must actually exist), so only true collisions
  fire.
