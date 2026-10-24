from typing import Any


class ResourceManager:
    async def get_status(self, user_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "resources": [], "quota": {}}

    async def list_resources(self, user_id: str) -> list[dict[str, Any]]:
        return []
