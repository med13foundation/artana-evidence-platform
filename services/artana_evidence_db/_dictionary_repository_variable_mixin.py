"""Variable, value-set, and resolution-policy dictionary repository helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.dictionary_support import DomainContextResolver
from artana_evidence_db.kernel_dictionary_models import (
    EntityResolutionPolicyModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from artana_evidence_db.kernel_domain_models import (
    EntityResolutionPolicy,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

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


def _normalize_synonyms(synonyms: list[str] | None) -> list[str]:
    if synonyms is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in synonyms:
        synonym = raw.strip()
        if not synonym:
            continue
        key = synonym.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(synonym)
    return normalized


def _domain_context_scope(domain_context: str | None) -> set[str] | None:
    normalized = DomainContextResolver.normalize(domain_context)
    if normalized is None:
        return None
    if normalized == DomainContextResolver.GENERAL_DEFAULT_DOMAIN:
        return {normalized}
    return {normalized, DomainContextResolver.GENERAL_DEFAULT_DOMAIN}


class GraphDictionaryRepositoryVariableMixin:
    """Provide variable, value-set, and resolution-policy repository operations."""

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

    def _ensure_domain_context_reference(self, domain_context: str) -> str:
        raise NotImplementedError

    def _ensure_sensitivity_reference(self, sensitivity: str) -> str:
        raise NotImplementedError

    # ── Variable definitions ──────────────────────────────────────────

    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        model = self._session.get(VariableDefinitionModel, variable_id)
        return VariableDefinition.model_validate(model) if model is not None else None

    def find_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[VariableDefinition]:
        stmt = select(VariableDefinitionModel)
        if not include_inactive:
            stmt = stmt.where(VariableDefinitionModel.is_active.is_(True))
        if domain_context is not None:
            stmt = stmt.where(
                VariableDefinitionModel.domain_context == domain_context,
            )
        if data_type is not None:
            stmt = stmt.where(VariableDefinitionModel.data_type == data_type)
        stmt = stmt.order_by(VariableDefinitionModel.canonical_name)
        return [
            VariableDefinition.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_variable_by_synonym(
        self,
        synonym: str,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> VariableDefinition | None:
        normalized_synonym = synonym.strip().lower()
        if not normalized_synonym:
            return None
        domain_context_scope = _domain_context_scope(domain_context)
        stmt = (
            select(VariableDefinitionModel)
            .join(VariableSynonymModel)
            .where(VariableSynonymModel.synonym == normalized_synonym)
        )
        if domain_context_scope is not None:
            stmt = stmt.where(
                VariableDefinitionModel.domain_context.in_(domain_context_scope),
            )
        if not include_inactive:
            stmt = stmt.where(
                and_(
                    VariableDefinitionModel.is_active.is_(True),
                    VariableSynonymModel.is_active.is_(True),
                ),
            )
        # Keep synonym resolution deterministic if historical duplicates exist.
        stmt = stmt.order_by(
            VariableSynonymModel.id.asc(),
            VariableDefinitionModel.id.asc(),
        )
        model = self._session.scalars(stmt).first()
        return VariableDefinition.model_validate(model) if model is not None else None

    def create_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str = "general",
        sensitivity: str = "INTERNAL",
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> VariableDefinition:
        normalized_data_type = self._ensure_data_type_reference(data_type)
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )
        normalized_sensitivity = self._ensure_sensitivity_reference(sensitivity)

        existing_by_id = self._session.get(VariableDefinitionModel, variable_id)
        if existing_by_id is not None:
            return VariableDefinition.model_validate(existing_by_id)

        existing_by_canonical = self._session.scalars(
            select(VariableDefinitionModel).where(
                VariableDefinitionModel.canonical_name == canonical_name,
            ),
        ).first()
        if existing_by_canonical is not None:
            return VariableDefinition.model_validate(existing_by_canonical)

        model = VariableDefinitionModel(
            id=variable_id,
            canonical_name=canonical_name,
            display_name=display_name,
            data_type=normalized_data_type,
            domain_context=normalized_domain_context,
            sensitivity=normalized_sensitivity,
            preferred_unit=preferred_unit,
            constraints=constraints or {},
            description=description,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=embedding_model,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        try:
            self._session.add(model)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing_after_conflict = self._session.scalars(
                select(VariableDefinitionModel).where(
                    or_(
                        VariableDefinitionModel.id == variable_id,
                        VariableDefinitionModel.canonical_name == canonical_name,
                    ),
                ),
            ).first()
            if existing_after_conflict is not None:
                return VariableDefinition.model_validate(existing_after_conflict)
            raise
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return VariableDefinition.model_validate(model)

    def set_variable_embedding(  # noqa: PLR0913
        self,
        variable_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> VariableDefinition:
        model = self._session.get(VariableDefinitionModel, variable_id)
        if model is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return VariableDefinition.model_validate(model)

    def create_synonym(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> VariableSynonym:
        normalized_synonym = synonym.strip().lower()
        if not normalized_synonym:
            msg = "synonym is required"
            raise ValueError(msg)

        normalized_source = source.strip() if isinstance(source, str) else source
        if normalized_source == "":
            normalized_source = None
        if isinstance(normalized_source, str):
            normalized_source = normalized_source[:64]

        conflicting_synonym_stmt = select(VariableSynonymModel).where(
            VariableSynonymModel.synonym == normalized_synonym,
            VariableSynonymModel.variable_id != variable_id,
            VariableSynonymModel.is_active.is_(True),
        )
        conflicting_synonym = self._session.scalars(conflicting_synonym_stmt).first()
        if conflicting_synonym is not None:
            msg = (
                f"Synonym '{normalized_synonym}' is already mapped to variable "
                f"'{conflicting_synonym.variable_id}'"
            )
            raise ValueError(msg)

        existing_stmt = select(VariableSynonymModel).where(
            VariableSynonymModel.variable_id == variable_id,
            VariableSynonymModel.synonym == normalized_synonym,
        )
        existing = self._session.scalars(existing_stmt).first()
        if existing is not None:
            return VariableSynonym.model_validate(existing)

        model = VariableSynonymModel(
            variable_id=variable_id,
            synonym=normalized_synonym,
            source=normalized_source,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        try:
            self._session.add(model)
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            existing_after_conflict = self._session.scalars(existing_stmt).first()
            if existing_after_conflict is not None:
                return VariableSynonym.model_validate(existing_after_conflict)
            conflicting_after_conflict = self._session.scalars(
                conflicting_synonym_stmt,
            ).first()
            if conflicting_after_conflict is not None:
                msg = (
                    f"Synonym '{normalized_synonym}' is already mapped to variable "
                    f"'{conflicting_after_conflict.variable_id}'"
                )
                raise ValueError(msg) from exc
            raise
        self._record_change(
            table_name=VariableSynonymModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return VariableSynonym.model_validate(model)

    def set_variable_review_status(
        self,
        variable_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> VariableDefinition:
        model = self._session.get(VariableDefinitionModel, variable_id)
        if model is None:
            msg = f"Variable '{variable_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.review_status = review_status
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        if review_status == "REVOKED":
            model.is_active = False
            model.valid_to = datetime.now(UTC)
            model.revocation_reason = revocation_reason
        else:
            model.is_active = True
            model.valid_to = None
            model.revocation_reason = None
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return VariableDefinition.model_validate(model)

    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> VariableDefinition:
        return self.set_variable_review_status(
            variable_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def create_value_set(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        variable_id: str,
        name: str,
        description: str | None = None,
        external_ref: str | None = None,
        is_extensible: bool = False,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> ValueSet:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            msg = "value_set_id is required"
            raise ValueError(msg)
        normalized_variable_id = variable_id.strip()
        if not normalized_variable_id:
            msg = "variable_id is required"
            raise ValueError(msg)
        normalized_name = name.strip()
        if not normalized_name:
            msg = "name is required"
            raise ValueError(msg)

        model = ValueSetModel(
            id=normalized_value_set_id,
            variable_id=normalized_variable_id,
            variable_data_type="CODED",
            name=normalized_name,
            description=description,
            external_ref=external_ref,
            is_extensible=is_extensible,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ValueSetModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return ValueSet.model_validate(model)

    def get_value_set(self, value_set_id: str) -> ValueSet | None:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            return None
        model = self._session.get(ValueSetModel, normalized_value_set_id)
        return ValueSet.model_validate(model) if model is not None else None

    def find_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]:
        stmt = select(ValueSetModel)
        if variable_id is not None:
            stmt = stmt.where(ValueSetModel.variable_id == variable_id)
        stmt = stmt.order_by(ValueSetModel.id)
        models = self._session.scalars(stmt).all()
        return [ValueSet.model_validate(model) for model in models]

    def create_value_set_item(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        code: str,
        display_label: str,
        synonyms: list[str] | None = None,
        external_ref: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> ValueSetItem:
        normalized_value_set_id = value_set_id.strip()
        if not normalized_value_set_id:
            msg = "value_set_id is required"
            raise ValueError(msg)
        normalized_code = code.strip()
        if not normalized_code:
            msg = "code is required"
            raise ValueError(msg)
        normalized_label = display_label.strip()
        if not normalized_label:
            msg = "display_label is required"
            raise ValueError(msg)

        model = ValueSetItemModel(
            value_set_id=normalized_value_set_id,
            code=normalized_code,
            display_label=normalized_label,
            synonyms=_normalize_synonyms(synonyms),
            external_ref=external_ref,
            sort_order=sort_order,
            is_active=is_active,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ValueSetItemModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return ValueSetItem.model_validate(model)

    def find_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]:
        stmt = select(ValueSetItemModel).where(
            ValueSetItemModel.value_set_id == value_set_id,
        )
        if not include_inactive:
            stmt = stmt.where(ValueSetItemModel.is_active.is_(True))
        stmt = stmt.order_by(ValueSetItemModel.sort_order, ValueSetItemModel.id)
        models = self._session.scalars(stmt).all()
        return [ValueSetItem.model_validate(model) for model in models]

    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> ValueSetItem:
        model = self._session.get(ValueSetItemModel, value_set_item_id)
        if model is None:
            msg = f"Value set item '{value_set_item_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.is_active = is_active
        model.review_status = "ACTIVE" if is_active else "REVOKED"
        model.reviewed_by = reviewed_by
        model.reviewed_at = datetime.now(UTC)
        model.revocation_reason = revocation_reason if not is_active else None
        self._session.flush()
        self._record_change(
            table_name=ValueSetItemModel.__tablename__,
            record_id=str(model.id),
            action="UPDATE" if is_active else "REVOKE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return ValueSetItem.model_validate(model)

    # ── Entity resolution policies ────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
        *,
        include_inactive: bool = False,
    ) -> EntityResolutionPolicy | None:
        stmt = select(EntityResolutionPolicyModel).where(
            EntityResolutionPolicyModel.entity_type == entity_type,
        )
        if not include_inactive:
            stmt = stmt.where(EntityResolutionPolicyModel.is_active.is_(True))
        model = self._session.scalars(stmt).first()
        return (
            EntityResolutionPolicy.model_validate(model) if model is not None else None
        )

    def find_resolution_policies(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[EntityResolutionPolicy]:
        stmt = select(EntityResolutionPolicyModel)
        if not include_inactive:
            stmt = stmt.where(EntityResolutionPolicyModel.is_active.is_(True))
        models = self._session.scalars(
            stmt.order_by(
                EntityResolutionPolicyModel.entity_type,
            ),
        ).all()
        return [EntityResolutionPolicy.model_validate(model) for model in models]

    def create_resolution_policy(  # noqa: PLR0913
        self,
        *,
        entity_type: str,
        policy_strategy: str,
        required_anchors: list[str],
        auto_merge_threshold: float = 1.0,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> EntityResolutionPolicy:
        normalized_entity_type = entity_type.strip().upper()
        existing_policy = self._session.get(
            EntityResolutionPolicyModel,
            normalized_entity_type,
        )
        if existing_policy is not None:
            return EntityResolutionPolicy.model_validate(existing_policy)

        model = EntityResolutionPolicyModel(
            entity_type=normalized_entity_type,
            policy_strategy=policy_strategy.strip().upper(),
            required_anchors=[str(anchor).strip() for anchor in required_anchors],
            auto_merge_threshold=max(float(auto_merge_threshold), 0.0),
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        try:
            self._session.add(model)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing_after_conflict = self._session.get(
                EntityResolutionPolicyModel,
                normalized_entity_type,
            )
            if existing_after_conflict is not None:
                return EntityResolutionPolicy.model_validate(existing_after_conflict)
            raise
        self._record_change(
            table_name=EntityResolutionPolicyModel.__tablename__,
            record_id=model.entity_type,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return EntityResolutionPolicy.model_validate(model)


__all__ = ["GraphDictionaryRepositoryVariableMixin"]
