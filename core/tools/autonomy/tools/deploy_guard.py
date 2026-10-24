from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common import find_secret_hits, json_dump, walk_files

HIGH_RISK = ('auth','security','migration','delete','payment','billing','infra','deploy','terraform','docker','secret')
def changed_files(root: Path):
    try:
        p=subprocess.run(['git','diff','--name-only','HEAD~1','HEAD'],cwd=root,text=True,capture_output=True,check=False)
        return [x.strip() for x in p.stdout.splitlines() if x.strip()]
    except Exception: return []

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('--output',default='reports/deploy_guard.json'); a=ap.parse_args(); root=Path(a.project).resolve()
    changed=changed_files(root); risk=[]
    for f in changed:
        low=f.lower()
        if any(k in low for k in HIGH_RISK): risk.append({'file':f,'reason':'high-impact path'})
    secrets=find_secret_hits(root)
    tests=sum(1 for p in walk_files(root) if 'test' in p.name.lower() or 'spec' in p.name.lower())
    result={'ready':not secrets and bool(tests),'changed_files':changed,'high_risk_changes':risk,'possible_secrets':secrets[:50],'test_file_count':tests,'required_checks':['targeted tests','lint/type checks','security scan','smoke test','rollback verification'],'approval':'human_required' if risk or secrets else 'policy_dependent'}
    json_dump(result,Path(a.output))

if __name__=='__main__': main()
