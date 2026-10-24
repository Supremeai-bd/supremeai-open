import re
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SkillMetadata(BaseModel):
    """
    Metadata information for discovering, versioning, and attributing a dynamic skill.
    """

    name: str = Field(
        ...,
        description="The unique, slugified name of the skill (e.g., 'data_cleaner').",
        examples=["sentiment_analyzer"],
    )
    version: str = Field(
        "1.0.0",
        description="The SemVer version string of the skill.",
        examples=["1.0.0", "0.2.1-beta"],
    )
    description: str = Field(
        ...,
        description="A concise description of the skill's purpose and functionality.",
        examples=[
            "Analyzes input text and classifies sentiment as positive, negative, or neutral."
        ],
    )
    author: str = Field(
        "supremeai_agent_id",
        description="The identifier of the agent or developer who authored this skill.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Keywords used for semantic and tokenized discovery of the skill.",
    )

    @model_validator(mode="after")
    def validate_semver(self):
        # Strict SemVer validation pattern
        pattern = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
        if not re.match(pattern, self.version):
            raise ValueError(f"Version '{self.version}' is not valid SemVer format.")
        return self


class SkillInterface(BaseModel):
    """
    Input and Output JSON Schema definitions to guarantee interface contracts during composition.
    """

    input_schema: dict[str, Any] = Field(
        ...,
        description="Valid JSON Schema (Draft 7+) defining expected input fields, types, and constraints.",
    )
    output_schema: dict[str, Any] = Field(
        ...,
        description="Valid JSON Schema (Draft 7+) describing structure and validation for output values.",
    )


class SkillExecution(BaseModel):
    """
    Execution parameters, runtime target, entry point, and system dependencies.
    """

    runtime: str = Field(
        "python3.11",
        description="The execution runtime environment (e.g., 'python3.11').",
    )
    entry_point: str = Field(
        "main.run",
        description="Entry point in standard 'file.function' format.",
        examples=["main.run", "processor.execute"],
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of pip package dependencies required for execution.",
    )
    timeout_seconds: int = Field(
        30, ge=1, le=300, description="Maximum execution timeout in seconds."
    )


class SkillTestCase(BaseModel):
    """
    Individual test case configuration used to perform validation in the execution sandbox.
    """

    input: dict[str, Any] = Field(
        ..., description="Dictionary representing the payload inputs for the test case."
    )
    expected_output: dict[str, Any] = Field(
        ...,
        description="Dictionary representing the expected payload output schema structure.",
    )


class SkillValidation(BaseModel):
    """
    Validation tests and security configurations used to verify skills before registration.
    """

    tests: list[SkillTestCase] = Field(
        default_factory=list,
        description="List of inputs and expected outputs to execute in tests.",
    )
    security_level: str = Field(
        "sandboxed",
        description="Execution context. Must be either 'sandboxed' or 'privileged'.",
    )

    @model_validator(mode="after")
    def validate_security(self):
        if self.security_level not in ("sandboxed", "privileged"):
            raise ValueError("security_level must be 'sandboxed' or 'privileged'.")
        return self


class UniversalSkillSchema(BaseModel):
    """
    The root schema defining a SupremeAI dynamic skill.
    """

    metadata: SkillMetadata
    interface: SkillInterface
    execution: SkillExecution
    validation: SkillValidation
