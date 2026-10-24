import os
import subprocess
import sys

from tests.core.test_allowed_hosts_policy import BACKEND_DIR, _boot_env

env = _boot_env(ALLOWED_HOSTS="api.example.com")
env.pop("INFISICAL_TOKEN", None)
env.pop("INFISICAL_CLIENT_SECRET", None)
env.pop("INFISICAL_CLIENT_ID", None)
env["INFISICAL_DISABLE"] = "true"

code = 'from core.config import settings; print("HOSTS=" + ",".join(settings.allowed_hosts))'
proc = subprocess.run(
    [sys.executable, "-c", code],
    cwd=str(BACKEND_DIR),
    env=env,
    capture_output=True,
    text=True,
)
print("RC:", proc.returncode)
print("STDOUT:\n", proc.stdout)
print("STDERR:\n", proc.stderr)
