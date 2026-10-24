#!/usr/bin/env python3
"""Mine LLM/provider configuration for free-capacity and resilience opportunities."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

PROVIDERS = ["gemini","groq","openrouter","cloudflare","nvidia","huggingface","ollama","deepseek","moonshot","together"]
KEYS = ["rpm","tpm","rpd","limit","quota","fallback","circuit","cache","redis","rate_limit","provider"]

def scan(root: Path):
    hits=defaultdict(list)
    for p in root.rglob("*"):
        if not p.is_file() or any(x in p.parts for x in [".git","node_modules",".venv","dist","build"]): continue
        if p.stat().st_size>2_000_000: continue
        try: t=p.read_text(encoding="utf-8",errors="ignore").lower()
        except OSError: continue
        for provider in PROVIDERS:
            if provider in t: hits[provider].append(str(p.relative_to(root)))
    opportunities=[]
    for provider, paths in hits.items():
        opportunities.append({"provider":provider,"files":len(set(paths)),"sample_files":sorted(set(paths))[:8],"opportunities":[
            "measure real request/token consumption rather than static limits",
            "route away before provider-specific rate-limit thresholds",
            "track per-task quality/latency to avoid blindly choosing cheapest/free capacity",
        ]})
    patterns={k:[] for k in KEYS}
    for p in root.rglob("*"):
        if p.is_file() and p.stat().st_size<1_500_000:
            try:t=p.read_text(encoding="utf-8",errors="ignore")
            except OSError:continue
            for k in KEYS:
                if re.search(rf"\\b{re.escape(k)}\\b",t,re.IGNORECASE): patterns[k].append(str(p.relative_to(root)))
    return {"providers":opportunities,"signals":{k:len(set(v)) for k,v in patterns.items()},"next_actions":[
        "Persist provider telemetry across workers.",
        "Calculate effective free-capacity score = remaining quota × quality × availability / latency.",
        "Learn routing weights from successful outcomes rather than static priority only.",
        "Detect providers whose configured limits are stale versus observed 429 responses.",
        "Use cache-hit and prompt-dedup rates to reduce paid/free-tier calls before adding more providers."]}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("root",nargs="?",default=".");ap.add_argument("--out",default="reports/gap-miner/provider_capacity.json");a=ap.parse_args(); r=scan(Path(a.root).resolve());o=Path(a.out);o.parent.mkdir(parents=True,exist_ok=True);o.write_text(json.dumps(r,indent=2),encoding="utf-8");print(json.dumps(r,indent=2))
if __name__=="__main__":main()
