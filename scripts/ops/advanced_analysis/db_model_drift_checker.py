#!/usr/bin/env python3
"""SupremeAI — Database Model vs Migration Drift Checker.

Parses SQLAlchemy ORM models and Alembic/SQL migrations to detect schema drift.

বাংলা মন্তব্য: এই স্ক্রিপ্টটি SQLAlchemy মডেল এবং Alembic/SQL মাইগ্রেশনের মধ্যে
স্কিমা ড্রিফট (অমিল) সনাক্ত করে। যদি মডেলে কোনো কলাম থাকে কিন্তু মাইগ্রেশনে
না থাকে, বা উল্টোটা হয়, তাহলে রিপোর্ট তৈরি করে।

Usage:
    python scripts/db_model_drift_checker.py
    python scripts/db_model_drift_checker.py --json
    python scripts/db_model_drift_checker.py --models-only
    python scripts/db_model_drift_checker.py --migrations-only

Exit codes:
    0 = no drift found (clean)
    1 = drift detected
    2 = errors encountered during analysis
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# রিপো রুট ডিরেক্টরি — স্ক্রিপ্ট অবস্থান থেকে দুই ধাপ উপরে
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = REPO_ROOT / "backend" / "models"
ALEMBIC_DIR = REPO_ROOT / "backend" / "alembic_migrations" / "versions"
SQL_MIGRATIONS_DIR = REPO_ROOT / "migrations"

# সমালোচনামূলক টেবিল — এগুলোতে ড্রিফট HIGH রিস্ক
CRITICAL_TABLES = frozenset({"users", "user_wallets", "transaction_ledger", "api_keys", "payments", "subscriptions"})


# ──────────────────────────────────────────────────────────────────────────────
# ডাটা ক্লাস — মডেল কলাম ও মাইগ্রেশন কলামের তথ্য ধারণ করে
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ModelColumn:
    """Represents a single column parsed from a SQLAlchemy model."""
    name: str
    col_type: str
    nullable: bool | None = None
    unique: bool = False
    has_default: bool = False
    fk_reference: str | None = None
    is_primary_key: bool = False


@dataclass
class ModelTable:
    """Represents a SQLAlchemy model class / DB table."""
    name: str
    columns: dict[str, ModelColumn] = field(default_factory=dict)
    indexes: list[str] = field(default_factory=list)
    source_file: str = ""


@dataclass
class MigrationColumn:
    """Represents a column as defined in a migration."""
    name: str
    col_type: str
    nullable: bool | None = None
    is_primary_key: bool = False


@dataclass
class MigrationTable:
    """Represents a table as built from migration history."""
    name: str
    columns: dict[str, MigrationColumn] = field(default_factory=dict)
    indexes: list[str] = field(default_factory=list)
    created_in: str = ""  # মাইগ্রেশন ফাইলের নাম
    operations: list[str] = field(default_factory=list)  # টাইমলাইন অপারেশন


@dataclass
class DriftIssue:
    """A single drift finding."""
    category: str  # missing_in_migrations, missing_in_model, type_mismatch, nullable_mismatch, missing_table, stale_table, missing_index
    risk: str  # HIGH, MEDIUM, LOW
    table: str
    column: str | None = None
    detail: str = ""
    model_type: str | None = None
    migration_type: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# হেল্পার ফাংশন
# ──────────────────────────────────────────────────────────────────────────────


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase class name to snake_case table name."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _normalize_type(raw_type: str) -> str:
    """Normalize a SQLAlchemy/SQL column type string for comparison."""
    t = raw_type.strip()
    # lowercase
    t = t.lower()
    # Remove common qualifiers for comparison
    t = t.replace("(timezone=true)", "")
    t = t.replace("timezone=true", "")
    t = t.replace("(as_uuid=true)", "")
    t = re.sub(r"\(length=\d+\)", "", t)
    t = re.sub(r"\(\d+(?:,\s*\d+)?\)", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    # সাধারণ টাইপ ম্যাপিং
    type_aliases = {
        "uuid": "uuid",
        "text": "text",
        "varchar": "string",
        "string": "string",
        "integer": "integer",
        "bigint": "bigint",
        "serial": "serial",
        "bigserial": "bigserial",
        "boolean": "boolean",
        "bool": "boolean",
        "float": "float",
        "real": "float",
        "numeric": "numeric",
        "decimal": "numeric",
        "json": "json",
        "jsonb": "jsonb",
        "datetime": "datetime",
        "timestamp": "datetime",
        "date": "date",
        "time": "time",
    }
    base = t.split("(")[0].strip().split(".")[-1].strip()
    for key, val in type_aliases.items():
        if base == key:
            return val
    return base


def _ast_name(node: ast.expr | None) -> str:
    """Extract a dotted name string from an AST Name/Attribute node."""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return ""


def _get_call_kwargs(call_node: ast.Call) -> dict[str, Any]:
    """Extract keyword arguments from an ast.Call node."""
    kwargs = {}
    for kw in call_node.keywords:
        if kw.arg:
            if isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = kw.value.value
            elif isinstance(kw.value, ast.Name):
                kwargs[kw.arg] = _ast_name(kw.value)
            elif isinstance(kw.value, ast.UnaryOp) and isinstance(kw.value.op, ast.USub):
                if isinstance(kw.value.operand, ast.Constant):
                    kwargs[kw.arg] = -kw.value.operand.value
            elif isinstance(kw.value, ast.Call):
                kwargs[kw.arg] = _ast_name(kw.value.func)
    return kwargs


def _infer_nullable_from_kwargs(kwargs: dict[str, Any]) -> bool | None:
    """Infer nullable from mapped_column/Column kwargs.

    SQLAlchemy default is nullable=True unless primary_key=True.
    """
    if "nullable" in kwargs:
        val = kwargs["nullable"]
        if isinstance(val, bool):
            return val
    if kwargs.get("primary_key") is True:
        return False
    return None  # অজানা — SQLAlchemy ডিফল্ট অনুযায়ী True


def _parse_type_from_call(call_node: ast.Call) -> str:
    """Extract type string from a SQLAlchemy type constructor call.

    e.g. String(255) -> 'String', UUID(as_uuid=True) -> 'UUID',
    JSON().with_variant(JSONB, 'postgresql') -> 'JSONB',  (PostgreSQL variant)
    """
    func_name = _ast_name(call_node.func)
    if not func_name:
        return "unknown"
    base = func_name.split(".")[-1]
    # with_variant হলো SQLAlchemy-এর dialect-specific type adaptation
    # যেহেতু এই প্রজেক্ট PostgreSQL ব্যবহার করে, তাই variant type-টি নেওয়া হবে
    if base == "with_variant" and len(call_node.args) >= 2:
        # args[0] = base type (Call বা Name), args[1] = dialect name
        variant_arg = call_node.args[1]
        if isinstance(variant_arg, ast.Constant) and "postgres" in str(variant_arg.value).lower():
            # PostgreSQL variant — args[0]-এ থাকা টাইপটি ব্যবহার করুন
            inner = call_node.args[0]
            if isinstance(inner, ast.Call):
                return _parse_type_from_call(inner)
            if isinstance(inner, ast.Name):
                return inner.id
        # Non-PostgreSQL variant — base type ব্যবহার করুন
        inner = call_node.args[0]
        if isinstance(inner, ast.Call):
            return _parse_type_from_call(inner)
        if isinstance(inner, ast.Name):
            return inner.id
    return base


def _extract_col_type_from_assignment(value: ast.expr) -> str:
    """Extract the column type from the right-hand side of a model attribute assignment.

    Handles both:
      Mapped[X] = mapped_column(String(255), ...)
      col_name = Column(String(255), ...)
    """
    if isinstance(value, ast.Call):
        func_name = _ast_name(value.func)
        if func_name.endswith("mapped_column") or func_name.endswith("Column"):
            # প্রথম positional argument হলো টাইপ
            if value.args:
                arg = value.args[0]
                if isinstance(arg, ast.Call):
                    return _parse_type_from_call(arg)
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return arg.value
                elif isinstance(arg, ast.Name):
                    return arg.id
            # টাইপ kwargs থেকেও আসতে পারে (e.g., type_=sa.String)
            kwargs = _get_call_kwargs(value)
            if "type_" in kwargs:
                return str(kwargs["type_"])
    return "unknown"


def _extract_fk_from_assignment(value: ast.Call) -> str | None:
    """Extract ForeignKey reference from a mapped_column/Column call."""
    if not isinstance(value, ast.Call):
        return None
    # ForeignKey(...)
    for arg in value.args:
        if isinstance(arg, ast.Call):
            func_name = _ast_name(arg.func)
            if func_name and func_name.endswith("ForeignKey"):
                if arg.args and isinstance(arg.args[0], ast.Constant):
                    return str(arg.args[0].value)
    # ForeignKey as kwarg
    for kw in value.keywords:
        if kw.arg == "ForeignKey" or kw.arg == "fk":
            if isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return None


def _extract_fk_from_first_arg(value: ast.Call) -> str | None:
    """Extract ForeignKey from the first positional arg of mapped_column if it's a ForeignKey(...)."""
    if not value.args:
        return None
    first_arg = value.args[0]
    if isinstance(first_arg, ast.Call):
        func_name = _ast_name(first_arg.func)
        if func_name and ("ForeignKey" in func_name):
            if first_arg.args and isinstance(first_arg.args[0], ast.Constant):
                return str(first_arg.args[0].value)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# মডেল পার্সার — SQLAlchemy মডেল থেকে টেবিল ও কলাম তথ্য বের করে
# ──────────────────────────────────────────────────────────────────────────────


def parse_models(models_dir: Path) -> dict[str, ModelTable]:
    """Parse all SQLAlchemy model files and return a dict of table_name -> ModelTable."""
    tables: dict[str, ModelTable] = {}

    if not models_dir.is_dir():
        print(f"[ERROR] Models directory not found: {models_dir}", file=sys.stderr)
        return tables

    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] Cannot read {py_file}: {exc}", file=sys.stderr)
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            print(f"[WARN] Syntax error in {py_file}: {exc}", file=sys.stderr)
            continue

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            # বেস ক্লাস চেক — Base, TimestampMixin, SoftDeleteMixin বা অন্য মডেল থেকে inherit করলে বাদ
            base_names = {b.id if isinstance(b, ast.Name) else _ast_name(b) for b in node.bases}
            if not base_names:
                continue

            # Base থেকে সরাসরি inherit করে কিনা চেক করুন
            is_orm_model = "Base" in base_names
            # Mixin থেকে inherit করলেও যদি Base না থাকে, তাহলে সেটা মডেল নয়
            if not is_orm_model:
                # Check if any base is itself a known model (间接继承)
                is_sub_model = any(b in tables or b.endswith("Mixin") for b in base_names)
                if not is_sub_model:
                    continue

            # __tablename__ খুঁজুন
            tablename = ""
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id == "__tablename__":
                            if isinstance(stmt.value, ast.Constant):
                                tablename = str(stmt.value.value)
                            elif isinstance(stmt.value, ast.Str):
                                tablename = stmt.value.s

            # __tablename__ না থাকলে ক্লাস নাম থেকে snake_case তৈরি করুন
            if not tablename:
                tablename = _camel_to_snake(node.name)

            # মডেলে Base inherit না থাকলে এবং Mixin হলে এড়িয়ে যান
            if not is_orm_model and not any(b in tables for b in base_names):
                continue

            table = ModelTable(name=tablename, source_file=str(py_file.relative_to(REPO_ROOT)))

            # কলাম পার্স করুন
            for stmt in node.body:
                if not isinstance(stmt, ast.AnnAssign) and not isinstance(stmt, ast.Assign):
                    continue

                # AnnAssign: name: Mapped[X] = mapped_column(...)
                if isinstance(stmt, ast.AnnAssign):
                    if not isinstance(stmt.target, ast.Name):
                        continue
                    col_name = stmt.target.id
                    if col_name.startswith("_") and col_name.endswith("_"):
                        continue  # __tablename__, __table_args__ ইত্যাদি এড়িয়ে যান

                    if stmt.value is None:
                        continue

                    col_type_raw = _extract_col_type_from_assignment(stmt.value)
                    kwargs = _get_call_kwargs(stmt.value)

                    # FK detection — ForeignKey প্রথম positional arg বা kwarg হিসেবে
                    fk_ref = _extract_fk_from_first_arg(stmt.value)
                    if not fk_ref:
                        fk_ref = _extract_fk_from_assignment(stmt.value)

                    nullable = _infer_nullable_from_kwargs(kwargs)
                    is_pk = bool(kwargs.get("primary_key", False))
                    is_unique = bool(kwargs.get("unique", False))
                    has_default = "default" in kwargs or "server_default" in kwargs

                    # যদি nullable None থাকে এবং PK না হয়, তাহলে SQLAlchemy ডিফল্ট True
                    if nullable is None and not is_pk:
                        nullable = True

                    table.columns[col_name] = ModelColumn(
                        name=col_name,
                        col_type=col_type_raw,
                        nullable=nullable,
                        unique=is_unique,
                        has_default=has_default,
                        fk_reference=fk_ref,
                        is_primary_key=is_pk,
                    )

                # Assign: col_name = Column(...)  (পুরনো স্টাইল)
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if not isinstance(target, ast.Name):
                            continue
                        col_name = target.id
                        if col_name.startswith("_"):
                            continue

                        if not isinstance(stmt.value, ast.Call):
                            continue

                        func_name = _ast_name(stmt.value.func)
                        if not (func_name and (func_name.endswith("Column") or func_name.endswith("mapped_column"))):
                            continue

                        col_type_raw = _extract_col_type_from_assignment(stmt.value)
                        kwargs = _get_call_kwargs(stmt.value)

                        fk_ref = _extract_fk_from_first_arg(stmt.value)
                        if not fk_ref:
                            fk_ref = _extract_fk_from_assignment(stmt.value)

                        nullable = _infer_nullable_from_kwargs(kwargs)
                        is_pk = bool(kwargs.get("primary_key", False))
                        is_unique = bool(kwargs.get("unique", False))
                        has_default = "default" in kwargs or "server_default" in kwargs

                        if nullable is None and not is_pk:
                            nullable = True

                        table.columns[col_name] = ModelColumn(
                            name=col_name,
                            col_type=col_type_raw,
                            nullable=nullable,
                            unique=is_unique,
                            has_default=has_default,
                            fk_reference=fk_ref,
                            is_primary_key=is_pk,
                        )

            # __table_args__ থেকে ইনডেক্স সংগ্রহ করুন
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id == "__table_args__":
                            _extract_indexes_from_table_args(stmt.value, table)

            if table.columns or is_orm_model:
                tables[tablename] = table

    return tables


def _extract_indexes_from_table_args(value: ast.expr, table: ModelTable) -> None:
    """Extract index names from __table_args__ tuple."""
    indexes_ast: list[ast.expr] = []
    if isinstance(value, ast.Tuple):
        indexes_ast = [e for e in value.elts if isinstance(e, ast.Call)]
    elif isinstance(value, ast.Call):
        # Index(...) directly
        indexes_ast = [value]

    for elem in indexes_ast:
        func_name = _ast_name(elem.func) if isinstance(elem, ast.Call) else ""
        if func_name and func_name.endswith("Index"):
            # প্রথম positional arg হলো ইনডেক্স নাম
            if elem.args and isinstance(elem.args[0], ast.Constant):
                table.indexes.append(str(elem.args[0].value))


# ──────────────────────────────────────────────────────────────────────────────
# অ্যালেম্বিক মাইগ্রেশন পার্সার
# ──────────────────────────────────────────────────────────────────────────────


def parse_alembic_migrations(migrations_dir: Path) -> dict[str, MigrationTable]:
    """Parse all Alembic migration .py files and build final expected schema.

    বাংলা মন্তব্য: সকল মাইগ্রেশন ফাইল থেকে স্কিমা পরিবর্তনের টাইমলাইন তৈরি করে
    এবং চূড়ান্ত প্রত্যাশিত স্কিমা নির্ধারণ করে।
    """
    tables: dict[str, MigrationTable] = {}

    if not migrations_dir.is_dir():
        print(f"[WARN] Alembic migrations directory not found: {migrations_dir}", file=sys.stderr)
        return tables

    migration_files = sorted(migrations_dir.glob("*.py"), key=lambda p: p.name)

    for py_file in migration_files:
        if py_file.name.startswith("__"):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] Cannot read {py_file}: {exc}", file=sys.stderr)
            continue

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError as exc:
            print(f"[WARN] Syntax error in {py_file}: {exc}", file=sys.stderr)
            continue

        migration_name = py_file.name
        _process_migration_ast(tree, tables, migration_name)

        # পাশাপাশি op.execute() এ RAW SQL ও পার্স করুন
        _process_raw_sql_in_migration(source, tables, migration_name)

    return tables


def _process_migration_ast(
    tree: ast.Module,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Process AST of a single migration file to extract op.* calls.

    বাংলা মন্তব্য: শুধু `upgrade()` ফাংশনের ভেতরের op.* কল প্রসেস করা হয়।
    আগে পুরো ফাইল (upgrade + downgrade উভয়) ast.walk() করা হতো, ফলে যেসব
    migration ভালো practice মেনে downgrade()-এ op.drop_table() রাখত, তাদের
    create_table + drop_table একে অপরকে cancel করে ফেলত এবং false-positive
    'missing_table' রিপোর্ট হতো। এই ফিক্সের পর দুইটা আসল HIGH-risk ইস্যু
    (transaction_ledger, user_wallets) ধরা পড়েছে যেগুলো আগে চাপা পড়েছিল।
    """
    upgrade_node: ast.AST = tree
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_node = node
            break

    for node in ast.walk(upgrade_node):
        if not isinstance(node, ast.Call):
            continue

        func_name = _ast_name(node.func)
        if not func_name.startswith("op."):
            continue

        op_name = func_name[3:]  # 'op.create_table' -> 'create_table'

        if op_name == "create_table":
            _handle_create_table(node, tables, migration_name)
        elif op_name == "add_column":
            _handle_add_column(node, tables, migration_name)
        elif op_name == "drop_column":
            _handle_drop_column(node, tables, migration_name)
        elif op_name == "alter_column":
            _handle_alter_column(node, tables, migration_name)
        elif op_name == "drop_table":
            _handle_drop_table(node, tables, migration_name)
        elif op_name == "create_index":
            _handle_create_index(node, tables, migration_name)
        elif op_name == "drop_index":
            _handle_drop_index(node, tables, migration_name)
        elif op_name == "create_foreign_key":
            pass  # FK constraints are tracked via column definitions
        elif op_name == "execute":
            # op.execute() with inline SQL handled in _process_raw_sql_in_migration
            pass


def _handle_create_table(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.create_table(table_name, *columns, **kwargs)."""
    if not call_node.args:
        return
    # প্রথম positional arg হলো টেবিল নাম
    table_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        table_name = str(call_node.args[0].value)
    if not table_name:
        return

    table = MigrationTable(name=table_name, created_in=migration_name)
    table.operations.append(f"[{migration_name}] CREATE TABLE {table_name}")

    # sa.Column("name", sa.Type(), ...) পার্স করুন
    for arg in call_node.args[1:]:
        if isinstance(arg, ast.Call):
            func = _ast_name(arg.func)
            if func and (func.endswith(".Column") or func.endswith("Column")):
                _parse_sa_column(arg, table)
            elif func and (func.endswith(".PrimaryKeyConstraint") or func.endswith("PrimaryKeyConstraint")):
                # PrimaryKeyConstraint("col1", "col2", ...)
                for pk_arg in arg.args:
                    if isinstance(pk_arg, ast.Constant):
                        col_name = str(pk_arg.value)
                        if col_name in table.columns:
                            table.columns[col_name].is_primary_key = True

    # ForeignKeyConstraint থেকে FK তথ্য সংগ্রহ
    for arg in call_node.args[1:]:
        if isinstance(arg, ast.Call):
            func = _ast_name(arg.func)
            if func and ("ForeignKeyConstraint" in func):
                # ForeignKeyConstraint(["col"], ["ref_table.id"])
                pass

    tables[table_name] = table


def _parse_sa_column(col_call: ast.Call, table: MigrationTable) -> None:
    """Parse a sa.Column(name, type, ...) call and add to table."""
    if not col_call.args:
        return
    # প্রথম arg: column name
    col_name = ""
    if isinstance(col_call.args[0], ast.Constant):
        col_name = str(col_call.args[0].value)
    if not col_name:
        return

    # দ্বিতীয় arg: type
    col_type = "unknown"
    if len(col_call.args) >= 2:
        type_arg = col_call.args[1]
        if isinstance(type_arg, ast.Call):
            col_type = _parse_type_from_call(type_arg)
        elif isinstance(type_arg, ast.Name):
            col_type = type_arg.id

    kwargs = _get_call_kwargs(col_call)
    nullable = kwargs.get("nullable")
    if nullable is None:
        # SQLAlchemy Column default: nullable=True unless primary_key
        nullable = True
    is_pk = bool(kwargs.get("primary_key", False))

    # PrimaryKeyConstraint দ্বারা PK নির্ধারিত হতে পারে — পরে আপডেট হবে
    table.columns[col_name] = MigrationColumn(
        name=col_name,
        col_type=col_type,
        nullable=nullable,
        is_primary_key=is_pk,
    )


def _handle_add_column(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.add_column(table_name, sa.Column(...))."""
    if len(call_node.args) < 2:
        return
    table_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        table_name = str(call_node.args[0].value)
    if not table_name:
        return

    col_arg = call_node.args[1]
    if isinstance(col_arg, ast.Call):
        func = _ast_name(col_arg.func)
        if func and ("Column" in func):
            if table_name not in tables:
                tables[table_name] = MigrationTable(name=table_name)
            table = tables[table_name]
            _parse_sa_column(col_arg, table)
            col_name = list(table.columns.keys())[-1] if table.columns else "?"
            table.operations.append(f"[{migration_name}] ADD COLUMN {col_name} TO {table_name}")


def _handle_drop_column(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.drop_column(table_name, 'col_name')."""
    if len(call_node.args) < 2:
        return
    table_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        table_name = str(call_node.args[0].value)
    col_name = _ast_name(call_node.args[1])
    if isinstance(call_node.args[1], ast.Constant):
        col_name = str(call_node.args[1].value)

    if table_name in tables and col_name in tables[table_name].columns:
        del tables[table_name].columns[col_name]
        tables[table_name].operations.append(f"[{migration_name}] DROP COLUMN {col_name} FROM {table_name}")


def _handle_alter_column(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.alter_column(table_name, 'col_name', ...)."""
    if len(call_node.args) < 2:
        return
    table_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        table_name = str(call_node.args[0].value)
    col_name = _ast_name(call_node.args[1])
    if isinstance(call_node.args[1], ast.Constant):
        col_name = str(call_node.args[1].value)

    kwargs = _get_call_kwargs(call_node)

    if table_name in tables and col_name in tables[table_name].columns:
        col = tables[table_name].columns[col_name]
        changes = []
        if "nullable" in kwargs:
            col.nullable = kwargs["nullable"]
            changes.append(f"nullable={kwargs['nullable']}")
        if "type_" in kwargs:
            col.col_type = str(kwargs["type_"])
            changes.append(f"type={kwargs['type_']}")
        if changes:
            tables[table_name].operations.append(
                f"[{migration_name}] ALTER COLUMN {table_name}.{col_name}: {', '.join(changes)}"
            )


def _handle_drop_table(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.drop_table('table_name')."""
    if not call_node.args:
        return
    table_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        table_name = str(call_node.args[0].value)
    if table_name in tables:
        del tables[table_name]


def _handle_create_index(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.create_index(index_name, table_name, [...]...)."""
    if len(call_node.args) < 2:
        return
    index_name = _ast_name(call_node.args[0])
    if isinstance(call_node.args[0], ast.Constant):
        index_name = str(call_node.args[0].value)
    if not index_name:
        index_name = f"_idx_{_ast_name(call_node.args[1]) if call_node.args else 'unknown'}_{migration_name}"
    table_name = _ast_name(call_node.args[1])
    if isinstance(call_node.args[1], ast.Constant):
        table_name = str(call_node.args[1].value)

    if not index_name or not table_name:
        return

    if table_name in tables:
        if index_name not in tables[table_name].indexes:
            tables[table_name].indexes.append(index_name)
            tables[table_name].operations.append(
                f"[{migration_name}] CREATE INDEX {index_name} ON {table_name}"
            )


def _handle_drop_index(
    call_node: ast.Call,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Handle op.drop_index(index_name, table_name=...)."""
    kwargs = _get_call_kwargs(call_node)
    index_name = _ast_name(call_node.args[0]) if call_node.args else ""
    if isinstance(call_node.args[0], ast.Constant) if call_node.args else False:
        index_name = str(call_node.args[0].value)
    table_name = kwargs.get("table_name", "")

    if table_name and table_name in tables:
        if index_name in tables[table_name].indexes:
            tables[table_name].indexes.remove(index_name)


# ──────────────────────────────────────────────────────────────────────────────
# Raw SQL পার্সার — op.execute() এর মধ্যে থাকা SQL এবং standalone .sql ফাইল
# ──────────────────────────────────────────────────────────────────────────────


def _process_raw_sql_in_migration(
    source: str,
    tables: dict[str, MigrationTable],
    migration_name: str,
) -> None:
    """Parse raw SQL inside op.execute() calls from migration source text.

    বাংলা মন্তব্য: কিছু মাইগ্রেশন op.execute() ব্যবহার করে raw SQL চালায়।
    এই ফাংশন সেগুলো থেকে CREATE TABLE, ALTER TABLE, CREATE INDEX ইত্যাদি
    পার্স করে স্কিমা আপডেট করে।
    """
    # op.execute("""...""") বা op.execute('...') থেকে SQL বের করুন
    sql_blocks = re.findall(r'op\.execute\(\s*[rf]?"{3}(.*?)"{3}', source, re.DOTALL)
    sql_blocks += re.findall(r"op\.execute\(\s*[rf]?'{3}(.*?)'{3}", source, re.DOTALL)
    # একক লাইন op.execute("SQL")
    sql_blocks += re.findall(r'op\.execute\(\s*"(.*?)"\s*\)', source, re.DOTALL)
    sql_blocks += re.findall(r"op\.execute\(\s*'(.*?)'\s*\)", source, re.DOTALL)

    for sql in sql_blocks:
        _apply_sql_to_schema(sql, tables, migration_name)


def parse_sql_migrations(sql_dir: Path) -> dict[str, MigrationTable]:
    """Parse standalone .sql migration files.

    বাংলা মন্তব্য: migrations/ ডিরেক্টরির .sql ফাইলগুলো থেকে
    CREATE TABLE, ALTER TABLE, CREATE INDEX ইত্যাদি পার্স করে।
    """
    tables: dict[str, MigrationTable] = {}

    if not sql_dir.is_dir():
        return tables

    for sql_file in sorted(sql_dir.glob("*.sql")):
        try:
            source = sql_file.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] Cannot read {sql_file}: {exc}", file=sys.stderr)
            continue

        _apply_sql_to_schema(source, tables, sql_file.name)

    return tables


def _apply_sql_to_schema(
    sql: str,
    tables: dict[str, MigrationTable],
    source_name: str,
) -> None:
    """Apply parsed SQL statements to the tables dict.

    বাংলা মন্তব্য: SQL স্টেটমেন্ট পার্স করে tables ডিকশনারি আপডেট করে।
    CREATE TABLE, ALTER TABLE ADD COLUMN, CREATE INDEX সাপোর্ট করে।
    """
    # মাল্টিলাইন SQL নরমালাইজ করুন
    sql_normalized = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)  # কমেন্ট সরান
    sql_normalized = re.sub(r"\s+", " ", sql_normalized).strip()

    # CREATE TABLE
    create_table_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in create_table_pattern.finditer(sql_normalized):
        table_name = m.group(1).lower()
        body = m.group(2)
        table = MigrationTable(name=table_name, created_in=source_name)
        table.operations.append(f"[{source_name}] CREATE TABLE {table_name}")
        _parse_sql_columns(body, table)
        tables[table_name] = table

    # ALTER TABLE ... ADD COLUMN
    alter_add_pattern = re.compile(
        r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+(\S+?)(?:\s+NOT\s+NULL|\s+NULL|\s+DEFAULT\s+[^,;]+|\s+UNIQUE|\s+PRIMARY\s+KEY)*\s*[,;)]",
        re.IGNORECASE,
    )
    for m in alter_add_pattern.finditer(sql_normalized):
        table_name = m.group(1).lower()
        col_name = m.group(2)
        col_type = m.group(3)
        if table_name not in tables:
            tables[table_name] = MigrationTable(name=table_name)
        tables[table_name].columns[col_name] = MigrationColumn(
            name=col_name,
            col_type=_normalize_type(col_type),
            nullable=True,
        )
        tables[table_name].operations.append(
            f"[{source_name}] ADD COLUMN {col_name} TO {table_name}"
        )

    # CREATE INDEX
    create_idx_pattern = re.compile(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)",
        re.IGNORECASE,
    )
    for m in create_idx_pattern.finditer(sql_normalized):
        index_name = m.group(1)
        table_name = m.group(2).lower()
        if table_name in tables:
            if index_name not in tables[table_name].indexes:
                tables[table_name].indexes.append(index_name)

    # DROP TABLE
    drop_table_pattern = re.compile(
        r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)",
        re.IGNORECASE,
    )
    for m in drop_table_pattern.finditer(sql_normalized):
        table_name = m.group(1).lower()
        if table_name in tables:
            del tables[table_name]

    # DROP TABLE ... CASCADE
    drop_cascade_pattern = re.compile(
        r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)\s+CASCADE",
        re.IGNORECASE,
    )
    for m in drop_cascade_pattern.finditer(sql_normalized):
        table_name = m.group(1).lower()
        if table_name in tables:
            del tables[table_name]


def _parse_sql_columns(body: str, table: MigrationTable) -> None:
    """Parse column definitions from a CREATE TABLE body string.

    বাংলা মন্তব্য: CREATE TABLE এর ভেতরের কলাম ডেফিনিশন পার্স করে।
    """
    # কলাম ডেফিনিশন প্যাটার্ন: column_name TYPE [constraints...]
    # CONSTRAINT PRIMARY KEY এবং FOREIGN KEY লাইন এড়িয়ে যান
    col_pattern = re.compile(
        r"(\w+)\s+"
        r"(TIMESTAMP\s+WITH\s+TIME\s+ZONE|TIMESTAMP|DATETIME|DATE|TIME|"
        r"UUID|TEXT|VARCHAR|CHAR|STRING|"
        r"INTEGER|INT|BIGINT|SERIAL|BIGSERIAL|SMALLINT|"
        r"NUMERIC|DECIMAL|REAL|FLOAT|DOUBLE\s+PRECISION|"
        r"BOOLEAN|BOOL|JSON|JSONB|BYTEA|"
        r"VECTOR\s*\([^)]*\)|"
        r"[A-Z][A-Z0-9_]*)"
        r"(.*?)?(?=,\s*\w+\s+[A-Z]|$)",
        re.IGNORECASE | re.DOTALL,
    )

    for m in col_pattern.finditer(body):
        col_name = m.group(1).lower()
        col_type_raw = m.group(2).upper()
        constraints = m.group(3) or ""
        constraints_upper = constraints.upper()

        # PRIMARY KEY, CONSTRAINT, FOREIGN KEY, UNIQUE, CHECK লাইন এড়িয়ে যান
        if col_name in ("primary", "constraint", "foreign", "unique", "check"):
            continue
        if "PRIMARY KEY" in constraints_upper and "REFERENCES" not in constraints_upper:
            # টেবিল-লেভেল PK constraint — কলাম নয়
            continue

        nullable = "NOT NULL" not in constraints_upper
        is_pk = "PRIMARY KEY" in constraints_upper
        col_type = _normalize_type(col_type_raw)

        table.columns[col_name] = MigrationColumn(
            name=col_name,
            col_type=col_type,
            nullable=nullable,
            is_primary_key=is_pk,
        )


# ──────────────────────────────────────────────────────────────────────────────
# ড্রিফট সনাক্তকরণ — মডেল ও মাইগ্রেশন তুলনা করে অমিল খুঁজে বের করে
# ──────────────────────────────────────────────────────────────────────────────


def detect_drift(
    model_tables: dict[str, ModelTable],
    migration_tables: dict[str, MigrationTable],
) -> list[DriftIssue]:
    """Compare model schema vs migration schema and return a list of drift issues.

    বাংলা মন্তব্য: মডেল ও মাইগ্রেশনের স্কিমা তুলনা করে পাঁচ ধরনের ড্রিফট সনাক্ত করে:
    ১. মডেলে আছে কিন্তু মাইগ্রেশনে নেই (missing_in_migrations)
    ২. মাইগ্রেশনে আছে কিন্তু মডেলে নেই (missing_in_model)
    ৩. টাইপ মিসম্যাচ (type_mismatch)
    ৪. Nullable মিসম্যাচ (nullable_mismatch)
    ৫. মডেলের টেবিলের কোনো মাইগ্রেশন নেই (missing_table)
    ৬. মাইগ্রেশনের টেবিল মডেলে নেই (stale_table)
    ৭. মডেলের ইনডেক্স মাইগ্রেশনে নেই (missing_index)
    """
    issues: list[DriftIssue] = []

    all_table_names = set(model_tables.keys()) | set(migration_tables.keys())

    for table_name in sorted(all_table_names):
        in_model = table_name in model_tables
        in_migration = table_name in migration_tables
        is_critical = table_name in CRITICAL_TABLES

        # ── কেস ১: মডেলে আছে কিন্তু মাইগ্রেশনে টেবিলই নেই ──
        if in_model and not in_migration:
            issues.append(DriftIssue(
                category="missing_table",
                risk="HIGH" if is_critical else "MEDIUM",
                table=table_name,
                detail=f"Model defines table '{table_name}' but no migration ever creates it. "
                       f"Source: {model_tables[table_name].source_file}",
            ))
            continue

        # ── কেস ২: মাইগ্রেশনে আছে কিন্তু মডেলে নেই ──
        if not in_model and in_migration:
            issues.append(DriftIssue(
                category="stale_table",
                risk="MEDIUM",
                table=table_name,
                detail=f"Migration created table '{table_name}' but no model defines it. "
                       f"Created in: {migration_tables[table_name].created_in}",
            ))
            continue

        # ── উভয় জায়গায় আছে — কলাম তুলনা করুন ──
        m_table = model_tables[table_name]
        mig_table = migration_tables[table_name]

        model_cols = set(m_table.columns.keys())
        mig_cols = set(mig_table.columns.keys())

        # কলাম যা মডেলে আছে কিন্তু মাইগ্রেশনে নেই
        for col_name in sorted(model_cols - mig_cols):
            mc = m_table.columns[col_name]
            risk = "HIGH" if is_critical else "MEDIUM"
            issues.append(DriftIssue(
                category="missing_in_migrations",
                risk=risk,
                table=table_name,
                column=col_name,
                model_type=mc.col_type,
                detail=f"Column '{col_name}' ({mc.col_type}) exists in model but was never added by any migration.",
            ))

        # কলাম যা মাইগ্রেশনে আছে কিন্তু মডেলে নেই
        for col_name in sorted(mig_cols - model_cols):
            mc = mig_table.columns[col_name]
            risk = "HIGH" if is_critical else "MEDIUM"
            issues.append(DriftIssue(
                category="missing_in_model",
                risk=risk,
                table=table_name,
                column=col_name,
                migration_type=mc.col_type,
                detail=f"Column '{col_name}' ({mc.col_type}) exists in migration but not in the model.",
            ))

        # কমন কলামের টাইপ ও nullable তুলনা
        for col_name in sorted(model_cols & mig_cols):
            mc = m_table.columns[col_name]
            migc = mig_table.columns[col_name]

            # টাইপ মিসম্যাচ
            norm_model = _normalize_type(mc.col_type)
            norm_mig = _normalize_type(migc.col_type)
            if norm_model != norm_mig and norm_model != "unknown" and norm_mig != "unknown":
                risk = "MEDIUM"
                if is_critical and col_name in ("id", "user_id"):
                    risk = "HIGH"
                issues.append(DriftIssue(
                    category="type_mismatch",
                    risk=risk,
                    table=table_name,
                    column=col_name,
                    model_type=mc.col_type,
                    migration_type=migc.col_type,
                    detail=f"Type mismatch for '{col_name}': model={mc.col_type} ({norm_model}), "
                           f"migration={migc.col_type} ({norm_mig})",
                ))

            # Nullable মিসম্যাচ
            if mc.nullable is not None and migc.nullable is not None:
                if mc.nullable != migc.nullable:
                    risk = "MEDIUM"
                    if is_critical:
                        risk = "HIGH"
                    model_null = "NULLABLE" if mc.nullable else "NOT NULL"
                    mig_null = "NULLABLE" if migc.nullable else "NOT NULL"
                    issues.append(DriftIssue(
                        category="nullable_mismatch",
                        risk=risk,
                        table=table_name,
                        column=col_name,
                        detail=f"Nullable mismatch for '{col_name}': model says {model_null}, "
                               f"migration says {mig_null}",
                    ))

        # ইনডেক্স তুলনা — মডেলে __table_args__ বা index=True থাকলে মাইগ্রেশনে আছে কিনা চেক
        # (শুধু নাম থেকে ইনডেক্স ট্র্যাক করা কঠিন, তাই এটি LOW রিস্ক)
        if m_table.indexes:
            for idx_name in m_table.indexes:
                if idx_name not in mig_table.indexes:
                    issues.append(DriftIssue(
                        category="missing_index",
                        risk="LOW",
                        table=table_name,
                        detail=f"Index '{idx_name}' defined in model but not found in migration history.",
                    ))

    return issues


# ──────────────────────────────────────────────────────────────────────────────
# রিপোর্ট জেনারেটর — মার্কডাউন ফরম্যাটে ফলাফল প্রদর্শন করে
# ──────────────────────────────────────────────────────────────────────────────


def generate_markdown_report(
    model_tables: dict[str, ModelTable],
    migration_tables: dict[str, MigrationTable],
    issues: list[DriftIssue],
) -> str:
    """Generate a structured Markdown drift report.

    বাংলা মন্তব্য: সকল ড্রিফট ইস্যু মার্কডাউন ফরম্যাটে সুন্দরভাবে সাজানো হয়।
    রিস্ক লেভেল অনুযায়ী বিভাগ করা হয়।
    """
    lines: list[str] = []
    lines.append("# 📊 SupremeAI Database Model vs Migration Drift Report")
    lines.append("")
    lines.append(f"**Models scanned:** {len(model_tables)} tables from `{MODELS_DIR.relative_to(REPO_ROOT)}`")
    lines.append(f"**Alembic migrations:** {len(migration_tables)} tables from `{ALEMBIC_DIR.relative_to(REPO_ROOT)}`")
    lines.append(f"**Drift issues found:** {len(issues)}")
    lines.append("")

    if not issues:
        lines.append("## ✅ No Drift Detected")
        lines.append("")
        lines.append("All model columns have corresponding migrations. Schema is in sync.")
        lines.append("")
        return "\n".join(lines)

    # রিস্ক অনুযায়ী গ্রুপ করুন
    high_issues = [i for i in issues if i.risk == "HIGH"]
    medium_issues = [i for i in issues if i.risk == "MEDIUM"]
    low_issues = [i for i in issues if i.risk == "LOW"]

    # ── সারাংশ টেবিল ──
    lines.append("## Summary")
    lines.append("")
    lines.append("| Risk | Count |")
    lines.append("|------|-------|")
    lines.append(f"| 🔴 HIGH | {len(high_issues)} |")
    lines.append(f"| 🟡 MEDIUM | {len(medium_issues)} |")
    lines.append(f"| 🟢 LOW | {len(low_issues)} |")
    lines.append("")

    # ── HIGH রিস্ক ──
    if high_issues:
        lines.append("## 🔴 HIGH Risk Issues")
        lines.append("")
        for idx, issue in enumerate(high_issues, 1):
            lines.append(f"### {idx}. [{issue.category}] `{issue.table}`")
            if issue.column:
                lines.append(f"- **Column:** `{issue.column}`")
            if issue.model_type:
                lines.append(f"- **Model type:** `{issue.model_type}`")
            if issue.migration_type:
                lines.append(f"- **Migration type:** `{issue.migration_type}`")
            lines.append(f"- **Detail:** {issue.detail}")
            lines.append("")

    # ── MEDIUM রিস্ক ──
    if medium_issues:
        lines.append("## 🟡 MEDIUM Risk Issues")
        lines.append("")
        for idx, issue in enumerate(medium_issues, 1):
            lines.append(f"### {idx}. [{issue.category}] `{issue.table}`")
            if issue.column:
                lines.append(f"- **Column:** `{issue.column}`")
            if issue.model_type:
                lines.append(f"- **Model type:** `{issue.model_type}`")
            if issue.migration_type:
                lines.append(f"- **Migration type:** `{issue.migration_type}`")
            lines.append(f"- **Detail:** {issue.detail}")
            lines.append("")

    # ── LOW রিস্ক ──
    if low_issues:
        lines.append("## 🟢 LOW Risk Issues")
        lines.append("")
        for idx, issue in enumerate(low_issues, 1):
            lines.append(f"### {idx}. [{issue.category}] `{issue.table}`")
            lines.append(f"- **Detail:** {issue.detail}")
            lines.append("")

    # ── মডেল স্কিমা ওভারভিউ ──
    lines.append("---")
    lines.append("## Model Schema Overview")
    lines.append("")
    lines.append("| Table | Columns | Source File |")
    lines.append("|-------|---------|-------------|")
    for tname in sorted(model_tables):
        t = model_tables[tname]
        lines.append(f"| `{tname}` | {len(t.columns)} | `{t.source_file}` |")
    lines.append("")

    # ── মাইগ্রেশন টাইমলাইন ──
    lines.append("## Migration Timeline")
    lines.append("")
    for tname in sorted(migration_tables):
        t = migration_tables[tname]
        if t.operations:
            lines.append(f"### `{tname}`")
            lines.append("")
            for op in t.operations:
                lines.append(f"- {op}")
            lines.append("")

    return "\n".join(lines)


def generate_json_report(
    model_tables: dict[str, ModelTable],
    migration_tables: dict[str, MigrationTable],
    issues: list[DriftIssue],
) -> str:
    """Generate JSON output of the drift report.

    বাংলা মন্তব্য: JSON ফরম্যাটে রিপোর্ট তৈরি করা হয় যা CI/CD পাইপলাইনে
    সহজেই পার্স করা যায়।
    """
    report: dict[str, Any] = {
        "summary": {
            "models_scanned": len(model_tables),
            "migration_tables": len(migration_tables),
            "total_issues": len(issues),
            "high_risk": sum(1 for i in issues if i.risk == "HIGH"),
            "medium_risk": sum(1 for i in issues if i.risk == "MEDIUM"),
            "low_risk": sum(1 for i in issues if i.risk == "LOW"),
        },
        "issues": [
            {
                "category": i.category,
                "risk": i.risk,
                "table": i.table,
                "column": i.column,
                "model_type": i.model_type,
                "migration_type": i.migration_type,
                "detail": i.detail,
            }
            for i in issues
        ],
        "model_tables": {
            name: {
                "columns": {
                    cname: {
                        "type": c.col_type,
                        "nullable": c.nullable,
                        "unique": c.unique,
                        "has_default": c.has_default,
                        "fk_reference": c.fk_reference,
                        "is_primary_key": c.is_primary_key,
                    }
                    for cname, c in t.columns.items()
                },
                "indexes": t.indexes,
                "source_file": t.source_file,
            }
            for name, t in model_tables.items()
        },
        "migration_tables": {
            name: {
                "columns": {
                    cname: {
                        "type": c.col_type,
                        "nullable": c.nullable,
                        "is_primary_key": c.is_primary_key,
                    }
                    for cname, c in t.columns.items()
                },
                "indexes": t.indexes,
                "created_in": t.created_in,
                "operations": t.operations,
            }
            for name, t in migration_tables.items()
        },
    }
    return json.dumps(report, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────────────
# মেইন এন্ট্রি পয়েন্ট
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    """Main entry point. Returns exit code 0=clean, 1=drift, 2=error."""
    parser = argparse.ArgumentParser(
        description="SupremeAI Database Model vs Migration Drift Checker",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON instead of Markdown",
    )
    parser.add_argument(
        "--models-only",
        action="store_true",
        help="Only parse and display model schema (skip drift check)",
    )
    parser.add_argument(
        "--migrations-only",
        action="store_true",
        help="Only parse and display migration schema (skip drift check)",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default=str(MODELS_DIR),
        help=f"Path to models directory (default: {MODELS_DIR})",
    )
    parser.add_argument(
        "--alembic-dir",
        type=str,
        default=str(ALEMBIC_DIR),
        help=f"Path to Alembic migrations directory (default: {ALEMBIC_DIR})",
    )
    parser.add_argument(
        "--sql-dir",
        type=str,
        default=str(SQL_MIGRATIONS_DIR),
        help=f"Path to SQL migrations directory (default: {SQL_MIGRATIONS_DIR})",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        default=False,
        help="CI mode: exit non-zero only for HIGH-risk drift issues, not "
        "MEDIUM/LOW advisory findings. Without this flag any issue fails as before.",
    )

    args = parser.parse_args()
    had_errors = False

    # ── মডেল পার্স করুন ──
    # বাংলা মন্তব্য: SQLAlchemy মডেল ফাইল থেকে স্কিমা তথ্য সংগ্রহ করা হচ্ছে
    model_tables = parse_models(Path(args.models_dir))
    if not model_tables and not args.migrations_only:
        print("[ERROR] No SQLAlchemy models found. Check --models-dir path.", file=sys.stderr)
        had_errors = True

    # ── অ্যালেম্বিক মাইগ্রেশন পার্স করুন ──
    # বাংলা মন্তব্য: Alembic মাইগ্রেশন ফাইল থেকে স্কিমা পরিবর্তনের ইতিহাস সংগ্রহ করা হচ্ছে
    migration_tables = parse_alembic_migrations(Path(args.alembic_dir))

    # ── SQL মাইগ্রেশন পার্স করুন ──
    # বাংলা মন্তব্য: Raw SQL মাইগ্রেশন ফাইল থেকেও স্কিমা পরিবর্তন সংগ্রহ করা হচ্ছে
    sql_tables = parse_sql_migrations(Path(args.sql_dir))
    # SQL মাইগ্রেশন থেকে প্রাপ্ত টেবিল ও কলাম মার্জ করুন
    for tname, stable in sql_tables.items():
        if tname in migration_tables:
            # বিদ্যমান টেবিলে নতুন কলাম যোগ করুন (যদি আগে থেকে না থাকে)
            for cname, col in stable.columns.items():
                if cname not in migration_tables[tname].columns:
                    migration_tables[tname].columns[cname] = col
            # ইনডেক্স মার্জ করুন
            for idx in stable.indexes:
                if idx not in migration_tables[tname].indexes:
                    migration_tables[tname].indexes.append(idx)
            migration_tables[tname].operations.extend(stable.operations)
        else:
            migration_tables[tname] = stable

    # ── শুধু মডেল দেখান ──
    if args.models_only:
        if args.json_output:
            print(json.dumps({
                "models": {
                    name: {
                        "columns": list(t.columns.keys()),
                        "source": t.source_file,
                    }
                    for name, t in model_tables.items()
                }
            }, indent=2, ensure_ascii=False))
        else:
            print(f"# Model Schema ({len(model_tables)} tables)\n")
            for tname in sorted(model_tables):
                t = model_tables[tname]
                print(f"## `{tname}` ({len(t.columns)} columns)")
                print(f"   Source: `{t.source_file}`")
                if t.indexes:
                    print(f"   Indexes: {', '.join(f'`{i}`' for i in t.indexes)}")
                print("")
                print("   | Column | Type | Nullable | Unique | PK | FK |")
                print("   |--------|------|----------|--------|----|----|")
                for cname in sorted(t.columns):
                    c = t.columns[cname]
                    fk_str = f"`{c.fk_reference}`" if c.fk_reference else ""
                    print(
                        f"   | `{cname}` | `{c.col_type}` | "
                        f"{'✓' if c.nullable else '✗'} | "
                        f"{'✓' if c.unique else ''} | "
                        f"{'PK' if c.is_primary_key else ''} | "
                        f"{fk_str} |"
                    )
                print("")
        return 0 if not had_errors else 2

    # ── শুধু মাইগ্রেশন দেখান ──
    if args.migrations_only:
        if args.json_output:
            print(json.dumps({
                "migrations": {
                    name: {
                        "columns": list(t.columns.keys()),
                        "created_in": t.created_in,
                        "operations": t.operations,
                    }
                    for name, t in migration_tables.items()
                }
            }, indent=2, ensure_ascii=False))
        else:
            print(f"# Migration Schema ({len(migration_tables)} tables)\n")
            for tname in sorted(migration_tables):
                t = migration_tables[tname]
                print(f"## `{tname}` ({len(t.columns)} columns)")
                print(f"   Created in: `{t.created_in}`")
                if t.indexes:
                    print(f"   Indexes: {', '.join(f'`{i}`' for i in t.indexes)}")
                print("")
                print("   | Column | Type | Nullable | PK |")
                print("   |--------|------|----------|----|")
                for cname in sorted(t.columns):
                    c = t.columns[cname]
                    print(
                        f"   | `{cname}` | `{c.col_type}` | "
                        f"{'✓' if c.nullable else '✗'} | "
                        f"{'PK' if c.is_primary_key else ''} |"
                    )
                print("")
                if t.operations:
                    print("   **Operations:**")
                    for op in t.operations:
                        print(f"   - {op}")
                    print("")
        return 0 if not had_errors else 2

    # ── ড্রিফট সনাক্তকরণ ──
    # বাংলা মন্তব্য: এখন মডেল ও মাইগ্রেশনের মধ্যে তুলনা করে ড্রিফট খুঁজে বের করা হচ্ছে
    issues = detect_drift(model_tables, migration_tables)

    # ── রিপোর্ট আউটপুট ──
    if args.json_output:
        print(generate_json_report(model_tables, migration_tables, issues))
    else:
        print(generate_markdown_report(model_tables, migration_tables, issues))

    # ── এক্সিট কোড নির্ধারণ ──
    # বাংলা মন্তব্য: কোনো সমস্যা থাকলে exit code ২, ড্রিফট থাকলে ১, পরিষ্কার থাকলে ০
    if had_errors:
        return 2
    if args.fail_on_critical:
        high_risk = [i for i in issues if i.risk == "HIGH"]
        return 1 if high_risk else 0
    if issues:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
