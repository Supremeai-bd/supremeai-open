from typing import Any


class SecureTunnel:
    async def create(self, peer_a: str, peer_b: str) -> dict[str, Any]:
        return {"status": "created", "peer_a": peer_a, "peer_b": peer_b}

    async def terminate(self, tunnel_id: str) -> None:
        pass
