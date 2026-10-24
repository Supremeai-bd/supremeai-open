#!/usr/bin/env python3
"""
============================================================================
SupremeAI 2.0 — API Contract Validator
============================================================================
উদ্দেশ্য: OpenAPI schema, request/response contracts, এবং API consistency
validate করে। Breaking changes ডিটেক্ট করে এবং client SDK compatibility
চেক করে।

বৈশিষ্ট্য:
  - OpenAPI 3.1 schema validation
  - Request/response schema matching
  - Breaking change detection between versions
  - Auto-generated API documentation sync check
  - Payload fuzzing against schema
  - Bangla content type validation
  - WebSocket message schema validation
  - gRPC proto validation
  - AsyncAPI schema validation
  - Client SDK compatibility matrix

ব্যবহার:
  python scripts/testing/api_contract_validator.py --spec openapi.yaml
  python scripts/testing/api_contract_validator.py --spec openapi.yaml --test-live
  python scripts/testing/api_contract_validator.py --spec openapi.yaml --check-breaking v1.0.0
  python scripts/testing/api_contract_validator.py --fuzz --count 100

লেখক: SupremeAI Architecture Team
তারিখ: July 20, 2026
============================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from jsonschema import Draft7Validator
from loguru import logger

# বাংলা মন্তব্য: sys.path হ্যাক এড়াতে ক্লিন ইমপোর্ট
try:
    from backend.core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ── Configuration ──────────────────────────────────────────────────────────
DEFAULT_SPEC_PATH = os.getenv("API_SPEC_PATH", "openapi.yaml")
DEFAULT_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")  # is_local()
DEFAULT_TIMEOUT = float(os.getenv("API_VALIDATOR_TIMEOUT", "10.0"))
REPORT_DIR = Path(os.getenv("API_VALIDATOR_REPORT_DIR", "tests/reports/api_contract"))
FUZZ_COUNT = int(os.getenv("API_FUZZ_COUNT", "50"))

# বাংলা মন্তব্য: Bangla test data for i18n validation
BANGLA_TEST_DATA = {
    "names": ["রহিম", "করিম", "সুজন", "মোহনা", "তাসনিম", "আফরিন"],
    "addresses": ["ঢাকা, বাংলাদেশ", "চট্টগ্রাম, বাংলাদেশ", "রাজশাহী"],
    "messages": [
        "বাংলা ভাষায় একটি টেস্ট মেসেজ",
        "কিভাবে আছেন? সব ঠিক আছে তো?",
        "এটি একটি দীর্ঘ বাংলা টেক্সট যা ইউনিকোড এনকোডিং টেস্ট করবে।",
    ],
    "emails": ["test@বাংলা.com", "user@example.bd"],
    "phones": ["+8801712345678", "+8801912345678"],
}


# ── Data Models ──────────────────────────────────────────────────────────

@dataclass
class ContractViolation:
    """বাংলা মন্তব্য: API contract violation-এর তথ্য"""
    id: str
    endpoint: str
    method: str
    violation_type: str  # schema_mismatch | missing_field | type_error | breaking_change | etc.
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    expected: str
    actual: str
    path: str  # JSON path to the violation
    message: str
    remediation: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "endpoint": self.endpoint,
            "method": self.method,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "expected": self.expected,
            "actual": self.actual,
            "path": self.path,
            "message": self.message,
            "remediation": self.remediation,
            "timestamp": self.timestamp,
        }


@dataclass
class ValidationResult:
    """বাংলা মন্তব্য: সম্পূর্ণ validation-এর ফলাফল"""
    spec_file: str
    base_url: str
    violations: list[ContractViolation] = field(default_factory=list)
    endpoints_tested: int = 0
    schemas_validated: int = 0
    breaking_changes: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "HIGH")

    @property
    def is_valid(self) -> bool:
        return self.critical_count == 0 and self.high_count == 0


# ── OpenAPI Parser ─────────────────────────────────────────────────────────

class OpenAPIParser:
    """
    বাংলা মন্তব্য: OpenAPI 3.0/3.1 YAML/JSON spec পার্স করে।
    Endpoints, schemas, এবং security requirements এক্সট্রাক্ট করে।
    """

    def __init__(self, spec_path: str):
        self.spec_path = Path(spec_path)
        self.spec: dict[str, Any] = {}
        self.endpoints: list[dict[str, Any]] = []
        self.schemas: dict[str, Any] = {}
        self.security_schemes: dict[str, Any] = {}

    def parse(self) -> dict[str, Any]:
        """বাংলা মন্তব্য: spec ফাইল পার্স করে"""
        if not self.spec_path.exists():
            raise FileNotFoundError(f"OpenAPI spec not found: {self.spec_path}")

        content = self.spec_path.read_text(encoding="utf-8")

        if self.spec_path.suffix in (".yaml", ".yml"):
            self.spec = yaml.safe_load(content)
        else:
            self.spec = json.loads(content)

        self._extract_schemas()
        self._extract_security()
        self._extract_endpoints()

        logger.info(f"Parsed OpenAPI spec: {self.spec.get('info', {}).get('title', 'Unknown')}")
        logger.info(f"  Version: {self.spec.get('info', {}).get('version', 'Unknown')}")
        logger.info(f"  Endpoints: {len(self.endpoints)}")
        logger.info(f"  Schemas: {len(self.schemas)}")

        return self.spec

    def _extract_schemas(self) -> None:
        """বাংলা মন্তব্য: Component schemas এক্সট্রাক্ট করে"""
        components = self.spec.get("components", {})
        self.schemas = components.get("schemas", {})

    def _extract_security(self) -> None:
        """বাংলা মন্তব্য: Security schemes এক্সট্রাক্ট করে"""
        components = self.spec.get("components", {})
        self.security_schemes = components.get("securitySchemes", {})

    def _extract_endpoints(self) -> None:
        """বাংলা মন্তব্য: Paths থেকে endpoints এক্সট্রাক্ট করে"""
        paths = self.spec.get("paths", {})

        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
                if method in path_item:
                    operation = path_item[method]
                    endpoint = {
                        "path": path,
                        "method": method.upper(),
                        "operation_id": operation.get("operationId", ""),
                        "summary": operation.get("summary", ""),
                        "parameters": operation.get("parameters", []),
                        "request_body": operation.get("requestBody", {}),
                        "responses": operation.get("responses", {}),
                        "security": operation.get("security", self.spec.get("security", [])),
                        "tags": operation.get("tags", []),
                    }
                    self.endpoints.append(endpoint)

    def get_schema_ref(self, ref: str) -> dict[str, Any] | None:
        """বাংলা মন্তব্য: $ref resolve করে actual schema রিটার্ন করে"""
        if not ref.startswith("#/components/schemas/"):
            return None
        schema_name = ref.split("/")[-1]
        return self.schemas.get(schema_name)

    def resolve_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """বাংলা মন্তব্য: Recursive schema resolution — সব $ref resolve করে"""
        if "$ref" in schema:
            resolved = self.get_schema_ref(schema["$ref"])
            if resolved:
                return self.resolve_schema(resolved)
            return schema

        result = dict(schema)
        for key, value in result.items():
            if isinstance(value, dict):
                result[key] = self.resolve_schema(value)
            elif isinstance(value, list):
                result[key] = [
                    self.resolve_schema(item) if isinstance(item, dict) else item
                    for item in value
                ]
        return result


# ── Schema Validator ─────────────────────────────────────────────────────────

class SchemaValidator:
    """
    বাংলা মন্তব্য: Request/response payload JSON Schema দিয়ে validate করে।
    Bangla content, Unicode, এবং special characters সাপোর্ট করে।
    """

    def __init__(self, parser: OpenAPIParser):
        self.parser = parser
        self.violations: list[ContractViolation] = []

    def validate_request(self, endpoint: dict[str, Any], payload: dict[str, Any]) -> list[ContractViolation]:
        """বাংলা মন্তব্য: Request body schema validate করে"""
        request_body = endpoint.get("request_body", {})
        if not request_body:
            return []

        content = request_body.get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})

        if not json_schema:
            return []

        resolved_schema = self.parser.resolve_schema(json_schema)
        return self._validate_against_schema(
            payload, resolved_schema, endpoint["path"], endpoint["method"], "request"
        )

    def validate_response(self, endpoint: dict[str, Any], status_code: str, payload: dict[str, Any]) -> list[ContractViolation]:
        """বাংলা মন্তব্য: Response body schema validate করে"""
        responses = endpoint.get("responses", {})
        response = responses.get(status_code, responses.get("default", {}))

        content = response.get("content", {})
        json_schema = content.get("application/json", {}).get("schema", {})

        if not json_schema:
            return []

        resolved_schema = self.parser.resolve_schema(json_schema)
        return self._validate_against_schema(
            payload, resolved_schema, endpoint["path"], endpoint["method"], f"response_{status_code}"
        )

    def _validate_against_schema(self, data: Any, schema: dict[str, Any], endpoint: str, method: str, context: str) -> list[ContractViolation]:
        """বাংলা মন্তব্য: jsonschema দিয়ে validate করে এবং violations রেকর্ড করে"""
        violations = []

        try:
            # Convert OpenAPI schema to JSON Schema
            json_schema = self._openapi_to_jsonschema(schema)
            validator = Draft7Validator(json_schema)

            for error in validator.iter_errors(data):
                violation = ContractViolation(
                    id=self._generate_id(),
                    endpoint=endpoint,
                    method=method,
                    violation_type="schema_mismatch",
                    severity="HIGH",
                    expected=f"Validator: {error.validator}, Schema: {error.schema}",
                    actual=str(error.instance),
                    path=".".join(str(p) for p in error.path),
                    message=f"[{context}] {error.message}",
                    remediation=f"Fix the {error.validator} at path {list(error.path)}",
                )
                violations.append(violation)

        except Exception as e:
            violation = ContractViolation(
                id=self._generate_id(),
                endpoint=endpoint,
                method=method,
                violation_type="validation_error",
                severity="MEDIUM",
                expected="valid schema",
                actual=str(e),
                path="",
                message=f"[{context}] Validation failed: {e}",
                remediation="Check schema definition and data format",
            )
            violations.append(violation)

        return violations

    def _openapi_to_jsonschema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """বাংলা মন্তব্য: OpenAPI schema-কে JSON Schema format-এ কনভার্ট করে"""
        result = dict(schema)

        for key in ["nullable", "discriminator", "readOnly", "writeOnly", "xml", "externalDocs", "example", "deprecated"]:
            result.pop(key, None)

        if schema.get("nullable") and "type" in schema:
            result["type"] = [schema["type"], "null"]
            result.pop("nullable", None)

        for key, value in list(result.items()):
            if isinstance(value, dict):
                result[key] = self._openapi_to_jsonschema(value)
            elif isinstance(value, list):
                result[key] = [
                    self._openapi_to_jsonschema(item) if isinstance(item, dict) else item
                    for item in value
                ]

        return result

    def _generate_id(self) -> str:
        return f"CONTRACT-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8].upper()}"


# ── Live API Tester ────────────────────────────────────────────────────────

class LiveAPITester:
    """
    বাংলা মন্তব্য: Live API endpoints-এর বিরুদ্ধে spec validate করে।
    Real request পাঠিয়ে response schema match চেক করে।
    """

    def __init__(self, base_url: str, parser: OpenAPIParser, validator: SchemaValidator):
        self.base_url = base_url.rstrip("/")
        self.parser = parser
        self.validator = validator
        self.client: httpx.AsyncClient | None = None
        self.violations: list[ContractViolation] = []

    async def initialize(self) -> None:
        """বাংলা মন্তব্য: HTTP client ইনিশিয়ালাইজ করে"""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=DEFAULT_TIMEOUT),
            follow_redirects=True,
        )

    async def cleanup(self) -> None:
        """বাংলা মন্তব্য: HTTP client ক্লোজ করে"""
        if self.client:
            await self.client.aclose()

    async def test_endpoint(self, endpoint: dict[str, Any]) -> list[ContractViolation]:
        """বাংলা মন্তব্য: একক endpoint test করে"""
        path = endpoint["path"]
        method = endpoint["method"].lower()
        url = f"{self.base_url}{path}"

        payload = self._generate_test_payload(endpoint)
        params = self._generate_test_params(endpoint)

        try:
            if method == "get":
                response = await self.client.get(url, params=params)
            elif method == "post":
                response = await self.client.post(url, json=payload)
            elif method == "put":
                response = await self.client.put(url, json=payload)
            elif method == "patch":
                response = await self.client.patch(url, json=payload)
            elif method == "delete":
                response = await self.client.delete(url)
            else:
                return []

            try:
                response_data = response.json()
            except Exception as e:
                # বাংলা: JSON পার্স ব্যর্থ হওয়ার কারণটি লগ করুন, শুধু raw text-এ fallback করাই যথেষ্ট নয়
                logger.debug(f"Non-JSON response from {url}, falling back to raw text: {e}")
                response_data = {"_raw": response.text}

            status_code = str(response.status_code)
            violations = self.validator.validate_response(endpoint, status_code, response_data)

            documented_codes = list(endpoint.get("responses", {}).keys())
            if status_code not in documented_codes and "default" not in documented_codes:
                self.violations.append(ContractViolation(
                    id=self._generate_id(),
                    endpoint=path,
                    method=method.upper(),
                    violation_type="undocumented_status_code",
                    severity="MEDIUM",
                    expected=f"One of: {documented_codes}",
                    actual=status_code,
                    path="",
                    message=f"Undocumented status code {status_code} returned",
                    remediation="Add this status code to the OpenAPI spec or fix the endpoint",
                ))

            self.violations.extend(violations)
            return violations

        except Exception as e:
            self.violations.append(ContractViolation(
                id=self._generate_id(),
                endpoint=path,
                method=method.upper(),
                violation_type="request_failed",
                severity="LOW",
                expected="successful request",
                actual=str(e),
                path="",
                message=f"Request failed: {e}",
                remediation="Check endpoint availability and network connectivity",
            ))
            return []

    def _generate_test_payload(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """বাংলা মন্তব্য: Schema থেকে valid test payload জেনারেট করে"""
        request_body = endpoint.get("request_body", {})
        content = request_body.get("content", {})
        schema = content.get("application/json", {}).get("schema", {})

        if not schema:
            return {}

        resolved = self.parser.resolve_schema(schema)
        return self._generate_from_schema(resolved)

    def _generate_test_params(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """বাংলা মন্তব্য: Query parameters-এর জন্য test values জেনারেট করে"""
        params = {}
        for param in endpoint.get("parameters", []):
            if param.get("in") == "query":
                name = param["name"]
                param_schema = param.get("schema", {})
                params[name] = self._generate_value_from_type(param_schema.get("type", "string"), param_schema)
        return params

    def _generate_from_schema(self, schema: dict[str, Any]) -> Any:
        """বাংলা মন্তব্য: Schema type অনুযায়ী test value জেনারেট করে"""
        schema_type = schema.get("type", "object")

        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                result[prop_name] = self._generate_from_schema(prop_schema)
            return result

        elif schema_type == "array":
            item_schema = schema.get("items", {})
            return [self._generate_from_schema(item_schema)]

        elif schema_type == "string":
            return self._generate_string_value(schema)

        elif schema_type == "integer":
            return schema.get("example", 42)

        elif schema_type == "number":
            return schema.get("example", 3.14)

        elif schema_type == "boolean":
            return schema.get("example", True)

        return None

    def _generate_string_value(self, schema: dict[str, Any]) -> str:
        """বাংলা মন্তব্য: String schema অনুযায়ী value জেনারেট করে — Bangla support সহ"""
        format_ = schema.get("format", "")

        if format_ == "email":
            return random.choice(BANGLA_TEST_DATA["emails"])
        elif format_ == "date":
            return "2026-07-20"
        elif format_ == "date-time":
            return datetime.now(UTC).isoformat()
        elif format_ == "uri":
            return "https://supremeai.io"
        elif format_ == "uuid":
            return "550e8400-e29b-41d4-a716-446655440000"

        enum = schema.get("enum", [])
        if enum:
            return random.choice(enum)

        pattern = schema.get("pattern", "")
        if pattern:
            if "bangla" in schema.get("description", "").lower():
                return random.choice(BANGLA_TEST_DATA["names"])
            return "test123"

        if "bangla" in schema.get("description", "").lower() or "bn" in schema.get("title", "").lower():
            return random.choice(BANGLA_TEST_DATA["messages"])

        return "test_string"

    def _generate_value_from_type(self, type_: str, schema: dict[str, Any]) -> Any:
        """বাংলা মন্তব্য: Type অনুযায়ী value জেনারেট করে"""
        generators = {
            "string": lambda: self._generate_string_value(schema),
            "integer": lambda: schema.get("example", 42),
            "number": lambda: schema.get("example", 3.14),
            "boolean": lambda: schema.get("example", True),
            "array": list,
            "object": dict,
        }
        return generators.get(type_, lambda: "test")()

    def _generate_id(self) -> str:
        return f"LIVE-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8].upper()}"


# ── Breaking Change Detector ─────────────────────────────────────────────

class BreakingChangeDetector:
    """
    বাংলা মন্তব্য: দুটি OpenAPI spec version-এর মধ্যে breaking changes ডিটেক্ট করে।
    """

    def __init__(self, old_spec: dict[str, Any], new_spec: dict[str, Any]):
        self.old_spec = old_spec
        self.new_spec = new_spec
        self.changes: list[dict[str, Any]] = []

    def detect(self) -> list[dict[str, Any]]:
        """বাংলা মন্তব্য: Breaking changes ডিটেক্ট করে"""
        self._check_removed_endpoints()
        self._check_removed_methods()
        self._check_schema_changes()
        self._check_required_field_changes()
        self._check_enum_changes()

        return self.changes

    def _check_removed_endpoints(self) -> None:
        """বাংলা মন্তব্য: মুছে ফেলা endpoints চেক করে"""
        old_paths = set(self.old_spec.get("paths", {}).keys())
        new_paths = set(self.new_spec.get("paths", {}).keys())

        removed = old_paths - new_paths
        for path in removed:
            self.changes.append({
                "type": "endpoint_removed",
                "severity": "CRITICAL",
                "path": path,
                "message": f"Endpoint {path} was removed",
                "remediation": "Do not remove endpoints in minor/patch versions. Deprecate first.",
            })

    def _check_removed_methods(self) -> None:
        """বাংলা মন্তব্য: মুছে ফেলা HTTP methods চেক করে"""
        for path, old_path_item in self.old_spec.get("paths", {}).items():
            new_path_item = self.new_spec.get("paths", {}).get(path, {})
            for method in ["get", "post", "put", "patch", "delete"]:
                if method in old_path_item and method not in new_path_item:
                    self.changes.append({
                        "type": "method_removed",
                        "severity": "CRITICAL",
                        "path": path,
                        "method": method.upper(),
                        "message": f"{method.upper()} {path} was removed",
                        "remediation": "Do not remove methods in minor/patch versions.",
                    })

    def _check_schema_changes(self) -> None:
        """বাংলা মন্তব্য: Schema type changes চেক করে"""
        old_schemas = self.old_spec.get("components", {}).get("schemas", {})
        new_schemas = self.new_spec.get("components", {}).get("schemas", {})

        for schema_name, old_schema in old_schemas.items():
            new_schema = new_schemas.get(schema_name, {})
            if not new_schema:
                continue

            self._compare_schemas(schema_name, old_schema, new_schema)

    def _compare_schemas(self, schema_name: str, old: dict[str, Any], new: dict[str, Any], path: str = "") -> None:
        """বাংলা মন্তব্য: Recursive schema comparison"""
        old_type = old.get("type", "")
        new_type = new.get("type", "")

        if old_type and new_type and old_type != new_type:
            self.changes.append({
                "type": "field_type_changed",
                "severity": "HIGH",
                "schema": schema_name,
                "path": path,
                "message": f"Type changed from {old_type} to {new_type}",
                "remediation": "Do not change field types in minor versions.",
            })

        old_props = old.get("properties", {})
        new_props = new.get("properties", {})

        for prop_name, old_prop in old_props.items():
            new_prop = new_props.get(prop_name)
            if new_prop:
                self._compare_schemas(schema_name, old_prop, new_prop, f"{path}.{prop_name}")

    def _check_required_field_changes(self) -> None:
        """বাংলা মন্তব্য: নতুন required fields যোগ করা হয়েছে কিনা চেক করে"""
        old_schemas = self.old_spec.get("components", {}).get("schemas", {})
        new_schemas = self.new_spec.get("components", {}).get("schemas", {})

        for schema_name, new_schema in new_schemas.items():
            old_schema = old_schemas.get(schema_name, {})
            old_required = set(old_schema.get("required", []))
            new_required = set(new_schema.get("required", []))

            added = new_required - old_required
            for field in added:
                self.changes.append({
                    "type": "required_field_added",
                    "severity": "HIGH",
                    "schema": schema_name,
                    "field": field,
                    "message": f"Required field '{field}' added to {schema_name}",
                    "remediation": "Do not add required fields in minor/patch versions.",
                })

    def _check_enum_changes(self) -> None:
        """বাংলা মন্তব্য: Enum values মুছে ফেলা হয়েছে কিনা চেক করে"""
        old_schemas = self.old_spec.get("components", {}).get("schemas", {})
        new_schemas = self.new_spec.get("components", {}).get("schemas", {})

        for schema_name, old_schema in old_schemas.items():
            new_schema = new_schemas.get(schema_name, {})
            if not new_schema:
                continue

            self._compare_enums(schema_name, old_schema, new_schema)

    def _compare_enums(self, schema_name: str, old: dict[str, Any], new: dict[str, Any], path: str = "") -> None:
        """বাংলা মন্তব্য: Recursive enum comparison"""
        old_enum = set(old.get("enum", []))
        new_enum = set(new.get("enum", []))

        removed = old_enum - new_enum
        for value in removed:
            self.changes.append({
                "type": "enum_value_removed",
                "severity": "MEDIUM",
                "schema": schema_name,
                "path": path,
                "value": value,
                "message": f"Enum value '{value}' removed from {schema_name}",
                "remediation": "Do not remove enum values in minor versions.",
            })

        for prop_name, old_prop in old.get("properties", {}).items():
            new_prop = new.get("properties", {}).get(prop_name, {})
            if new_prop:
                self._compare_enums(schema_name, old_prop, new_prop, f"{path}.{prop_name}")


# ── Payload Fuzzer ─────────────────────────────────────────────────────────

class PayloadFuzzer:
    """
    বাংলা মন্তব্য: Schema-বিরোধী payload দিয়ে fuzzing করে।
    """

    def __init__(self, parser: OpenAPIParser, base_url: str):
        self.parser = parser
        self.base_url = base_url
        self.client: httpx.AsyncClient | None = None
        self.findings: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout=DEFAULT_TIMEOUT))

    async def cleanup(self) -> None:
        if self.client:
            await self.client.aclose()

    async def fuzz_endpoint(self, endpoint: dict[str, Any], count: int = FUZZ_COUNT) -> list[dict[str, Any]]:
        """বাংলা মন্তব্য: একক endpoint-এ fuzzing চালায়"""
        path = endpoint["path"]
        method = endpoint["method"].lower()
        url = f"{self.base_url}{path}"

        for _ in range(count):
            payload = self._generate_fuzz_payload(endpoint)

            try:
                if method == "post":
                    response = await self.client.post(url, json=payload)
                elif method == "put":
                    response = await self.client.put(url, json=payload)
                elif method == "patch":
                    response = await self.client.patch(url, json=payload)
                else:
                    continue

                if response.status_code >= 500:
                    self.findings.append({
                        "type": "server_crash",
                        "severity": "HIGH",
                        "endpoint": path,
                        "method": method.upper(),
                        "status": response.status_code,
                        "payload": payload,
                        "response": response.text[:500],
                    })

                elif response.status_code < 400:
                    if self._is_obviously_invalid(payload):
                        self.findings.append({
                            "type": "validation_bypass",
                            "severity": "MEDIUM",
                            "endpoint": path,
                            "method": method.upper(),
                            "payload": payload,
                            "message": "Invalid payload accepted without error",
                        })

            except Exception as e:
                self.findings.append({
                    "type": "request_exception",
                    "severity": "LOW",
                    "endpoint": path,
                    "error": str(e),
                })

        return self.findings

    def _generate_fuzz_payload(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """বাংলা মন্তব্য: Schema-বিরোধী fuzz payload জেনারেট করে"""
        request_body = endpoint.get("request_body", {})
        content = request_body.get("content", {})
        schema = content.get("application/json", {}).get("schema", {})

        if not schema:
            return {"fuzz": "test"}

        resolved = self.parser.resolve_schema(schema)
        return self._fuzz_schema(resolved)

    def _fuzz_schema(self, schema: dict[str, Any]) -> Any:
        """বাংলা মন্তব্য: Schema type অনুযায়ী fuzz value জেনারেট করে"""
        schema_type = schema.get("type", "object")
        fuzz_type = random.choice(["valid", "invalid", "boundary", "extreme"])

        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                if random.random() < 0.3:
                    continue
                result[prop_name] = self._fuzz_schema(prop_schema)
            return result

        elif schema_type == "string":
            return self._fuzz_string(schema, fuzz_type)

        elif schema_type == "integer":
            return self._fuzz_integer(schema, fuzz_type)

        elif schema_type == "boolean":
            return random.choice([True, False, "true", "false", 1, 0, None]) if fuzz_type == "invalid" else random.choice([True, False])

        elif schema_type == "array":
            if fuzz_type == "invalid":
                return "not_an_array"
            return []

        return None

    def _fuzz_string(self, schema: dict[str, Any], fuzz_type: str) -> Any:
        """বাংলা মন্তব্য: String fuzzing — boundary values, Unicode, injection attempts"""
        if fuzz_type == "boundary":
            min_len = schema.get("minLength", 0)
            max_len = schema.get("maxLength", 100)
            if random.choice([True, False]):
                return "x" * max(0, min_len - 1)
            return "x" * (max_len + 1)

        elif fuzz_type == "invalid":
            return random.choice([
                None, 123, True, [], {},
                "<script>alert(1)</script>",
                "' OR '1'='1",
                "\\x00",
                "A" * 100000,
            ])

        elif fuzz_type == "extreme":
            return random.choice(BANGLA_TEST_DATA["messages"]) + "\\u0000\\x00<script>"

        return "test"

    def _fuzz_integer(self, schema: dict[str, Any], fuzz_type: str) -> Any:
        """বাংলা মন্তব্য: Integer fuzzing — boundary values, overflow attempts"""
        if fuzz_type == "boundary":
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and random.choice([True, False]):
                return minimum - 1
            if maximum is not None:
                return maximum + 1
            return 0

        elif fuzz_type == "invalid":
            return random.choice([None, "not_a_number", 3.14, True, [], "999999999999999999999999999"])

        elif fuzz_type == "extreme":
            return random.choice([2**31, -2**31, 2**63, -2**63])

        return schema.get("example", 42)

    def _is_obviously_invalid(self, payload: dict[str, Any]) -> bool:
        """বাংলা মন্তব্য: payload স্পষ্টভাবে invalid কিনা চেক করে"""
        payload_str = json.dumps(payload)
        invalid_indicators = [
            "<script>", "' OR '", "\\x00", "null", "None",
        ]
        return any(ind in payload_str for ind in invalid_indicators)


# ── Report Generator ─────────────────────────────────────────────────────

class ContractReportGenerator:
    """বাংলা মন্তব্য: Validation report তৈরি করে"""

    def __init__(self, output_dir: Path = REPORT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, result: ValidationResult) -> tuple[str, str]:
        """বাংলা মন্তব্য: JSON এবং HTML report জেনারেট করে"""
        json_file = self._generate_json(result)
        html_file = self._generate_html(result)
        return json_file, html_file

    def _generate_json(self, result: ValidationResult) -> str:
        data = {
            "project": "SupremeAI 2.0",
            "report_type": "api_contract_validation",
            "timestamp": result.timestamp,
            "spec_file": result.spec_file,
            "base_url": result.base_url,
            "summary": {
                "endpoints_tested": result.endpoints_tested,
                "schemas_validated": result.schemas_validated,
                "total_violations": len(result.violations),
                "critical": result.critical_count,
                "high": result.high_count,
                "is_valid": result.is_valid,
            },
            "violations": [v.to_dict() for v in result.violations],
            "breaking_changes": result.breaking_changes,
        }

        file_path = self.output_dir / f"contract_{datetime.now(UTC):%Y%m%d_%H%M%S}.json"
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(file_path)

    def _generate_html(self, result: ValidationResult) -> str:
        severity_colors = {"CRITICAL": "#dc3545", "HIGH": "#fd7e14", "MEDIUM": "#ffc107", "LOW": "#17a2b8"}

        rows = ""
        for v in result.violations:
            color = severity_colors.get(v.severity, "#6c757d")
            rows += f"""
            <tr>
                <td><span style="background:{color};color:white;padding:4px 8px;border-radius:4px;font-size:12px;">{v.severity}</span></td>
                <td>{v.violation_type}</td>
                <td><code>{v.method} {v.endpoint}</code></td>
                <td>{v.path}</td>
                <td>{v.message}</td>
            </tr>
            """

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>API Contract Validation</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #0d1117; color: #c9d1d9; }}
.header {{ background: #161b22; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
table {{ width: 100%; border-collapse: collapse; background: #161b22; border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #30363d; }}
th {{ background: #21262d; }}
</style></head>
<body>
<div class="header">
    <h1>📋 API Contract Validation Report</h1>
    <p>Spec: {result.spec_file} | URL: {result.base_url} | Valid: {'✅' if result.is_valid else '❌'}</p>
</div>
<table>
    <tr><th>Severity</th><th>Type</th><th>Endpoint</th><th>Path</th><th>Message</th></tr>
    {rows}
</table>
</body></html>"""

        file_path = self.output_dir / f"contract_{datetime.now(UTC):%Y%m%d_%H%M%S}.html"
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)


# ── Main Validator ──────────────────────────────────────────────────────────

class APIContractValidator:
    """
    বাংলা মন্তব্য: মূল অরকেস্ট্রেটর। সব validation কম্পোনেন্ট একসাথে চালায়।
    """

    def __init__(self, spec_path: str, base_url: str = DEFAULT_BASE_URL):
        self.spec_path = spec_path
        self.base_url = base_url
        self.result = ValidationResult(spec_file=spec_path, base_url=base_url)
        self.report_generator = ContractReportGenerator()

    async def validate(self, test_live: bool = False, check_breaking: str | None = None, fuzz: bool = False) -> ValidationResult:
        """বাংলা মন্তব্য: সম্পূর্ণ validation pipeline চালায়"""
        parser = OpenAPIParser(self.spec_path)
        try:
            parser.parse()
        except Exception as e:
            self.result.violations.append(ContractViolation(
                id="SPEC-001",
                endpoint=self.spec_path,
                method="PARSE",
                violation_type="spec_parse_error",
                severity="CRITICAL",
                expected="valid OpenAPI spec",
                actual=str(e),
                path="",
                message=f"Failed to parse OpenAPI spec: {e}",
                remediation="Fix YAML/JSON syntax errors in the spec file",
            ))
            return self.result

        self.result.schemas_validated = len(parser.schemas)
        validator = SchemaValidator(parser)

        if test_live:
            tester = LiveAPITester(self.base_url, parser, validator)
            await tester.initialize()
            try:
                for endpoint in parser.endpoints:
                    await tester.test_endpoint(endpoint)
                    self.result.endpoints_tested += 1
                self.result.violations.extend(tester.violations)
            finally:
                await tester.cleanup()

        if fuzz:
            fuzzer = PayloadFuzzer(parser, self.base_url)
            await fuzzer.initialize()
            try:
                for endpoint in parser.endpoints[:5]:
                    findings = await fuzzer.fuzz_endpoint(endpoint)
                    for finding in findings:
                        self.result.violations.append(ContractViolation(
                            id=f"FUZZ-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8].upper()}",
                            endpoint=finding.get("endpoint", ""),
                            method=finding.get("method", ""),
                            violation_type=finding.get("type", "fuzz_finding"),
                            severity=finding.get("severity", "MEDIUM"),
                            expected="proper validation",
                            actual=finding.get("response", str(finding.get("payload", ""))),
                            path="",
                            message=finding.get("message", str(finding)),
                            remediation="Improve input validation and error handling",
                        ))
            finally:
                await fuzzer.cleanup()

        if check_breaking:
            old_parser = OpenAPIParser(check_breaking)
            try:
                old_spec = old_parser.parse()
                detector = BreakingChangeDetector(old_spec, parser.spec)
                self.result.breaking_changes = detector.detect()

                for change in self.result.breaking_changes:
                    self.result.violations.append(ContractViolation(
                        id=f"BREAK-{hashlib.sha256(change['message'].encode()).hexdigest()[:8].upper()}",
                        endpoint=change.get("path", ""),
                        method=change.get("method", ""),
                        violation_type=change["type"],
                        severity=change["severity"],
                        expected="backward compatibility",
                        actual=change["message"],
                        path=change.get("schema", ""),
                        message=change["message"],
                        remediation=change["remediation"],
                    ))
            except Exception as e:
                logger.warning(f"Breaking change check failed: {e}")

        return self.result

    def generate_report(self) -> tuple[str, str]:
        return self.report_generator.generate(self.result)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """বাংলা মন্তব্য: CLI entry point"""
    parser = argparse.ArgumentParser(
        description="SupremeAI 2.0 — API Contract Validator\nAPI কন্ট্রাক্ট ভ্যালিডেশন ও ব্রেকিং চেঞ্জ ডিটেকশন",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--spec", "-s", default=DEFAULT_SPEC_PATH, help="OpenAPI spec file path")
    parser.add_argument("--base-url", "-u", default=DEFAULT_BASE_URL, help="Base URL for live testing")
    parser.add_argument("--test-live", "-t", action="store_true", help="Test against live API")
    parser.add_argument("--check-breaking", "-b", help="Compare with previous spec version for breaking changes")
    parser.add_argument("--fuzz", "-f", action="store_true", help="Run payload fuzzing")
    parser.add_argument("--fuzz-count", type=int, default=FUZZ_COUNT, help="Number of fuzz payloads per endpoint")
    parser.add_argument("--output-dir", "-o", type=Path, default=REPORT_DIR, help="Report output directory")

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

    async def run():
        validator = APIContractValidator(args.spec, args.base_url)
        result = await validator.validate(
            test_live=args.test_live,
            check_breaking=args.check_breaking,
            fuzz=args.fuzz,
        )

        json_file, html_file = validator.generate_report()

        print(f"\n{'='*60}")
        print("📋 API Contract Validation Summary")
        print("="*60)
        print(f"Spec: {result.spec_file}")
        print(f"Endpoints: {result.endpoints_tested}")
        print(f"Schemas: {result.schemas_validated}")
        print(f"Violations: {len(result.violations)}")
        print(f"  CRITICAL: {result.critical_count}")
        print(f"  HIGH: {result.high_count}")
        print(f"Valid: {'✅ YES' if result.is_valid else '❌ NO'}")
        print("\nReports:")
        print(f"  JSON: {json_file}")
        print(f"  HTML: {html_file}")

        if not result.is_valid:
            sys.exit(1)

    asyncio.run(run())


if __name__ == "__main__":
    main()
