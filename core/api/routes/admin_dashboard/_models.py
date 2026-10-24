"""Pydantic request models for the admin dashboard router.

All request bodies keep their original class names (and Field descriptions)
so the OpenAPI ``components.schemas`` section is identical to the pre-split
single-file module."""

from pydantic import BaseModel, Field


# User CRUD model
class UserUpdate(BaseModel):
    username: str
    role: str
    permissions: list[str]


# Environment Configuration Editor
class ConfigUpdate(BaseModel):
    env_vars: dict[str, str]


class RouterOverrideRequest(BaseModel):
    provider: str
    model: str
    remaining_requests: int


class ImpersonateRequest(BaseModel):
    user_id: str
    otp: str | None = None


class GateOverridePayload(BaseModel):
    target_status: str = Field(..., description="Must be 'UNLOCKED' or 'LOCKED'")
    reason: str = Field(..., min_length=10, description="Detailed justification for manual bypass")
    admin_secret: str = Field(..., description="Master JWT/Vault secret key for authentication")


class DeployGateToggle(BaseModel):
    status: str
    reason: str


class ApprovalDecisionPayload(BaseModel):
    id: str
    approve: bool | None = None
    action: str | None = None
    reason: str = ""
    otp: str = ""


class AlertAcknowledgePayload(BaseModel):
    alert_id: str


class ApprovalActionPayload(BaseModel):
    id: str
    approve: bool
    reason: str = ""
    otp: str = ""
