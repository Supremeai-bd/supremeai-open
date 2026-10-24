import os
import hashlib
from difflib import SequenceMatcher

plans_base = r'f:\supremeai\docs\plans'

all_files = []
for root, dirs, files in os.walk(plans_base):
    for f in files:
        if f.endswith('.md') and f != 'README.md':
            all_files.append(os.path.join(root, f))

file_data = []
for fp in all_files:
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as fh:
            text = fh.read()
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            header = lines[0] if lines else ''
            file_data.append({
                'path': fp,
                'rel': os.path.relpath(fp, plans_base),
                'size': len(text),
                'header': header,
                'hash': hashlib.md5(text.encode('utf-8', errors='ignore')).hexdigest(),
            })
    except Exception as e:
        print(f"Warning reading plan {fp}: {e}")

hashes = {}
duplicates = []
for fd in file_data:
    h = fd['hash']
    if h in hashes:
        duplicates.append((hashes[h], fd['rel']))
    else:
        hashes[h] = fd['rel']

similar_pairs = []
for i in range(len(file_data)):
    for j in range(i + 1, len(file_data)):
        f1 = file_data[i]
        f2 = file_data[j]
        b1 = os.path.basename(f1['path']).lower()
        b2 = os.path.basename(f2['path']).lower()
        ratio = SequenceMatcher(None, b1, b2).ratio()
        if ratio > 0.7:
            similar_pairs.append((f1['rel'], f2['rel'], f'Name ratio: {ratio:.2f}'))
        else:
            h_ratio = SequenceMatcher(None, f1['header'], f2['header']).ratio()
            if h_ratio > 0.8:
                similar_pairs.append((f1['rel'], f2['rel'], f'Header ratio: {h_ratio:.2f}'))

with open(r'f:\supremeai\scripts\duplicate_audit.txt', 'w', encoding='utf-8') as out:
    out.write('=== EXACT DUPLICATES ===\n')
    for orig, dup in duplicates:
        out.write(f'{orig} <===> {dup}\n')
    out.write('\n=== SIMILAR PAIRS ===\n')
    for f1, f2, reason in similar_pairs:
        out.write(f'{f1} <===> {f2} ({reason})\n')

print('Success writing duplicate audit.')
