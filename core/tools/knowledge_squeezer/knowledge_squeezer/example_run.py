import asyncio

from .engine import KnowledgeSqueezer
from .providers import default_providers


async def run() -> None:
    providers = default_providers()
    engine = KnowledgeSqueezer(providers)
    result = await engine.squeeze(
        "Design a high-concurrency idempotent job submission API",
        domain="distributed-systems",
    )
    print(result.artifact.stable_text())


if __name__ == "__main__":
    asyncio.run(run())
