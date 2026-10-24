import json
import os
import sys
import urllib.error
import urllib.request


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_issue.py <vulnerability-report.json>")
        sys.exit(1)

    report_path = sys.argv[1]
    if not os.path.exists(report_path):
        print(f"Report file {report_path} not found.")
        sys.exit(0)

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read report: {e}")
        sys.exit(1)

    vulnerabilities = data.get("dependencies", [])
    if not vulnerabilities:
        print("No vulnerabilities found to report.")
        sys.exit(0)

    # Filter to only keep packages that actually have vulnerabilities
    vuln_packages = [v for v in vulnerabilities if v.get("vulns")]
    if not vuln_packages:
        print("No critical vulnerabilities found.")
        sys.exit(0)

    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPOSITORY")

    if not github_token or not github_repo:
        print("GITHUB_TOKEN or GITHUB_REPOSITORY not set. Cannot create issue.")
        sys.exit(0)

    # Create the issue body
    body_lines = ["### 🚨 Security Vulnerabilities Detected\n", "The `dependency-vulnerability-scan` pipeline has found the following issues:\n"]
    for pkg in vuln_packages:
        pkg_name = pkg.get("name")
        pkg_version = pkg.get("version")
        for v in pkg.get("vulns", []):
            body_lines.append(f"- **{pkg_name}** ({pkg_version}): {v.get('id')} - {v.get('fix_versions', 'No fix available')}")
            body_lines.append(f"  - Details: {v.get('aliases', [])}")

    body = "\n".join(body_lines)

    payload = {
        "title": "🚨 Security Vulnerability Detected by pip-audit",
        "body": body,
        "labels": ["security", "automated-issue"]
    }

    url = f"https://api.github.com/repos/{github_repo}/issues"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 201:
                print("✅ Successfully created GitHub Issue for vulnerabilities.")
            else:
                print(f"Failed to create issue. Status: {response.status}")
    except urllib.error.URLError as e:
        print(f"Failed to create issue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
