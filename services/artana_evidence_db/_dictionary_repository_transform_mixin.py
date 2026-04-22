"""Transform-registry helpers for the graph-service dictionary repository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_dictionary_models import TransformRegistryModel
from artana_evidence_db.kernel_domain_models import (
    TransformRegistry,
    TransformVerificationResult,
)
from artana_evidence_db.transform_runtime_support import (
    is_supported_transform,
    verify_transform_fixture,
)
from sqlalchemy import and_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]


def _to_json_value(value: object) -> JSONValue:  # noqa: PLR0911
    """Convert database values into JSON-compatible values."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, set):
        return [_to_json_value(item) for item in sorted(value, key=str)]
    return str(value)


def _snapshot_model(model: object) -> JSONObject:
    """Build a JSON-serializable snapshot of a SQLAlchemy model instance."""
    snapshot: JSONObject = {}
    for key, value in vars(model).items():
        if key.startswith("_"):
            continue
        snapshot[key] = _to_json_value(value)
    return snapshot


class GraphDictionaryRepositoryTransformMixin:
    """Provide transform-registry repository operations."""

    _session: Session

    def _record_change(  # noqa: PLR0913
        self,
        *,
        table_name: str,
        record_id: str,
        action: str,
        before_snapshot: JSONObject | None,
        after_snapshot: JSONObject | None,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> None:
        raise NotImplementedError

    def _ensure_data_type_reference(self, data_type: str) -> str:
        raise NotImplementedError

    def create_transform(  # noqa: PLR0913
        self,
        *,
        transform_id: str,
        input_unit: str,
        output_unit: str,
        implementation_ref: str,
        category: str = "UNIT_CONVERSION",
        input_data_type: str | None = None,
        output_data_type: str | None = None,
        is_deterministic: bool = True,
        is_production_allowed: bool = False,
        test_input: JSONValue | None = None,
        expected_output: JSONValue | None = None,
        description: str | None = None,
        status: str = "ACTIVE",
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> TransformRegistry:
        normalized_transform_id = transform_id.strip()
        if not normalized_transform_id:
            msg = "transform_id is required"
            raise ValueError(msg)
        normalized_input_unit = input_unit.strip()
        if not normalized_input_unit:
            msg = "input_unit is required"
            raise ValueError(msg)
        normalized_output_unit = output_unit.strip()
        if not normalized_output_unit:
            msg = "output_unit is required"
            raise ValueError(msg)
        normalized_impl_ref = implementation_ref.strip()
        if not normalized_impl_ref:
            msg = "implementation_ref is required"
            raise ValueError(msg)

        normalized_category = category.strip().upper()
        if normalized_category not in {
            "UNIT_CONVERSION",
            "NORMALIZATION",
            "DERIVATION",
        }:
            msg = f"Unsupported transform category: {category}"
            raise ValueError(msg)

        normalized_status = status.strip().upper()
        if not normalized_status:
            msg = "status is required"
            raise ValueError(msg)

        normalized_input_data_type = (
            self._ensure_data_type_reference(input_data_type)
            if input_data_type is not None
            else None
        )
        normalized_output_data_type = (
            self._ensure_data_type_reference(output_data_type)
            if output_data_type is not None
            else None
        )

        model = TransformRegistryModel(
            id=normalized_transform_id,
            input_unit=normalized_input_unit,
            output_unit=normalized_output_unit,
            category=normalized_category,
            input_data_type=normalized_input_data_type,
            output_data_type=normalized_output_data_type,
            implementation_ref=normalized_impl_ref,
            is_deterministic=is_deterministic,
            is_production_allowed=is_production_allowed,
            test_input=test_input,
            expected_output=expected_output,
            description=description,
            status=normalized_status,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=TransformRegistryModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return TransformRegistry.model_validate(model)

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
        *,
        include_inactive: bool = False,
        require_production: bool = False,
    ) -> TransformRegistry | None:
        stmt = select(TransformRegistryModel).where(
            and_(
                TransformRegistryModel.input_unit == input_unit,
                TransformRegistryModel.output_unit == output_unit,
                TransformRegistryModel.status == "ACTIVE",
            ),
        )
        if not include_inactive:
            stmt = stmt.where(TransformRegistryModel.is_active.is_(True))
        if require_production:
            stmt = stmt.where(TransformRegistryModel.is_production_allowed.is_(True))
        model = self._session.scalars(stmt).first()
        return TransformRegistry.model_validate(model) if model is not None else None

    def find_transforms(
        self,
        *,
        status: str = "ACTIVE",
        include_inactive: bool = False,
        production_only: bool = False,
    ) -> list[TransformRegistry]:
        stmt = select(TransformRegistryModel).where(
            TransformRegistryModel.status == status,
        )
        if not include_inactive:
            stmt = stmt.where(TransformRegistryModel.is_active.is_(True))
        if production_only:
            stmt = stmt.where(TransformRegistryModel.is_production_allowed.is_(True))
        return [
            TransformRegistry.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def verify_transform(self, transform_id: str) -> TransformVerificationResult:
        model = self._session.get(TransformRegistryModel, transform_id)
        checked_at = datetime.now(UTC)
        if model is None:
            msg = f"Transform '{transform_id}' not found"
            raise ValueError(msg)

        if model.test_input is None or model.expected_output is None:
            return TransformVerificationResult(
                transform_id=model.id,
                passed=False,
                message="Verification fixture is missing test_input and/or expected_output",
                actual_output=None,
                expected_output=model.expected_output,
                checked_at=checked_at,
            )

        if not is_supported_transform(model.implementation_ref):
            return TransformVerificationResult(
                transform_id=model.id,
                passed=False,
                message=(
                    "Unsupported implementation_ref; no runtime transform function "
                    "is registered"
                ),
                actual_output=None,
                expected_output=model.expected_output,
                checked_at=checked_at,
            )

        passed, message, actual_output = verify_transform_fixture(
            implementation_ref=model.implementation_ref,
            test_input=_to_json_value(model.test_input),
            expected_output=_to_json_value(model.expected_output),
        )
        return TransformVerificationResult(
            transform_id=model.id,
            passed=passed,
            message=message,
            actual_output=actual_output,
            expected_output=_to_json_value(model.expected_output),
            checked_at=checked_at,
        )

    def verify_all_transforms(
        self,
        *,
        status: str = "ACTIVE",
        include_inactive: bool = False,
    ) -> list[TransformVerificationResult]:
        stmt = select(TransformRegistryModel).where(
            TransformRegistryModel.status == status,
        )
        if not include_inactive:
            stmt = stmt.where(TransformRegistryModel.is_active.is_(True))
        models = self._session.scalars(stmt).all()
        return [
            self.verify_transform(model.id)
            for model in models
            if model.test_input is not None and model.expected_output is not None
        ]

    def promote_transform(
        self,
        transform_id: str,
        *,
        reviewed_by: str,
    ) -> TransformRegistry:
        model = self._session.get(TransformRegistryModel, transform_id)
        if model is None:
            msg = f"Transform '{transform_id}' not found"
            raise ValueError(msg)
        if not model.is_active:
            msg = f"Transform '{transform_id}' must be active to promote"
            raise ValueError(msg)

        verification_result = self.verify_transform(transform_id)
        if not verification_result.passed:
            msg = (
                f"Transform '{transform_id}' failed verification and cannot be promoted: "
                f"{verification_result.message}"
            )
            raise ValueError(msg)

        model.is_production_allowed = True
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.review_status = "ACTIVE"
        if model.revocation_reason:
            model.revocation_reason = None

        self._session.flush()
        return TransformRegistry.model_validate(model)


__all__ = ["GraphDictionaryRepositoryTransformMixin"]
