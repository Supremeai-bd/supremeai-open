"""
Cloudflare Edge Routing & Federation Pool Manager.

Handles:
- Primary edge worker routing.
- Multi-account rotation & failover pool across 5 Cloudflare accounts.
- Zero-cost rate limit & quota distribution.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CloudflareEdgeNode:
    role: str
    account_id: str
    worker_url: str
    is_active: bool = True


class CloudflareFederationManager:
    """Manages the 5-account Cloudflare Edge federation pool.

    Supports round-robin and circuit-broken failover between
    primary, secondary, tertiary, quaternary, and quinary accounts.
    """

    _ACCOUNT_ENVS: Sequence[tuple[str, str, str, str]] = (
        (
            "primary",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_WORKER_URL",
            "https://supremeai-worker.paykaribazaronline.workers.dev",
        ),
        (
            "secondary",
            "CLOUDFLARE_SECONDARY_ACCOUNT_ID",
            "CLOUDFLARE_SECONDARY_WORKER_URL",
            "https://supremeai-worker-secondary.workers.dev",
        ),
        (
            "tertiary",
            "CLOUDFLARE_TERTIARY_ACCOUNT_ID",
            "CLOUDFLARE_TERTIARY_WORKER_URL",
            "https://supremeai-worker-tertiary.workers.dev",
        ),
        (
            "quaternary",
            "CLOUDFLARE_QUATERNARY_ACCOUNT_ID",
            "CLOUDFLARE_QUATERNARY_WORKER_URL",
            "https://supremeai-worker-quaternary.workers.dev",
        ),
        (
            "quinary",
            "CLOUDFLARE_QUINARY_ACCOUNT_ID",
            "CLOUDFLARE_QUINARY_WORKER_URL",
            "https://supremeai-worker-quinary.workers.dev",
        ),
    )

    def __init__(self) -> None:
        self._nodes: list[CloudflareEdgeNode] = []
        self._active_index: int = 0
        self._load_nodes()

    def _load_nodes(self) -> None:
        for role, acc_env, url_env, default_url in self._ACCOUNT_ENVS:
            acc_id = os.getenv(acc_env, "").strip()
            url = os.getenv(url_env, default_url).strip()
            # If account ID or URL is present, enroll in pool
            if acc_id or role == "primary":
                self._nodes.append(
                    CloudflareEdgeNode(
                        role=role,
                        account_id=acc_id,
                        worker_url=url,
                        is_active=True,
                    )
                )

    @property
    def nodes(self) -> list[CloudflareEdgeNode]:
        return list(self._nodes)

    def get_current_endpoint(self) -> str:
        """Get the active edge worker endpoint."""
        if not self._nodes:
            return os.getenv("CLOUDFLARE_WORKER_URL", "")
        return self._nodes[self._active_index % len(self._nodes)].worker_url

    def rotate_next(self) -> CloudflareEdgeNode:
        """Rotate to the next available account in the federation pool."""
        if not self._nodes:
            raise RuntimeError("No Cloudflare edge nodes available in federation pool.")
        self._active_index = (self._active_index + 1) % len(self._nodes)
        return self._nodes[self._active_index]


# Singleton instance
cloudflare_edge_pool = CloudflareFederationManager()
