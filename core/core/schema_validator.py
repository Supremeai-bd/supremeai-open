from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from core.logging_config import logger

T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(Exception):
    def __init__(self, model_name: str, errors: list[dict[str, Any]]):
        self.model_name = model_name
        self.errors = errors
        msg = f"Validation failed for {model_name}: {errors}"
        super().__init__(msg)


class SchemaValidator:
    def __init__(self) -> None:
        self._models: dict[str, type[BaseModel]] = {}

    def register(self, name: str, model: type[BaseModel]) -> None:
        self._models[name] = model

    def validate(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if name not in self._models:
            raise KeyError(f"Schema '{name}' is not registered.")
        model_cls = self._models[name]
        try:
            instance = model_cls.model_validate(payload)
            return {"status": "ok", "schema": name, "data": instance.model_dump()}
        except ValidationError as exc:
            errors = [
                {
                    "loc": ".".join(str(loc) for loc in error["loc"]),
                    "msg": error["msg"],
                    "input_type": error.get("input_type"),
                    "type": error["type"],
                }
                for error in exc.errors()
            ]
            logger.error(f"Validation failed for {name}: {errors}")
            raise SchemaValidationError(name, errors) from exc

    def _prepare_for_retry(
        self, name: str, payload: dict[str, Any], attempt: int
    ) -> dict[str, Any]:
        last = self.try_parse(name, payload)
        if last.get("status") == "ok":
            return last
        return {
            "status": "retry",
            "schema": name,
            "attempt": attempt,
            "last_error": str(last.get("error")),
        }

    def validate_with_retry(
        self, name: str, payload: dict[str, Any], max_attempts: int = 2
    ) -> dict[str, Any]:
        last = self.try_parse(name, payload)
        if last.get("status") == "ok":
            return last
        for attempt in range(1, max_attempts + 1):
            last = self._prepare_for_retry(name, payload, attempt)
            if last.get("status") == "ok":
                return last
        return {
            "status": "error",
            "schema": name,
            "error": str(last.get("last_error")),
            "attempts": max_attempts,
        }

    def try_parse(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.validate(name, payload)
        except (SchemaValidationError, KeyError) as exc:
            return {"status": "error", "schema": name, "error": str(exc)}


validator = SchemaValidator()
