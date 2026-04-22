"""
Artana Resource Library - SQLAlchemy Base Configuration
Database foundation with type safety and audit capabilities.
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# Naming convention for constraints and indexes
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """Base class for all database models with audit fields."""

    metadata = metadata
    type_annotation_map: ClassVar[dict[type, object]] = {
        str: str,  # Ensure strings are not converted to Text
    }

    # Audit fields - automatically managed
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        doc="Record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        doc="Last update timestamp",
    )

    def __repr__(self) -> str:
        """String representation of the model instance."""
        return f"<{self.__class__.__name__}(id={getattr(self, 'id', None)})>"
