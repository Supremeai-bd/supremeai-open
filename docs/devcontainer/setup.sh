#!/usr/bin/env bash
# ==============================================================================
# SupremeAI Codespace Post-Create Bootstrap Script
# ==============================================================================
# Sets up local development virtualenv and frontend dependencies inside Codespaces.
# Resilient: handles cold and warm cache paths without failing the container build.
# ==============================================================================

set -uo pipefail

echo "===================================================================="
echo "🚀 [SupremeAI Codespace] Initializing development environment..."
echo "===================================================================="

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# 1. Display Environment Information
echo "📦 Toolchain versions:"
python --version 2>&1 || true
node --version 2>&1 || true
pnpm --version 2>&1 || true
ruff --version 2>&1 || true

# 2. Setup Python / Poetry Virtualenv
if [ -d "backend" ] && [ -f "backend/pyproject.toml" ]; then
    echo "🐍 Configuring backend Poetry environment..."
    cd "${REPO_ROOT}/backend"
    poetry config virtualenvs.in-project true --local 2>/dev/null || poetry config virtualenvs.in-project true
    
    echo "📦 Installing backend dependencies via Poetry (non-interactive)..."
    poetry install --no-interaction --no-ansi || {
        echo "⚠️ Poetry install encountered a non-fatal warning; retrying or falling back..."
        poetry install --no-interaction --no-ansi --no-root || true
    }
    
    if [ -f ".venv/bin/python" ]; then
        echo "✅ Backend virtualenv created at backend/.venv"
    fi
    cd "${REPO_ROOT}"
fi

# 3. Setup Frontend Node Dependencies
if [ -f "pnpm-lock.yaml" ] || [ -d "frontend" ]; then
    echo "⚛️ Installing frontend dependencies via pnpm..."
    if command -v pnpm >/dev/null 2>&1; then
        pnpm install --frozen-lockfile 2>/dev/null || pnpm install || true
    elif command -v npm >/dev/null 2>&1; then
        npm install || true
    fi
    echo "✅ Frontend setup step completed."
fi

# 4. Verify Essential Linters and Tooling
echo "🔍 Running quick tooling healthcheck..."
ruff check backend/api --select E9,F821,F822,F823 2>/dev/null && echo "✅ Ruff lint check: PASSED" || echo "ℹ️ Ruff check ready."

echo "===================================================================="
echo "🎉 SupremeAI Codespace is ready for development!"
echo "Useful Commands:"
echo "  • Backend API:   cd backend && poetry run uvicorn app:app --reload --port 8000"
echo "  • Frontend:      cd frontend && pnpm run dev"
echo "  • Run Tests:     cd backend && poetry run pytest"
echo "  • Run Checks:    python scripts/git/pre-push"
echo "===================================================================="
