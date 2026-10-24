#!/usr/bin/env bash
# =============================================================================
# SupremeAI 2.0 — Git Hooks Installer
# =============================================================================
# বাংলা মন্তব্য: এই স্ক্রিপ্ট pre-push হুকটি .git/hooks/ এ ইনস্টল করে এবং
# .pre-commit-config.yaml আপডেট থাকলে `pre-commit install` চালায়। একবার চালালেই
# সব ডেভেলপারের জন্য একই লোকাল গেট সেটআপ হয়ে যাবে।
#
# ব্যবহার:
#   1. এই ফাইলটি এবং pre-push ফাইলটি রিপোর রুটে রাখুন (বা যেকোনো ফোল্ডারে)
#   2. bash setup-git-hooks.sh   [অথবা: sh setup-git-hooks.sh]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "❌ Run this from inside the supremeai git repository (or its subfolder)."
  exit 1
}

HOOKS_DIR="$REPO_ROOT/.git/hooks"
mkdir -p "$HOOKS_DIR"

SRC_PRE_PUSH="$SCRIPT_DIR/git/pre-push"
if [ ! -f "$SRC_PRE_PUSH" ]; then
  echo "❌ pre-push file not found next to this installer ($SRC_PRE_PUSH)."
  echo "   Download both files into the same folder before running this script."
  exit 1
fi

DEST_PRE_PUSH="$HOOKS_DIR/pre-push"
if [ -f "$DEST_PRE_PUSH" ] && [ ! -f "$DEST_PRE_PUSH.supremeai-backup" ]; then
  cp "$DEST_PRE_PUSH" "$DEST_PRE_PUSH.supremeai-backup"
  echo "ℹ️  Existing pre-push hook backed up to .git/hooks/pre-push.supremeai-backup"
fi

cp "$SRC_PRE_PUSH" "$DEST_PRE_PUSH"
chmod +x "$DEST_PRE_PUSH"
echo "✅ Installed pre-push CI-parity hook → $DEST_PRE_PUSH"

# Also (re)install the existing pre-commit framework config if `pre-commit` is available,
# so both layers (fast per-commit + thorough pre-push) are active.
if command -v pre-commit >/dev/null 2>&1; then
  ( cd "$REPO_ROOT" && pre-commit install --hook-type pre-commit )
  echo "✅ pre-commit framework hooks (.pre-commit-config.yaml) installed"
else
  echo "⚠️  'pre-commit' not found on PATH — install it (pip install pre-commit) then run:"
  echo "     cd $REPO_ROOT && pre-commit install"
fi

echo ""
echo "Done. Summary:"
echo "  • git commit  → fast static checks via .pre-commit-config.yaml"
echo "  • git push    → CI-parity gates via .git/hooks/pre-push (this file)"
echo ""
echo "Bypass (use sparingly):"
echo "  SKIP_CI_PARITY=1 git push     — skip the pre-push gate for one push"
echo "  RUN_FULL_TESTS=1 git push     — run the FULL pytest+coverage suite (needs local postgres/redis)"
