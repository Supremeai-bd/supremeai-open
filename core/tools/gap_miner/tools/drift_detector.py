#!/usr/bin/env python3
"""Detect drift between implementation, docs, configuration, and CI signals."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

EXCLUDED={'.git','node_modules','.venv','venv','dist','build','.next','.turbo','__pycache__'}
TOKENS=['supabase','redis','postgres','sqlite','firebase','render','vercel','cloudflare','gemini','groq','deepseek','huggingface','moonshot','ollama','docker','terraform','playwright','vitest','pytest','turbo','pnpm']
def scan(root):
 blobs=[]
 for base,ds,ns in os.walk(root):
  ds[:]=[d for d in ds if d not in EXCLUDED]
  for n in ns:
   p=Path(base)/n
   try:
    if p.suffix.lower() in {'.md','.py','.ts','.tsx','.js','.jsx','.json','.yaml','.yml','.toml','.ini'} and p.stat().st_size<1_500_000: blobs.append((p,p.read_text('utf-8','ignore').lower()))
   except OSError: _ = None
 findings=[]
 docs=[(p,t) for p,t in blobs if p.suffix.lower()=='.md' or 'docs' in p.parts]
 for token in TOKENS:
  code=sum(token in t for p,t in blobs if p.suffix.lower() not in {'.md'})
  doc=sum(token in t for p,t in docs)
  ci=sum(token in t for p,t in blobs if '.github' in p.parts)
  if code>=2 and doc==0: findings.append({'severity':'medium','type':'undocumented_infra','token':token,'evidence':f'code/config mentions={code}, docs mentions={doc}','recommendation':f'Document actual {token} usage and operational assumptions.'})
  if doc>=3 and code==0: findings.append({'severity':'low','type':'stale_documentation','token':token,'evidence':f'docs mentions={doc}, code/config mentions={code}','recommendation':f'Verify whether {token} is still deployed; remove stale docs or restore missing implementation.'})
  if code>=3 and ci==0 and token in {'docker','terraform','playwright','pytest','vitest','pnpm'}: findings.append({'severity':'medium','type':'ci_blind_spot','token':token,'evidence':f'code/config={code}, CI mentions={ci}','recommendation':f'Add a CI validation step for {token} if it is production-relevant.'})
 return findings

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('root',nargs='?',default='.'); ap.add_argument('--out',default='reports/drift-report.json'); a=ap.parse_args(); root=Path(a.root).resolve(); f=scan(root); out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'project':root.name,'findings':f},indent=2),encoding='utf-8'); print(json.dumps({'findings':f},indent=2))
if __name__=='__main__': main()
