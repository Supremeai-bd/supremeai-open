#!/usr/bin/env bash
# Per-clone activation of the shipped .githooks/ suite (R63, #2343)
# ================================================================
# Git never auto-activates a versioned hooks directory: the default hooks
# path is $GIT_DIR/hooks and a repo-shipped directory (.githooks/) is only
# honored through the client-side `core.hooksPath` config, which is set per
# clone and is never version-controlled (git's standing anti-malware posture,
# githooks(1)/git-config(1)). Consequence: this repo's pre-commit / pre-push
# / post-commit suite runs NOWHERE by default, and every direct push from a
# standard clone — agent worktrees, scout worktrees, human clones — pushes
# with the Board-Freshness pre-push gate (#4177, Universal Invariant 1's
# local layer) silently dark.
#
# This script closes that gap the honest way (warn-and-instruct, the #2343
# option-D boundary): it sets the config in YOUR clone only, idempotently,
# and verifies the suite it points at is actually executable. It never
# touches any other git config, never mutates tracked files, and has a
# read-only --check mode for loop/CI callers.
#
# Usage:
#   bash scripts/setup_git_hooks.sh           # activate (idempotent) + verify
#   bash scripts/setup_git_hooks.sh --check   # verify only, exit 1 if dark
#
# Receipts printed to stdout; failures exit non-zero (fail-closed).
set -euo pipefail

CHECK_ONLY=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=1
elif [[ -n "${1:-}" ]]; then
  echo "unknown argument: $1 (supported: none | --check)" >&2
  exit 2
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/.githooks"
EXPECTED=".githooks"

fail() {
  echo "[hooks] FAIL: $1" >&2
  exit 1
}

# 1. The shipped suite must exist and be executable — pointing core.hooksPath
#    at a missing or non-executable suite would silently keep the gate dark
#    while LOOKING configured (the exact failure mode this lane closes).
[[ -d "${HOOKS_DIR}" ]] || fail ".githooks/ not found at repo root — nothing to activate"
for hook in pre-commit pre-push post-commit; do
  [[ -f "${HOOKS_DIR}/${hook}" ]] || fail ".githooks/${hook} missing — suite incomplete, refusing to point hooksPath at a broken suite"
  [[ -x "${HOOKS_DIR}/${hook}" ]] || fail ".githooks/${hook} exists but is not executable — chmod +x it first"
done

CURRENT="$(git config --get core.hooksPath || true)"

if [[ "${CHECK_ONLY}" -eq 1 ]]; then
  if [[ -z "${CURRENT}" ]]; then
    echo "[hooks] CHECK: core.hooksPath is UNSET on this clone — Board-Freshness pre-push gate (#4177) is dark."
    echo "[hooks] CHECK: fix: git config core.hooksPath .githooks   (or re-run without --check)"
    exit 1
  fi
  echo "[hooks] CHECK: core.hooksPath=${CURRENT} — gate layer active."
  exit 0
fi

# 2. Activate (idempotent): setting the same value repeatedly is a no-op.
git config core.hooksPath "${EXPECTED}"
FINAL="$(git config --get core.hooksPath)"
[[ "${FINAL}" == "${EXPECTED}" ]] || fail "config set failed: expected '${EXPECTED}', read back '${FINAL}'"

# 3. Prove the wiring end-to-end: git must resolve the pre-push hook through
#    the configured path (rev-parse --git-path honors core.hooksPath).
RESOLVED="$(git rev-parse --git-path hooks/pre-push)"
[[ -x "${RESOLVED}" ]] || fail "git does not resolve hooks/pre-push through the configured path (got: ${RESOLVED})"

if [[ -z "${CURRENT}" ]]; then
  echo "[hooks] ACTIVATED: core.hooksPath=${EXPECTED} (was unset) — Board-Freshness pre-push gate (#4177) now live on this clone."
else
  echo "[hooks] ACTIVATED (idempotent re-run): core.hooksPath=${EXPECTED} (was: ${CURRENT}) — no change needed."
fi
echo "[hooks] receipt: git resolves pre-push via ${RESOLVED}"
