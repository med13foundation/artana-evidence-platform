"""
SQLAlchemy repository implementations for storage configurations and operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import and_, case, func, select

from src.domain.repositories.storage_repository import (
    StorageConfigurationRepository,
    StorageOperationRepository,
)
from src.infrastructure.mappers.storage_mapper import StorageMapper
from src.models.database.storage import (
    StorageConfigurationModel,
    StorageHealthSnapshotModel,
    StorageOperationModel,
    StorageOperationStatusEnum,
    StorageOperationTypeEnum,
)
from src.type_definitions.storage import (
    StorageOperationRecord,
    StorageProviderTestResult,
    StorageUsageMetrics,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.domain.entities.storage_configuration import (
        StorageConfiguration,
        StorageHealthSnapshot,
        StorageOperation,
    )
    from src.type_definitions.common import JSONObject


class SqlAlchemyStorageConfigurationRepository(StorageConfigurationRepository):
    """SQLAlchemy implementation of the storage configuration repository."""

    def __init__(self, session: Session):
        self._session = session

    def create(self, configuration: StorageConfiguration) -> StorageConfiguration:
        model = StorageMapper.apply_configuration_to_model(configuration)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return StorageMapper.configuration_from_model(model)

    def update(self, configuration: StorageConfiguration) -> StorageConfiguration:
        model = self._session.get(StorageConfigurationModel, str(configuration.id))
        if model is None:
            msg = f"Storage configuration {configuration.id} not found"
            raise ValueError(msg)
        StorageMapper.apply_configuration_to_model(configuration, model=model)
        self._session.commit()
        self._session.refresh(model)
        return StorageMapper.configuration_from_model(model)

    def get_by_id(self, configuration_id: UUID) -> StorageConfiguration | None:
        model = self._session.get(StorageConfigurationModel, str(configuration_id))
        if model is None:
            return None
        return StorageMapper.configuration_from_model(model)

    def list_configurations(
        self,
        *,
        include_disabled: bool = False,
    ) -> list[StorageConfiguration]:
        stmt = select(StorageConfigurationModel)
        if not include_disabled:
            stmt = stmt.where(StorageConfigurationModel.enabled.is_(True))
        results = self._session.execute(stmt).scalars().all()
        return [StorageMapper.configuration_from_model(model) for model in results]

    def paginate_configurations(
        self,
        *,
        include_disabled: bool = False,
        page: int = 1,
        per_page: int = 25,
    ) -> tuple[list[StorageConfiguration], int]:
        page = max(page, 1)
        if per_page < 1:
            per_page = 25
        filter_clause = (
            StorageConfigurationModel.enabled.is_(True)
            if not include_disabled
            else None
        )
        stmt = select(StorageConfigurationModel)
        count_stmt = select(func.count()).select_from(StorageConfigurationModel)
        if filter_clause is not None:
            stmt = stmt.where(filter_clause)
            count_stmt = count_stmt.where(filter_clause)
        stmt = (
            stmt.order_by(StorageConfigurationModel.created_at.desc())
            .limit(per_page)
            .offset(
                (page - 1) * per_page,
            )
        )
        total = int(self._session.execute(count_stmt).scalar() or 0)
        models = self._session.execute(stmt).scalars().all()
        return (
            [StorageMapper.configuration_from_model(model) for model in models],
            total,
        )

    def delete(self, configuration_id: UUID) -> bool:
        model = self._session.get(StorageConfigurationModel, str(configuration_id))
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True


class SqlAlchemyStorageOperationRepository(StorageOperationRepository):
    """SQLAlchemy implementation for storage operation logs and health data."""

    def __init__(self, session: Session):
        self._session = session

    def record_operation(self, operation: StorageOperation) -> StorageOperationRecord:
        model = StorageMapper.operation_to_model(operation)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return StorageMapper.operation_record_from_model(model)

    def list_operations(
        self,
        configuration_id: UUID,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        stmt = (
            select(StorageOperationModel)
            .where(StorageOperationModel.configuration_id == str(configuration_id))
            .order_by(StorageOperationModel.created_at.desc())
            .limit(limit)
        )
        results = self._session.execute(stmt).scalars().all()
        return [StorageMapper.operation_record_from_model(model) for model in results]

    def list_failed_store_operations(
        self,
        *,
        limit: int = 100,
    ) -> list[StorageOperationRecord]:
        stmt = (
            select(StorageOperationModel)
            .where(
                StorageOperationModel.operation_type
                == StorageOperationTypeEnum.STORE.value,
                StorageOperationModel.status == StorageOperationStatusEnum.FAILED.value,
            )
            .order_by(StorageOperationModel.created_at.desc())
            .limit(limit)
        )
        results = self._session.execute(stmt).scalars().all()
        return [StorageMapper.operation_record_from_model(model) for model in results]

    def update_operation_metadata(
        self,
        operation_id: UUID,
        metadata: JSONObject,
    ) -> StorageOperationRecord:
        model = self._session.get(StorageOperationModel, str(operation_id))
        if model is None:
            msg = f"Storage operation {operation_id} not found"
            raise ValueError(msg)
        model.metadata_payload = metadata
        self._session.commit()
        self._session.refresh(model)
        return StorageMapper.operation_record_from_model(model)

    def upsert_health_snapshot(
        self,
        snapshot: StorageHealthSnapshot,
    ) -> StorageHealthSnapshot:
        model = self._session.get(
            StorageHealthSnapshotModel,
            str(snapshot.configuration_id),
        )
        instance = StorageMapper.apply_health_snapshot_to_model(snapshot, model=model)
        self._session.add(instance)
        self._session.commit()
        return snapshot

    def get_health_snapshot(
        self,
        configuration_id: UUID,
    ) -> StorageHealthSnapshot | None:
        model = self._session.get(
            StorageHealthSnapshotModel,
            str(configuration_id),
        )
        if model is None:
            return None
        return StorageMapper.health_snapshot_from_model(model)

    def record_test_result(
        self,
        result: StorageProviderTestResult,
    ) -> StorageProviderTestResult:
        model = StorageOperationModel(
            id=str(uuid4()),
            configuration_id=str(result.configuration_id),
            user_id=None,
            operation_type=StorageOperationTypeEnum.TEST.value,
            key="connection_test",
            file_size_bytes=None,
            status=(
                StorageOperationStatusEnum.SUCCESS.value
                if result.success
                else StorageOperationStatusEnum.FAILED.value
            ),
            error_message=None if result.success else result.message,
            metadata_payload={
                "message": result.message,
                "capabilities": list(result.capabilities),
                "latency_ms": result.latency_ms,
                **result.metadata,
            },
        )
        model.created_at = result.checked_at
        model.updated_at = result.checked_at
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return result

    def get_usage_metrics(
        self,
        configuration_id: UUID,
    ) -> StorageUsageMetrics | None:
        stmt = select(
            func.count(StorageOperationModel.id).label("total_operations"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            StorageOperationModel.operation_type
                            == StorageOperationTypeEnum.STORE.value,
                            1,
                        ),
                        else_=0,
                    ),
                ),
                0,
            ).label("total_files"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                StorageOperationModel.operation_type
                                == StorageOperationTypeEnum.STORE.value,
                                StorageOperationModel.status
                                == StorageOperationStatusEnum.SUCCESS.value,
                            ),
                            StorageOperationModel.file_size_bytes,
                        ),
                        else_=0,
                    ),
                ),
                0,
            ).label("total_size_bytes"),
            func.max(StorageOperationModel.created_at).label("last_operation_at"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            StorageOperationModel.status
                            == StorageOperationStatusEnum.FAILED.value,
                            1,
                        ),
                        else_=0,
                    ),
                ),
                0,
            ).label("failed_operations"),
        ).where(StorageOperationModel.configuration_id == str(configuration_id))
        row = self._session.execute(stmt).one()
        total_operations = int(row.total_operations or 0)
        if total_operations == 0:
            return StorageUsageMetrics(
                configuration_id=configuration_id,
                total_files=0,
                total_size_bytes=0,
                last_operation_at=None,
                error_rate=0.0,
            )
        error_rate = (
            float(row.failed_operations) / float(total_operations)
            if total_operations
            else 0.0
        )
        return StorageUsageMetrics(
            configuration_id=configuration_id,
            total_files=int(row.total_files or 0),
            total_size_bytes=int(row.total_size_bytes or 0),
            last_operation_at=row.last_operation_at,
            error_rate=error_rate,
        )
