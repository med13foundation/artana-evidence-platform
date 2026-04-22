"""Service-local SQLAlchemy base and metadata configuration."""

from __future__ import annotations

from typing import ClassVar

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base class for graph-service ORM models."""

    metadata = metadata
    type_annotation_map: ClassVar[dict[type, object]] = {
        str: str,
    }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={getattr(self, 'id', None)})>"


__all__ = ["Base", "metadata"]
