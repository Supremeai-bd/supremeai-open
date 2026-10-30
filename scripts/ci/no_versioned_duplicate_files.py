import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ACTIVE = ['core', 'gateway', 'browser', 'studio/src', 'scripts', 'tests', 'vscode']
PATTERNS = [
    re.compile(r'_\d{4}_\d{2}_\d{2}'),
    re.compile(r'_seq\d+'),
]
EXCEPTIONS = {
    'core/github/scripts/ci_summary_v2.py',
    'core/api/routes/admin_v1.py',
    'gateway/routes/admin_v1.py',
    'core/data/supremeai_long_term_knowledge_v1.json',
    'core/eval/task_eval_set_v1.json',
}

violations = []
for rootname in ACTIVE:
    base = os.path.join(ROOT, rootname)
    if not os.path.exists(base):
        continue
    for dp, _, fs in os.walk(base):
        if any(x in dp.split(os.sep) for x in ['_archive', 'node_modules', 'dist', 'build', '__pycache__', '.git']):
            continue
        for f in fs:
            rel = os.path.relpath(os.path.join(dp, f), ROOT).replace(os.sep, '/')
            if rel in EXCEPTIONS:
                continue
            for pat in PATTERNS:
                if pat.search(f):
                    violations.append(rel)

if violations:
    print('FAIL: versioned duplicate files found in active paths:')
    for v in sorted(violations):
        print('  -', v)
    sys.exit(1)
print('OK: no dated/seq versioned duplicate files in active paths.')