from __future__ import annotations

import argparse
import asyncio
import json

from .engine import KnowledgeSqueezer
from .providers import default_providers


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run SupremeAI Knowledge Squeezer")
    parser.add_argument("topic")
    parser.add_argument("--domain", default="general")
    parser.add_argument("--context", default="")
    args = parser.parse_args()

    providers = default_providers()
    if not providers:
        raise SystemExit("Set at least one provider API key: DEEPSEEK_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY")

    engine = KnowledgeSqueezer(providers)
    result = await engine.squeeze(args.topic, context=args.context, domain=args.domain)
    print(json.dumps(result.artifact.to_dict(), ensure_ascii=False, indent=2))
    print("\nSCORE:", json.dumps(result.score_breakdown, indent=2))
    print("PROMOTION_ELIGIBLE:", result.promotion_eligible)


if __name__ == "__main__":
    asyncio.run(main())
