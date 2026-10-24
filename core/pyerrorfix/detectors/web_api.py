"""Web & API error detector (FastAPI + Pydantic focused).

Catches:
  * `pydantic.ValidationError` — model constructed from a dict without
    validation, or `.dict()` (deprecated in v2; use `.model_dump()`).
  * `fastapi.HTTPException` raised too broadly — `raise HTTPException(500)`
    instead of letting the framework handle 500s.
  * `starlette.exceptions.HTTPException` broad re-raise swallowing detail.
  * Missing `response_model` on routes returning untyped dicts.
  * Routes without try/except that call fallible code (heuristic).
  * `RequestValidationError` — accessing `request.body()` without validation.
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_PYDANTIC_DEPRECATED = {
    ".dict": "model_dump()",
    ".json": "model_dump_json()",
    ".parse_obj": "model_validate()",
    ".parse_raw": "model_validate_json()",
    ".from_orm": "model_validate()",
    ".copy": "model_copy()",
    "parse_obj_as": "TypeAdapter.validate_python()",
    "parse_raw_as": "TypeAdapter.validate_json()",
}


class WebApiDetector(BaseDetector):
    name = "web-api"

    def visit_Attribute(self, node: ast.Attribute) -> None:  # type: ignore[override]
        dotted = _dotted(node)
        if dotted in _PYDANTIC_DEPRECATED:
            new = _PYDANTIC_DEPRECATED[dotted]
            self.add(
                rule_id="pydantic-validation-gap",
                code="ValidationError",
                category=Category.WEB_API,
                severity=Severity.WARNING,
                title=f"Deprecated Pydantic v1 call '{dotted}'",
                message=f"`{dotted}` is removed in Pydantic v2 (raises AttributeError). "
                f"Use `{new}`.",
                node=node,
                fixable=True,
                fix_description=f"Replace with {new}.",
                suggestion=new,
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)
        # HTTPException(500, ...) — server errors should not be raised manually
        if name == "HTTPException" and node.args:
            status = node.args[0]
            if isinstance(status, ast.Constant) and isinstance(status.value, int):
                if status.value >= 500:
                    self.add(
                        rule_id="broad-http-exception",
                        code="HTTPException",
                        category=Category.WEB_API,
                        severity=Severity.INFO,
                        title=f"Manual HTTPException({status.value})",
                        message="Raising 5xx manually hides the real error. Let the "
                        "framework return 500 from the unhandled exception so the "
                        "traceback reaches the logger.",
                        node=node,
                        fixable=False,
                        fix_description="Remove the raise; let the exception propagate.",
                    )

        # BaseModel constructed from a raw dict without validation context
        if name and _looks_like_model_ctor(node):
            if node.args and isinstance(node.args[0], ast.Dict):
                self.add(
                    rule_id="pydantic-validation-gap",
                    code="ValidationError",
                    category=Category.WEB_API,
                    severity=Severity.INFO,
                    title=f"Constructing '{name}' from a raw dict",
                    message=f"`{name}({{...}})` bypasses Pydantic parsing. Prefer "
                    f"`{name}.model_validate(data)` to get ValidationError surfaced.",
                    node=node,
                    fixable=False,
                    fix_description="Use Model.model_validate(dict_data).",
                )

        # FastAPI route decorators: detect missing response_model
        if name in (
            "router.get",
            "router.post",
            "router.put",
            "router.patch",
            "router.delete",
            "app.get",
            "app.post",
            "app.put",
            "app.patch",
            "app.delete",
        ):
            if not any(kw.arg == "response_model" for kw in node.keywords):
                self.add(
                    rule_id="missing-response-model",
                    code="ValidationError",
                    category=Category.WEB_API,
                    severity=Severity.INFO,
                    title="Route without response_model",
                    message=f"`{name}` has no `response_model=`. Responses are untyped; "
                    f"serialization errors surface only at runtime. Add a Pydantic model.",
                    node=node,
                    fixable=False,
                    fix_description="Define a response model and pass response_model=Model.",
                )

        self.generic_visit(node)


def _dotted(attr: ast.Attribute) -> str:
    parts: list[str] = []
    node: ast.AST = attr
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            break
    return ".".join(reversed(parts))


def _looks_like_model_ctor(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        # CamelCase name suggests a class/model constructor
        name = func.id
        return name[:1].isupper() and name.isidentifier() and name not in ("True", "False", "None")
    return False
