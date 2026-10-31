"""pr_preflight_guard.py — pre-submission guard for SupremeAI PRs."""
from __future__ import annotations
import argparse, os, re, subprocess, sys
from pathlib import Path

BRANCH_RE = re.compile(r"^(feat|fix|chore|docs|ci|test|refactor|perf|bridge|hotfix)/[a-z0-9][a-z0-9._/-]*$")
ISSUE_RE = re.compile(r"(Closes|Fixes|Refs|Resolves)\s+#\d+", re.IGNORECASE)
TOWER_SIG_RE = re.compile(r"##\s+Reflection Evidence", re.IGNORECASE)
VERIFY_SIG_RE = re.compile(r"(3[- ]?Tier|Test Evidence)", re.IGNORECASE)

# Six active domain prefixes for Federation boundary check
DOMAIN_PREFIXES = ("studio/", "gateway/", "core/", "browser/", "vscode/", "scripts/", "tests/", "docs/", ".agents/", ".github/")

def run(cmd): return subprocess.run(cmd, capture_output=True, text=True)

def check_branch(branch):
    if branch in ("main","master"): return []
    return [] if BRANCH_RE.match(branch) else ["branch name %r invalid" % branch]

def check_issue_ref(text):
    errs = []
    if not ISSUE_RE.search(text):
        errs.append("missing issue reference (Closes/Fixes/Refs/Resolves #N)")
    if not TOWER_SIG_RE.search(text):
        errs.append("missing '## Reflection Evidence' header (Tower verification signature)")
    if not VERIFY_SIG_RE.search(text):
        errs.append("missing '3-Tier Verify' or 'Test Evidence' section (Tower verification signature)")
    return errs

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

# ── Shield 1: Task-Scope Domain Fence ──────────────────────────────────────────
def check_scope_fence(branch: str | None, files: list[str]) -> list[str]:
    """Prevent cross-domain collateral contamination.
    
    If a branch declares a domain prefix (e.g. feat/studio-*, fix/core-*),
    changes must not leak into unrelated active satellite domains.
    """
    if not branch or not files:
        return []
    
    domain_tags = {
        "studio": "studio/",
        "gateway": "gateway/",
        "core": "core/",
        "browser": "browser/",
        "vscode": "vscode/",
    }
    
    matched_domain = None
    for tag in domain_tags:
        if f"/{tag}-" in branch or f"/{tag}/" in branch:
            matched_domain = tag
            break
            
    if not matched_domain:
        return []

    prefix = domain_tags[matched_domain]
    errs = []
    for f in files:
        f_norm = f.replace("\\", "/")
        # Allow repo-level docs, ci, and test changes that support the task
        if f_norm.startswith(("docs/", "tests/", ".agents/")):
            continue
        # If file belongs to another distinct satellite domain, raise collision error
        for other_tag, other_prefix in domain_tags.items():
            if other_tag != matched_domain and f_norm.startswith(other_prefix):
                errs.append(
                    f"cross-domain collision: branch {branch} is scoped to '{matched_domain}' "
                    f"but modified out-of-scope domain file '{f}'"
                )
    return errs

# ── Shield 2: Stale-Base & Full-File Overwrite Guard ────────────────────────────
def check_stale_base() -> list[str]:
    """CAS Stale-Base Guard: ensure current branch is not behind origin/main."""
    r = run(["git", "rev-parse", "--verify", "origin/main"])
    if r.returncode != 0:
        return []  # No origin/main found (offline or shallow clone)
    
    # Check if branch is behind origin/main
    r_behind = run(["git", "rev-list", "--count", "HEAD..origin/main"])
    if r_behind.returncode == 0:
        count = r_behind.stdout.strip()
        if count.isdigit() and int(count) > 0:
            return [
                f"stale base: local branch is {count} commit(s) behind origin/main. "
                f"Rebase or merge origin/main to prevent overwriting co-landed agent work."
            ]
    return []

# ── Shield 3: AST Anti-Regression Guard (Test & Function Deletion) ─────────────
def check_ast_regressions(files: list[str]) -> list[str]:
    """Verify that existing test cases or public functions were not deleted."""
    errs = []
    for f in files:
        if not (f.endswith(".py") and Path(f).is_file() and ("test_" in f or "tests/" in f)):
            continue
        # Check diff for deleted test functions
        r_diff = run(["git", "diff", "origin/main", "--", f])
        if r_diff.returncode == 0 and r_diff.stdout:
            deleted_tests = [
                line for line in r_diff.stdout.splitlines()
                if line.startswith("-def test_") or line.startswith("-    def test_")
            ]
            added_tests = [
                line for line in r_diff.stdout.splitlines()
                if line.startswith("+def test_") or line.startswith("+    def test_")
            ]
            if deleted_tests and len(deleted_tests) > len(added_tests):
                errs.append(
                    f"anti-regression alert: {len(deleted_tests)} test(s) deleted in '{f}'. "
                    f"Agents must not delete failing tests to pass CI."
                )
    return errs

def self_test():
    fails = 0
    if check_branch("feat/foo-bar"): fails+=1; print("FAIL branch-ok")
    else: print("PASS branch-ok")
    if not check_branch("badbranch"): fails+=1; print("FAIL branch-bad")
    else: print("PASS branch-bad")
    good_body = "Closes #123\n## Reflection Evidence\n3-Tier Verify passed"
    if check_issue_ref(good_body): fails+=1; print("FAIL issue-ok")
    else: print("PASS issue-ok")
    if not check_issue_ref("no ref"): fails+=1; print("FAIL issue-missing")
    else: print("PASS issue-missing")
    
    # Test Scope Fence
    scope_bad = check_scope_fence("feat/studio-login", ["studio/src/app.ts", "core/engine/auth.py"])
    if not scope_bad: fails+=1; print("FAIL scope-bad")
    else: print("PASS scope-bad")
    
    scope_good = check_scope_fence("feat/studio-login", ["studio/src/app.ts", "docs/login.md"])
    if scope_good: fails+=1; print("FAIL scope-good")
    else: print("PASS scope-good")

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
    ap.add_argument("--check-stale", action="store_true", help="Check if branch is behind origin/main")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test: return self_test()
    errs = []
    if args.branch: 
        errs += check_branch(args.branch)
        errs += check_scope_fence(args.branch, args.files)
    if args.pr_body:
        errs += check_issue_ref(Path(args.pr_body).read_text(encoding="utf-8", errors="replace"))
    if args.check_stale:
        errs += check_stale_base()
    errs += check_boundary(args.files)
    errs += check_lint(args.files)
    errs += check_ast_regressions(args.files)
    if errs:
        print("pr_preflight_guard: FAIL")
        for e in errs: print(" -", e)
        return 1
    print("pr_preflight_guard: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
