#!/bin/sh
# =============================================================================
# verify_studio_parity.sh — Federation Studio Parity & Drift Auditor (#399)
# =============================================================================
# Mission (issue #399, docs/FEDERATION_PARITY.md):
#   Verify byte/hash parity between the monorepo mirror surface (`frontend/`)
#   and the standalone `Supremeai-bd/supremeai-studio` repository, plus
#   dependency-map and design-token alignment. Produces a transparent audit
#   report and classifies every finding into one of three verdicts.
#
# Design doctrine (house style — docs/INGRESS_SECURITY_POLICY.md §5.2):
#   - Dependency-free: POSIX sh + git + coreutils only (one optional,
#     honestly-degraded JSON/dependency plane requires python3 and reports
#     SKIPPED when absent — it never blocks what it cannot verify, and it
#     never claims verification it did not do).
#   - Fail-closed on drift (exit 1), fail-honest on operational errors
#     (exit 2). Exit 0 ONLY when every executed plane reports parity.
#   - Read-only: this script never mutates either tree, never clones,
#     never touches the network. The workflow owns clone/artifact/alert IO.
#   - Secret hygiene: `.env*` and credential-shaped files are excluded from
#     the surface BEFORE any read; their contents are never hashed, logged
#     or reported.
#
# Exit contract (machine-readable, asserted by the CI workflow):
#   0 = PARITY  (all executed planes clean; skipped planes recorded honestly)
#   1 = DRIFT   (at least one executed plane found divergence)
#   2 = ERROR   (operational failure — cannot verify; e.g. missing roots,
#                unreadable files. UNVERIFIABLE is not "clean".)
#
# Flags:
#   --monorepo-root DIR   Monorepo checkout containing `frontend/` (required).
#   --studio-root DIR     Standalone studio checkout root      (required).
#   --report FILE         Write the markdown audit report here.
#   --json FILE           Write a machine-readable summary JSON here
#                         (requires python3; skipped honestly when absent).
#   --exclude PAT         Extra surface exclusion (matched against the
#                         slash-free basename OR the relative path via
#                         `case` glob). Repeatable; adds to the defaults.
#   --self-test           Offline guard-the-guard fixture suite; runs the
#                         auditor against generated trees and asserts every
#                         exit contract. Never touches real repositories.
# =============================================================================

set -u

PROGRAM="verify_studio_parity.sh"
TAB="$(printf '\t')"

# --- defaults -----------------------------------------------------------------
MONOREPO_ROOT=""
STUDIO_ROOT=""
REPORT_FILE=""
JSON_FILE=""
SELF_TEST=0
USER_EXCLUDES=""
PARITY_RUN_ID="${PARITY_RUN_ID:-}"   # opt-in report correlation id (set -u safe)

# Default mirror-surface exclusions (basenames or glob patterns).
# Rationale documented in docs/FEDERATION_PARITY.md §2:
#   .git/.github           — repo-specific plumbing, not product surface
#   node_modules/.next/... — build outputs, never mirrored
#   *.env / .env*          — SECRETS. Never hashed, never read, never reported.
#   vercel.json            — deployment-target-specific config
#   lockfiles              — byte-parity across repos is meaningless;
#                            dependency alignment is covered by the dep plane.
#   package.json           — name/scripts fields legitimately differ between
#                            the two repos; alignment is owned by the
#                            dependency plane (never byte-judged).
DEFAULT_EXCLUDES=".git .github node_modules .next dist build coverage .vercel .nuxt out .env* *.env vercel.json package.json package-lock.json pnpm-lock.yaml yarn.lock bun.lockb"

# Cap report rows per plane so a pathological tree cannot produce a
# multi-megabyte issue body (house style: bridge payload files[:100]).
MAX_ROWS=200

# --- tiny helpers -------------------------------------------------------------
log() { printf '%s\n' "$*"; }
err() { printf '%s\n' "$*" >&2; }
die2() {
    err "::error::${PROGRAM}: $*"
    exit 2
}
count_rows() { # $1=file -> row count (0 for empty/missing); single output
    if [ -s "$1" ]; then
        wc -l < "$1" | tr -d ' '
    else
        printf 0
    fi
}
# sha256 backend (GNU coreutils / macOS shasum). Empty output = backend failed.
hash_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1
    else
        :
    fi
}
usage() {
    cat <<'USAGE'
verify_studio_parity.sh — Federation Studio Parity & Drift Auditor (#399)

Usage:
  sh scripts/audit/verify_studio_parity.sh \
       --monorepo-root /path/to/monorepo \
       --studio-root   /path/to/supremeai-studio \
       [--report parity-report.md] [--json parity-summary.json]
       [--exclude pattern] ... [--self-test]

Exit contract:
  0 = PARITY   all executed planes clean (skips recorded honestly)
  1 = DRIFT    at least one executed plane found divergence
  2 = ERROR    operational failure — cannot verify (missing roots, unreadable)
USAGE
    exit 2
}

# --- arg parsing --------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --monorepo-root) [ $# -ge 2 ] || die2 "--monorepo-root needs a value"; MONOREPO_ROOT="$2"; shift 2 ;;
        --studio-root)   [ $# -ge 2 ] || die2 "--studio-root needs a value";   STUDIO_ROOT="$2";   shift 2 ;;
        --report)        [ $# -ge 2 ] || die2 "--report needs a value";        REPORT_FILE="$2";   shift 2 ;;
        --json)          [ $# -ge 2 ] || die2 "--json needs a value";          JSON_FILE="$2";     shift 2 ;;
        --exclude)       [ $# -ge 2 ] || die2 "--exclude needs a value";       USER_EXCLUDES="$USER_EXCLUDES $2"; shift 2 ;;
        --self-test)     SELF_TEST=1; shift ;;
        --help|-h)       usage ;;
        *)               die2 "unknown argument: $1 (see --help)" ;;
    esac
done

# =============================================================================
# Self-test mode — offline fixture suite, asserts the full exit contract.
# =============================================================================
if [ "$SELF_TEST" -eq 1 ]; then
    SELFTEST_BASE="$(mktemp -d "${TMPDIR:-/tmp}/parity-selftest.XXXXXX")" || { err "mktemp failed"; exit 2; }
    FAILS=0
    PASSES=0

    fixture_init() { # $1=name -> sets MR SR (monorepo/studio fixture roots)
        MR="$SELFTEST_BASE/$1/monorepo"; SR="$SELFTEST_BASE/$1/studio"
        mkdir -p "$MR/frontend/src" "$SR"
    }
    mk_file() { # $1=root $2=relpath $3=content
        mkdir -p "$(dirname "$1/$2")"
        printf '%s' "$3" > "$1/$2"
    }
    check() { # $1=label $2=expected $3=actual
        if [ "$2" = "$3" ]; then
            log "PASS $1"; PASSES=$((PASSES + 1))
        else
            log "FAIL $1 (expected=$2 actual=$3)"; FAILS=$((FAILS + 1))
        fi
    }

    # s1: identical trees -> 0, verdict PARITY
    fixture_init s1
    mk_file "$MR" "frontend/src/app.tsx" "export const a=1;"
    mk_file "$SR" "src/app.tsx"          "export const a=1;"
    mk_file "$MR" "frontend/package.json" '{"name":"m","dependencies":{"react":"18.2.0"}}'
    mk_file "$SR" "package.json"          '{"name":"s","dependencies":{"react":"18.2.0"}}'
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" \
        --report "$SELFTEST_BASE/s1.md" --json "$SELFTEST_BASE/s1.json" >/dev/null 2>&1
    check "s1 identical trees exit 0" 0 $?
    grep -q "VERDICT: PARITY" "$SELFTEST_BASE/s1.md" 2>/dev/null
    check "s1 verdict PARITY" 0 $?

    # s2: byte drift -> 1, report carries the drifted path + classification
    fixture_init s2
    mk_file "$MR" "frontend/package.json" '{"dependencies":{"react":"18.2.0"}}'
    mk_file "$SR" "package.json"          '{"dependencies":{"react":"18.2.0"}}'
    mk_file "$MR" "frontend/src/app.tsx" "export const a=1;"
    mk_file "$SR" "src/app.tsx"          "export const a=2;"
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s2.md" >/dev/null 2>&1
    check "s2 byte drift exit 1" 1 $?
    grep -q "src/app.tsx" "$SELFTEST_BASE/s2.md"
    check "s2 report names drifted path" 0 $?
    grep -q "DRIFTED" "$SELFTEST_BASE/s2.md"
    check "s2 report classifies DRIFTED" 0 $?

    # s3: one-sided files -> 1, both directions classified
    fixture_init s3
    mk_file "$MR" "frontend/package.json" '{}'
    mk_file "$SR" "package.json"          '{}'
    mk_file "$MR" "frontend/src/only_mono.tsx" "mono"
    mk_file "$SR" "src/only_studio.tsx"        "studio"
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s3.md" >/dev/null 2>&1
    check "s3 one-sided files exit 1" 1 $?
    grep -q "MONOREPO_ONLY" "$SELFTEST_BASE/s3.md"
    check "s3 MONOREPO_ONLY row" 0 $?
    grep -q "STUDIO_ONLY" "$SELFTEST_BASE/s3.md"
    check "s3 STUDIO_ONLY row" 0 $?

    # s4: missing studio root -> 2 (operational, never reported as clean)
    fixture_init s4
    sh "$0" --monorepo-root "$MR" --studio-root "$SELFTEST_BASE/s4/does-not-exist" >/dev/null 2>&1
    check "s4 missing studio root exit 2" 2 $?

    # s5: studio without package.json -> 2 (not a studio checkout)
    fixture_init s5
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" >/dev/null 2>&1
    check "s5 studio without package.json exit 2" 2 $?

    # s6: dependency drift -> 1 with VERSION_MISMATCH + MISSING_IN_STUDIO rows
    fixture_init s6
    mk_file "$MR" "frontend/package.json" '{"name":"m","dependencies":{"react":"18.2.0"},"devDependencies":{"typescript":"5.4.0"}}'
    mk_file "$SR" "package.json"          '{"name":"s","dependencies":{"react":"19.0.0"}}'
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s6.md" >/dev/null 2>&1
    check "s6 dependency drift exit 1" 1 $?
    grep -q "VERSION_MISMATCH" "$SELFTEST_BASE/s6.md"
    check "s6 VERSION_MISMATCH row" 0 $?
    grep -q "MISSING_IN_STUDIO" "$SELFTEST_BASE/s6.md"
    check "s6 MISSING_IN_STUDIO row" 0 $?

    # s7: design-token drift -> 1 with the token file named
    fixture_init s7
    mk_file "$MR" "frontend/package.json" '{}'
    mk_file "$SR" "package.json"          '{}'
    mk_file "$MR" "frontend/src/styles/tokens.json" '{"color.primary":"#000000"}'
    mk_file "$SR" "src/styles/tokens.json"          '{"color.primary":"#ffffff"}'
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s7.md" >/dev/null 2>&1
    check "s7 token drift exit 1" 1 $?
    grep -q "tokens.json" "$SELFTEST_BASE/s7.md"
    check "s7 token file named" 0 $?

    # s8: .env excluded BEFORE read — divergence there never blocks parity and
    #     secret contents never reach the report
    fixture_init s8
    mk_file "$MR" "frontend/package.json" '{}'
    mk_file "$SR" "package.json"          '{}'
    mk_file "$MR" "frontend/src/app.tsx" "same"
    mk_file "$SR" "src/app.tsx"          "same"
    mk_file "$MR" "frontend/.env.local"  "TOPSECRET_MONO=1"
    mk_file "$SR" ".env.local"           "TOPSECRET_STUDIO=2"
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s8.md" >/dev/null 2>&1
    check "s8 env-only divergence exit 0 (excluded plane)" 0 $?
    grep -q "TOPSECRET" "$SELFTEST_BASE/s8.md"
    check "s8 secret content never in report" 1 $?

    # s9: JSON mode — valid JSON with verdict + per-plane counts
    fixture_init s9
    mk_file "$MR" "frontend/package.json" '{}'
    mk_file "$SR" "package.json"          '{}'
    mk_file "$MR" "frontend/src/app.tsx" "same"
    mk_file "$SR" "src/app.tsx"          "same"
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --json "$SELFTEST_BASE/s9.json" >/dev/null 2>&1
    check "s9 json run exit 0" 0 $?
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import json,sys;d=json.load(open('$SELFTEST_BASE/s9.json'));sys.exit(0 if d.get('verdict')=='PARITY' and d['planes']['byte']['identical']==1 else 1)"
        check "s9 json verdict+counts" 0 $?
    else
        log "SKIP s9 json verdict+counts (python3 absent — plane honestly skipped)"
    fi

    # s10: determinism — two runs over the same drifted tree byte-match
    fixture_init s10
    mk_file "$MR" "frontend/package.json" '{}'
    mk_file "$SR" "package.json"          '{}'
    mk_file "$MR" "frontend/src/x.tsx" "v1"
    mk_file "$SR" "src/x.tsx"          "v2"
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s10a.md" >/dev/null 2>&1
    sh "$0" --monorepo-root "$MR" --studio-root "$SR" --report "$SELFTEST_BASE/s10b.md" >/dev/null 2>&1
    if cmp -s "$SELFTEST_BASE/s10a.md" "$SELFTEST_BASE/s10b.md"; then
        check "s10 report determinism" 0 0
    else
        check "s10 report determinism" same differing
    fi

    rm -rf "$SELFTEST_BASE"
    log "self-test: $PASSES passed, $FAILS failed"
    [ "$FAILS" -eq 0 ] || exit 1
    exit 0
fi

# =============================================================================
# Main audit
# =============================================================================
[ -n "$MONOREPO_ROOT" ] || die2 "--monorepo-root is required (see --help)"
[ -n "$STUDIO_ROOT" ] || die2 "--studio-root is required (see --help)"

# Normalize trailing slashes (find output prefix-stripping depends on it).
while [ "${MONOREPO_ROOT%/}" != "$MONOREPO_ROOT" ]; do MONOREPO_ROOT="${MONOREPO_ROOT%/}"; done
while [ "${STUDIO_ROOT%/}" != "$STUDIO_ROOT" ]; do STUDIO_ROOT="${STUDIO_ROOT%/}"; done

[ -d "$MONOREPO_ROOT" ] || die2 "monorepo root does not exist: $MONOREPO_ROOT"
[ -d "$STUDIO_ROOT" ] || die2 "studio root does not exist: $STUDIO_ROOT"
[ -d "$MONOREPO_ROOT/frontend" ] || die2 "monorepo root has no frontend/ mirror surface: $MONOREPO_ROOT/frontend (pass the checkout that contains frontend/)"
[ -f "$STUDIO_ROOT/package.json" ] || die2 "studio root has no package.json — not a studio checkout: $STUDIO_ROOT"

command -v sha256sum >/dev/null 2>&1 || command -v shasum >/dev/null 2>&1 ||
    die2 "no sha256 backend (sha256sum/shasum) available — byte plane cannot run"

AUDIT_TMP="$(mktemp -d "${TMPDIR:-/tmp}/parity-audit.XXXXXX")" || die2 "mktemp failed"
trap 'rm -rf "$AUDIT_TMP"' EXIT INT TERM

MONO_LIST="$AUDIT_TMP/mono.list"
STUDIO_LIST="$AUDIT_TMP/studio.list"
BOTH_LIST="$AUDIT_TMP/both.list"
MONO_ONLY="$AUDIT_TMP/mono_only.list"
STUDIO_ONLY="$AUDIT_TMP/studio_only.list"
ANOM_FILE="$AUDIT_TMP/anomalies.txt"
BYTE_ROWS="$AUDIT_TMP/byte_rows.txt"
DEP_ROWS="$AUDIT_TMP/dep_rows.txt"
TOKEN_ROWS="$AUDIT_TMP/token_rows.txt"
: > "$ANOM_FILE"; : > "$BYTE_ROWS"; : > "$DEP_ROWS"; : > "$TOKEN_ROWS"

is_excluded() { # $1=relative path -> 0 if excluded
    _p="$1"
    _base="${_p##*/}"
    for ex in $DEFAULT_EXCLUDES $USER_EXCLUDES; do
        # SC2254 silenced with intent: DEFAULT_EXCLUDES carries glob-class entries
        # (".env*", "*.env") whose pattern semantics are REQUIRED here — quoting
        # $ex would degrade secret-file exclusion to literal-only matching.
        # shellcheck disable=SC2254
        case "$_base" in
            $ex) return 0 ;;
        esac
        # shellcheck disable=SC2254
        case "$_p" in
            $ex) return 0 ;;
            */$ex) return 0 ;;
            $ex/*) return 0 ;;
        esac
    done
    # absolute secret guard — applies regardless of exclude-list edits
    case "$_base" in
        .env | *.env | .env.* | *.pem | *.key | *.p12 | *credential*) return 0 ;;
    esac
    return 1
}

# Enumerate the mirror surface (line-oriented; newline-in-filename files are
# recorded as anomalies and skipped — the anomaly count survives the pipeline
# subshell via the anomaly file, never via a variable).
list_side() { # $1=base-dir $2=strip-prefix $3=outfile
    find "$1" -type f | while IFS= read -r f; do
        case "$f" in
            *"
"*) printf 'x\n' >> "$ANOM_FILE"; continue ;;
        esac
        rel="${f#"$2"}"
        is_excluded "$rel" && continue
        printf '%s\n' "$rel"
    done | LC_ALL=C sort > "$3"
}

list_side "$MONOREPO_ROOT/frontend" "$MONOREPO_ROOT/frontend/" "$MONO_LIST"
list_side "$STUDIO_ROOT" "$STUDIO_ROOT/" "$STUDIO_LIST"

LC_ALL=C comm -12 "$MONO_LIST" "$STUDIO_LIST" > "$BOTH_LIST"
LC_ALL=C comm -23 "$MONO_LIST" "$STUDIO_LIST" > "$MONO_ONLY"
LC_ALL=C comm -13 "$MONO_LIST" "$STUDIO_LIST" > "$STUDIO_ONLY"
ANOMALIES="$(count_rows "$ANOM_FILE")"

# --- Plane 1: byte/hash parity -------------------------------------------------
N_IDENTICAL=0; N_DRIFTED=0; N_MONO_ONLY=0; N_STUDIO_ONLY=0; N_UNREADABLE=0
PLANE_ERROR=0

while IFS= read -r rel; do
    hm="$(hash_file "$MONOREPO_ROOT/frontend/$rel")"
    hs="$(hash_file "$STUDIO_ROOT/$rel")"
    if [ -z "$hm" ] || [ -z "$hs" ]; then
        N_UNREADABLE=$((N_UNREADABLE + 1))
        printf 'UNREADABLE\t%s\n' "$rel" >> "$BYTE_ROWS"
        continue
    fi
    if [ "$hm" = "$hs" ]; then
        N_IDENTICAL=$((N_IDENTICAL + 1))
    else
        N_DRIFTED=$((N_DRIFTED + 1))
        printf 'DRIFTED\t%s\n' "$rel" >> "$BYTE_ROWS"
    fi
done < "$BOTH_LIST"

while IFS= read -r rel; do
    N_MONO_ONLY=$((N_MONO_ONLY + 1))
    printf 'MONOREPO_ONLY\t%s\n' "$rel" >> "$BYTE_ROWS"
done < "$MONO_ONLY"
while IFS= read -r rel; do
    N_STUDIO_ONLY=$((N_STUDIO_ONLY + 1))
    printf 'STUDIO_ONLY\t%s\n' "$rel" >> "$BYTE_ROWS"
done < "$STUDIO_ONLY"

if [ "$N_UNREADABLE" -gt 0 ]; then
    # Unverifiable surface is never "clean" (boundary-guard doctrine).
    BYTE_VERDICT="ERROR"
    PLANE_ERROR=1
elif [ "$N_DRIFTED" -gt 0 ] || [ "$N_MONO_ONLY" -gt 0 ] || [ "$N_STUDIO_ONLY" -gt 0 ]; then
    BYTE_VERDICT="DRIFT"
else
    BYTE_VERDICT="PASS"
fi

# --- Plane 2: dependency-map parity (python3-assisted, honest degradation) -----
DEP_VERDICT="SKIPPED"
DEP_REASON="python3 unavailable"
if command -v python3 >/dev/null 2>&1; then
    DEP_REASON=""
    python3 - "$MONOREPO_ROOT/frontend/package.json" "$STUDIO_ROOT/package.json" \
        > "$DEP_ROWS" 2>/dev/null <<'PYEOF' || DEP_REASON="dependency plane crashed — recorded as advisory, never silently clean"
import json, sys
try:
    mono = json.load(open(sys.argv[1], encoding="utf-8"))
    studio = json.load(open(sys.argv[2], encoding="utf-8"))
except Exception:
    print("PARSE_ERROR\tpackage.json\t-\t-")
    sys.exit(0)
m, s = {}, {}
for src, acc in ((mono, m), (studio, s)):
    for sect in ("dependencies", "devDependencies"):
        for k, v in (src.get(sect) or {}).items():
            acc[k] = str(v)
for k in sorted(set(m) | set(s)):
    mv, sv = m.get(k), s.get(k)
    if mv is None:
        print("MISSING_IN_MONOREPO\t%s\t-\t%s" % (k, sv))
    elif sv is None:
        print("MISSING_IN_STUDIO\t%s\t%s\t-" % (k, mv))
    elif mv != sv:
        print("VERSION_MISMATCH\t%s\t%s\t%s" % (k, mv, sv))
PYEOF
    if [ -s "$DEP_ROWS" ]; then
        N_DEP_ROWS="$(count_rows "$DEP_ROWS")"
        case "$(head -n 1 "$DEP_ROWS")" in
            PARSE_ERROR*)
                DEP_VERDICT="SKIPPED"
                DEP_REASON="package.json unparseable — recorded in report, not silently clean"
                ;;
            *) DEP_VERDICT="DRIFT" ;;
        esac
    else
        N_DEP_ROWS=0
        if [ -n "$DEP_REASON" ]; then
            DEP_VERDICT="SKIPPED"
        else
            DEP_VERDICT="PASS"
        fi
    fi
else
    N_DEP_ROWS=0
fi

# --- Plane 3: design-token alignment (filtered view of the byte plane) ---------
N_TOKEN_ROWS=0
while IFS="$TAB" read -r cls rel; do
    case "$rel" in
        *tokens*.json | *tokens*.css | *tokens*.js | *tokens*.ts | *tokens*.cjs | *tokens*.mjs) ;;
        *) continue ;;
    esac
    printf '%s\t%s\n' "$cls" "$rel" >> "$TOKEN_ROWS"
    N_TOKEN_ROWS=$((N_TOKEN_ROWS + 1))
done < "$BYTE_ROWS"
if [ "$PLANE_ERROR" -eq 1 ]; then
    TOKEN_VERDICT="ERROR"
elif [ "$N_TOKEN_ROWS" -gt 0 ]; then
    TOKEN_VERDICT="DRIFT"
else
    TOKEN_VERDICT="PASS"
fi

# --- Overall verdict ------------------------------------------------------------
if [ "$PLANE_ERROR" -eq 1 ]; then
    VERDICT="ERROR"
elif [ "$BYTE_VERDICT" = "DRIFT" ] || [ "$DEP_VERDICT" = "DRIFT" ] || [ "$TOKEN_VERDICT" = "DRIFT" ]; then
    VERDICT="DRIFT"
else
    VERDICT="PARITY"
fi

# --- Report (deterministic: no timestamps; PARITY_RUN_ID opt-in) ----------------
if [ -n "$REPORT_FILE" ]; then
    {
        printf '# Studio Parity Audit Report (#399)\n\n'
        printf -- '- monorepo_root: `%s`\n' "$MONOREPO_ROOT"
        printf -- '- studio_root: `%s`\n' "$STUDIO_ROOT"
        [ -n "$PARITY_RUN_ID" ] && printf -- '- run_id: `%s`\n' "$PARITY_RUN_ID"
        printf -- '- surface_files_identical: %s\n' "$N_IDENTICAL"
        N_USER_EX="$(printf '%s' "$USER_EXCLUDES" | wc -w | tr -d ' ')"
        printf -- '- surface_exclusions: documented defaults (+%s user patterns)\n' "$N_USER_EX"
        [ "$ANOMALIES" -gt 0 ] &&
            printf -- '- anomalies: %s newline-in-filename file(s) skipped (line-oriented audit cannot carry them)\n' "$ANOMALIES"
        printf '\n## Verdict\n\n'
        printf 'VERDICT: %s\n' "$VERDICT"
        printf -- '- byte_parity: %s (identical=%s drifted=%s monorepo_only=%s studio_only=%s unreadable=%s)\n' \
            "$BYTE_VERDICT" "$N_IDENTICAL" "$N_DRIFTED" "$N_MONO_ONLY" "$N_STUDIO_ONLY" "$N_UNREADABLE"
        printf -- '- dependency_parity: %s%s\n' "$DEP_VERDICT" "${DEP_REASON:+ (reason: $DEP_REASON)}"
        printf -- '- design_token_parity: %s (rows=%s)\n' "$TOKEN_VERDICT" "$N_TOKEN_ROWS"
        printf '\n## Byte drift\n\n'
        if [ -s "$BYTE_ROWS" ]; then
            printf '| class | path |\n|---|---|\n'
            head -n "$MAX_ROWS" "$BYTE_ROWS" | while IFS="$TAB" read -r c p; do
                printf '| %s | `%s` |\n' "$c" "$p"
            done
            TOTAL_ROWS="$(count_rows "$BYTE_ROWS")"
            if [ "$TOTAL_ROWS" -gt "$MAX_ROWS" ]; then
                printf '\n_+%s more rows truncated (cap %s)_\n' "$((TOTAL_ROWS - MAX_ROWS))" "$MAX_ROWS"
            fi
        else
            printf '_none — all surface files hash-identical in both directions_\n'
        fi
        printf '\n## Dependency drift\n\n'
        if [ "$DEP_VERDICT" = "SKIPPED" ]; then
            printf '_SKIPPED: %s_\n' "$DEP_REASON"
        elif [ -s "$DEP_ROWS" ]; then
            printf '| class | package | monorepo | studio |\n|---|---|---|---|\n'
            head -n "$MAX_ROWS" "$DEP_ROWS" | while IFS="$TAB" read -r c p mv sv; do
                printf '| %s | `%s` | %s | %s |\n' "$c" "$p" "${mv:--}" "${sv:--}"
            done
        else
            printf '_none — dependency maps aligned_\n'
        fi
        printf '\n## Design tokens\n\n'
        if [ -s "$TOKEN_ROWS" ]; then
            printf '| class | path |\n|---|---|\n'
            head -n "$MAX_ROWS" "$TOKEN_ROWS" | while IFS="$TAB" read -r c p; do
                printf '| %s | `%s` |\n' "$c" "$p"
            done
        else
            printf '_none — token files aligned (or none present on the surface)_\n'
        fi
        printf '\n## Plane notes\n\n'
        printf -- '- Unreadable files classify the run ERROR (UNVERIFIABLE is never clean).\n'
        printf -- '- Remediation direction: monorepo `frontend/` is the public-first SSOT; STUDIO_ONLY rows flow studio -> monorepo, MONOREPO_ONLY / DRIFTED rows flow monorepo -> studio (bi-directional alerting — docs/FEDERATION_PARITY.md §4).\n'
        printf -- '- Skipped planes are recorded with reasons; a skipped plane never masks drift in executed planes.\n'
    } > "$REPORT_FILE"
fi

# --- JSON summary ---------------------------------------------------------------
if [ -n "$JSON_FILE" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$JSON_FILE" "$VERDICT" "$BYTE_VERDICT" "$DEP_VERDICT" "$TOKEN_VERDICT" \
        "$N_IDENTICAL" "$N_DRIFTED" "$N_MONO_ONLY" "$N_STUDIO_ONLY" "$N_UNREADABLE" \
        "${N_DEP_ROWS:-0}" "$N_TOKEN_ROWS" <<'PYEOF'
import json, sys
out, verdict = sys.argv[1], sys.argv[2]
byte_v, dep_v, tok_v = sys.argv[3], sys.argv[4], sys.argv[5]
ident, drifted, mono_only, studio_only, unreadable, dep_rows, tok_rows = map(int, sys.argv[6:13])
doc = {
    "verdict": verdict,
    "planes": {
        "byte": {"verdict": byte_v, "identical": ident, "drifted": drifted,
                 "monorepo_only": mono_only, "studio_only": studio_only,
                 "unreadable": unreadable},
        "dependencies": {"verdict": dep_v, "rows": dep_rows},
        "design_tokens": {"verdict": tok_v, "rows": tok_rows},
    },
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2, sort_keys=True)
    fh.write("\n")
PYEOF
fi

# --- Exit contract ----------------------------------------------------------------
log "${PROGRAM}: VERDICT=${VERDICT} byte=${BYTE_VERDICT}(i=${N_IDENTICAL},d=${N_DRIFTED},mo=${N_MONO_ONLY},so=${N_STUDIO_ONLY},u=${N_UNREADABLE}) deps=${DEP_VERDICT}(${N_DEP_ROWS:-0}) tokens=${TOKEN_VERDICT}(${N_TOKEN_ROWS})"
if [ "$VERDICT" = "PARITY" ]; then exit 0; fi
if [ "$VERDICT" = "DRIFT" ]; then exit 1; fi
exit 2
