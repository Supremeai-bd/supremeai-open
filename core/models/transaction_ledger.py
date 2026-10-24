# Pydantic schemas for tracking Immutable Billing Ledgers
# বাংলা মন্তব্য: প্রতিটি ট্রানজেকশন ট্র্যাক করার ইমিউটেবল লেজার স্কিমা।

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TransactionLedgerEntry(BaseModel):
    transaction_id: str = Field(..., description="Unique Transaction ID")
    user_id: str = Field(..., description="Target User ID")
    amount_usd: float = Field(..., description="Amount charged (negative) or credited (positive)")
    transaction_type: Literal["token_usage", "byoc_deployment", "topup", "monthly_grant"]
    description: str = Field(
        ..., description="Context description (e.g. model name, tokens, or invoice ID)"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["success", "failed", "pending"] = "success"
