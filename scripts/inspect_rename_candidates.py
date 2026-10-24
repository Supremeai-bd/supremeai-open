import os
import re

def clean(s):
    return s.encode('ascii', 'ignore').decode('ascii').strip()

log_file = r'f:\supremeai\scripts\rename_preview.txt'

plans_base = r'f:\supremeai\docs\plans'

mapping = {}

with open(log_file, 'w', encoding='utf-8') as out:
    for sub in ['architecture', 'features', 'infrastructure', 'design']:
        p = os.path.join(plans_base, sub)
        if not os.path.exists(p):
            continue
        out.write(f'=== docs/plans/{sub} ===\n')
        for f in sorted(os.listdir(p)):
            safe_ascii = clean(f)
            has_unicode = any(ord(c) > 127 for c in f)
            has_space = ' ' in f
            is_generic = 'implementation_plan' in f or f.startswith('Plan_')
            if has_unicode or has_space or is_generic:
                fp = os.path.join(p, f)
                try:
                    with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
                        lines = [line.strip() for line in fh.readlines() if line.strip()]
                        header = lines[0] if lines else ''
                except Exception as e:
                    header = str(e)
                out.write(f'FILE: {repr(f)}\n  HEADER: {header[:100]}\n')

print('Wrote inspection to', log_file)
