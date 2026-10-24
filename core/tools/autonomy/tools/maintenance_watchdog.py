from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import json_dump, read_text, rel, walk_files


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('--output',default='reports/maintenance.json'); a=ap.parse_args(); root=Path(a.project).resolve()
    rows=[]; todos=[]
    for p in walk_files(root):
        try: size=p.stat().st_size
        except OSError: continue
        if size>300_000: rows.append({'file':rel(root,p),'issue':'large_file','bytes':size})
        if p.suffix.lower() in {'.py','.ts','.tsx','.js','.jsx'}:
            t=read_text(p)
            for i,line in enumerate(t.splitlines(),1):
                if re.search(r'\b(TODO|FIXME|XXX|HACK)\b',line,re.IGNORECASE): todos.append({'file':rel(root,p),'line':i,'marker':line.strip()[:160]})
    result={'large_files':sorted(rows,key=lambda x:-x['bytes'])[:100],'debt_markers':todos[:300],'recommendations':['split high-churn large files','turn important TODO/FIXME markers into tracked issues','add health checks for repeated failure signatures','periodically remove dead integrations']}
    json_dump(result,Path(a.output))
if __name__=='__main__': main()
