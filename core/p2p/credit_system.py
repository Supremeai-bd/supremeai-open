import uuid
from typing import Any

from core.logging_config import logger


class CreditLedger:
    async def earn(self, user_id: str, amount: float, reason: str) -> dict[str, Any]:
        return {
            "tx_id": str(uuid.uuid4()),
            "user_id": user_id,
            "amount": amount,
            "reason": reason,
            "type": "credit",
        }

    async def spend(self, user_id: str, amount: float, reason: str) -> dict[str, Any]:
        return {
            "tx_id": str(uuid.uuid4()),
            "user_id": user_id,
            "amount": -amount,
            "reason": reason,
            "type": "debit",
        }

    async def opt_out(self, user_id: str) -> None:
        logger.info(f"User {user_id} opted out of P2P")

    async def opt_in(self, user_id: str) -> None:
        logger.info(f"User {user_id} opted in to P2P")

    async def balance(self, user_id: str) -> float:
        return 0.0


class ResourceBroker:
    async def match(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"matched": False, "reason": "no_available_peers"}
