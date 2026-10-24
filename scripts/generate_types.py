#!/usr/bin/env python3
"""
SupremeAI — Pydantic → TypeScript/Dart Type Generator
=======================================================

Scans all Pydantic BaseModel subclasses under `backend/schemas/` and
generates TypeScript interfaces (`.d.ts`) and Dart model classes (`.dart`).

Usage:
    python scripts/generate_types.py              # Generate all types
    python scripts/generate_types.py --watch      # Watch mode (requires watchdog)
    python scripts/generate_types.py --validate   # Validate existing types match schemas

Output:
    packages/shared-types/src/typescript/  ← TypeScript .d.ts files
    packages/shared-types/src/dart/        ← Dart .dart files

Bengali:
    পাইথন পিজ্যান্টিক মডেল থেকে টাইপস্ক্রিপ্ট ও ডার্ট ফাইল জেনারেট করার লুপ
    মডেল স্কিমার যেকোনো পরিবর্তনে টাইপ ড্রিফট সনাক্ত করা হয়
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union, get_args, get_origin

# ── Add backend to sys.path ──────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
sys.path.insert(0, str(_BACKEND_DIR))

# ── UTF-8 stdout (Windows cp1252-এ emoji/unicode crash ঠেকাতে) ─────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Constants ─────────────────────────────────────────────────────────────────
SCHEMAS_PACKAGE = "schemas"
OUTPUT_TS_DIR = Path(__file__).resolve().parent.parent / "packages" / "shared-types" / "src" / "typescript"
OUTPUT_DART_DIR = Path(__file__).resolve().parent.parent / "packages" / "shared-types" / "src" / "dart"
CHECKSUM_FILE = Path(__file__).resolve().parent.parent / "packages" / "shared-types" / ".type_checksums.json"

# Type mapping: Python type → TypeScript type
PY_TO_TS: dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    bytes: "string",
    datetime: "string",  # ISO 8601
    Any: "any",
}

# Type mapping: Python type → Dart type
PY_TO_DART: dict[type, str] = {
    str: "String",
    int: "int",
    float: "double",
    bool: "bool",
    bytes: "List<int>",
    datetime: "DateTime",
    Any: "dynamic",
}

# Types that should be skipped (internal/abstract)
SKIP_TYPES = {"BaseModel", "ABC", "Generic"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_python_type_name(tp: type) -> str:
    """Get a clean Python type name for a type annotation."""
    origin = get_origin(tp)
    if origin is not None:
        args = get_args(tp)
        if origin is list:
            return f"list[{_get_python_type_name(args[0])}]" if args else "list"
        if origin in (dict, dict):
            return f"dict[{_get_python_type_name(args[0])}, {_get_python_type_name(args[1])}]" if len(args) >= 2 else "dict"
        if origin in (set, set):
            return f"set[{_get_python_type_name(args[0])}]" if args else "set"
        if origin is tuple:
            return f"tuple[{', '.join(_get_python_type_name(a) for a in args)}]" if args else "tuple"
        if origin is type(None) or origin is None:
            return "None"
        if origin is Union:  # type: ignore[name-defined]
            return " | ".join(_get_python_type_name(a) for a in args)
    if tp is type(None):
        return "None"
    if hasattr(tp, "__name__"):
        return tp.__name__
    return str(tp)


def _resolve_type_string(tp: type, type_map: dict[type, str], model_names: set[str]) -> str:
    """Resolve a Python type to its target language type string."""
    origin = get_origin(tp)
    args = get_args(tp)

    # Handle Optional[X] = Union[X, None]
    if origin is type(None) or origin is None:
        return "null"
    if origin is Union:  # type: ignore[name-defined]
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            base = _resolve_type_string(non_none_args[0], type_map, model_names)
            return f"{base} | null" if type_map is PY_TO_TS else f"{base}?"
        return " | ".join(_resolve_type_string(a, type_map, model_names) for a in non_none_args)

    # Direct mapping
    if tp in type_map:
        return type_map[tp]

    # Check if it's a known model
    if hasattr(tp, "__name__") and tp.__name__ in model_names:
        return tp.__name__

    # Generic types
    if origin is list:
        inner = _resolve_type_string(args[0], type_map, model_names) if args else "any"
        return f"{inner}[]" if type_map is PY_TO_TS else f"List<{inner}>"
    if origin in (dict, dict):
        key_t = _resolve_type_string(args[0], type_map, model_names) if args else "string"
        val_t = _resolve_type_string(args[1], type_map, model_names) if len(args) >= 2 else "any"
        return f"Record<{key_t}, {val_t}>" if type_map is PY_TO_TS else f"Map<{key_t}, {val_t}>"
    if origin in (set, set):
        inner = _resolve_type_string(args[0], type_map, model_names) if args else "any"
        return f"Set<{inner}>" if type_map is PY_TO_DART else f"{inner}[]"
    if origin is tuple:
        inners = ", ".join(_resolve_type_string(a, type_map, model_names) for a in args) if args else "any"
        return f"[{inners}]" if type_map is PY_TO_TS else f"({inners})"

    # Fallback
    if hasattr(tp, "__name__"):
        return type_map.get(tp, tp.__name__)
    return "any"


def _get_field_type(field: Any, model_names: set[str]) -> tuple[str, str]:
    """Get TypeScript and Dart type strings for a Pydantic field."""
    ts_type = _resolve_type_string(field.annotation, PY_TO_TS, model_names) if field.annotation else "any"
    dart_type = _resolve_type_string(field.annotation, PY_TO_DART, model_names) if field.annotation else "dynamic"
    return ts_type, dart_type


def _is_pydantic_model(obj: Any) -> bool:
    """Check if an object is a Pydantic BaseModel subclass."""
    try:
        from pydantic import BaseModel
        return isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    except ImportError:
        return False


def _to_camel_case(name: str) -> str:
    """Convert snake_case to camelCase for TypeScript/Dart."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _compute_checksum(content: str) -> str:
    """Compute SHA-256 checksum of generated content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Scanner ───────────────────────────────────────────────────────────────────


def discover_models() -> dict[str, type]:
    """Discover all Pydantic BaseModel subclasses in the schemas package."""
    models: dict[str, type] = {}

    try:
        import schemas as schemas_pkg
    except ImportError as e:
        print(f"❌ Cannot import schemas package: {e}")
        return models

    package_path = Path(schemas_pkg.__file__).resolve().parent

    # Walk all .py files in the schemas directory
    for file_path in sorted(package_path.glob("*.py")):
        if file_path.name == "__init__.py":
            continue
        module_name = f"schemas.{file_path.stem}"
        try:
            module = importlib.import_module(module_name)
            for name, obj in inspect.getmembers(module):
                if _is_pydantic_model(obj) and name not in SKIP_TYPES:
                    models[name] = obj
        except Exception as e:
            print(f"  ⚠️  Could not import {module_name}: {e}")

    return models


# ── TypeScript Generator ─────────────────────────────────────────────────────


def generate_typescript(models: dict[str, type]) -> dict[str, str]:
    """Generate TypeScript interface definitions for all models."""
    model_names = set(models.keys())
    files: dict[str, str] = {}

    for name, model_cls in sorted(models.items()):
        lines: list[str] = []
        lines.append("// Auto-generated by SupremeAI Type Generator")
        lines.append(f"// Source: {model_cls.__module__}.{name}")
        lines.append("")

        # Docstring
        if model_cls.__doc__:
            lines.append(f"/** {model_cls.__doc__.strip()} */")

        lines.append(f"export interface {name} {{")

        # Fields
        try:
            for field_name, field in model_cls.model_fields.items():
                ts_type, _ = _get_field_type(field, model_names)
                is_required = field.is_required()
                optional_suffix = "?" if not is_required else ""
                description = field.description or ""
                if description:
                    lines.append(f"  /** {description} */")
                lines.append(f"  {_to_camel_case(field_name)}{optional_suffix}: {ts_type};")
        except Exception as e:
            print(f"  ⚠️  Error processing {name} fields: {e}")
            lines.append(f"  // Error: {e}")

        lines.append("}")
        lines.append("")

        files[name] = "\n".join(lines)

    # Generate index file
    index_lines = [
        "// Auto-generated by SupremeAI Type Generator",
        "",
    ]
    for name in sorted(models.keys()):
        index_lines.append(f"export * from './{name}';")
    index_lines.append("")
    files["index"] = "\n".join(index_lines)

    return files


# ── Dart Generator ────────────────────────────────────────────────────────────


def generate_dart(models: dict[str, type]) -> dict[str, str]:
    """Generate Dart model classes for all models."""
    model_names = set(models.keys())
    files: dict[str, str] = {}

    for name, model_cls in sorted(models.items()):
        lines: list[str] = []
        lines.append("// Auto-generated by SupremeAI Type Generator")
        lines.append(f"// Source: {model_cls.__module__}.{name}")
        lines.append("")
        lines.append("// ignore_for_file: prefer_final_fields, non_constant_identifier_names")
        lines.append("")

        # Class definition
        if model_cls.__doc__:
            lines.append(f"/// {model_cls.__doc__.strip()}")

        lines.append(f"class {name} {{")

        # Constructor
        fields_info: list[tuple[str, str, str, bool]] = []
        try:
            for field_name, field in model_cls.model_fields.items():
                _, dart_type = _get_field_type(field, model_names)
                is_required = field.is_required()
                fields_info.append((field_name, _to_camel_case(field_name), dart_type, is_required))
        except Exception as e:
            print(f"  ⚠️  Error processing {name} fields: {e}")

        # Fields
        for _, camel_name, dart_type, _ in fields_info:
            lines.append(f"  {dart_type} {camel_name};")

        lines.append("")

        # Constructor
        constructor_params = []
        for orig_name, camel_name, dart_type, is_required in fields_info:
            if is_required:
                constructor_params.append(f"    required this.{camel_name},")
            else:
                constructor_params.append(f"    this.{camel_name},")

        if constructor_params:
            lines.append(f"  {name}({{")
            lines.extend(constructor_params)
            lines.append("  });")
        else:
            lines.append(f"  {name}();")

        lines.append("")

        # fromJson factory
        lines.append(f"  factory {name}.fromJson(Map<String, dynamic> json) {{")
        lines.append(f"    return {name}(")
        for orig_name, camel_name, dart_type, _ in fields_info:
            json_key = _to_camel_case(orig_name)
            lines.append(f"      {camel_name}: json['{json_key}'] as {dart_type},")
        lines.append("    );")
        lines.append("  }")

        lines.append("")

        # toJson method
        lines.append("  Map<String, dynamic> toJson() {")
        lines.append("    return {")
        for orig_name, camel_name, _, _ in fields_info:
            json_key = _to_camel_case(orig_name)
            lines.append(f"      '{json_key}': {camel_name},")
        lines.append("    };")
        lines.append("  }")

        lines.append("}")
        lines.append("")

        files[name] = "\n".join(lines)

    # Generate index file
    index_lines = [
        "// Auto-generated by SupremeAI Type Generator",
        "",
    ]
    for name in sorted(models.keys()):
        index_lines.append(f"export '{name}.dart';")
    index_lines.append("")
    files["index"] = "\n".join(index_lines)

    return files


# ── Writer ────────────────────────────────────────────────────────────────────


def write_files(files: dict[str, str], output_dir: Path, extension: str) -> dict[str, str]:
    """Write generated files to disk and return checksums."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checksums: dict[str, str] = {}

    for name, content in files.items():
        if name == "index":
            filename = output_dir / f"index{extension}"
        else:
            filename = output_dir / f"{name}{extension}"

        filename.write_text(content, encoding="utf-8")
        checksums[name] = _compute_checksum(content)
        # বাংলা: আগে `Path.cwd()`-এর উপর নির্ভর করত — CI-তে working-directory `backend`
        # থাকলে output ফাইল (repo root-এ) `relative_to(cwd)` ValueError ফেলে দিত।
        print(f"  ✅ Generated {filename.relative_to(_REPO_ROOT)}")

    return checksums


def save_checksums(ts_checksums: dict[str, str], dart_checksums: dict[str, str]) -> None:
    """Save checksums for drift detection."""
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "typescript": ts_checksums,
        "dart": dart_checksums,
    }
    CHECKSUM_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKSUM_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  ✅ Checksums saved to {CHECKSUM_FILE.relative_to(_REPO_ROOT)}")


def detect_drift() -> bool:
    """Detect if generated types are out of sync with schemas."""
    if not CHECKSUM_FILE.exists():
        print("  ⚠️  No checksum file found. Run generation first.")
        return True

    old_checksums = json.loads(CHECKSUM_FILE.read_text(encoding="utf-8"))
    models = discover_models()
    if not models:
        return True

    set(models.keys())
    drift_detected = False

    # Check TypeScript
    ts_files = generate_typescript(models)
    for name, content in ts_files.items():
        new_hash = _compute_checksum(content)
        old_hash = old_checksums.get("typescript", {}).get(name)
        if old_hash != new_hash:
            print(f"  🔴 Drift detected in TypeScript: {name}")
            drift_detected = True

    # Check Dart
    dart_files = generate_dart(models)
    for name, content in dart_files.items():
        new_hash = _compute_checksum(content)
        old_hash = old_checksums.get("dart", {}).get(name)
        if old_hash != new_hash:
            print(f"  🔴 Drift detected in Dart: {name}")
            drift_detected = True

    if not drift_detected:
        print("  ✅ No drift detected. All types are in sync.")

    return drift_detected


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    """Main entry point for the type generator."""
    parser = argparse.ArgumentParser(
        description="Generate TypeScript and Dart types from Pydantic models",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: regenerate on file changes (requires watchdog)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate that generated types match schemas (drift detection)",
    )
    parser.add_argument(
        "--ts-only",
        action="store_true",
        help="Generate TypeScript only",
    )
    parser.add_argument(
        "--dart-only",
        action="store_true",
        help="Generate Dart only",
    )
    args = parser.parse_args()

    print("🔍 Discovering Pydantic models...")
    models = discover_models()

    if not models:
        print("❌ No Pydantic models found in schemas package.")
        return 1

    print(f"  Found {len(models)} models: {', '.join(sorted(models.keys()))}")
    print()

    # Validate mode
    if args.validate:
        print("🔍 Running drift detection...")
        drift = detect_drift()
        return 1 if drift else 0

    # Generate TypeScript
    if not args.dart_only:
        print("📄 Generating TypeScript interfaces...")
        ts_files = generate_typescript(models)
        ts_checksums = write_files(ts_files, OUTPUT_TS_DIR, ".d.ts")
        print()

    # Generate Dart
    if not args.ts_only:
        print("📄 Generating Dart model classes...")
        dart_files = generate_dart(models)
        dart_checksums = write_files(dart_files, OUTPUT_DART_DIR, ".dart")
        print()

    # Save checksums
    ts_checksums = ts_checksums if not args.dart_only else {}
    dart_checksums = dart_checksums if not args.ts_only else {}
    save_checksums(ts_checksums, dart_checksums)

    print()
    print("✅ Type generation complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
