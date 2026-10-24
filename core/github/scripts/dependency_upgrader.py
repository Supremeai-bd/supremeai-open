#!/usr/bin/env python3
import json
import os
import subprocess


def upgrade_python_deps():
    print("Checking Python dependencies via Poetry...")
    try:
        # Check outdated dependencies
        result = subprocess.run(
            ["poetry", "show", "-o", "--json"],
            cwd="backend",
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return "Failed to run poetry show"

        data = json.loads(result.stdout)
        # poetry show -o --json format usually has a list under 'packages' or it's a list itself
        packages = data if isinstance(data, list) else data.get("packages", [])

        upgraded = []
        for pkg in packages:
            name = pkg.get("name")
            current = pkg.get("version", "0.0.0")
            latest = pkg.get("latest", "0.0.0")

            # SemVer check: Only upgrade if major version is the same
            curr_major = current.split('.')[0] if '.' in current else current
            latest_major = latest.split('.')[0] if '.' in latest else latest

            if curr_major == latest_major and current != latest:
                print(f"Upgrading {name} from {current} to {latest}")
                subprocess.run(["poetry", "update", name], cwd="backend")
                upgraded.append(f"- Python: `{name}` ({current} -> {latest})")

        if not upgraded:
            return "- No Python dependencies needed safe minor/patch upgrades."
        return "\n".join(upgraded)

    except Exception as e:
        return f"Error upgrading Python deps: {e}"

def upgrade_node_deps(path, label):
    print(f"Checking Node dependencies via pnpm in {path}...")
    try:
        if not os.path.exists(path):
            return f"- {label} path not found."

        # Check outdated
        result = subprocess.run(
            ["pnpm", "outdated", "--format", "json"],
            cwd=path,
            capture_output=True,
            text=True
        )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            data = {}

        upgraded = []
        for name, info in data.items():
            current = info.get("current", "0.0.0")
            latest = info.get("latest", "0.0.0")

            curr_major = current.split('.')[0] if '.' in current else current
            latest_major = latest.split('.')[0] if '.' in latest else latest

            if curr_major == latest_major and current != latest:
                print(f"Upgrading {name} from {current} to {latest}")
                subprocess.run(["pnpm", "update", f"{name}@{latest}"], cwd=path)
                upgraded.append(f"- {label}: `{name}` ({current} -> {latest})")

        if not upgraded:
            return f"- No {label} dependencies needed safe minor/patch upgrades."
        return "\n".join(upgraded)

    except Exception as e:
        return f"Error upgrading Node deps in {label}: {e}"

def main():
    summary = []
    summary.append("### 📦 Safe Dependency Upgrades (Minor/Patch)")

    # Python (Backend)
    if os.path.exists("backend"):
        summary.append("\n**Backend (Poetry):**")
        summary.append(upgrade_python_deps())

    # Node (Frontend)
    if os.path.exists("apps/studio-client"):
        summary.append("\n**Frontend (pnpm):**")
        summary.append(upgrade_node_deps("apps/studio-client", "Frontend"))

    summary_text = "\n".join(summary)
    print(summary_text) # Output to stdout for redirection

    # Write to GITHUB_OUTPUT for next steps
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            # Multi-line output format for GitHub Actions
            f.write("summary<<EOF\n")
            f.write(summary_text + "\n")
            f.write("EOF\n")

if __name__ == "__main__":
    main()
