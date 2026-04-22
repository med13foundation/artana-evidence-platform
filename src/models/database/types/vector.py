"""Custom SQLAlchemy type for pgvector-compatible embeddings.

Uses the native `VECTOR(n)` type on PostgreSQL and JSON arrays on non-Postgres
dialects for local tooling and test harnesses.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from sqlalchemy.types import TypeDecorator, UserDefinedType


class _PostgresVector(UserDefinedType[object]):
    """Minimal PostgreSQL VECTOR(n) type descriptor."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_kw: object) -> str:
        return f"VECTOR({self.dimensions})"


class VectorEmbedding(TypeDecorator[list[float] | None]):
    """Dialect-aware vector embedding column type."""

    impl = sa.JSON
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect: sa.Dialect) -> sa.types.TypeEngine[object]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PostgresVector(self.dimensions))
        return dialect.type_descriptor(sa.JSON())

    def process_bind_param(
        self,
        value: list[float] | tuple[float, ...] | None,
        dialect: sa.Dialect,
    ) -> str | list[float] | None:
        if value is None:
            return None

        normalized = [float(item) for item in value]
        if dialect.name == "postgresql":
            return "[" + ",".join(f"{item:.12g}" for item in normalized) + "]"
        return normalized

    def process_result_value(
        self,
        value: object,
        _dialect: sa.Dialect,
    ) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list | tuple):
            return [float(item) for item in value]
        if isinstance(value, memoryview):
            value = value.tobytes().decode("utf-8")
        if isinstance(value, bytes):
            value = value.decode("utf-8")

        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                stripped = stripped[1:-1].strip()
            if not stripped:
                return []

            # Handle JSON array payloads and vector string payloads.
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [float(item) for item in parsed]

            return [float(token) for token in stripped.split(",") if token.strip()]

        return None


__all__ = ["VectorEmbedding"]
