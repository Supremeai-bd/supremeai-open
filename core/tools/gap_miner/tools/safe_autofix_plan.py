#!/usr/bin/env python3
"""Generate a ranked, patch-ready remediation plan from Gap Miner JSON; never edits source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ORDER={'critical':4,'high':3,'medium':2,'low':1,'info':0}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('report'); ap.add_argument('--out',default='reports/autofix-plan.md'); a=ap.parse_args(); data=json.loads(Path(a.report).read_text('utf-8')); fs=sorted(data.get('findings',[]),key=lambda f:(-ORDER.get(f.get('severity','info'),0),-f.get('score',0)))
 lines=['# Safe Autofix Plan','', 'This is an execution plan only. It does not modify source code.','', '| Priority | Severity | Path | Finding | Suggested change |','|---:|---|---|---|---|']
 for i,f in enumerate(fs,1): lines.append(f"| {i} | {f.get('severity')} | `{f.get('path')}` | {f.get('title')} | {f.get('recommendation')} |")
 lines+=['','## Autonomous execution policy','','**Safe to automate:** formatting, report generation, deterministic metadata refresh, adding missing tests only when generated from existing fixtures.','','**Human approval required:** authentication, authorization, secrets, database migrations, dependency major upgrades, destructive file operations, deployment settings.']
 out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text('\n'.join(lines)+'\n',encoding='utf-8'); print(out)
if __name__=='__main__': main()
