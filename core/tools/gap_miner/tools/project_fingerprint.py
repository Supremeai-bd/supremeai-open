#!/usr/bin/env python3
"""Universal project fingerprint: creates a compact, deterministic architecture map."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

EXCLUDED={'.git','node_modules','.venv','venv','dist','build','coverage','.next','.turbo','target','__pycache__','.pytest_cache'}
EXTS={'.py','.ts','.tsx','.js','.jsx','.mjs','.cjs','.go','.rs','.java','.kt','.dart','.php','.rb','.json','.yaml','.yml','.toml','.ini','.md','.sql','.sh','.ps1'}
IMPORT_RE=re.compile(r'^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))',re.MULTILINE)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('root',nargs='?',default='.'); ap.add_argument('--out',default='reports/project-fingerprint.json'); args=ap.parse_args()
    root=Path(args.root).resolve(); files=[]; ext=Counter(); dirs=Counter(); sizes=[]; imports=Counter(); symbols=Counter()
    for base, ds, ns in os.walk(root):
        ds[:]=[d for d in ds if d not in EXCLUDED]
        for n in ns:
            p=Path(base)/n
            try:s=p.stat().st_size
            except OSError:continue
            if not p.is_file(): continue
            files.append(p); ext[p.suffix.lower() or '<none>']+=1; sizes.append((s,p));
            rel=p.relative_to(root)
            if rel.parts: dirs[rel.parts[0]]+=1
            if p.suffix.lower() in EXTS and s<1_500_000:
                try:t=p.read_text('utf-8','ignore')
                except OSError:t=''
                for a,b in IMPORT_RE.findall(t): imports[(a or b).split('.')[0]]+=1
                if p.suffix.lower()=='.py': symbols['python']+=len(re.findall(r'^\s*(?:def|class)\s+',t,re.MULTILINE))
                elif p.suffix.lower() in {'.ts','.tsx','.js','.jsx'}: symbols['javascript']+=len(re.findall(r'^\s*(?:export\s+)?(?:async\s+)?function\s+|^\s*(?:export\s+)?class\s+',t,re.MULTILINE))
    manifest=[p.name for p in [root/'package.json',root/'pyproject.toml',root/'requirements.txt',root/'Cargo.toml',root/'go.mod',root/'pubspec.yaml'] if p.exists()]
    likely_services=[]
    for p in files:
        r=str(p.relative_to(root)).replace('\\','/').lower()
        if any(x in r for x in ['api/','routes/','controllers/','services/','workers/','functions/','handlers/']): likely_services.append(r)
    payload={'project':root.name,'root':str(root),'fingerprint':hashlib.sha256('\n'.join(sorted(str(p.relative_to(root)) for p in files)).encode()).hexdigest()[:16], 'files':len(files),'extensions':ext.most_common(20),'top_level_dirs':dirs.most_common(20),'manifests':manifest,'largest_files':[{'path':str(p.relative_to(root)).replace('\\','/'),'bytes':s} for s,p in sorted(sizes,reverse=True)[:25]],'import_hubs':imports.most_common(25),'symbol_counts':dict(symbols),'service_like_files':likely_services[:100]}
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8'); print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
