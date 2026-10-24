from __future__ import annotations

import argparse
import json
from dataclasses import asdict

try:
    from card_builder import build_knowledge_cards
    from injector import ToolKnowledgeInjector
except ImportError:
    from tools.knowledge.card_builder import build_knowledge_cards
    from tools.knowledge.injector import ToolKnowledgeInjector


def main() -> None:
    parser = argparse.ArgumentParser(description="SupremeAI Tool Knowledge Injector")
    parser.add_argument("--inject", action="store_true", help="Write knowledge cards to ai_memory DB")
    parser.add_argument("--update-only", action="store_true", help="Only inject cards whose content hash changed (dedup mode)")
    parser.add_argument("--verify", action="store_true", help="Run recall verification after injection")
    parser.add_argument("--json", action="store_true", help="JSON output mode")
    parser.add_argument("--export", type=str, help="Export knowledge cards to JSON file (no DB write)")
    args = parser.parse_args()

    cards = build_knowledge_cards()
    injector = ToolKnowledgeInjector()

    if args.export:
        export_data = {"version": "2.0.0", "total": len(cards), "cards": [asdict(c) for c in cards]}
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        print(f"[OK] Exported {len(cards)} knowledge cards to {args.export}")
        return

    dry_run = not args.inject
    update_only = getattr(args, "update_only", False)
    results = injector.inject(cards, dry_run=dry_run, update_only=update_only)

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        mode = "DRY-RUN PREVIEW" if dry_run else "LIVE INJECTION"
        print("=" * 70)
        print(f"  SUPREMEAI TOOL KNOWLEDGE INJECTOR — {mode}")
        print("=" * 70)
        print(f"  Total Knowledge Cards : {results['total']}")
        print(f"  {'Previewed' if dry_run else 'Injected'} into ai_memory : {results['injected']}")
        print(f"  Unchanged (hash match)  : {results.get('unchanged', 0)}")
        print(f"  Skipped (no DB)         : {results['skipped']}")
        print(f"  Failed                  : {results['failed']}")
        if update_only:
            print("  Mode: UPDATE-ONLY (dedup active)")
        print("-" * 70)
        category_map: dict[str, list[str]] = {}
        for item in results["items"]:
            cat = item["category"]
            category_map.setdefault(cat, []).append(f"  + [{item['tool_id']}]")
        for cat, tools in sorted(category_map.items()):
            print(f"\n  [{cat}]")
            for t in tools:
                print(t)
        print("=" * 70)

        if args.verify and args.inject:
            test_queries = ToolKnowledgeInjector.build_verification_queries()
            print("\n  RECALL VERIFICATION (24 query coverage)")
            print("-" * 70)
            verify_results = injector.verify_recall(test_queries)
            passed = sum(1 for r in verify_results if r.get("hits", 0) > 0)
            for r in verify_results:
                hits = r.get("hits", 0)
                icon = "OK" if hits > 0 else "MISS"
                print(f"  [{icon}] Query: '{r['query'][:55]}' -> {hits} hits")
            print("-" * 70)
            print(f"  Recall Coverage: {passed}/{len(test_queries)} queries returned hits")
            print("=" * 70)
