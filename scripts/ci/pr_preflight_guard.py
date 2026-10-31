"""pr_preflight_guard.py — pre-submission guard for SupremeAI PRs."""
from __future__ import annotations
import argparse, re, subprocess, sys
from pathlib import Path
BRANCH_RE = re.compile(r"^(feat|fix|chore|docs|ci|test|refactor|perf|bridge|hotfix)/[a-z0-9][a-z0-9._/-]*$")
ISSUE_RE = re.compile(r"(Closes|Fixes|Refs|Resolves)\s+#\d+", re.IGNORECASE)
def run(cmd): return subprocess.run(cmd, capture_output=True, text=True)
def check_branch(branch):
    if branch in ("main","master"): return []
    return [] if BRANCH_RE.match(branch) else ["branch name %r invalid" % branch]
def check_issue_ref(text):
    return [] if ISSUE_RE.search(text) else ["missing issue reference (Closes/Fixes/Refs/Resolves #N)"]
def check_boundary(files):
    if not files: return []
    r = run([sys.executable, "scripts/ci/boundary_sanitization_guard.py", "--files", *files])
    return [l for l in (r.stdout+r.stderr).splitlines() if l.strip()] if r.returncode != 0 else []
def check_lint(files):
    errs = []
    for f in files:
        if f.endswith(".py") and Path(f).is_file():
            if run([sys.executable, "-m", "py_compile", f]).returncode != 0:
                errs.append("python syntax error: %s" % f)
        if f.endswith(".json") and Path(f).is_file():
            if run([sys.executable, "-c", "import json,sys; json.load(open(sys.argv[1],encoding='utf-8'))", f]).returncode != 0:
                errs.append("json syntax error: %s" % f)
    return errs
def self_test():
    fails = 0
    if check_branch("feat/foo-bar"): fails+=1; print("FAIL branch-ok")
    else: print("PASS branch-ok")
    if not check_branch("badbranch"): fails+=1; print("FAIL branch-bad")
    else: print("PASS branch-bad")
    if check_issue_ref("Closes #123"): fails+=1; print("FAIL issue-ok")
    else: print("PASS issue-ok")
    if not check_issue_ref("no ref"): fails+=1; print("FAIL issue-missing")
    else: print("PASS issue-missing")
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        p=os.path.join(d,"bad.py")
        open(p,"w").write("def broken(: pass\n")
        if not check_lint([p]): fails+=1; print("FAIL lint-bad")
        else: print("PASS lint-bad")
        p2=os.path.join(d,"good.py")
        open(p2,"w").write("x=1\n")
        if check_lint([p2]): fails+=1; print("FAIL lint-good")
        else: print("PASS lint-good")
    print("self-test: %d failure(s)" % fails)
    return 0 if fails==0 else 1
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default=None)
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--pr-body", default=None)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test: return self_test()
    errs = []
    if args.branch: errs += check_branch(args.branch)
    if args.pr_body:
        errs += check_issue_ref(Path(args.pr_body).read_text(encoding="utf-8", errors="replace"))
    errs += check_boundary(args.files)
    errs += check_lint(args.files)
    if errs:
        print("pr_preflight_guard: FAIL")
        for e in errs: print(" -", e)
        return 1
    print("pr_preflight_guard: PASS")
    return 0
if __name__ == "__main__":
    sys.exit(main())
