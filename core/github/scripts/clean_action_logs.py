import json
import os
import sys
import urllib.error
import urllib.request


def main():
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")

    if not repo or not token:
        print("Missing GITHUB_REPOSITORY or GITHUB_TOKEN environment variables.")
        return 1

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    print(f"Fetching workflow runs for {repo}...")

    try:
        req = urllib.request.Request(url + "?per_page=1", headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"Failed to fetch runs: {e}")
        return 1

    total_count = data.get("total_count", 0)
    print(f"Total workflow runs currently: {total_count}")

    if total_count < 300:
        print("Total runs are less than 300. No cleanup needed.")
        return 0

    print("Total runs reached 300. Proceeding with cleanup...")

    runs = []
    page = 1
    while True:
        try:
            req = urllib.request.Request(url + f"?per_page=100&page={page}", headers=headers)
            with urllib.request.urlopen(req) as resp:
                r_data = json.loads(resp.read())
        except Exception:
            break

        page_runs = r_data.get("workflow_runs", [])
        if not page_runs:
            break
        runs.extend(page_runs)
        page += 1
        if len(runs) >= total_count or len(runs) >= 1000:
            break

    runs.sort(key=lambda x: x["created_at"], reverse=True)

    human_runs = []
    autofix_runs = []
    dependabot_runs = []
    other_bot_runs = []

    for run in runs:
        actor_login = run.get("actor", {}).get("login", "")
        actor_type = run.get("actor", {}).get("type", "User")

        if "dependabot" in actor_login.lower():
            dependabot_runs.append(run)
        elif "github-actions" in actor_login.lower() or actor_login.lower() == "supremeai-bot":
            autofix_runs.append(run)
        elif actor_type == "Bot" or "[bot]" in actor_login.lower():
            other_bot_runs.append(run)
        else:
            human_runs.append(run)

    keep_run_ids = set()

    for r in human_runs[:100]:
        keep_run_ids.add(r["id"])

    for r in autofix_runs[:50]:
        keep_run_ids.add(r["id"])

    for r in dependabot_runs[:10]:
        keep_run_ids.add(r["id"])

    for r in other_bot_runs[:10]:
        keep_run_ids.add(r["id"])

    runs_to_delete = [r for r in runs if r["id"] not in keep_run_ids]

    print(f"Keeping {len(keep_run_ids)} runs.")
    print(f"Deleting {len(runs_to_delete)} old runs...")

    deleted_count = 0
    for run in runs_to_delete:
        run_id = run["id"]
        del_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
        req = urllib.request.Request(del_url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req):
                deleted_count += 1
                print(f"Deleted run {run_id}")
        except Exception as e:
            print(f"Failed to delete run {run_id}: {e}")

    print(f"Cleanup finished. Deleted {deleted_count} workflow runs.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
