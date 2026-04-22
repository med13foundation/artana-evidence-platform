"""SQLAlchemy implementation for data source activation policies."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from sqlalchemy import select
from sqlalchemy.orm import Session  # noqa: TC002

from src.domain.entities.data_source_activation import (
    ActivationScope,
    DataSourceActivation,
    PermissionLevel,
)
from src.domain.repositories.data_source_activation_repository import (
    DataSourceActivationRepository,
)
from src.models.database.data_source_activation import (
    ActivationScopeEnum,
    DataSourceActivationModel,
    PermissionLevelEnum,
)


class SqlAlchemyDataSourceActivationRepository(DataSourceActivationRepository):
    """SQLAlchemy-backed activation policy repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_domain(model: DataSourceActivationModel) -> DataSourceActivation:
        return DataSourceActivation(
            id=UUID(str(model.id)),
            catalog_entry_id=model.catalog_entry_id,
            scope=ActivationScope(model.scope.value),
            permission_level=PermissionLevel(model.permission_level.value),
            research_space_id=(
                UUID(str(model.research_space_id)) if model.research_space_id else None
            ),
            updated_by=UUID(str(model.updated_by)),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def get_rule(
        self,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation | None:
        stmt = select(DataSourceActivationModel).where(
            DataSourceActivationModel.catalog_entry_id == catalog_entry_id,
            DataSourceActivationModel.scope == ActivationScopeEnum(scope.value),
        )
        if scope == ActivationScope.RESEARCH_SPACE:
            stmt = stmt.where(
                DataSourceActivationModel.research_space_id == str(research_space_id),
            )
        else:
            stmt = stmt.where(DataSourceActivationModel.research_space_id.is_(None))

        model = self._session.execute(stmt).scalar_one_or_none()
        return self._to_domain(model) if model else None

    def list_rules_for_source(
        self,
        catalog_entry_id: str,
    ) -> list[DataSourceActivation]:
        stmt = select(DataSourceActivationModel).where(
            DataSourceActivationModel.catalog_entry_id == catalog_entry_id,
        )
        models = self._session.execute(stmt).scalars().all()
        return [self._to_domain(model) for model in models]

    def list_rules_for_sources(
        self,
        catalog_entry_ids: list[str],
    ) -> dict[str, list[DataSourceActivation]]:
        if not catalog_entry_ids:
            return {}

        stmt = select(DataSourceActivationModel).where(
            DataSourceActivationModel.catalog_entry_id.in_(catalog_entry_ids),
        )
        models = self._session.execute(stmt).scalars().all()
        rules_by_source: dict[str, list[DataSourceActivation]] = {}
        for model in models:
            rules_by_source.setdefault(model.catalog_entry_id, []).append(
                self._to_domain(model),
            )
        return rules_by_source

    def set_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        permission_level: PermissionLevel,
        updated_by: UUID,
        research_space_id: UUID | None = None,
    ) -> DataSourceActivation:
        existing = self.get_rule(catalog_entry_id, scope, research_space_id)
        if existing:
            model = self._session.get(DataSourceActivationModel, str(existing.id))
            if model is None:
                msg = "Activation rule disappeared during update"
                raise RuntimeError(msg)
            model.permission_level = PermissionLevelEnum(permission_level.value)
            model.is_active = permission_level != PermissionLevel.BLOCKED
            model.updated_by = str(updated_by)
        else:
            research_space_value = str(research_space_id) if research_space_id else None
            model = DataSourceActivationModel(
                catalog_entry_id=catalog_entry_id,
                scope=ActivationScopeEnum(scope.value),
                research_space_id=research_space_value,
                permission_level=PermissionLevelEnum(permission_level.value),
                is_active=permission_level != PermissionLevel.BLOCKED,
                updated_by=str(updated_by),
            )
            self._session.add(model)

        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def delete_rule(
        self,
        *,
        catalog_entry_id: str,
        scope: ActivationScope,
        research_space_id: UUID | None = None,
    ) -> None:
        stmt = select(DataSourceActivationModel).where(
            DataSourceActivationModel.catalog_entry_id == catalog_entry_id,
            DataSourceActivationModel.scope == ActivationScopeEnum(scope.value),
        )
        if scope == ActivationScope.RESEARCH_SPACE:
            stmt = stmt.where(
                DataSourceActivationModel.research_space_id == str(research_space_id),
            )
        else:
            stmt = stmt.where(DataSourceActivationModel.research_space_id.is_(None))

        model = self._session.execute(stmt).scalar_one_or_none()
        if model:
            self._session.delete(model)
            self._session.commit()
