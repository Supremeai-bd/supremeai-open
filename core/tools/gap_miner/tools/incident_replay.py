#!/usr/bin/env python3
"""Turn incident/error logs into deterministic replay cases and regression seeds."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

PATTERNS=[('timeout',re.IGNORECASE|0),('rate_limit',re.IGNORECASE),('429',0),('connection',re.IGNORECASE),('traceback',re.IGNORECASE),('exception',re.IGNORECASE),('error',re.IGNORECASE),('failed',re.IGNORECASE)]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--out',default='reports/incidents/replay_cases.json'); ap.add_argument('--context',type=int,default=3); a=ap.parse_args(); p=Path(a.input); text=p.read_text('utf-8','ignore'); lines=text.splitlines(); cases=[]
 for i,line in enumerate(lines):
  if any(re.search(pattern,line,flags) for pattern,flags in PATTERNS):
   block='\n'.join(lines[max(0,i-a.context):min(len(lines),i+a.context+1)])
   cid=hashlib.sha1(block.encode()).hexdigest()[:12]
   cases.append({'id':cid,'trigger_line':i+1,'signal':line[:500],'context':block,'regression_test_hint':'Replay this input against the same route/provider and assert the original failure class is prevented or handled.'})
 seen=set(); uniq=[]
 for c in cases:
  if c['id'] not in seen: seen.add(c['id']); uniq.append(c)
 payload={'source':str(p),'case_count':len(uniq),'cases':uniq[:500]}; out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); print(f'created {len(uniq)} replay candidates -> {out}')
if __name__=='__main__': main()
