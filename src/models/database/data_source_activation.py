"""SQLAlchemy model for data source activation policies."""

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ActivationScopeEnum(str, Enum):
    """Scope types for activation policies."""

    GLOBAL = "global"
    RESEARCH_SPACE = "research_space"


class PermissionLevelEnum(str, Enum):
    """Permission levels controlling catalog behavior."""

    BLOCKED = "blocked"
    VISIBLE = "visible"
    AVAILABLE = "available"


class DataSourceActivationModel(Base):
    """SQLAlchemy persistence model for activation policies."""

    __tablename__ = "data_source_activation_rules"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    __table_args__ = (
        UniqueConstraint(
            "catalog_entry_id",
            "scope",
            "research_space_id",
            name="uq_data_source_activation_scope",
        ),
    )

    catalog_entry_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("source_catalog_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope: Mapped[ActivationScopeEnum] = mapped_column(
        SQLEnum(
            ActivationScopeEnum,
            name="activationscopeenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ActivationScopeEnum.GLOBAL,
        server_default=ActivationScopeEnum.GLOBAL.value,
        index=True,
    )
    research_space_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    permission_level: Mapped[PermissionLevelEnum] = mapped_column(
        SQLEnum(
            PermissionLevelEnum,
            name="data_source_permission_level",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PermissionLevelEnum.AVAILABLE,
        server_default=PermissionLevelEnum.AVAILABLE.value,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    updated_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
