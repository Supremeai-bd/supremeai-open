#!/usr/bin/env bash
# =============================================================================
# Canonical drift-artifact regeneration entrypoint (issue #1004)
# =============================================================================
# বাংলা: ৮টি ছড়ানো generator-এর একটিমাত্র ক্যানোনিকল entrypoint। CI-র drift
# গেটের (ci.yml + ci-advanced-checks.yml) হুবহু mirror — এক কমান্ডে সব
# mechanical artifact রিজেনারেট, কোনোটা ভুলে যাওয়ার সুযোগ নেই।
#
# Race control contract (issue #1004):
#   - Local dev:  `bash scripts/ci/regen_all_artifacts.sh`            (write mode)
#   - CI PR gate: `bash scripts/ci/regen_all_artifacts.sh --check`    (exit 1 on drift)
#   - Post-merge bot (artifact-regen.yml): write mode + serialized
#     concurrency group → parallel merge-এর পরেও main সবসময় byte-fresh।
#
# STATUS.md দাবি (human honesty gate) ব্যতিক্রম — generate_status_proof ব্যর্থ
# হলে mechanical artifacts তবুও commit-যোগ্য থাকে; claim drift আলাদা exit
# code (2) রিপোর্ট হয়। Bot কখনো হাতে-লেখা দাবি রিওয়াইট করে না (মিথ্যা দাবি
# auto-laundering যেন না হয়)।
#
# Exit codes:
#   0 — সব সফল; লিখিত হলে CHANGED=<files> প্রিন্ট হয় (খালি মানে no-op)
#   1 — --check মোডে drift ধরা পড়েছে (বা কোনো generator ব্যর্থ)
#   2 — mechanical artifacts ঠিক আছে/লেখা হয়েছে, কিন্তু STATUS.md claim drift
#   3 — অপ্রত্যাশিত generator ব্যর্থতা (write মোড)
# =============================================================================
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${REPO_ROOT}" ]]; then
  echo "ERROR: must run inside a git worktree/clone of supremeai" >&2
  exit 3
fi
cd "${REPO_ROOT}"

CHECK_MODE=0
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=1
fi

# CI drift-গেটের সাথে হুবহু ক্রম (ci-advanced-checks.yml:91-113 + ci.yml:456)
# format: <generator-path>|<generated-artifacts…>
MECHANICAL_STEPS=(
  "scripts/ci/generate_route_inventory.py|docs/generated/route_inventory.json"
  "scripts/ci/generate_route_graph.py|docs/generated/route_knowledge_graph.json"
  "scripts/ci/generate_topology_mermaid.py|docs/generated/route_topology.mmd"
  "scripts/audit/generate_route_consumer_inventory.py|docs/generated/route_consumer_inventory.json docs/generated/route_consumer_inventory.md"
  "scripts/ci/generate_route_client_inventory.py|docs/audit_reports/route_client_inventory.json docs/audit_reports/route_client_inventory.md"
  "scripts/ci/generate_module_capability_matrix.py|docs/generated/module_capability_matrix.json"
  "scripts/ci/generate_domain_dependency_graph.py|docs/generated/domain_dependency_graph.json docs/generated/domain_dependency_graph.mmd"
  "scripts/governance/architecture_check.py|docs/generated/backend_import_graph.json"
)
STATUS_PROOF_STEP="scripts/ci/generate_status_proof.py|docs/generated/STATUS_PROOF.md"

declare -a CHANGED=()
STATUS_CLAIM_DRIFT=0

track_changes() {
  local artifacts="$1"
  for art in ${artifacts}; do
    if [[ ! -f "${art}" ]]; then
      continue
    fi
    if ! git ls-files --error-unmatch "${art}" >/dev/null 2>&1; then
      CHANGED+=("${art}")  # untracked new artifact
    elif ! git diff --quiet -- "${art}" 2>/dev/null; then
      CHANGED+=("${art}")
    fi
  done
}

echo "== Canonical artifact regeneration (issue #1004) =="
echo "repo: ${REPO_ROOT}"
echo "mode: $([[ ${CHECK_MODE} -eq 1 ]] && echo CHECK || echo WRITE)"
echo ""

# --- Step 0: export backend/openapi.json fresh from the app (issue #2203) ----
# #1748/#2174 untracked backend/openapi.json — it is no longer shipped by
# checkout, so every consumer (generate_route_inventory.py etc.) needs it
# exported from the FastAPI app first. Source of truth = the routes themselves.
# Resolution order: backend/.venv/bin/python (local dev / setup-backend cache
# restore) → poetry run (CI with poetry) → hard exit 3 (no silent drift).
export_openapi_schema() {
  (
    cd backend || exit 3
    # PYTHONHASHSEED=0: @app.api_route("/", methods=["GET","HEAD"]) — FastAPI
    # route.methods একটি set; hash randomization-এ iteration order প্রতি
    # process-এ বদলায় → root path-এর operationId flip করে → source_sha256
    # drift। Fixed seed = byte-identical export, প্রতিবার (issue #2203)।
    if [[ -x .venv/bin/python ]]; then
      PYTHONHASHSEED=0 PYTHONPATH="." .venv/bin/python scripts/validate_openapi.py
    elif command -v poetry >/dev/null 2>&1; then
      PYTHONHASHSEED=0 PYTHONPATH="." poetry run python scripts/validate_openapi.py
    else
      echo "ERROR: cannot export backend/openapi.json — no backend/.venv and no poetry on PATH (issue #2203)" >&2
      exit 3
    fi
  )
}
echo "--- backend/scripts/validate_openapi.py (fresh schema export, #2203)"
if ! export_openapi_schema; then
  echo "FATAL: OpenAPI schema export failed — downstream generators would run on a stale/missing document; aborting (issue #2203)" >&2
  exit 3
fi
echo ""

# --- Mechanical artifacts (self-healing scope) -------------------------------
for step in "${MECHANICAL_STEPS[@]}"; do
  script_path="${step%%|*}"
  artifacts="${step#*|}"
  echo "--- ${script_path}"
  if ! python "${script_path}"; then
    echo "GENERATOR FAILED: ${script_path}" >&2
    exit 1
  fi
  track_changes "${artifacts}"
done

# --- Route registry sanity (validator, no writes; CI parity) ------------------
if ! python scripts/ci/validate_route_registry.py >/dev/null; then
  echo "VALIDATOR FAILED: scripts/ci/validate_route_registry.py" >&2
  exit 1
fi

# --- STATUS.md claim gate (human-owned; separate contract) --------------------
echo "--- ${STATUS_PROOF_STEP%%|*}"
status_script="${STATUS_PROOF_STEP%%|*}"
status_artifacts="${STATUS_PROOF_STEP#*|}"
if python "${status_script}"; then
  track_changes "${status_artifacts}"
else
  STATUS_CLAIM_DRIFT=1
  echo "STATUS.md claim drift detected (exit non-zero) — mechanical artifacts"
  echo "remain commit-eligible; STATUS.md/claims need HUMAN correction." >&2
  track_changes "${status_artifacts}"
fi

echo ""
if [[ "${#CHANGED[@]}" -gt 0 ]]; then
  echo "CHANGED artifacts:"
  printf '  %s\n' "${CHANGED[@]}"
  echo "CHANGED=${CHANGED[*]}"
else
  echo "(no drift — all artifacts byte-fresh)"
  echo "CHANGED="
fi

if [[ "${CHECK_MODE}" -eq 1 ]]; then
  # স্পষ্ট সেমান্টিক্স: 2 = claim drift (সবচেয়ে actionable), 1 = mechanical drift
  if [[ ${STATUS_CLAIM_DRIFT} -eq 1 ]]; then
    echo "CHECK FAILED: STATUS.md claim drift (machine-checkable claims stale)" >&2
    exit 2
  fi
  if [[ "${#CHANGED[@]}" -gt 0 ]]; then
    echo "CHECK FAILED: drift detected — run without --check and commit the diff" >&2
    exit 1
  fi
  echo "CHECK PASSED: all drift artifacts byte-fresh"
  exit 0
fi

# Write মোড
if [[ ${STATUS_CLAIM_DRIFT} -eq 1 ]]; then
  # mechanical artifacts লেখা হয়েছে; caller (bot) সেগুলো commit করতে পারে,
  # কিন্তু claim drift রিপোর্ট করতে হবে।
  echo "WRITE MODE: mechanical artifacts updated; STATUS.md claim drift present — exit 2"
  exit 2
fi
echo "WRITE MODE: regeneration complete — exit 0"
exit 0
