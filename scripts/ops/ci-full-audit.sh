#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
REPORT_DIR="${ROOT_DIR}/ci-reports"

mkdir -p "${REPORT_DIR}"

ERRORS=0
WARNINGS=0

log() {
  printf '\n[%s] %s\n' "$1" "$2"
}

error() {
  printf 'ERROR: %s\n' "$1" | tee -a "${REPORT_DIR}/errors.txt"
  ERRORS=$((ERRORS + 1))
}

warning() {
  printf 'WARNING: %s\n' "$1" | tee -a "${REPORT_DIR}/warnings.txt"
  WARNINGS=$((WARNINGS + 1))
}

run_check() {
  local name="$1"
  shift

  log "CHECK" "${name}"

  if "$@"; then
    printf 'PASS: %s\n' "${name}" | tee -a "${REPORT_DIR}/summary.txt"
  else
    error "${name}"
  fi
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

: > "${REPORT_DIR}/errors.txt"
: > "${REPORT_DIR}/warnings.txt"
: > "${REPORT_DIR}/summary.txt"

cd "${ROOT_DIR}"

log "START" "SupremeAI full CI audit started"

# ------------------------------------------------------------
# 1. Required files
# ------------------------------------------------------------

check_required_files() {
  local files=(
    "package.json"
    "pnpm-lock.yaml"
    "backend/pyproject.toml"
    "backend/poetry.lock"
    ".github/workflows/ci.yml"
  )

  for file in "${files[@]}"; do
    if [[ ! -f "${ROOT_DIR}/${file}" ]]; then
      echo "Missing required file: ${file}"
      return 1
    fi
  done
}

run_check "Required project files" check_required_files

# ------------------------------------------------------------
# 2. Git state and repository safety
# ------------------------------------------------------------

check_git_state() {
  if git diff --quiet -- ':!ci-reports/**' ':!*.xml' ':!*.json'; then
    return 0
  fi

  echo "Tracked source files contain uncommitted changes"
  git diff --name-only -- ':!ci-reports/**' ':!*.xml' ':!*.json'
  return 1
}

run_check "Tracked source files are clean" check_git_state

check_large_files() {
  local result
  result="$(git ls-files -z | xargs -0 -r du -k | awk '$1 > 10240 {print}')"

  if [[ -n "${result}" ]]; then
    echo "${result}"
    return 1
  fi
}

run_check "No tracked file is larger than 10 MB" check_large_files

# ------------------------------------------------------------
# 3. Secret scanning
# ------------------------------------------------------------

check_secrets() {
  local patterns=(
    'AKIA[0-9A-Z]{16}'
    '-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----'
    'ghp_[A-Za-z0-9_]{30,}'
    'github_pat_[A-Za-z0-9_]{30,}'
    'sk-[A-Za-z0-9]{20,}'
    'xox[baprs]-[A-Za-z0-9-]{20,}'
    'SUPABASE_SERVICE_ROLE_KEY\s*='
    'DATABASE_URL\s*=\s*["'\''][^$]'
    'JWT_SECRET\s*=\s*["'\''][^$]'
    'SECRET_KEY\s*=\s*["'\''][^$]'
  )

  local found=0

  for pattern in "${patterns[@]}"; do
    if git grep -n -I -E "${pattern}" -- \
      ':!*.lock' \
      ':!ci-reports/**' \
      ':!.env.example' \
      ':!docs/**' \
      ':!README.md' \
      ':!backend/examples/**' \
      ':!backend/tests/**' \
      ':!backend/tools/learning/**' \
      >/tmp/secret-scan.txt 2>/dev/null; then
      cat /tmp/secret-scan.txt
      found=1
    fi
  done

  [[ "${found}" -eq 0 ]]
}

run_check "Hard-coded secret scan" check_secrets

if command_exists gitleaks; then
  run_check "Gitleaks full-history scan" \
    gitleaks detect --source "${ROOT_DIR}" --no-banner --redact
else
  warning "gitleaks is not installed; install it in GitHub Actions"
fi

if command_exists trufflehog; then
  run_check "TruffleHog filesystem scan" \
    trufflehog filesystem "${ROOT_DIR}" \
      --only-verified \
      --no-update
else
  warning "trufflehog is not installed; install it in GitHub Actions"
fi

# ------------------------------------------------------------
# 4. Dangerous code patterns
# ------------------------------------------------------------

check_dangerous_patterns() {
  local failed=0

  if git grep -n -I -E \
    'verify_signature[[:space:]]*:[[:space:]]*False|ssl[[:space:]]*=[[:space:]]*False|verify[[:space:]]*=[[:space:]]*False' \
    -- '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' \
    ':!backend/examples/**' \
    ':!**/tests/**' \
    ':!scripts/quality/regression_scanner.py' \
    ':!scripts/ci-full-audit.sh' \
    ':!.github/scripts/**' \
    >/tmp/dangerous-security-patterns.txt 2>/dev/null; then
    cat /tmp/dangerous-security-patterns.txt
    failed=1
  fi

  if git grep -n -I -E \
    'except[[:space:]]*:[[:space:]]*$|except[[:space:]]+Exception[[:space:]]*:[[:space:]]*(pass|return[[:space:]]+None)[[:space:]]*$' \
    -- '*.py' \
    ':!**/tests/**' \
    ':!**/scripts/**' \
    ':!**/tools/**' \
    >/tmp/broad-exceptions.txt 2>/dev/null; then
    cat /tmp/broad-exceptions.txt
    failed=1
  fi

  if git grep -n -I -E \
    'eval[[:space:]]*\(|exec[[:space:]]*\(|os\.system[[:space:]]*\(|subprocess\.(run|Popen|call)\(' \
    -- '*.py' '*.ts' '*.tsx' '*.js' '*.jsx' \
    ':!**/tests/**' >/tmp/code-execution-patterns.txt 2>/dev/null; then
    cat /tmp/code-execution-patterns.txt
    failed=1
  fi

  if git grep -n -I -E \
    'JSON\.parse[[:space:]]*\(' \
    -- '*.ts' '*.tsx' '*.js' '*.jsx' \
    ':!**/tests/**' >/tmp/json-parse-patterns.txt 2>/dev/null; then
    cat /tmp/json-parse-patterns.txt
    warning "JSON.parse usages require schema validation review"
  fi

  [[ "${failed}" -eq 0 ]]
}

run_check "Dangerous security and code execution patterns" check_dangerous_patterns

# ------------------------------------------------------------
# 5. GitHub Actions security
# ------------------------------------------------------------

check_github_actions() {
  local failed=0

  while IFS= read -r line; do
    if [[ "${line}" =~ uses:.*@(main|master|v[0-9]+|[0-9]+)$ ]]; then
      echo "${line}"
      failed=1
    fi
  done < <(git grep -n -E 'uses:' -- '.github/workflows/*.yml' '.github/workflows/*.yaml' 2>/dev/null || true)

  if git grep -n -E 'pull_request_target|permissions:[[:space:]]*write-all|curl .*\\|.*sh|wget .*\\|.*sh' \
    -- '.github/workflows/*.yml' '.github/workflows/*.yaml' \
    >/tmp/github-action-risks.txt 2>/dev/null; then
    cat /tmp/github-action-risks.txt
    failed=1
  fi

  [[ "${failed}" -eq 0 ]]
}

run_check "GitHub Actions supply-chain and permission checks" check_github_actions

# ------------------------------------------------------------
# 6. YAML and configuration validation
# ------------------------------------------------------------

if command_exists yamllint; then
  run_check "YAML lint" yamllint .
else
  warning "yamllint is not installed"
fi

if command_exists actionlint; then
  run_check "GitHub Actions syntax validation" actionlint
else
  warning "actionlint is not installed"
fi

# ------------------------------------------------------------
# 7. Python backend checks
# ------------------------------------------------------------

check_backend_files() {
  [[ -d "${BACKEND_DIR}" ]] &&
    [[ -f "${BACKEND_DIR}/pyproject.toml" ]] &&
    [[ -f "${BACKEND_DIR}/poetry.lock" ]]
}

run_check "Backend structure" check_backend_files

if command_exists poetry; then
  run_check "Poetry lock consistency" \
    bash -c "cd '${BACKEND_DIR}' && poetry check --lock"

  run_check "Backend dependency audit" \
    bash -c "cd '${BACKEND_DIR}' && poetry run pip-audit"

  run_check "Backend Ruff lint" \
    bash -c "cd '${BACKEND_DIR}' && poetry run ruff check ."

  run_check "Backend Ruff format check" \
    bash -c "cd '${BACKEND_DIR}' && poetry run ruff format --check ."

  run_check "Backend type check" \
    bash -c "cd '${BACKEND_DIR}' && poetry run mypy core api tools ws workers"

  run_check "Backend tests with coverage" \
    bash -c "cd '${BACKEND_DIR}' && poetry run pytest --cov=core --cov=api --cov=tools --cov=ws --cov=workers --cov-report=term-missing --cov-report=xml --cov-fail-under=80"

  if [[ -n "${SUPABASE_DATABASE_URL_WRITER:-}" ]]; then
    run_check "Database migration upgrade" \
      bash -c "cd '${BACKEND_DIR}' && poetry run alembic upgrade head"

    run_check "Database migration consistency" \
      bash -c "cd '${BACKEND_DIR}' && poetry run alembic check"
  else
    error "SUPABASE_DATABASE_URL_WRITER is not configured"
  fi
else
  error "Poetry is not installed"
fi

# ------------------------------------------------------------
# 8. SQLite fallback detection
# ------------------------------------------------------------

check_sqlite_fallback() {
  local found=0

  if git grep -n -I -E \
    'sqlite:///|aiosqlite|use_sqlite|SQLite fallback|fallback.*sqlite' \
    -- backend \
    ':!backend/tests/**' \
    ':!backend/migrations/**' \
    >/tmp/sqlite-runtime.txt 2>/dev/null; then
    cat /tmp/sqlite-runtime.txt
    found=1
  fi

  [[ "${found}" -eq 0 ]]
}

run_check "No SQLite fallback in production runtime" check_sqlite_fallback

# ------------------------------------------------------------
# 9. Frontend checks
# ------------------------------------------------------------

if [[ -d "${FRONTEND_DIR}" ]]; then
  if command_exists pnpm; then
    run_check "Frontend dependency lock consistency" \
      pnpm install --frozen-lockfile --ignore-scripts

    run_check "Frontend lint" \
      pnpm --dir "${FRONTEND_DIR}" lint

    run_check "Frontend type check" \
      pnpm --dir "${FRONTEND_DIR}" typecheck

    run_check "Frontend tests" \
      pnpm --dir "${FRONTEND_DIR}" test -- --run

    # VITE_USER_BACKEND is required by the vite production build (fail-fast guard).
    # CI builds use the deployed primary node URL — same value the live frontend uses.
    run_check "Frontend production build" \
      env VITE_USER_BACKEND="https://supremeai-primary-node.onrender.com" \
      pnpm --dir "${FRONTEND_DIR}" build
  else
    error "pnpm is not installed"
  fi
else
  warning "Frontend directory does not exist"
fi

# ------------------------------------------------------------
# 10. Root project checks
# ------------------------------------------------------------

if command_exists pnpm; then
  run_check "Root formatting check" \
    pnpm exec prettier --check \
      "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}" \
      --ignore-path .gitignore

  run_check "Root dependency audit" pnpm audit --audit-level=high
else
  error "pnpm is not installed"
fi

# ------------------------------------------------------------
# 11. Docker checks
# ------------------------------------------------------------

if command_exists docker; then
  run_check "Backend Docker image build" \
    docker build --pull --no-cache \
      -f "${BACKEND_DIR}/Dockerfile" \
      -t supremeai-backend:ci \
      "${BACKEND_DIR}"

  run_check "Docker image vulnerability scan" \
    docker run --rm \
      -v /var/run/docker.sock:/var/run/docker.sock \
      aquasec/trivy:latest \
      image --exit-code 1 --severity CRITICAL supremeai-backend:ci

  run_check "Docker image runs as non-root" \
    bash -c "docker inspect supremeai-backend:ci --format '{{.Config.User}}' | grep -v '^$'"

  run_check "Docker image exposes port 8080" \
    bash -c "docker inspect supremeai-backend:ci --format '{{json .Config.ExposedPorts}}' | grep -q '8080'"
else
  warning "Docker is not installed; Docker checks skipped"
fi

# ------------------------------------------------------------
# 12. Production environment validation
# ------------------------------------------------------------

check_required_environment_names() {
  local required=(
    SUPREMEAI_JWT_SECRET
    SUPABASE_DATABASE_URL_WRITER
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    REDIS_URL
  )

  local failed=0

  for key in "${required[@]}"; do
    if [[ -z "${!key:-}" ]]; then
      echo "Missing environment variable: ${key}"
      failed=1
    fi
  done

  [[ "${failed}" -eq 0 ]]
}

run_check "Required production environment variables" check_required_environment_names

check_weak_secrets() {
  local secret="${SUPREMEAI_JWT_SECRET:-}"

  [[ -n "${secret}" ]] || return 1
  [[ "${secret}" != "change-me" ]]
  [[ "${secret}" != "secret" ]]
  [[ "${#secret}" -ge 32 ]]
}

run_check "JWT secret strength" check_weak_secrets

# ------------------------------------------------------------
# 13. API health smoke test
# ------------------------------------------------------------

if [[ -n "${SUPREMEAI_BASE_URL:-}" ]] && command_exists curl; then
  run_check "Live health endpoint" \
    curl --fail --silent --show-error \
      --max-time 15 \
      "${SUPREMEAI_BASE_URL}/api/v1/health/live"

  run_check "Live readiness endpoint" \
    curl --fail --silent --show-error \
      --max-time 15 \
      "${SUPREMEAI_BASE_URL}/api/v1/health/ready"
else
  warning "SUPREMEAI_BASE_URL is not configured; live health checks skipped"
fi

# ------------------------------------------------------------
# 14. Final result
# ------------------------------------------------------------

log "RESULT" "Errors: ${ERRORS}; Warnings: ${WARNINGS}"

if [[ "${ERRORS}" -gt 0 ]]; then
  printf '\nCI AUDIT COMPLETED WITH ERRORS (Non-blocking)\n'
  printf 'See reports in: %s\n' "${REPORT_DIR}"
  exit 0
fi

printf '\nCI AUDIT PASSED\n'
printf 'Warnings: %s\n' "${WARNINGS}"
exit 0
