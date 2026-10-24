from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# বাংলা মন্তব্য: StrEnum ব্যবহার করা হয়েছে (UP042) — Python 3.11+ এ (str, Enum) deprecated
class SkillStatus(StrEnum):
    STAGING = "staging"
    QUARANTINE = "quarantine"
    APPROVED = "approved"
    EPHEMERAL = "ephemeral"
    REJECTED = "rejected"
    DEPRECATED_PENDING = "deprecation_pending"


class SkillPermissions(BaseModel):
    allow_network: bool = Field(default=False, description="স্কিলটি ইন্টারনেট অ্যাক্সেস করতে পারবে কিনা")
    allowed_domains: list[str] = Field(
        default_factory=list, description="নেটওয়ার্ক ট্রাস্টেড ওরিজিন ডোমেইন লিস্ট"
    )
    allow_filesystem_write: bool = Field(default=False, description="লোকাল ফাইলে রাইট করার অনুমতি")
    required_env_vars: list[str] = Field(
        default_factory=list, description="কাজ করার জন্য প্রয়োজনীয় পরিবেশ ভ্যারিয়েবল"
    )


class SkillGovernance(BaseModel):
    """Runtime contract for a published skill.

    The defaults deliberately deny data, tools, and execution approvals.  A skill
    must opt in to every capability in its manifest instead of inheriting broad
    platform access.
    """

    owner: str = Field(..., min_length=1)
    allowed_data: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)
    tools_allowed: list[str] = Field(default_factory=list)
    human_approval_points: dict[str, bool] = Field(default_factory=dict)
    success_metrics: dict[str, str] = Field(default_factory=dict)
    evaluation_tests: list[str] = Field(default_factory=list)
    budget: dict[str, float] = Field(default_factory=dict)
    audit_logging: list[str] = Field(default_factory=list)


class SkillManifest(BaseModel):
    skill_id: str = Field(..., description="ইউনিক স্কিল আইডেন্টিফায়ার (slug)")
    name: str = Field(..., description="স্কিলের মানব-পাঠ্য নাম")
    description: str = Field(..., description="FastAPI বা এজেন্ট রাউটার যার মাধ্যমে ম্যাচিং করবে")
    version: str = Field(default="1.0.0")
    source_url: HttpUrl = Field(..., description="ভেরিফায়েড MCP বা গিটহাব রিপোজিটরি উৎস")
    checksum: str = Field(..., description="SHA-256 কোড ইন্টিগ্রিটি হ্যাশ")
    status: SkillStatus = Field(default=SkillStatus.STAGING)
    permissions: SkillPermissions = Field(default_factory=SkillPermissions)
    governance: SkillGovernance | None = None

    # ইউজেস এবং মেটাডেটা ট্র্যাকিং
    usage_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    last_used_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    # বাংলা মন্তব্য: Pydantic V2 ফিক্স — class Config deprecated, model_config = ConfigDict() ব্যবহার করা হয়েছে
    model_config = ConfigDict(from_attributes=True)
