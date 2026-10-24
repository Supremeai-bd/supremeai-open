"""M23 P-C: coldstart knowledge seed → knowledge-base importer manifest adapter.

বাংলা মন্তব্য: দুটি পরিণত আমদানি-মেশিন (import_knowledge_base.py + rag ingest)
অচল ছিল কারণ `knowledge/coldstart_knowledge_seed_comprehensive.json`-এর
কার্গো-ফরম্যাট ({meta, categories[].entries[]}) importer-এর flat record চুক্তির
সাথে মিলত না — "বই ঘরে আছে, কিন্তু দরজা বন্ধ"। এই adapter মালপত্র-সংযোগ করে
(মেশিন-প্রতিস্থাপন নয়): ১৩২-এন্ট্রি (১২১ বাংলা) বই-কনভয়কে importer-চুক্তিতে
অনুবাদ করে, ফলে `import_knowledge_base.py --validate-only` প্রথমবারের মতো
প্রকৃত বই-পথ যাচাই করতে পারে।

HITL সীমা-সত্য: সব রেকর্ড `status="draft"` জন্ম নেয় — approved করা কেবল
মানুষের (মালিকের) সিদ্ধান্ত; কোনো auto-approve নেই। শুধু `--validate-only`
মোডে কোনো ফাইল লেখা হয় না — প্রতিবেদন stdout-এ যায় (CI/pytest গেট)।

ব্যবহার:
    python scripts/adapt_coldstart_knowledge.py --validate-only
    python scripts/adapt_coldstart_knowledge.py --out /tmp/knowledge_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_SOURCE = REPO_ROOT / "knowledge" / "coldstart_knowledge_seed_comprehensive.json"
MANIFEST_VERSION = "coldstart-adapter-v1"

# বাংলা: coldstart seed শিক্ষামূলক concept/pattern/fact — কোনো risk ক্ষেত্রই নেই;
# তাই সৎ ডিফল্ট "low" (নিচের কমেন্টে ঘোষিত — নীরব বানানো নয়)।
DEFAULT_RISK_LEVEL = "low"
# বাংলা: HITL — approved ঘোষণা মানুষ করবেন; adapter সবসময় draft দেয়।
DEFAULT_STATUS = "draft"

# বাংলা: seed-এর confidence স্ট্রিং-স্তরের ('high') — importer চুক্তি সংখ্যা [0,1]।
# ঘোষিত অর্ডার-ম্যাপ (ফেক নির্ভুলতা নয়: 'high'='প্রমাণিত ধারণা', 'low'='মনোনীত');
# অজানা স্তর এলে fail-closed ব্যতিক্রম — চুপচাপ 0.8 ধরে নেওয়া নয়।
CONFIDENCE_LEVEL_MAP = {"high": 0.9, "medium": 0.7, "low": 0.5}


def _confidence_to_number(raw: Any, entry_id: str) -> float:
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        level = str(raw or "").strip().lower()
        if level not in CONFIDENCE_LEVEL_MAP:
            raise ValueError(
                f"entry {entry_id!r}: unknown confidence level {raw!r} — "
                f"expected one of {sorted(CONFIDENCE_LEVEL_MAP)} (fail-closed, no silent default)"
            )
        value = CONFIDENCE_LEVEL_MAP[level]
    if not 0 <= value <= 1:
        raise ValueError(f"entry {entry_id!r}: confidence {value} out of contract range [0,1]")
    return value


def _key_for(entry_id: str, category_id: str) -> str:
    """knowledge_key চুক্তি: [a-z0-9_.-]{3,120} — সংঘর্ষ এড়াতে category উপসর্গ।"""
    return f"coldstart.{category_id}.{entry_id}".lower()


def adapt(source: Path | None = None) -> dict[str, Any]:
    """coldstart {meta,categories} থেকে importer-manifest গঠন করে।"""
    source = source or DEFAULT_SOURCE
    payload = json.loads(source.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []

    for category in payload.get("categories", []):
        category_id = str(category.get("category_id", "")).strip()
        domain = str(category.get("domain", "")).strip() or "general"
        for entry in category.get("entries", []):
            entry_id = str(entry.get("id", "")).strip()
            question = str(entry.get("question", "")).strip()
            answer = str(entry.get("answer", "")).strip()
            if not entry_id or not question or not answer:
                # বাংলা: অসম্পূর্ণ এন্ট্রি চুপচাপ বাদ দেওয়া = ভুয়া "সব ঠিক";
                # পরিবর্তে স্পষ্ট error-প্রসঙ্গ সহ ব্যতিক্রম — validate() এগুলো
                # ধরবে না কারণ রেকর্ড তৈরিই হয়নি।
                raise ValueError(
                    f"incomplete coldstart entry in category '{category_id}': id="
                    f"{entry_id!r}, question_present={bool(question)}, answer_present={bool(answer)}"
                )
            records.append(
                {
                    "knowledge_key": _key_for(entry_id, category_id),
                    "title": question[:200],
                    "domain": domain,
                    "namespace": category_id,
                    "content": answer,
                    "source_document": str(source.relative_to(REPO_ROOT)),
                    "source_section": f"{category_id}/{entry_id}",
                    "confidence": _confidence_to_number(entry.get("confidence"), entry_id),
                    "risk_level": DEFAULT_RISK_LEVEL,
                    "status": DEFAULT_STATUS,
                    "tags": list(entry.get("tags", [])) or ["coldstart", category_id],
                }
            )

    return {"manifest_version": MANIFEST_VERSION, "records": records}


def validate_report(manifest: dict[str, Any], source: Path) -> dict[str, Any]:
    """importer-এর নিজস্ব validate() চালিয়ে প্রতিবেদন গঠন (সৎ সংখ্যা)।"""
    scripts_dir = BACKEND_DIR / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import importlib.util

    importer_path = scripts_dir / "import_knowledge_base.py"
    spec = importlib.util.spec_from_file_location("import_knowledge_base", importer_path)
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)  # type: ignore[union-attr]

    records = manifest["records"]
    errors = importer.validate(records)
    bengali_count = sum(
        1 for r in records if any("\u0980" <= ch <= "\u09ff" for ch in r["content"])
    )
    return {
        "manifest_version": manifest["manifest_version"],
        "record_count": len(records),
        "bengali_content_count": bengali_count,
        "errors": errors,
        "status_default": DEFAULT_STATUS,
        "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Adapt coldstart knowledge seed to importer manifest (M23 P-C)"
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, help="Write adapted manifest JSON here")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.out and args.validate_only:
        print("--out cannot be combined with --validate-only", file=sys.stderr)
        return 2

    manifest = adapt(args.source)
    report = validate_report(manifest, args.source)

    if args.validate_only:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2 if report["errors"] else 0

    if args.out:
        args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2 if report["errors"] else 0

    # ডিফল্ট: manifest stdout-এ — পাইপ-বান্ধব।
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
