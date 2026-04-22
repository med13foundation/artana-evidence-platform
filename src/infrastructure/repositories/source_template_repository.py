"""
SQLAlchemy implementation of the SourceTemplate repository.

Provides persistence and query operations for reusable data source templates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, or_, select

from src.domain.repositories.source_template_repository import (
    SourceTemplateRepository,
)
from src.infrastructure.mappers.source_template_mapper import SourceTemplateMapper
from src.models.database.source_template import (
    SourceTemplateModel,
    SourceTypeEnum,
    TemplateCategoryEnum,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnElement

    from src.domain.entities.source_template import SourceTemplate, TemplateCategory
    from src.domain.entities.user_data_source import SourceType
    from src.type_definitions.common import JSONObject


class SqlAlchemySourceTemplateRepository(SourceTemplateRepository):
    """SQLAlchemy-backed repository for SourceTemplate entities."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            error = "Session not provided"
            raise ValueError(error)
        return self._session

    def save(self, template: SourceTemplate) -> SourceTemplate:
        model = self.session.get(SourceTemplateModel, str(template.id))
        if model is None:
            model = SourceTemplateMapper.to_model(template)
            self.session.add(model)
        else:
            SourceTemplateMapper.update_model(model, template)
        self.session.commit()
        self.session.refresh(model)
        return SourceTemplateMapper.to_domain(model)

    def find_by_id(self, template_id: UUID) -> SourceTemplate | None:
        model = self.session.get(SourceTemplateModel, str(template_id))
        return SourceTemplateMapper.to_domain(model) if model else None

    def find_by_creator(
        self,
        creator_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(SourceTemplateModel.created_by == str(creator_id))
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_public_templates(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(SourceTemplateModel.is_public.is_(True))
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_by_category(
        self,
        category: TemplateCategory,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(
                SourceTemplateModel.category == TemplateCategoryEnum(category.value),
            )
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_by_source_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(
                SourceTemplateModel.source_type == SourceTypeEnum(source_type.value),
            )
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_approved_templates(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(SourceTemplateModel.is_approved.is_(True))
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_by_tag(
        self,
        tag: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(SourceTemplateModel.tags.contains([tag]))
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def search_by_name(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .where(SourceTemplateModel.name.ilike(f"%{query}%"))
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def find_available_for_user(
        self,
        user_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        condition: ColumnElement[bool] = SourceTemplateModel.is_public.is_(True)
        if user_id:
            condition = or_(
                SourceTemplateModel.is_public.is_(True),
                SourceTemplateModel.created_by == str(user_id),
            )

        stmt = (
            select(SourceTemplateModel)
            .where(condition)
            .order_by(desc(SourceTemplateModel.updated_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def increment_usage(self, template_id: UUID) -> SourceTemplate | None:
        model = self.session.get(SourceTemplateModel, str(template_id))
        if model is None:
            return None
        model.usage_count += 1
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return SourceTemplateMapper.to_domain(model)

    def update_success_rate(
        self,
        template_id: UUID,
        success_rate: float,
    ) -> SourceTemplate | None:
        model = self.session.get(SourceTemplateModel, str(template_id))
        if model is None:
            return None
        model.success_rate = success_rate
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return SourceTemplateMapper.to_domain(model)

    def approve_template(self, template_id: UUID) -> SourceTemplate | None:
        model = self.session.get(SourceTemplateModel, str(template_id))
        if model is None:
            return None
        model.is_approved = True
        model.approved_at = datetime.now(UTC).isoformat(timespec="seconds")
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return SourceTemplateMapper.to_domain(model)

    def make_public(self, template_id: UUID) -> SourceTemplate | None:
        model = self.session.get(SourceTemplateModel, str(template_id))
        if model is None:
            return None
        model.is_public = True
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return SourceTemplateMapper.to_domain(model)

    def delete(self, template_id: UUID) -> bool:
        model = self.session.get(SourceTemplateModel, str(template_id))
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def count_by_creator(self, creator_id: UUID) -> int:
        stmt = select(func.count()).where(
            SourceTemplateModel.created_by == str(creator_id),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_by_category(self, category: TemplateCategory) -> int:
        stmt = select(func.count()).where(
            SourceTemplateModel.category == TemplateCategoryEnum(category.value),
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_public_templates(self) -> int:
        stmt = select(func.count()).where(SourceTemplateModel.is_public.is_(True))
        return int(self.session.execute(stmt).scalar_one())

    def exists(self, template_id: UUID) -> bool:
        stmt = select(func.count()).where(SourceTemplateModel.id == str(template_id))
        return bool(self.session.execute(stmt).scalar_one())

    def get_popular_templates(self, limit: int = 10) -> list[SourceTemplate]:
        stmt = (
            select(SourceTemplateModel)
            .order_by(desc(SourceTemplateModel.usage_count))
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [SourceTemplateMapper.to_domain(model) for model in results]

    def get_template_statistics(self) -> JSONObject:
        total_stmt = select(func.count()).select_from(SourceTemplateModel)
        public_stmt = select(func.count()).where(
            SourceTemplateModel.is_public.is_(True),
        )
        approved_stmt = select(func.count()).where(
            SourceTemplateModel.is_approved.is_(True),
        )
        usage_sum_stmt = select(
            func.coalesce(func.sum(SourceTemplateModel.usage_count), 0),
        )
        success_avg_stmt = select(
            func.coalesce(func.avg(SourceTemplateModel.success_rate), 0.0),
        )

        return {
            "total_templates": int(self.session.execute(total_stmt).scalar_one()),
            "public_templates": int(self.session.execute(public_stmt).scalar_one()),
            "approved_templates": int(
                self.session.execute(approved_stmt).scalar_one(),
            ),
            "total_usage": int(self.session.execute(usage_sum_stmt).scalar_one()),
            "average_success_rate": float(
                self.session.execute(success_avg_stmt).scalar_one(),
            ),
        }
