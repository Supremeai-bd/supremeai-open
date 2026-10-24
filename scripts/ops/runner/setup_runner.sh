#!/usr/bin/env bash
set -euo pipefail

# Runner Setup Script for CI/CD and local development
# Configures environment secrets, services, and local runners

BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

setup_local_runner() {
    echo "Setting up local development runner..."

    # Ensure .env exists
    if [ ! -f "$BASE_DIR/.env" ]; then
        if [ -f "$BASE_DIR/.env.example" ]; then
            cp "$BASE_DIR/.env.example" "$BASE_DIR/.env"
            echo "Created .env from .env.example"
        else
            echo "Warning: .env.example not found"
        fi
    fi

    # Bootstrap missing env keys
    if [ -f "$BASE_DIR/scripts/bootstrap_env.py" ]; then
        cd "$BASE_DIR" && python scripts/bootstrap_env.py
    fi

    # Install backend deps
    if [ -f "$BASE_DIR/backend/pyproject.toml" ]; then
        echo "Installing backend dependencies..."
        cd "$BASE_DIR/backend" && poetry install --no-interaction --no-ansi --no-root || true
    fi

    # Install frontend deps
    if [ -f "$BASE_DIR/package.json" ]; then
        echo "Installing frontend dependencies..."
        cd "$BASE_DIR" && pnpm install --frozen-lockfile --prefer-offline || true
    fi

    echo "Local runner setup complete."
}

setup_docker_runner() {
    echo "Setting up Docker runner..."
    cd "$BASE_DIR"
    # #708: infrastructure/docker/ never existed — use the root compose file
    # (same fix as the package.json docker:build/docker:up scripts).
    docker-compose -f docker-compose.yml build
    docker-compose -f docker-compose.yml up -d
    echo "Docker runner started."
}

teardown_docker_runner() {
    echo "Tearing down Docker runner..."
    cd "$BASE_DIR"
    docker-compose -f docker-compose.yml down
    echo "Docker runner stopped."
}

case "${1:-}" in
    local)
        setup_local_runner
        ;;
    docker)
        setup_docker_runner
        ;;
    teardown)
        teardown_docker_runner
        ;;
    *)
        echo "Usage: $0 {local|docker|teardown}"
        exit 1
        ;;
esac
