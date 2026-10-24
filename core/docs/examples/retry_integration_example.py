"""
বাংলা মন্তব্য: রিট্রাই হ্যান্ডলারের ইন্টিগ্রেশন এক্সাম্পল - বিভিন্ন সিস্টেম কম্পোনেন্টে রিট্রাই হ্যান্ডলার ব্যবহারের উদাহরণ।
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.logging_config import logger

from .retry_handler import retry_handler, retry_with_budget


# Example: Database operation retry
@retry_handler(max_retries=3, delay=0.5, backoff=2.0, exceptions=(ConnectionError, TimeoutError))
async def database_operation(query: str) -> dict[str, Any]:
    """
    বাংলা মন্তব্য: ডাটাবেস অপারেশন যেটি কানেকশন সমস্যার কারণে ব্যর্থ হতে পারে।
    """
    logger.info(f"ডাটাবেস কুয়েরি চলছে: {query}")

    # Simulate potential failure
    import random

    if random.random() < 0.6:  # 60% chance of failure
        raise ConnectionError("ডাটাবেস কানেকশন ব্যর্থ হয়েছে")

    return {"status": "success", "data": f"রিজাল্ট ফর কুয়েরি: {query}"}


# Example: API call retry
@retry_handler(
    max_retries=5,
    delay=1.0,
    backoff=1.5,
    exceptions=(ConnectionError, TimeoutError, OSError),
    use_jitter=True,
)
async def external_api_call(endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    বাংলা মন্তব্য: এক্সটার্নাল এপিআই কল যেটি নেটওয়ার্ক সমস্যার কারণে ব্যর্থ হতে পারে।
    """
    logger.info(f"এপিআই কল চলছে: {endpoint}")

    # Simulate potential failure
    import random

    if random.random() < 0.7:  # 70% chance of failure
        raise TimeoutError(f"এপিআই কল টাইমআউট: {endpoint}")

    return {"status": "success", "response": f"রিসপন্স ফর এন্ডপয়েন্ট: {endpoint}", "payload": payload}


# Example: File operation retry with budget
@retry_with_budget(max_retries=2, delay=0.2, backoff=2.0)
def file_operation(file_path: str, content: str) -> bool:
    """
    বাংলা মন্তব্য: ফাইল অপারেশন যেটি কনকারেন্ট অ্যাক্সেসের কারণে ব্যর্থ হতে পারে।
    """
    logger.info(f"ফাইল অপারেশন চলছে: {file_path}")

    # Simulate potential failure
    import random

    if random.random() < 0.5:  # 50% chance of failure
        raise OSError(f"ফাইল অপারেশন ব্যর্থ: {file_path}")

    # In real scenario, we would actually write to file
    logger.info(f"ফাইল সফলভাবে লেখা হয়েছে: {file_path}")
    return True


# Example: Service orchestration with retry
class ServiceOrchestrator:
    """
    বাংলা মন্তব্য: মাল্টি-স্টেপ অপারেশন যেখানে প্রতিটি স্টেপ রিট্রাইয়ের যোগ্য।
    """

    @retry_handler(max_retries=2, delay=0.5, backoff=2.0)
    async def step_one(self) -> str:
        logger.info("স্টেপ ১ চলছে...")
        import random

        if random.random() < 0.4:  # 40% chance of failure
            raise RuntimeError("স্টেপ ১ ব্যর্থ হয়েছে")
        return "স্টেপ ১ সফল"

    @retry_handler(max_retries=2, delay=0.5, backoff=2.0)
    async def step_two(self, input_data: str) -> str:
        logger.info(f"স্টেপ ২ চলছে... ইনপুট: {input_data}")
        import random

        if random.random() < 0.4:  # 40% chance of failure
            raise RuntimeError("স্টেপ ২ ব্যর্থ হয়েছে")
        return f"স্টেপ ২ সফল - ইনপুট: {input_data}"

    @retry_handler(max_retries=2, delay=0.5, backoff=2.0)
    async def step_three(self, input_data: str) -> str:
        logger.info(f"স্টেপ ৩ চলছে... ইনপুট: {input_data}")
        import random

        if random.random() < 0.4:  # 40% chance of failure
            raise RuntimeError("স্টেপ ৩ ব্যর্থ হয়েছে")
        return f"স্টেপ ৩ সফল - ইনপুট: {input_data}"

    async def execute_workflow(self) -> str:
        """
        বাংলা মন্তব্য: মাল্টি-স্টেপ ওয়ার্কফ্লো যেখানে প্রতিটি স্টেপ আলাদা আলাদা ভাবে রিট্রাই করে।
        """
        logger.info("ওয়ার্কফ্লো শুরু হচ্ছে...")

        result1 = await self.step_one()
        result2 = await self.step_two(result1)
        result3 = await self.step_three(result2)

        return f"ওয়ার্কফ্লো সফল: {result3}"


async def main():
    """
    বাংলা মন্তব্য: রিট্রাই হ্যান্ডলার ইন্টিগ্রেশন এক্সাম্পল মেইন ফাংশন।
    """
    logger.info("রিট্রাই হ্যান্ডলার ইন্টিগ্রেশন এক্সাম্পল শুরু হচ্ছে...")

    # Test database operation
    logger.info("\n1. ডাটাবেস অপারেশন টেস্ট:")
    try:
        db_result = await database_operation("SELECT * FROM users")
        logger.info(f"DB Result: {db_result}")
    except Exception as e:
        logger.error(f"DB Operation failed: {e}")

    # Test API call
    logger.info("\n2. এপিআই কল টেস্ট:")
    try:
        api_result = await external_api_call("/api/users", {"id": 1})
        logger.info(f"API Result: {api_result}")
    except Exception as e:
        logger.error(f"API Call failed: {e}")

    # Test file operation
    logger.info("\n3. ফাইল অপারেশন টেস্ট:")
    try:
        file_result = file_operation("/tmp/test.txt", "test content")
        logger.info(f"File Result: {file_result}")
    except Exception as e:
        logger.error(f"File Operation failed: {e}")

    # Test service orchestration
    logger.info("\n4. সার্ভিস অর্কেস্ট্রেশন টেস্ট:")
    orchestrator = ServiceOrchestrator()
    try:
        workflow_result = await orchestrator.execute_workflow()
        logger.info(f"Workflow Result: {workflow_result}")
    except Exception as e:
        logger.error(f"Workflow failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
