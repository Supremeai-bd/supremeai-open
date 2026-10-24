#!/usr/bin/env bash
set -euo pipefail

# Agent Task Runner
# Executes isolated tasks within a worktree context

WORKTREES_DIR="$(cd "$(dirname "$0")/.." && pwd)/.worktrees"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

run_task() {
    local task_name="$1"
    local command="${2:-pytest}"
    local worktree_path="$WORKTREES_DIR/$task_name"

    if [ ! -d "$worktree_path" ]; then
        echo "Error: Worktree not found for task '$task_name'. Run setup_worktree.sh create first."
        exit 1
    fi

    echo "Running task '$task_name' in $worktree_path"
    cd "$worktree_path"

    if [ -f "pyproject.toml" ]; then
        poetry run $command
    elif [ -f "package.json" ]; then
        pnpm run $command
    else
        eval "$command"
    fi
}

run_task "${1:-}" "${2:-pytest}"
