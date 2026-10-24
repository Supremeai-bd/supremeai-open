#!/usr/bin/env python3
"""বাংলা মন্তব্য: SupremeAI Self-Audit Static Scanner (উন্নত ও অপ্টিমাইজড সংস্করণ)।

উদ্দেশ্য: `ruff`/`mypy`-এর মতো external dependency ছাড়াই (Zero Cost),
শুধু Python stdlib `ast` module ব্যবহার করে পুরো কোডবেসে common bug
pattern খুঁজে বের করা — যাতে CI-তে network/pip install না লাগলেও এই
স্ক্যান চলতে পারে (offline-safe, low-cost runners-এও কাজ করে)।

চেক করা হয়:
  1. Python syntax error (guaranteed real bug)
  2. Mutable default argument (`def f(x: list = [])`)
  3. `except: pass` — silent failure swallow (flag করে, human review-এর জন্য)
  4. Naive `datetime.now()` ব্যবহার (timezone-unaware — multi-region risk)
  5. Byte-identical duplicate ফাইল (Zero-Duplication নীতি)
  6. Hardcoded secret-সদৃশ প্যাটার্ন (basic heuristic, false-positive-prone)
  7. ডুপ্লিকেট ক্লাস মেথড ডিটেকশন (একই ক্লাসের ভেতর ডুপ্লিকেট মেথড ওভাররাইট - প্রপার্টি সেটার বাদে)
  8. প্রোডাকশন কোডে debug print() স্টেটমেন্ট ডিটেকশন
  9. TODO / FIXME / HACK / XXX ট্র্যাকিং
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", "venv", "__pycache__", ".venv", ".venv_ci",
    "archive", "dist", "build", ".turbo", ".pytest_cache",
}
CODE_EXTS = (".py",)
SRC_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx")

SECRET_RE = re.compile(
    r'(api[_-]?key|secret|password|token|private[_-]?key)\s*=\s*[\'"][A-Za-z0-9_\-/+=]{8,}[\'"]',
    re.IGNORECASE,
)


def iter_files(root: Path, exts: tuple[str, ...]):
    try:
        for p in root.iterdir():
            if p.name in SKIP_DIRS:
                continue
            if p.is_dir():
                yield from iter_files(p, exts)
            elif p.suffix in exts:
                yield p
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")


def scan_python(root: Path) -> dict:
    syntax_errors = []
    mutable_defaults = []
    except_pass = []
    naive_datetime = []
    duplicate_methods = []
    print_statements = []
    todo_fixmes = []

    for path in iter_files(root, CODE_EXTS):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            # বাংলা: ফাইল পড়া না গেলে পুরো audit থেকে চুপচাপ বাদ না দিয়ে stderr-এ জানিয়ে দিন
            print(f"  ⚠️  Skipped from audit (unreadable): {path.relative_to(root)}: {e}", file=sys.stderr)
            continue

        rel = str(path.relative_to(root))

        for i, line in enumerate(src.splitlines(), 1):
            if "datetime.now()" in line and "utcnow" not in line:
                naive_datetime.append(f"{rel}:{i}")
            if any(x in line for x in ("TODO", "FIXME", "XXX", "HACK")):
                todo_fixmes.append(f"{rel}:{i}: {line.strip()[:100]}")
            if "print(" in line and "/tests/" not in rel and "test_" not in path.name and "/scripts/" not in rel:
                print_statements.append(f"{rel}:{i}: {line.strip()[:100]}")

        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError as e:
            syntax_errors.append(f"{rel}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in list(node.args.defaults) + list(node.args.kw_defaults):
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        mutable_defaults.append(f"{rel}:{node.lineno}: def {node.name}(...)")
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    except_pass.append(f"{rel}:{node.lineno}")
            if isinstance(node, ast.ClassDef):
                seen = {}
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Getter/Setter/Deleter জোড়া বাদ দিয়ে ডুপ্লিকেট খোঁজা (False Positive এড়াতে)
                        is_property_accessor = False
                        for dec in item.decorator_list:
                            if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter"):
                                is_property_accessor = True
                                break
                        if is_property_accessor:
                            continue

                        if item.name in seen:
                            duplicate_methods.append(f"{rel}:{item.lineno}: class {node.name} redefines method '{item.name}' (first at line {seen[item.name]})")
                        else:
                            seen[item.name] = item.lineno

    return {
        "syntax_errors": syntax_errors,
        "mutable_default_args": mutable_defaults,
        "except_pass_blocks": except_pass,
        "naive_datetime_now": naive_datetime,
        "duplicate_methods_in_class": duplicate_methods,
        "print_statements": print_statements,
        "todo_fixmes": todo_fixmes,
    }


def scan_duplicates(root: Path) -> list[list[str]]:
    hashes: dict[str, list[str]] = defaultdict(list)
    for path in iter_files(root, SRC_EXTS):
        try:
            data = path.read_bytes()
        except Exception as e:
            # বাংলা: ফাইল পড়া না গেলে অডিট থেকে চুপচাপ বাদ না দিয়ে stderr-এ জানিয়ে দিন
            print(f"  ⚠️  Skipped (unreadable): {path.relative_to(root)}: {e}", file=sys.stderr)
            continue
        if len(data) < 50:
            continue
        h = hashlib.md5(data).hexdigest()
        hashes[h].append(str(path.relative_to(root)))
    return [v for v in hashes.values() if len(v) > 1]


def scan_secrets(root: Path) -> list[str]:
    hits = []
    for path in iter_files(root, CODE_EXTS):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            # বাংলা: ফাইল পড়া না গেলে secret-scan থেকে চুপচাপ বাদ না দিয়ে stderr-এ জানিয়ে দিন
            print(f"  ⚠️  Skipped secret scan (unreadable): {path.relative_to(root)}: {e}", file=sys.stderr)
            continue
        rel = str(path.relative_to(root))
        if "/tests/" in rel or rel.startswith("tests/"):
            continue  # টেস্ট mock value বাদ — false positive কমাতে
        for i, line in enumerate(src.splitlines(), 1):
            if SECRET_RE.search(line) and "os.environ" not in line and "getenv" not in line:
                hits.append(f"{rel}:{i}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI offline self-audit scanner")
    parser.add_argument("--path", default=".", help="স্ক্যান করার root path")
    parser.add_argument("--json", default=None, help="JSON রিপোর্ট সেভ করার পাথ")
    parser.add_argument(
        "--fail-on-syntax-error",
        action="store_true",
        help="Syntax error পেলে non-zero exit code দিন (CI gate হিসেবে ব্যবহারের জন্য)",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    py_report = scan_python(root)
    dup_report = scan_duplicates(root)
    secret_report = scan_secrets(root)

    report = {
        **py_report,
        "duplicate_file_groups": dup_report,
        "possible_hardcoded_secrets": secret_report,
    }

    print("=== SupremeAI Self-Audit Scan ===")
    print(f"Syntax errors:              {len(report['syntax_errors'])}")
    print(f"Mutable default args:       {len(report['mutable_default_args'])}")
    print(f"except: pass blocks:        {len(report['except_pass_blocks'])}")
    print(f"Naive datetime.now():       {len(report['naive_datetime_now'])}")
    print(f"Duplicate file groups:      {len(report['duplicate_file_groups'])}")
    print(f"Possible hardcoded secrets: {len(report['possible_hardcoded_secrets'])}")
    print(f"Duplicate class methods:    {len(report['duplicate_methods_in_class'])}")
    print(f"Production print() calls:   {len(report['print_statements'])}")
    print(f"TODO/FIXME/HACK comments:   {len(report['todo_fixmes'])}")

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            print(f"\nJSON report saved to: {args.json}")
        except UnicodeEncodeError:
            print("\nJSON report saved successfully.")

    if args.fail_on_syntax_error and report["syntax_errors"]:
        print("\n❌ Syntax error detected - CI failing.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
