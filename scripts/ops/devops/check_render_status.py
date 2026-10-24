import os
import sys
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
load_dotenv()
key = os.getenv("RENDER_API_KEY_1") or os.getenv("RENDER_API_KEY") or os.getenv("RENDER_API_KEY_4")
if not key:
    print("❌ No Render API key found.")
    exit(1)

res = requests.get("https://api.render.com/v1/services?limit=20", headers={"Authorization": f"Bearer {key}"})
if res.status_code != 200:
    print(f"❌ Render API returned {res.status_code}: {res.text}")
    exit(1)

data = res.json()
print(f"✅ Render connection successful! Found {len(data)} service(s):")
for item in data:
    s = item.get("service", {})
    name = s.get("name", "unnamed")
    repo = s.get("repo", "no-repo")
    branch = s.get("branch", "main")
    suspended = s.get("suspended", "not suspended")
    service_type = s.get("type", "")
    print(f"  • {name} [{service_type}]")
    print(f"    Repo: {repo} (branch: {branch})")
    print(f"    Suspended: {suspended}")
