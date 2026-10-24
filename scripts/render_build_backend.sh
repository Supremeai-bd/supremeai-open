#!/usr/bin/env bash
# Smart Build Script for SupremeAI Backend (Self-Healing)
#
# SECURITY NOTE: an earlier revision uploaded the full poetry install logs to a
# public kvdb.io bucket (https://kvdb.io/9y62Spaye2gXXGUnvgebsa/log) to debug
# Render builds. Build logs can contain package URLs, internal hostnames and
# environment summaries, so that external upload channel has been removed.
# Logs now stay on the build machine only (Render keeps them visible in the
# dashboard), and the tail is echoed to stdout for quick triage.

echo "==========================================="
echo "🚀 Starting Smart Build for Backend..."
echo "==========================================="

# Install poetry if not available
if ! command -v poetry &> /dev/null; then
    echo "📦 Installing Poetry..."
    # Issue #707: pin the tool install (unpinned = supply-chain risk). Version
    # matches the repo-wide poetry pin used by backend/Dockerfile,
    # backend/Dockerfile.ci and backend/services/scraper/Dockerfile.
    pip install poetry==2.4.1
fi

echo "📦 Attempting to install backend dependencies..."
# Disable exit-on-error temporarily to catch failures
set +e

poetry install --only main > poetry_install.log 2>&1
EXIT_CODE=$?

# Re-enable exit-on-error
set -e

if [ $EXIT_CODE -ne 0 ]; then
    echo "⚠️ Dependency installation failed with exit code $EXIT_CODE!"
    echo "---- Last 50 lines of poetry_install.log ----"
    tail -n 50 poetry_install.log
    echo "---------------------------------------------"
    echo "🧹 Possible corrupted cache detected. Clearing .venv and ~/.cache/pypoetry..."

    # Remove local virtual environment if it exists
    rm -rf .venv

    # Remove poetry global cache
    rm -rf ~/.cache/pypoetry

    echo "🔄 Retrying clean installation..."
    set +e
    poetry install --only main > poetry_install2.log 2>&1
    EXIT_CODE2=$?
    set -e
    if [ $EXIT_CODE2 -ne 0 ]; then
        echo "Second installation failed. Log tail:"
        tail -n 50 poetry_install2.log
        exit 1
    fi
else
    echo "✅ Backend dependencies installed successfully."
fi

echo "🎉 Backend build finished successfully!"
