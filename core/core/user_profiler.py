import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.logging_config import logger


class UserMode(StrEnum):
    FAST_TRACK = "FAST_TRACK"
    LEARNING = "LEARNING"
    PRODUCTION = "PRODUCTION"


@dataclass
class UserProfile:
    user_id: str
    mode: UserMode = UserMode.FAST_TRACK
    goals: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)


class UserProfiler:
    MODES = [m.value for m in UserMode]

    async def classify_user(self, user_id: str) -> UserProfile:
        return UserProfile(user_id=user_id)

    async def update_from_history(self, user_id: str, task: dict[str, Any]) -> None:
        logger.debug(f"Updating user profile for {user_id} from task")
        try:
            from brain.user_digital_twin import InteractionType, get_twin_manager

            manager = get_twin_manager()
            twin = manager.get_or_create(user_id)

            req_type = task.get("type", "question")
            if "code" in req_type.lower():
                i_type = InteractionType.CODE_REQUEST
            else:
                i_type = InteractionType.QUESTION

            await twin.record_interaction(
                interaction_type=i_type,
                content=str(task.get("content", "")),
                duration_ms=task.get("duration_ms", 100),
                success=task.get("success", True),
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")
