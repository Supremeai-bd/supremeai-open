#!/usr/bin/env python3
"""Compress repetitive AI prompts/templates while preserving explicit constraints and structure."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

STOP={'the', 'a', 'an', 'and', 'or', 'of', 'to', 'for', 'with', 'in', 'on', 'is', 'are', 'be', 'this', 'that', 'it', 'as', 'from', 'by', 'you', 'your', 'our', 'we', 'please', 'can', 'should', 'must'}
def normalize(s): return re.sub(r'\s+',' ',s.strip().lower())
def key_sentence(s): return hashlib.sha1(normalize(s).encode()).hexdigest()[:10]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('input'); ap.add_argument('--out',default='reports/prompt-distilled.txt'); a=ap.parse_args(); text=Path(a.input).read_text('utf-8','ignore'); chunks=re.split(r'\n\s*\n+',text.strip()); seen=set(); kept=[]; dropped=[]
 for c in chunks:
  c=c.strip()
  if not c: continue
  # remove obvious repeated boilerplate, but never collapse instruction-bearing lines
  norm=normalize(c); sig=re.sub(r'\b\d+\b','{N}',norm)
  if sig in seen and not re.search(r'\b(must|never|always|required|security|constraint|format)\b',norm): dropped.append(c); continue
  seen.add(sig); kept.append(c)
 result='\n\n'.join(kept)+'\n'; out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(result,encoding='utf-8'); print(f'blocks: {len(chunks)} -> {len(kept)}; removed {len(dropped)} duplicate blocks; output={out}')
if __name__=='__main__': main()
