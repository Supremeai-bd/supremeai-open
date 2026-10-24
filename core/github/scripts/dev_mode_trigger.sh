#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# dev_mode_trigger.sh — maintainer-only Developer Mode trigger + audit trail
# (issue #877 / ARCH-GAP-01 GAP-07 · OPS-08 §5)
#
# Developer Mode (SupremeAI / external agent acting as assigned developer)
# MUST be activated through this gate. Chat instructions like
# "SupremeAI, fix issue #900" are NOT a valid trigger.
#
#   Authorization : caller needs repo `admin` or `maintain` permission
#                   (checked via GitHub collaborators/permission API)
#   Audit trail   : (1) audit comment on the issue
#                   (2) slot entry in AGENT_SLOT_REGISTRY.yaml (≤ 7 days)
#                   (3) label `supremeai:dev-mode:<slot>` on the issue
#
# Usage:
#   bash .github/scripts/dev_mode_trigger.sh activate <slot> <ISSUE_ID> [notes]
#   bash .github/scripts/dev_mode_trigger.sh deactivate <slot>
# Exit: 0 = success · 1 = forbidden / conflict · 2 = usage or API error
# ---------------------------------------------------------------------------
set -euo pipefail

CMD="${1:-}"
REGISTRY="docs/master_docs/AGENT_SLOT_REGISTRY.yaml"
REPO="${GITHUB_REPOSITORY:-SaifulHaqueNiloy/supremeai}"
MAX_DAYS=7

usage() {
  echo "usage: dev_mode_trigger.sh activate <slot> <ISSUE_ID> [notes] | deactivate <slot>"
  exit 2
}
[ -n "$CMD" ] || usage

# ---- Authorization: caller must be admin/maintain ---------------------------
ACTOR=$(gh api user -q .login) || { echo "::error::GitHub API auth failed"; exit 2; }
PERM=$(gh api "repos/${REPO}/collaborators/${ACTOR}/permission" -q .permission 2>/dev/null) || PERM="none"
case "$PERM" in
  admin|maintain) echo "✅ authorization: @${ACTOR} (${PERM})" ;;
  *)
    echo "::error::FORBIDDEN — Developer Mode trigger requires admin/maintain permission (actor @${ACTOR} has '${PERM}')"
    exit 1 ;;
esac

# ---- Registry helpers (text-safe edits: preserve YAML header comments) ------
registry_add_slot() { # slot tool notes expires
  local slot="$1" tool="$2" notes="$3" expires="$4"
  python3 - "$REGISTRY" "$slot" "$tool" "$expires" "$notes" "$ACTOR" <<'PY'
import sys, re, datetime
path, slot, tool, expires, notes, actor = sys.argv[1:7]
today = datetime.date.today().isoformat()
src = open(path, encoding='utf-8').read()
entry = (
    f'  - slot: {slot}\n'
    f'    tool: "{tool}"\n'
    f'    maintainer: "@{actor}"\n'
    f'    assigned_on: "{today}"\n'
    f'    expires_on: "{expires}"\n'
    f'    active: true\n'
    f'    notes: "{notes}"\n'
)
if re.search(r'^slots: \[\]', src, re.M):
    src = re.sub(r'^slots: \[\][^\n]*', 'slots:\n' + entry.rstrip('\n'), src, count=1, flags=re.M)
elif re.search(r'^slots:\s*$', src, re.M):
    src = re.sub(r'^(slots:[ \t]*)$', r'\1' + entry.rstrip('\n'), src, count=1, flags=re.M)
else:
    sys.exit('registry has no slots: anchor line')
if not src.endswith('\n'):
    src += '\n'
open(path, 'w', encoding='utf-8').write(src)
PY
}

registry_deactivate_slot() { # slot
  python3 - "$REGISTRY" "$1" <<'PY'
import sys, re
path, slot = sys.argv[1:3]
lines = open(path, encoding='utf-8').readlines()
out, inside, found = [], False, False
for l in lines:
    if re.match(rf'^  - slot: {re.escape(slot)}\s*$', l):
        inside, found = True, True
    elif inside and re.match(r'^  - slot:', l):
        inside = False
    if inside and re.match(r'^\s+active:\s*true\s*$', l):
        l = re.sub(r'active:\s*true', 'active: false  # deactivated via dev_mode_trigger.sh', l)
    out.append(l)
if not found:
    sys.exit(f'no entry for {slot} in registry')
open(path, 'w', encoding='utf-8').write(''.join(out))
PY
}

# ---- Commands ----------------------------------------------------------------
case "$CMD" in
  activate)
    SLOT="${2:?usage: dev_mode_trigger.sh activate <slot> <ISSUE_ID> [notes]}"
    ISSUE="${3:?usage: dev_mode_trigger.sh activate <slot> <ISSUE_ID> [notes]}"
    NOTES="${4:-Dev Mode activation}"
    echo "$SLOT" | grep -qE '^agent-[0-9]+$' || { echo "::error::slot must match agent-[0-9]+"; exit 2; }
    # conflict: slot already active?
    if grep -A5 -E "^  - slot: ${SLOT}\$" "$REGISTRY" 2>/dev/null | grep -q 'active: true'; then
      echo "::error::slot ${SLOT} is already ACTIVE (see ${REGISTRY}) — transfer/deactivate first"
      exit 1
    fi
    EXPIRES=$(date -d "+${MAX_DAYS} days" +%F 2>/dev/null || date -v+"${MAX_DAYS}"d +%F)
    TOOL="SupremeAI (Developer Mode)"
    AUDIT="🔧 **Developer Mode activated** — slot \`${SLOT}\` by @${ACTOR} · issue #${ISSUE} · expires **${EXPIRES}** (${MAX_DAYS}-day max, OPS-08 §5 / GAP-07 audit trail)

> ${NOTES}"
    # Audit (1): issue comment
    gh issue comment "$ISSUE" --body "$AUDIT" > /dev/null
    # Audit (2): registry entry
    registry_add_slot "$SLOT" "$TOOL" "$NOTES" "$EXPIRES"
    # Audit (3): visual label (auto-create if missing)
    LABEL="supremeai:dev-mode:${SLOT}"
    gh label create "$LABEL" --color F59E0B --description "Developer Mode active (${SLOT})" 2>/dev/null || true
    gh issue edit "$ISSUE" --add-label "$LABEL" > /dev/null
    echo "✅ Developer Mode activated: slot=${SLOT} issue=#${ISSUE} expires=${EXPIRES} (comment + registry + label recorded)"
    ;;
  deactivate)
    SLOT="${2:?usage: dev_mode_trigger.sh deactivate <slot>}"
    registry_deactivate_slot "$SLOT"
    echo "✅ slot ${SLOT} deactivated in ${REGISTRY} — remove the issue label manually if needed"
    ;;
  *)
    usage ;;
esac
