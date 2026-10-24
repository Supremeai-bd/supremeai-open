#!/usr/bin/env python3
"""Find architectural coupling and layering smells using lightweight static signals."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

IMPORT_PATTERNS={"python":re.compile(r"^(?:from|import)\s+([A-Za-z0-9_./-]+)",re.MULTILINE),"js":re.compile(r"(?:from\s+[\"']([^\"']+)|require\(\s*[\"']([^\"']+))",re.MULTILINE)}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".");ap.add_argument("--out",default="reports/gap-miner/architecture.json");a=ap.parse_args();root=Path(a.root).resolve();fan=Counter();cross=[]
 for p in root.rglob("*"):
  if not p.is_file() or p.stat().st_size>1_500_000 or any(x in p.parts for x in [".git","node_modules",".venv","dist","build"]):continue
  if p.suffix==".py": pat=IMPORT_PATTERNS["python"]
  elif p.suffix in {".ts",".tsx",".js",".jsx"}: pat=IMPORT_PATTERNS["js"]
  else: continue
  try:t=p.read_text(encoding="utf-8",errors="ignore")
  except OSError:continue
  imports=[]
  for m in pat.finditer(t): imports.append(next((x for x in m.groups() if x),""))
  fan[str(p.relative_to(root))]=len(set(imports))
  local=[x for x in imports if x.startswith((".", "src/", "backend/"))]
  if len(local)>20: cross.append({"path":str(p.relative_to(root)),"local_imports":len(local)})
 result={"high_fanout_files":[{"path":k,"unique_import_targets":v} for k,v in fan.most_common(30)],"high_local_coupling":sorted(cross,key=lambda x:-x["local_imports"])[:30],"recommendations":["Keep domain modules dependent on stable interfaces, not concrete infrastructure.","Extract shared primitives from cyclic clusters rather than adding more cross-imports.","Prefer explicit adapters for LLM/provider/database integrations."]}
 o=Path(a.out);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result,indent=2))
if __name__=="__main__":main()
