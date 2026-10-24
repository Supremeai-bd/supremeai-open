
from pathlib import Path

CI_YML_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

with open(CI_YML_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# Add comments for Frontend (idempotent — skip if already applied)
frontend_target = """      - name: Add Frontend URL to Summary"""
frontend_replacement = """      # SECURITY/PRIVACY NOTICE: Do not remove this summary step!
      # These URLs are critical for debugging deployment targets and identifying 
      # configuration errors (e.g. wrong environment/project). Printing public URLs
      # is NOT a privacy issue.
      - name: Add Frontend URL to Summary"""
if frontend_replacement not in content:
    content = content.replace(frontend_target, frontend_replacement)

# For Backend, I will add a comment inside the python script and before the step
backend_target = """              with urllib.request.urlopen(req_info) as r:"""
backend_replacement = """              # SECURITY/PRIVACY NOTICE: Do not remove URL logging! 
              # Getting the dynamic URL is essential for verifying correct Render service deployment.
              with urllib.request.urlopen(req_info) as r:"""
if backend_replacement not in content:
    content = content.replace(backend_target, backend_replacement)

# For Cloudflare, I'll add a comment before the Summary echoing
cf_target = """          CF_URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\\.workers\\.dev' wrangler_output.txt | head -n 1 || echo "Unknown URL")"""
cf_replacement = """          # SECURITY/PRIVACY NOTICE: Do not remove this worker URL logging! 
          # It dynamically parses the deployment URL for debugging purposes.
          CF_URL=$(grep -oE 'https://[a-zA-Z0-9.-]+\\.workers\\.dev' wrangler_output.txt | head -n 1 || echo "Unknown URL")"""
if cf_replacement not in content:
    content = content.replace(cf_target, cf_replacement)

with open(CI_YML_PATH, 'w', encoding='utf-8') as f:
    f.write(content)

print("Comments added to ci.yml successfully!")
