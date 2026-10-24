"""
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).
SupremeAI — Escrow Service
============================

Escrow system for secure transaction handling.
- Multi-party agreement tracking
- State management
- Release conditions
- Zero-cost: uses Upstash Redis for state persistence
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from core.cache import get_cache
from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
ESCROW_TTL = 30 * 24 * 3600  # 30 days
RELEASE_TIMEOUT = 7 * 24 * 3600  # 7 days for manual release


class EscrowStatus(StrEnum):
    PENDING = "pending"
    FUNDED = "funded"
    CONDITION_MET = "condition_met"
    RELEASED = "released"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Escrow:
    """Escrow transaction record."""

    escrow_id: str
    payer_id: str
    payee_id: str
    amount: float
    currency: str
    conditions: list[str]
    status: EscrowStatus
    created_at: datetime
    expires_at: datetime | None = None
    released_at: datetime | None = None


class EscrowService:
    """
    Manages escrow transactions with state machine logic.
    """

    def __init__(self, cache: Any = None) -> None:
        self.cache = cache or get_cache()
        self._escrows: dict[str, Escrow] = {}
        logger.info("EscrowService initialized")

    def _escrow_key(self, escrow_id: str) -> str:
        return f"escrow:{escrow_id}"

    async def create_escrow(
        self,
        payer_id: str,
        payee_id: str,
        amount: float,
        currency: str = "USD",
        conditions: list[str] | None = None,
        expires_in_days: int = 30,
    ) -> str:
        """
        Create a new escrow transaction.

        Args:
            payer_id: Payer user ID.
            payee_id: Payee user ID.
            amount: Transaction amount.
            currency: Currency code.
            conditions: List of release conditions.
            expires_in_days: Expiration days.

        Returns:
            Escrow ID.

        Raises:
            ValueError: If amount is invalid.
        """
        # বাংলা মন্তব্য: Amount validation - negative বা zero amount গ্রহণযোগ্য নয়
        if amount <= 0:
            raise ValueError(f"Escrow amount must be positive, got {amount}")

        # বাংলা মন্তব্য: Amount precision check (max 2 decimal places for USD)
        if round(amount, 2) != amount:
            raise ValueError(f"Escrow amount has too many decimal places: {amount}")

        # বাংলা মন্তব্য: Maximum escrow amount limit
        max_amount = 1_000_000.0  # $1M limit
        if amount > max_amount:
            raise ValueError(f"Escrow amount exceeds maximum limit of ${max_amount:,.2f}")

        escrow_id = f"escrow_{secrets.token_hex(16)}"

        escrow = Escrow(
            escrow_id=escrow_id,
            payer_id=payer_id,
            payee_id=payee_id,
            amount=amount,
            currency=currency,
            conditions=conditions or [],
            status=EscrowStatus.PENDING,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            released_at=None,
        )

        await self.cache.set(
            self._escrow_key(escrow_id),
            escrow.__dict__,
            ttl=ESCROW_TTL,
        )

        self._escrows[escrow_id] = escrow
        return escrow  # type: ignore

    def create_escrow_sync(
        self,
        payer_id: str,
        payee_id: str,
        amount: float,
        currency: str = "USD",
        conditions: list[str] | None = None,
        expires_in_days: int = 30,
    ) -> Escrow:
        # বাংলা মন্তব্য: Amount validation - negative বা zero amount গ্রহণযোগ্য নয়
        if amount <= 0:
            raise ValueError(f"Escrow amount must be positive, got {amount}")

        # বাংলা মন্তব্য: Amount precision check (max 2 decimal places for USD)
        if round(amount, 2) != amount:
            raise ValueError(f"Escrow amount has too many decimal places: {amount}")

        # বাংলা মন্তব্য: Maximum escrow amount limit
        max_amount = 1_000_000.0  # $1M limit
        if amount > max_amount:
            raise ValueError(f"Escrow amount exceeds maximum limit of ${max_amount:,.2f}")

        escrow_id = f"esc_{secrets.token_hex(8)}"
        escrow = Escrow(
            escrow_id=escrow_id,
            payer_id=payer_id,
            payee_id=payee_id,
            amount=amount,
            currency=currency,
            conditions=conditions or [],
            status=EscrowStatus.PENDING,
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            released_at=None,
        )
        self._escrows[escrow_id] = escrow
        return escrow

    def get_escrow_sync(self, escrow_id: str) -> Escrow | None:
        return self._escrows.get(escrow_id)

    def update_escrow_status_sync(self, escrow_id: str, status: EscrowStatus) -> Escrow | None:
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            return None
        updated = Escrow(
            escrow_id=escrow.escrow_id,
            payer_id=escrow.payer_id,
            payee_id=escrow.payee_id,
            amount=escrow.amount,
            currency=escrow.currency,
            conditions=escrow.conditions,
            status=status,
            created_at=escrow.created_at,
            expires_at=escrow.expires_at,
            released_at=(
                datetime.now(UTC) if status == EscrowStatus.RELEASED else escrow.released_at
            ),
        )
        self._escrows[escrow_id] = updated
        return updated

    def list_active_escrows_sync(self) -> list[Escrow]:
        return list(self._escrows.values())

    async def fund_escrow(self, escrow_id: str, payment_reference: str) -> bool:
        """
        Mark escrow as funded.

        Args:
            escrow_id: Escrow ID.
            payment_reference: Payment reference.

        Returns:
            Success status.
        """
        escrow_data = await self.cache.get(self._escrow_key(escrow_id))
        if not escrow_data:
            return False

        # Update status
        escrow_data["status"] = EscrowStatus.FUNDED.value
        escrow_data["payment_reference"] = payment_reference

        await self.cache.set(
            self._escrow_key(escrow_id),
            escrow_data,
            ttl=ESCROW_TTL,
        )

        return True

    async def mark_condition_met(self, escrow_id: str, condition_index: int) -> bool:
        """
        Mark a condition as met.

        Args:
            escrow_id: Escrow ID.
            condition_index: Index of satisfied condition.

        Returns:
            Success status.
        """
        escrow_data = await self.cache.get(self._escrow_key(escrow_id))
        if not escrow_data:
            return False

        if escrow_data["status"] != EscrowStatus.FUNDED.value:
            return False

        # Track met conditions
        if "met_conditions" not in escrow_data:
            escrow_data["met_conditions"] = []

        if condition_index not in escrow_data["met_conditions"]:
            escrow_data["met_conditions"].append(condition_index)

        # Check if all conditions met
        if escrow_data["met_conditions"] and len(escrow_data["met_conditions"]) >= len(
            escrow_data.get("conditions", [])
        ):
            escrow_data["status"] = EscrowStatus.CONDITION_MET.value

        await self.cache.set(
            self._escrow_key(escrow_id),
            escrow_data,
            ttl=ESCROW_TTL,
        )

        return True

    async def release_funds(self, escrow_id: str, authorized_by: str) -> bool:
        """
        Release funds to payee.

        Args:
            escrow_id: Escrow ID.
            authorized_by: Authorizing user ID.

        Returns:
            Success status.
        """
        escrow_data = await self.cache.get(self._escrow_key(escrow_id))
        if not escrow_data:
            return False

        if escrow_data["status"] != EscrowStatus.CONDITION_MET.value:
            return False

        escrow_data["status"] = EscrowStatus.RELEASED.value
        escrow_data["released_at"] = datetime.now(UTC).isoformat()
        escrow_data["released_by"] = authorized_by

        await self.cache.set(
            self._escrow_key(escrow_id),
            escrow_data,
            ttl=ESCROW_TTL,
        )

        return True

    async def dispute(self, escrow_id: str, reason: str, disputant: str) -> bool:
        """
        Raise dispute on escrow.

        Args:
            escrow_id: Escrow ID.
            reason: Dispute reason.
            disputant: User raising dispute.

        Returns:
            Success status.
        """
        escrow_data = await self.cache.get(self._escrow_key(escrow_id))
        if not escrow_data:
            return False

        escrow_data["status"] = EscrowStatus.DISPUTED.value
        escrow_data["dispute_reason"] = reason
        escrow_data["disputed_by"] = disputant
        escrow_data["disputed_at"] = datetime.now(UTC).isoformat()

        await self.cache.set(
            self._escrow_key(escrow_id),
            escrow_data,
            ttl=ESCROW_TTL,
        )

        return True

    async def get_escrow(self, escrow_id: str) -> Escrow | None:
        """Get escrow details."""
        data = await self.cache.get(self._escrow_key(escrow_id))
        if not data:
            return None

        return Escrow(**data)

    async def list_escrows(self, user_id: str, role: str = "payer") -> list[Escrow]:
        """List escrows for a user."""
        # This would need a secondary index in production
        results = []
        for escrow_id in list(self._escrows.keys()):
            escrow = await self.get_escrow(escrow_id)
            if escrow:
                user_field = f"{role}_id"
                if getattr(escrow, user_field, None) == user_id:
                    results.append(escrow)

        return results

    async def auto_release_check(self) -> list[str]:
        """
        Check for escrows ready for auto-release.
        Called by scheduled job.
        """
        now = datetime.now(UTC)
        ready = []

        for escrow_id in list(self._escrows.keys()):
            escrow = await self.get_escrow(escrow_id)
            if escrow and escrow.status == EscrowStatus.CONDITION_MET:
                if escrow.expires_at and (now - escrow.expires_at).days > 7:
                    ready.append(escrow_id)

        return ready


# Singleton
_service_instance: EscrowService | None = None


def get_escrow_service() -> EscrowService:
    """Get or create the singleton EscrowService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EscrowService()
    return _service_instance
