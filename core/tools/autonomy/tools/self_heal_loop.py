from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import count_tokens_rough, json_dump

ERROR_PATTERNS = [
    ('python_traceback', r'Traceback \(most recent call last\):'),
    ('exception', r'\b(?:Exception|Error):'),
    ('http_5xx', r'\b5\d\d\b'),
    ('timeout', r'(?i)timeout|timed out'),
    ('dependency', r'(?i)module not found|cannot import|package.*not found'),
]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('project'); ap.add_argument('--log'); ap.add_argument('--output',default='reports/self_heal.json'); args=ap.parse_args()
    root=Path(args.project).resolve(); log=Path(args.log) if args.log else None
    text=log.read_text(encoding='utf-8',errors='replace') if log and log.exists() else ''
    kinds=[name for name,pat in ERROR_PATTERNS if re.search(pat,text)]
    files=[]
    for m in re.finditer(r'(?:File|at)\s+["\']?([^\s"\']+\.(?:py|ts|tsx|js|jsx))["\']?', text): files.append(m.group(1))
    uniq=[]
    for f in files:
        if f not in uniq: uniq.append(f)
    checks=[]
    if 'python_traceback' in kinds or 'exception' in kinds: checks += ['reproduce failing test or command', 'inspect nearest changed code path', 'add a regression test before patching']
    if 'dependency' in kinds: checks += ['verify lockfile and environment parity', 'check package/version mismatch']
    if 'http_5xx' in kinds or 'timeout' in kinds: checks += ['inspect retry/backoff/circuit-breaker policy', 'check upstream health and request budgets']
    result={'project':str(root),'failure_summary':{'detected_patterns':kinds,'suspected_files':uniq[:20]},'repair_plan':checks or ['collect a reproducible failure signal first'], 'patch_policy':{'mode':'plan_only','max_files_recommended':5,'require_tests':True,'require_human_approval_for_data_or_auth_changes':True}, 'verification': ['run targeted regression test','run lint/type checks for changed modules','run focused integration test','run full CI before production deploy'], 'input_size_tokens_estimate':count_tokens_rough(text)}
    json_dump(result, Path(args.output))

if __name__=='__main__': main()
