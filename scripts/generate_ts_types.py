#!/usr/bin/env python3
"""
Generate TypeScript definitions from Pydantic models.

This script keeps the frontend's shared types in sync with the backend
API schemas described in src/models/api/.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import sys
import types
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union, get_args, get_origin
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic.fields import FieldInfo

from pydantic import BaseModel

DEFAULT_OUTPUT_PATH = Path("src/web/types/generated.ts")
OUTPUT_PATH = DEFAULT_OUTPUT_PATH

PRIMITIVE_TYPE_MAP: dict[type[object], str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
    datetime: "string",
    date: "string",
    UUID: "string",
}


def _load_models(module_path: str) -> Sequence[type[BaseModel]]:
    module = importlib.import_module(module_path)
    models: list[type[BaseModel]] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        # Only include Pydantic BaseModel subclasses for now
        # TypedDict support needs more work for generic types
        if issubclass(obj, BaseModel) and obj is not BaseModel:
            generic_metadata = getattr(obj, "__pydantic_generic_metadata__", None)
            if isinstance(generic_metadata, dict) and generic_metadata.get("args"):
                continue
            models.append(obj)
    return models


UNION_TYPES = (Union, types.UnionType)


def _discover_default_modules(repo_root: Path) -> list[str]:
    base_dir = repo_root / "src/models/api"
    modules: list[str] = []
    if base_dir.exists():
        for path in base_dir.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            rel = path.with_suffix("").relative_to(repo_root)
            modules.append(".".join(rel.parts))

    # Include shared data discovery parameter models used by generated contracts.
    discovery_parameters = "src.domain.entities.data_discovery_parameters"
    if discovery_parameters not in modules:
        modules.append(discovery_parameters)

    return sorted(set(modules))


def _parse_args(default_modules: list[str]) -> tuple[list[str], argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description="Generate TypeScript types from platform Pydantic models.",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help=(
            "Module path to include (e.g., artana_evidence_db.service_contracts). "
            "When provided, only the specified modules are loaded."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Destination file for generated TypeScript types.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated output does not match the current file.",
    )
    args = parser.parse_args()
    modules = sorted(set(args.module)) if args.module else default_modules
    return modules, args


def _ts_type_from_string(annotation: str) -> str:
    """Handle string type annotations."""
    if annotation == "JSONObject":
        return "JSONObject"
    if annotation == "JSONValue":
        return "JSONValue"
    if annotation == "JSONArray":
        return "JSONArray"
    if annotation.startswith("list["):
        inner_type = annotation[5:-1]  # Extract inner type from list[T]
        return f"{inner_type}[]"
    if annotation.startswith("dict["):
        return "Record<string, unknown>"
    return annotation


def _ts_type_from_literal_value(value: object) -> str:
    """Render a Python literal value as a TypeScript literal."""
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    return "unknown"


def _ts_type_from_origin(origin: object, args: tuple[object, ...]) -> str:
    """Handle generic types with an origin."""
    if origin is Literal:
        values = {_ts_type_from_literal_value(arg) for arg in args}
        return " | ".join(sorted(values)) if values else "unknown"

    if origin in (list, tuple, set, frozenset):
        inner = _ts_type(args[0]) if args else "unknown"
        return (
            f"{inner}[]"
            if origin is not tuple
            else "[" + ", ".join(_ts_type(arg) for arg in args) + "]"
        )

    if origin in (dict,):
        key_type = _ts_type(args[0]) if args else "string"
        value_type = _ts_type(args[1]) if len(args) > 1 else "unknown"
        if key_type != "string":
            key_type = "string"
        return f"Record<{key_type}, {value_type}>"

    if origin in UNION_TYPES:
        ts_parts = []
        include_null = False
        for arg in args:
            if arg is type(None):
                include_null = True
            else:
                ts_parts.append(_ts_type(arg))
        union = " | ".join(sorted(set(ts_parts))) or "unknown"
        return f"{union} | null" if include_null else union

    # Fallback for unknown origins
    return "unknown"


def _ts_type(annotation: object) -> str:
    """Convert Python/Pydantic type to TypeScript type."""
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        return _ts_type_from_origin(origin, args)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__

    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        values = [repr(member.value) for member in annotation]
        return " | ".join(values) if values else "string"

    if isinstance(annotation, str):
        return _ts_type_from_string(annotation)

    if isinstance(annotation, type):
        return PRIMITIVE_TYPE_MAP.get(annotation, "unknown")

    return "unknown"


def _render_field(name: str, field: FieldInfo) -> str:
    optional = "?" if not field.is_required() else ""
    ts_type = _ts_type(field.annotation)
    return f"  {name}{optional}: {ts_type};"


def _render_interface(model: type[BaseModel]) -> str:
    # Special handling for known generic response types
    if model.__name__ == "PaginatedResponse":
        return _render_paginated_response_interface()

    lines = [f"export interface {model.__name__} {{"]
    for field_name, field in model.model_fields.items():
        lines.append(_render_field(field_name, field))
    lines.append("}")
    return "\n".join(lines)


def _render_paginated_response_interface() -> str:
    """Special handling for PaginatedResponse to preserve generic type information."""
    return """export interface PaginatedResponse<T = unknown> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}"""


def _render_typescript_output(models: list[type[BaseModel]]) -> str:
    contents = [
        "// Auto-generated by scripts/generate_ts_types.py. Do not edit.",
        "/* eslint-disable */",
        "/* prettier-ignore */",
        "",
        "export type JSONValue = string | number | boolean | null | JSONArray | JSONObject;",
        "export type JSONObject = { [key: string]: JSONValue };",
        "export type JSONArray = JSONValue[];",
        "",
    ]

    models.sort(key=lambda x: x.__name__)

    for model in models:
        contents.append(_render_interface(model))
        contents.append("")
    return "\n".join(contents).rstrip() + "\n"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for path in (repo_root, repo_root / "services"):
        resolved = str(path)
        if resolved not in sys.path:
            sys.path.append(resolved)

    module_names, args = _parse_args(_discover_default_modules(repo_root))
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    display_path = (
        output_path.relative_to(repo_root)
        if output_path.is_relative_to(repo_root)
        else output_path
    )

    models: list[type[BaseModel]] = []
    seen_models: set[type[BaseModel]] = set()
    for module in module_names:
        for model in _load_models(module):
            if model not in seen_models:
                seen_models.add(model)
                models.append(model)

    if not models:
        msg = "No Pydantic models discovered for TypeScript generation"
        raise RuntimeError(msg)

    rendered_output = _render_typescript_output(models)
    if args.check:
        current_output = (
            output_path.read_text(encoding="utf-8") if output_path.exists() else None
        )
        if current_output != rendered_output:
            msg = (
                "TypeScript type output is out of date. "
                f"Run scripts/generate_ts_types.py --output {display_path}"
            )
            raise SystemExit(msg)
        print(f"✅ TypeScript types are up to date at {display_path}")  # noqa: T201
        return

    output_path.write_text(rendered_output, encoding="utf-8")
    print(f"✅ Wrote TypeScript types to {display_path}")  # noqa: T201


if __name__ == "__main__":
    main()
