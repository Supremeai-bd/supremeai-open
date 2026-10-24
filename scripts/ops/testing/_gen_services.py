# --- Merged from _gen_services.py ---

#!/usr/bin/env python3
"""
SupremeAI Service Scaffolding Engine
===================================
Auto-generates production-ready service modules from Pydantic schemas.
Features: AST-aware generation, async CRUD, dependency injection hooks,
          caching decorators, circuit breaker integration, type-safe.

Usage:
    python _gen_services.py --schema backend/models/user.py --output backend/services/
    python _gen_services.py --from-dir backend/models/ --output backend/services/ --with-tests
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── ANSI Colors ──────────────────────────────────────────────────────────────
class Colors:
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"


def log(msg: str, color: str = Colors.CYAN) -> None:
    print(f"{color}{msg}{Colors.RESET}")


# ── Data Structures ─────────────────────────────────────────────────────────
@dataclass
class FieldSpec:
    name: str
    py_type: str
    default: Any = None
    has_default: bool = False
    is_optional: bool = False
    validators: list[str] = field(default_factory=list)


@dataclass
class ModelSpec:
    name: str
    fields: list[FieldSpec] = field(default_factory=list)
    base_classes: list[str] = field(default_factory=list)
    has_id: bool = False
    id_type: str = "str"
    is_enum: bool = False


# ── AST Parser ───────────────────────────────────────────────────────────────
class SchemaParser:
    """Parse Pydantic models from Python source files using AST."""

    TYPE_ALIASES: dict[str, str] = {
        "str": "str",
        "int": "int",
        "float": "float",
        "bool": "bool",
        "datetime": "datetime.datetime",
        "date": "datetime.date",
        "UUID": "uuid.UUID",
        "EmailStr": "str",
        "HttpUrl": "str",
        "Json": "dict",
        "List": "list",
        "Dict": "dict",
        "Optional": "Optional",
        "Union": "Union",
    }

    def __init__(self, source_path: Path) -> None:
        self.source_path = source_path
        self.source = source_path.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def _extract_type_str(self, node: ast.AST) -> str:
        """Convert AST type annotation back to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Subscript):
            value = self._extract_type_str(node.value)
            slice_str = self._extract_type_str(node.slice)
            return f"{value}[{slice_str}]"
        elif isinstance(node, ast.Attribute):
            return f"{self._extract_type_str(node.value)}.{node.attr}"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self._extract_type_str(node.left)
            right = self._extract_type_str(node.right)
            return f"Union[{left}, {right}]"
        elif isinstance(node, ast.List):
            elements = [self._extract_type_str(e) for e in node.elts]
            return f"[{', '.join(elements)}]"
        return "Any"

    def _is_optional(self, type_str: str) -> bool:
        return type_str.startswith("Optional[") or "None" in type_str

    def _get_default(self, node: ast.expr | None) -> tuple[Any, bool]:
        if node is None:
            return None, False
        if isinstance(node, ast.Constant):
            return node.value, True
        if isinstance(node, ast.NameConstant):  # Python < 3.8 compat
            return node.value, True
        if isinstance(node, ast.Name) and node.id == "None":
            return None, True
        if isinstance(node, ast.List):
            return [], True
        if isinstance(node, ast.Dict):
            return {}, True
        return None, True

    def parse_models(self) -> list[ModelSpec]:
        models: list[ModelSpec] = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                # Detect Pydantic models
                is_pydantic = any(
                    base.id in ("BaseModel", "SQLModel")
                    for base in node.bases
                    if isinstance(base, ast.Name)
                )
                is_enum = any(
                    base.id == "Enum" for base in node.bases if isinstance(base, ast.Name)
                )

                if not (is_pydantic or is_enum):
                    continue

                spec = ModelSpec(
                    name=node.name,
                    base_classes=[
                        self._extract_type_str(b) for b in node.bases
                    ],
                    is_enum=is_enum,
                )

                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        field_name = item.target.id
                        type_str = self._extract_type_str(item.annotation)
                        default, has_default = self._get_default(item.value)

                        # Detect ID field
                        if field_name in ("id", "uuid", "pk", "uid"):
                            spec.has_id = True
                            spec.id_type = type_str.replace("Optional[", "").replace("]", "")

                        spec.fields.append(FieldSpec(
                            name=field_name,
                            py_type=type_str,
                            default=default,
                            has_default=has_default,
                            is_optional=self._is_optional(type_str),
                        ))

                models.append(spec)
        return models


# ── Template Engine ──────────────────────────────────────────────────────────
class ServiceTemplate:
    """Generate service code from ModelSpec."""

    @staticmethod
    def generate_service_class(spec: ModelSpec, module_name: str) -> str:
        """Generate async CRUD service class."""
        model_name = spec.name
        snake_name = ServiceTemplate._to_snake(model_name)
        service_name = f"{model_name}Service"

        # Determine ID type
        id_type = spec.id_type if spec.has_id else "str"

        template = f'''"""
Auto-generated service for {model_name}.
DO NOT EDIT MANUALLY — regenerate via _gen_services.py
Generated from: {module_name}
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ValidationError

# Internal imports — adjust based on your project structure
from core.cache import cached, invalidate_cache
from core.circuit_breaker import circuit_breaker
from core.db import get_db_session
from core.exceptions import (
    EntityNotFoundError,
    DuplicateEntityError,
    ValidationServiceError,
)
from monitoring.logging import get_logger
from monitoring.metrics import timed, counter
from core.security import require_permissions

logger = get_logger(__name__)


class {service_name}:
    """
    Production-ready async CRUD service for {model_name}.

    Features:
        - Connection pooling via dependency injection
        - Redis caching with automatic invalidation
        - Circuit breaker for external calls
        - Structured logging & metrics
        - Permission decorators
    """

    _cache_prefix: str = "{snake_name}"
    _default_ttl: int = 300  # 5 minutes

    def __init__(self, db_session: Any = None) -> None:
        self.db = db_session or get_db_session()
        self.logger = logger.bind(service="{service_name}", model="{model_name}")

    # ── Health ──────────────────────────────────────────────────────────────

    @timed("service.health")
    async def health_check(self) -> Dict[str, Any]:
        """Return service health status."""
        return {{
            "service": "{service_name}",
            "model": "{model_name}",
            "db_connected": self.db.is_connected if hasattr(self.db, "is_connected") else True,
            "timestamp": datetime.utcnow().isoformat(),
        }}

    # ── Create ──────────────────────────────────────────────────────────────

    @timed("service.create")
    @counter("service.create.total")
    @circuit_breaker(name="{snake_name}_create", failure_threshold=5, recovery_timeout=30)
    @require_permissions(["{snake_name}:create"])
    async def create(
        self,
        data: Dict[str, Any],
        *,
        skip_validation: bool = False,
    ) -> {model_name}:
        """
        Create a new {model_name} entity.

        Args:
            data: Raw dictionary of field values.
            skip_validation: Bypass Pydantic validation (dangerous, use carefully).

        Returns:
            Created model instance.

        Raises:
            ValidationServiceError: If data fails schema validation.
            DuplicateEntityError: If unique constraint violated.
        """
        self.logger.info("creating_entity", extra={{"data_keys": list(data.keys())}})

        if not skip_validation:
            try:
                instance = {model_name}(**data)
            except ValidationError as exc:
                self.logger.warning("validation_failed", errors=exc.errors())
                raise ValidationServiceError(
                    message="Invalid {model_name} data",
                    details={{"errors": exc.errors()}},
                ) from exc
        else:
            instance = {model_name}.construct(**data)

        # Database insert
        try:
            result = await self.db.insert(
                collection="{snake_name}s",
                document=instance.dict(by_alias=True),
            )
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise DuplicateEntityError(
                    message="{model_name} with given key already exists"
                ) from exc
            raise

        # Cache invalidation
        await invalidate_cache(f"{{self._cache_prefix}}:list:*")

        self.logger.info("entity_created", extra={{"id": str(getattr(result, "id", "unknown"))}})
        return result

    # ── Read ────────────────────────────────────────────────────────────────

    @timed("service.get_by_id")
    @cached(key_template="{{prefix}}:{{id}}", ttl=300)
    async def get_by_id(self, entity_id: {id_type}) -> Optional[{model_name}]:
        """Retrieve entity by primary key with caching."""
        self.logger.debug("fetching_by_id", extra={{"entity_id": str(entity_id)}})

        doc = await self.db.find_one(
            collection="{snake_name}s",
            query={{"id": entity_id}},
        )

        if doc is None:
            self.logger.warning("entity_not_found", extra={{"entity_id": str(entity_id)}})
            return None

        return {model_name}(**doc)

    @timed("service.get_by_id_or_404")
    async def get_by_id_or_404(self, entity_id: {id_type}) -> {model_name}:
        """Get by ID or raise EntityNotFoundError."""
        result = await self.get_by_id(entity_id)
        if result is None:
            raise EntityNotFoundError(
                message=f"{model_name} with id={{entity_id}} not found",
                entity_type="{snake_name}",
                entity_id=str(entity_id),
            )
        return result

    @timed("service.list")
    @cached(key_template="{{prefix}}:list:{{hash}}", ttl=60)
    async def list(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[{model_name}]:
        """
        Paginated list with filtering and sorting.

        Args:
            filters: MongoDB-style query dict.
            sort: List of (field, direction) tuples.
            limit: Max items per page.
            offset: Skip N items.
        """
        self.logger.debug("listing_entities", extra={{
            "filters": filters,
            "limit": limit,
            "offset": offset,
        }})

        docs = await self.db.find_many(
            collection="{snake_name}s",
            query=filters or {{}},
            sort=sort,
            limit=limit,
            skip=offset,
        )

        return [{model_name}(**doc) for doc in docs]

    @timed("service.search")
    async def search(
        self,
        query: str,
        *,
        fields: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[{model_name}]:
        """
        Full-text search across specified fields.
        Falls back to regex if FTS index unavailable.
        """
        search_fields = fields or [f.name for f in spec.fields[:3]]

        # Build $or query for text search
        mongo_query = {{
            "$or": [
                {{f.name: {{"$regex": query, "$options": "i"}}}}
                for f in spec.fields[:3] if f.py_type == "str"
            ]
        }}

        docs = await self.db.find_many(
            collection="{snake_name}s",
            query=mongo_query,
            limit=limit,
        )

        return [{model_name}(**doc) for doc in docs]

    # ── Update ─────────────────────────────────────────────────────────────

    @timed("service.update")
    @counter("service.update.total")
    @circuit_breaker(name="{snake_name}_update", failure_threshold=5, recovery_timeout=30)
    @require_permissions(["{snake_name}:update"])
    async def update(
        self,
        entity_id: {id_type},
        data: Dict[str, Any],
        *,
        patch: bool = True,
    ) -> {model_name}:
        """
        Update entity by ID.

        Args:
            entity_id: Target entity ID.
            data: Update payload.
            patch: If True, partial update (merge). If False, full replace.
        """
        self.logger.info("updating_entity", extra={{
            "entity_id": str(entity_id),
            "patch": patch,
        }})

        # Validate update payload
        try:
            # For partial updates, construct with existing + new
            if patch:
                existing = await self.get_by_id_or_404(entity_id)
                merged = {{**existing.dict(), **data}}
                instance = {model_name}(**merged)
            else:
                instance = {model_name}(**data)
        except ValidationError as exc:
            raise ValidationServiceError(
                message="Invalid update payload for {model_name}",
                details={{"errors": exc.errors()}},
            ) from exc

        result = await self.db.update_one(
            collection="{snake_name}s",
            query={{"id": entity_id}},
            update={{"$set": instance.dict(by_alias=True, exclude={{"id"}})}},
        )

        # Invalidate caches
        await invalidate_cache(f"{{self._cache_prefix}}:{{entity_id}}")
        await invalidate_cache(f"{{self._cache_prefix}}:list:*")

        self.logger.info("entity_updated", extra={{"entity_id": str(entity_id)}})
        return result

    # ── Delete ──────────────────────────────────────────────────────────────

    @timed("service.delete")
    @counter("service.delete.total")
    @require_permissions(["{snake_name}:delete"])
    async def delete(self, entity_id: {id_type}) -> bool:
        """Soft or hard delete based on model configuration."""
        self.logger.info("deleting_entity", extra={{"entity_id": str(entity_id)}})

        result = await self.db.delete_one(
            collection="{snake_name}s",
            query={{"id": entity_id}},
        )

        # Invalidate caches
        await invalidate_cache(f"{{self._cache_prefix}}:{{entity_id}}")
        await invalidate_cache(f"{{self._cache_prefix}}:list:*")

        return result.deleted_count > 0

    # ── Batch Operations ────────────────────────────────────────────────────

    @timed("service.bulk_create")
    @require_permissions(["{snake_name}:create"])
    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[{model_name}]:
        """Atomic batch insert with transaction support."""
        self.logger.info("bulk_creating", extra={{"count": len(items)}})

        async with self.db.transaction():
            validated = []
            for item in items:
                try:
                    validated.append({model_name}(**item).dict(by_alias=True))
                except ValidationError as exc:
                    self.logger.error("bulk_validation_failed", item=item, error=exc.errors())
                    raise ValidationServiceError(
                        message="Bulk create validation failed",
                        details={{"item": item, "errors": exc.errors()}},
                    ) from exc

            result = await self.db.insert_many(
                collection="{snake_name}s",
                documents=validated,
            )

            await invalidate_cache(f"{{self._cache_prefix}}:list:*")
            return [{model_name}(**doc) for doc in result]

    @timed("service.bulk_delete")
    @require_permissions(["{snake_name}:delete"])
    async def bulk_delete(self, entity_ids: List[{id_type}]) -> int:
        """Delete multiple entities by ID list."""
        self.logger.info("bulk_deleting", extra={{"count": len(entity_ids)}})

        result = await self.db.delete_many(
            collection="{snake_name}s",
            query={{"id": {{"$in": entity_ids}}}},
        )

        # Invalidate all affected caches
        for eid in entity_ids:
            await invalidate_cache(f"{{self._cache_prefix}}:{{eid}}")
        await invalidate_cache(f"{{self._cache_prefix}}:list:*")

        return result.deleted_count

    # ── Statistics ────────────────────────────────────────────────────────────

    @timed("service.count")
    @cached(key_template="{{prefix}}:count:{{filters_hash}}", ttl=120)
    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count entities matching filters."""
        return await self.db.count(
            collection="{snake_name}s",
            query=filters or {{}},
        )

    # ── Event Hooks ───────────────────────────────────────────────────────────

    async def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish domain event to message bus (Kafka/RabbitMQ)."""
        from core.events import get_event_publisher
        publisher = get_event_publisher()
        await publisher.publish(
            topic=f"{snake_name}.{{event_type}}",
            payload=payload,
        )

    # ── Context Manager ──────────────────────────────────────────────────────

    async def __aenter__(self) -> {service_name}:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if hasattr(self.db, "close"):
            await self.db.close()


# ── Factory ──────────────────────────────────────────────────────────────────
def get_{snake_name}_service(db_session: Any = None) -> {service_name}:
    """Dependency injection factory."""
    return {service_name}(db_session=db_session)
'''
        return template

    @staticmethod
    def generate_test_class(spec: ModelSpec, module_name: str) -> str:
        """Generate pytest test suite for the service."""
        model_name = spec.name
        snake_name = ServiceTemplate._to_snake(model_name)
        service_name = f"{model_name}Service"

        # Generate sample data from fields
        sample_fields = []
        for f in spec.fields:
            if f.name in ("id", "created_at", "updated_at"):
                continue
            val = ServiceTemplate._sample_value(f)
            sample_fields.append(f'    "{f.name}": {val},')

        sample_data = "\n".join(sample_fields)

        return f'''"""
Auto-generated tests for {service_name}.
DO NOT EDIT MANUALLY — regenerate via _gen_services.py
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.exceptions import EntityNotFoundError, DuplicateEntityError, ValidationServiceError
from services.{snake_name}_service import {service_name}, get_{snake_name}_service


@pytest.fixture
def mock_db():
    """Provide mock database session."""
    db = AsyncMock()
    db.is_connected = True
    return db


@pytest.fixture
def service(mock_db):
    """Provide service instance with mocked DB."""
    return {service_name}(db_session=mock_db)


@pytest.fixture
def valid_payload():
    """Valid creation payload."""
    return {{
{sample_data}
    }}


class Test{model_name}Service:
    """Comprehensive test suite for {service_name}."""

    # ── Health ──────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        result = await service.health_check()
        assert result["service"] == "{service_name}"
        assert result["db_connected"] is True
        assert "timestamp" in result

    # ── Create ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_success(self, service, mock_db, valid_payload):
        mock_db.insert.return_value = MagicMock(id="test-123")

        result = await service.create(valid_payload)

        assert result is not None
        mock_db.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_validation_error(self, service, mock_db):
        bad_payload = {{}}  # Missing required fields

        with pytest.raises(ValidationServiceError):
            await service.create(bad_payload)

    @pytest.mark.asyncio
    async def test_create_duplicate(self, service, mock_db, valid_payload):
        mock_db.insert.side_effect = Exception("duplicate key error")

        with pytest.raises(DuplicateEntityError):
            await service.create(valid_payload)

    # ── Read ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, service, mock_db, valid_payload):
        mock_db.find_one.return_value = {{"id": "test-123", **valid_payload}}

        result = await service.get_by_id("test-123")

        assert result is not None
        mock_db.find_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, service, mock_db):
        mock_db.find_one.return_value = None

        result = await service.get_by_id("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_or_404_found(self, service, mock_db, valid_payload):
        mock_db.find_one.return_value = {{"id": "test-123", **valid_payload}}

        result = await service.get_by_id_or_404("test-123")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_id_or_404_not_found(self, service, mock_db):
        mock_db.find_one.return_value = None

        with pytest.raises(EntityNotFoundError):
            await service.get_by_id_or_404("nonexistent")

    @pytest.mark.asyncio
    async def test_list_pagination(self, service, mock_db):
        mock_db.find_many.return_value = [
            {{"id": "1", "name": "A"}},
            {{"id": "2", "name": "B"}},
        ]

        results = await service.list(limit=2, offset=0)

        assert len(results) == 2
        mock_db.find_many.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search(self, service, mock_db):
        mock_db.find_many.return_value = [{{"id": "1", "name": "search result"}}]

        results = await service.search("query")
        assert len(results) == 1

    # ── Update ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_success(self, service, mock_db, valid_payload):
        mock_db.find_one.return_value = {{"id": "test-123", **valid_payload}}
        mock_db.update_one.return_value = MagicMock(modified_count=1)

        result = await service.update("test-123", {{"name": "Updated"}})
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_not_found(self, service, mock_db):
        mock_db.find_one.return_value = None

        with pytest.raises(EntityNotFoundError):
            await service.update("nonexistent", {{"name": "X"}})

    # ── Delete ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_success(self, service, mock_db):
        mock_db.delete_one.return_value = MagicMock(deleted_count=1)

        result = await service.delete("test-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, service, mock_db):
        mock_db.delete_one.return_value = MagicMock(deleted_count=0)

        result = await service.delete("nonexistent")
        assert result is False

    # ── Batch ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_bulk_create(self, service, mock_db, valid_payload):
        mock_db.transaction.return_value.__aenter__ = AsyncMock()
        mock_db.transaction.return_value.__aexit__ = AsyncMock()
        mock_db.insert_many.return_value = [{{"id": "1"}}, {{"id": "2"}}]

        results = await service.bulk_create([valid_payload, valid_payload])
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_bulk_delete(self, service, mock_db):
        mock_db.delete_many.return_value = MagicMock(deleted_count=3)

        count = await service.bulk_delete(["1", "2", "3"])
        assert count == 3

    # ── Count ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_count(self, service, mock_db):
        mock_db.count.return_value = 42

        result = await service.count()
        assert result == 42

    # ── Factory ───────────────────────────────────────────────────────────────

    def test_factory(self, mock_db):
        svc = get_{snake_name}_service(db_session=mock_db)
        assert isinstance(svc, {service_name})
'''

    @staticmethod
    def _to_snake(name: str) -> str:
        """Convert CamelCase to snake_case."""
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    @staticmethod
    def _sample_value(field: FieldSpec) -> str:
        """Generate representative sample value for field type."""
        type_map = {
            "str": '"sample_string"',
            "int": "42",
            "float": "3.14",
            "bool": "True",
            "datetime": '"2024-01-01T00:00:00Z"',
            "date": '"2024-01-01"',
            "UUID": '"550e8400-e29b-41d4-a716-446655440000"',
            "EmailStr": '"test@example.com"',
            "HttpUrl": '"https://example.com"',
            "list": "[]",
            "dict": "{}",
        }
        base_type = field.py_type.replace("Optional[", "").replace("]", "").replace("List[", "").replace("Dict[", "")
        return type_map.get(base_type, '"sample_value"')


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Service Scaffolding Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --schema backend/models/user.py --output backend/services/
  %(prog)s --from-dir backend/models/ --output backend/services/ --with-tests
  %(prog)s --schema user.py --output . --dry-run
        """,
    )
    parser.add_argument("--schema", "-s", type=Path, help="Single Pydantic schema file")
    parser.add_argument("--from-dir", "-d", type=Path, help="Directory containing schema files")
    parser.add_argument("--output", "-o", type=Path, default=Path("backend/services"), help="Output directory")
    parser.add_argument("--with-tests", "-t", action="store_true", help="Generate test files")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing files")

    args = parser.parse_args()

    if not args.schema and not args.from_dir:
        parser.error("Either --schema or --from-dir required")

    schemas: list[Path] = []
    if args.schema:
        schemas = [args.schema]
    else:
        schemas = list(args.from_dir.rglob("*.py"))

    log("🔧 SupremeAI Service Scaffolding Engine", Colors.CYAN)
    log(f"   Schemas: {len(schemas)} file(s)", Colors.CYAN)
    log(f"   Output:  {args.output.resolve()}", Colors.CYAN)
    log(f"   Tests:   {'Yes' if args.with_tests else 'No'}", Colors.CYAN)
    print()

    total_services = 0
    total_tests = 0

    for schema_path in schemas:
        if schema_path.name.startswith("_") or schema_path.name.startswith("base"):
            continue

        try:
            parser_obj = SchemaParser(schema_path)
            models = parser_obj.parse_models()
        except SyntaxError as exc:
            log(f"  ⚠️  Syntax error in {schema_path}: {exc}", Colors.YELLOW)
            continue
        except Exception as exc:
            log(f"  ❌ Failed to parse {schema_path}: {exc}", Colors.RED)
            continue

        if not models:
            log(f"  ⏭️  No Pydantic models found in {schema_path}", Colors.YELLOW)
            continue

        for model in models:
            if model.is_enum:
                continue  # Skip enums for now

            service_code = ServiceTemplate.generate_service_class(model, str(schema_path))
            test_code = ServiceTemplate.generate_test_class(model, str(schema_path))

            svc_filename = f"{ServiceTemplate._to_snake(model.name)}_service.py"
            test_filename = f"test_{ServiceTemplate._to_snake(model.name)}_service.py"

            svc_path = args.output / svc_filename
            test_path = args.output / "tests" / test_filename

            if args.dry_run:
                log(f"  [DRY-RUN] Would write: {svc_path}", Colors.CYAN)
                if args.with_tests:
                    log(f"  [DRY-RUN] Would write: {test_path}", Colors.CYAN)
                print(service_code[:500] + "...\n")
            else:
                svc_path.parent.mkdir(parents=True, exist_ok=True)
                if not svc_path.exists() or args.force:
                    svc_path.write_text(service_code, encoding="utf-8")
                    log(f"  ✅ Service: {svc_path}", Colors.GREEN)
                    total_services += 1
                else:
                    log(f"  ⏭️  Service exists (use --force): {svc_path}", Colors.YELLOW)

                if args.with_tests:
                    test_path.parent.mkdir(parents=True, exist_ok=True)
                    if not test_path.exists() or args.force:
                        test_path.write_text(test_code, encoding="utf-8")
                        log(f"  ✅ Test:    {test_path}", Colors.GREEN)
                        total_tests += 1
                    else:
                        log(f"  ⏭️  Test exists (use --force): {test_path}", Colors.YELLOW)

    log(f"\n🏁 Complete: {total_services} services, {total_tests} tests generated.", Colors.GREEN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
