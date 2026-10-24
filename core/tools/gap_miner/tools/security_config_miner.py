#!/usr/bin/env python3
"""Read-only security/config hygiene scanner. Never prints secret values."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SECRET_NAMES=re.compile(r"(secret|token|password|api[_-]?key|private[_-]?key|access[_-]?key)",re.IGNORECASE)
BAD_FILES={".env",".env.local",".env.production","id_rsa","id_ed25519","credentials.json","service-account.json"}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".");ap.add_argument("--out",default="reports/gap-miner/security_config.json");a=ap.parse_args();root=Path(a.root).resolve();issues=[]
    for p in root.rglob("*"):
        if not p.is_file() or any(x in p.parts for x in [".git","node_modules",".venv","dist","build"]):continue
        if p.name in BAD_FILES: issues.append({"severity":"high","type":"sensitive_filename","path":str(p.relative_to(root))})
        if p.suffix in {".py",".ts",".tsx",".js",".jsx",".json",".yaml",".yml",".toml"} and p.stat().st_size<2_000_000:
            try:t=p.read_text(encoding="utf-8",errors="ignore")
            except OSError:continue
            if SECRET_NAMES.search(t) and re.search(r"[=:]\s*[\"'][^\"']{16,}[\"']",t):
                issues.append({"severity":"high","type":"possible_hardcoded_secret","path":str(p.relative_to(root)),"evidence":"credential-like assignment detected; value intentionally omitted"})
    gi=(root/".gitignore")
    ignored=gi.read_text(encoding="utf-8",errors="ignore") if gi.exists() else ""
    for rule in [".env","*.pem","*.key"]:
        if rule not in ignored:issues.append({"severity":"medium","type":"missing_gitignore_rule","rule":rule})
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({"issues":issues,"count":len(issues)},indent=2),encoding="utf-8");print(json.dumps({"count":len(issues)},indent=2))
if __name__=="__main__":main()
