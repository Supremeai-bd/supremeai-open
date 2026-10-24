# Shared state workspace memory for Multi-Agent Swarm Orchestrations
# বাংলা মন্তব্য: সোয়ার্ম এজেন্টদের মধ্যে কাজের ফলাফল ও ফাইল স্টেট শেয়ার করার শেয়ার্ড মেমরি ক্লাস।

from typing import Any

from pydantic import BaseModel, Field


class SharedWorkspace(BaseModel):
    task_id: str = Field(..., description="Unique Master Task ID")
    original_prompt: str = Field(..., description="User query context")
    # বাংলা মন্তব্য: আর্কিটেকচার এখন ডোমেইন-অ্যাগনস্টিক। এটি শুধু কোড নয়, যেকোনো কাজের ফলাফল (লিগ্যাল ড্রাফট, রিপোর্ট) ধারণ করবে।
    work_product: dict[str, Any] = Field(
        default_factory=dict,
        description="Domain-agnostic work product (code, documents, analysis)",
    )
    test_results: dict[str, Any] = Field(default_factory=dict)
    execution_logs: list[str] = Field(default_factory=list)
    errors: list[str] = Field(
        default_factory=list, description="Errors encountered during execution"
    )
    # Issue #1816: IntegrationAgent.run reads getattr(workspace, "kwargs", {})
    # and api/routes/agent_action.py writes platform credentials/context here,
    # but the field never existed — pydantic raised on the assignment and every
    # platform-sync action 500'd. Declared now (additive, default empty).
    kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra call context (e.g. platform tokens/content) for DAG agents",
    )
    # বাংলা মন্তব্য: প্রতিটি কাজের জন্য নির্ধারিত ইনটেন্ট এখানে সংরক্ষণ করা হবে, যা অর্কেস্ট্রেটরকে সঠিক DAG তৈরিতে সাহায্য করবে।
    intent: str = Field(
        default="general_task",
        description="The classified intent of the user's prompt (e.g., 'code_generation', 'legal_analysis')",
    )

    def log(self, message: str):
        self.execution_logs.append(message)

    def add_error(self, error_message: str):
        self.log(f"ERROR: {error_message}")
        self.errors.append(error_message)
