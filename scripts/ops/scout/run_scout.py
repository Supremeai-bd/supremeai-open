#!/usr/bin/env python3
"""Ecosystem Scout — daily discovery pipeline CLI (#4055).

বাংলা: এই script daily cron-এ চলবে। Pipeline:
  1. Fetch trending repos (GitHub + other sources)
  2. Dedup (fingerprint against known set)
  3. Gap analysis (cross-reference inventory.yaml)
  4. Score (relevance × improvement × cost)
  5. Filter by threshold
  6. Output recommendations (auditor reviews next)

Hard governance rule (Roadmap v2 §4.2):
  Discovery agents may discover. Auditor may recommend.
  Only governed issue-generation workflow may create issues.

Usage:
  python scripts/scout/run_scout.py
  python scripts/scout/run_scout.py --limit 5 --no-mock
  python scripts/scout/run_scout.py --json  # output as JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_scout(
    limit: int = 10,
    use_mock: bool = True,
    output_json: bool = False,
) -> list[dict]:
    """Run the full scout pipeline.

    বাংলা: সম্পূর্ণ scout pipeline চালায় → list of recommendation dicts।
    """
    from backend.ecosystem_scout.sources.github_trending import fetch_github_trending
    from backend.ecosystem_scout.gap_analyzer import analyze_gaps_batch
    from backend.ecosystem_scout.recommender import filter_recommendations, score_findings_batch
    from backend.scout.dedup import ContentDeduplicator

    # Step 1: Fetch
    findings = fetch_github_trending(limit=limit, use_mock=use_mock)
    print(f"📦 Step 1: Fetched {len(findings)} findings from GitHub trending", file=sys.stderr)

    # Step 2: Dedup (in this run — no known_fingerprints for prototype)
    # বাংলা (#4157): কোনো আলাদা dedup মডিউল নেই — pre-existing canonical ইঞ্জিন
    # backend.scout.dedup.ContentDeduplicator রিইউজ করা হয়েছে। প্রথম লাইন ডিফেন্স
    # হলো ScoutFinding.fingerprint (SSOT: models.make_finding-এ sha256), দ্বিতীয়
    # লাইন ডিফেন্স হলো description-এর near-duplicate (Jaccard, 0.80 threshold)।
    dedup = ContentDeduplicator()
    seen_fingerprints: set[str] = set()
    unique: list = []
    duplicates: list = []
    for f in findings:
        if f.fingerprint and f.fingerprint in seen_fingerprints:
            duplicates.append(f)
            continue
        if f.description and dedup.record_content(f.description)[1]:
            duplicates.append(f)
            continue
        if f.fingerprint:
            seen_fingerprints.add(f.fingerprint)
        unique.append(f)
    print(f"🔍 Step 2: Deduped {len(duplicates)} duplicates → {len(unique)} unique", file=sys.stderr)

    # Step 3: Gap analysis
    analyzed = analyze_gaps_batch(unique)
    gaps = [f for f in analyzed if f.gap_analysis.get("gap")]
    known = [f for f in analyzed if not f.gap_analysis.get("gap")]
    print(f"📊 Step 3: Gap analysis → {len(gaps)} new gaps, {len(known)} already known", file=sys.stderr)

    # Step 4: Score
    recommendations = score_findings_batch(analyzed)
    print(f"⭐ Step 4: Scored {len(recommendations)} findings", file=sys.stderr)

    # Step 5: Filter
    filtered = filter_recommendations(recommendations)
    print(f"✅ Step 5: {len(filtered)} recommendations above threshold (auditor review next)", file=sys.stderr)

    # Output
    result = [r.to_dict() for r in filtered]
    if output_json:
        print(json.dumps({"recommendations": result}, indent=2))
    else:
        print("\n" + "=" * 70)
        print("ECOSYSTEM SCOUT — RECOMMENDATIONS FOR AUDITOR REVIEW")
        print("=" * 70)
        for r in filtered:
            arch = " [ARCHITECTURAL — Tier-3]" if r.is_architectural else ""
            print(f"\n  {r.finding.repo_name} (⭐{r.finding.stars}){arch}")
            print(f"    {r.finding.description[:80]}")
            print(f"    Score: {r.score:.4f} | {r.reason}")
            print(f"    Gap: {r.finding.gap_analysis.get('gap', '?')} | URL: {r.finding.repo_url}")
        print("\n" + "=" * 70)
        print(f"Total: {len(filtered)} recommendations (auditor review next)")
        print("=" * 70)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Ecosystem Scout — daily discovery pipeline (#4055)")
    parser.add_argument("--limit", type=int, default=10, help="max findings to fetch")
    parser.add_argument("--no-mock", action="store_true", help="attempt real fetch (may fail)")
    parser.add_argument("--json", action="store_true", help="output as JSON")
    args = parser.parse_args()

    run_scout(
        limit=args.limit,
        use_mock=not args.no_mock,
        output_json=args.json,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
