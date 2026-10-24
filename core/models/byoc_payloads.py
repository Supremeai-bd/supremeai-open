# Pydantic payloads for Secure BYOC configurations
# বাংলা মন্তব্য: BYOC ক্রেডেনশিয়াল এবং কন্টেইনার ডিপ্লয়মেন্ট রিকোয়েস্ট ভ্যালিডেশন স্কিমা।

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class GCPServiceAccountPayload(BaseModel):
    type: str = Field(..., description="Credentials Type (must be service_account)")
    project_id: str = Field(..., description="GCP Project ID")
    private_key_id: str = Field(..., description="GCP Private Key ID")
    private_key: str = Field(..., description="GCP Private Key")
    client_email: str = Field(..., description="GCP Client Email")

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        # GCP Project IDs: 6 to 30 characters, lowercase letters, numbers, and hyphens.
        if not re.match(r"^[a-z0-9\-]{6,30}$", v):
            raise ValueError("Invalid GCP Project ID format")
        return v

    @field_validator("client_email")
    @classmethod
    def validate_client_email(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Invalid Client Email format")
        return v


class BYOCCredentialsPayload(BaseModel):
    provider: Literal["gcp", "aws", "azure"] = "gcp"
    gcp_credentials: GCPServiceAccountPayload


class BYOCDeployRequest(BaseModel):
    skill_name: str = Field(..., description="Name of the skill container to spin up")
    provider: Literal["gcp", "aws", "azure"] = "gcp"
    memory_limit: str = "256Mi"
    cpu_limit: str = "1000m"
