#!/bin/sh
# ============================================================================
# SupremeAI unified deploy script (issue #339) — POSIX sh, fail-closed.
#
# Boot-smoke contract: bash -n scripts/deploy.sh   (syntax gate, no execution)
#
# Dry-run orchestration ONLY in the public reference: every step that would
# touch real infrastructure requires DEPLOY_CONFIRM="yes" AND a configured
# environment. Missing confirmation is a clean no-op exit 0 with a loud note
# (the reference never mutates clouds).
# ============================================================================
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MANIFEST="$ROOT/deployments/render.yaml"
INVENTORY="$ROOT/deployments/secrets-inventory.json"
DOCKERFILE="$ROOT/deployments/Dockerfile"

note() { printf '%s\n' "$*"; }
die()  { printf 'DEPLOY REFUSED: %s\n' "$*" >&2; exit 1; }

[ -f "$MANIFEST" ]   || die "missing $MANIFEST"
[ -f "$INVENTORY" ]  || die "missing $INVENTORY"
[ -f "$DOCKERFILE" ] || die "missing $DOCKERFILE"

# --- integrity gate 1: no secret VALUES in any manifest (names only) --------
# A value-shaped assignment (KEY=<literal>) anywhere in deployments/ is a
# hard stop; sync:false / generateValue / documented placeholders are the
# only accepted shapes.
if grep -RInE '^[[:space:]]*-?[[:space:]]*[A-Z_][A-Z0-9_]*:[[:space:]]*["'"'"']?[A-Za-z0-9_+/=-]{16,}' "$ROOT/deployments" 2>/dev/null | grep -vE 'secrets-inventory|inventory_version|description|purpose|set_in|owner|key|reference' | grep -qE 'KEY|TOKEN|SECRET|PASSWORD|URL'; then
  die "possible literal secret value in deployments/ - see deployments/README.md"
fi

# --- integrity gate 2: python-side deep validation (manifests + inventory) --
python3 - "$ROOT" <<'PYEOF'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
manifest = (root / "deployments" / "render.yaml").read_text(encoding="utf-8")
inventory = json.loads((root / "deployments" / "secrets-inventory.json").read_text(encoding="utf-8"))
inv_keys = {s["key"] for s in inventory["secrets"]}
declared = [ln.split("key:")[1].strip() for ln in manifest.splitlines() if "key:" in ln and "- key:" in ln]
unknown = [k for k in declared if k not in inv_keys and not k.startswith("PYTHON_VERSION") and not k.startswith("SUPREMEAI_ROUTING_POLICY")]
if unknown:
    print("DEPLOY REFUSED: manifest env keys missing from inventory:", unknown, file=sys.stderr)
    sys.exit(1)
print(f"integrity gate 2 OK: {len(declared)} declared env keys, {len(inv_keys)} inventoried")
PYEOF

# --- deploy gate -------------------------------------------------------------
if [ "${DEPLOY_CONFIRM:-}" != "yes" ]; then
  note "Dry-run complete: manifests + inventory validated (gates 1+2)."
  note "Set DEPLOY_CONFIRM=yes and configure the Render/Redis environment to proceed."
  note "The public reference never mutates cloud infrastructure."
  exit 0
fi

die "live deploy requires the operator's Render CLI + dashboard secrets; not part of the public reference"
