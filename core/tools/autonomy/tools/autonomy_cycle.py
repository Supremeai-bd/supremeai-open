from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd, output):
    p=subprocess.run([sys.executable,*cmd],cwd=cwd,text=True,capture_output=True)
    output.append({'cmd':' '.join(cmd),'returncode':p.returncode,'stderr':p.stderr[-2000:]})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('--output',default='reports/autonomy_cycle.json'); a=ap.parse_args(); root=Path(a.project).resolve(); out=[]
    tools=Path(__file__).resolve().parent
    jobs=[['maintenance_watchdog.py',str(root)],['deploy_guard.py',str(root)],['capability_builder.py',str(root),'--goal','general project improvement']]
    for j in jobs: run([str(tools/j[0]),*j[1:]],root,out)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps({'project':str(root),'cycle':'observe-diagnose-plan-verify','steps':out},indent=2),encoding='utf-8')
if __name__=='__main__': main()
