"""Service-local SQLAlchemy implementation of graph governance dictionary storage."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from artana_evidence_db._dictionary_repository_constraints_merge_mixin import (
    GraphDictionaryRepositoryConstraintsMergeMixin,
)
from artana_evidence_db._dictionary_repository_transform_mixin import (
    GraphDictionaryRepositoryTransformMixin,
)
from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.dictionary_search import (
    search_dictionary_entries,
    search_dictionary_entries_by_domain,
)
from artana_evidence_db.dictionary_support import (
    DomainContextResolver,
    get_constraint_schema_for_data_type,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryChangelogModel,
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    DictionarySensitivityLevelModel,
    EntityResolutionPolicyModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from artana_evidence_db.kernel_domain_models import (
    DictionaryChangelog,
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    DictionarySearchResult,
    EntityResolutionPolicy,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
    VariableSynonym,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from artana_evidence_db.graph_domain_config import (
        BuiltinEntityTypeDefinition,
        BuiltinQualifierDefinition,
        BuiltinRelationConstraintDefinition,
        BuiltinRelationSynonymDefinition,
        BuiltinRelationTypeDefinition,
        DictionaryDomainContextDefinition,
    )
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]
_DATA_TYPE_HINTS: dict[str, tuple[str, str]] = {
    "INTEGER": ("int", "Whole-number value"),
    "FLOAT": ("float", "Decimal numeric value"),
    "STRING": ("str", "Free-form text"),
    "DATE": ("datetime", "Date/time value"),
    "CODED": ("str", "Enumerated coded value"),
    "BOOLEAN": ("bool", "True/False value"),
    "JSON": ("dict", "Structured JSON payload"),
}
_SENSITIVITY_DESCRIPTIONS: dict[str, str] = {
    "PUBLIC": "Data suitable for broad sharing",
    "INTERNAL": "Internal-only research data",
    "PHI": "Sensitive regulated patient data",
}


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


def _humanize(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("_", " ").split())


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


class GraphDictionaryRepository(
    GraphDictionaryRepositoryConstraintsMergeMixin,
    GraphDictionaryRepositoryTransformMixin,
):
    """Service-local SQLAlchemy implementation of the graph dictionary repository."""

    def __init__(
        self,
        session: Session,
        *,
        builtin_domain_contexts: tuple[DictionaryDomainContextDefinition, ...],
        builtin_entity_types: tuple[BuiltinEntityTypeDefinition, ...] = (),
        builtin_relation_types: tuple[BuiltinRelationTypeDefinition, ...] = (),
        builtin_relation_synonyms: tuple[BuiltinRelationSynonymDefinition, ...] = (),
        builtin_relation_constraints: tuple[
            BuiltinRelationConstraintDefinition,
            ...,
        ] = (),
        builtin_qualifier_definitions: tuple[
            BuiltinQualifierDefinition,
            ...,
        ] = (),
    ) -> None:
        self._session = session
        self._builtin_domain_contexts = builtin_domain_contexts
        self._builtin_entity_types = builtin_entity_types
        self._builtin_relation_types = builtin_relation_types
        self._builtin_relation_synonyms = builtin_relation_synonyms
        self._builtin_relation_constraints = builtin_relation_constraints
        self._builtin_qualifier_definitions = builtin_qualifier_definitions
        # Build in-memory wildcard constraint lookup (source_type, relation_type) → profile.
        # Wildcard target_type="*" entries can't be stored in the DB (FK on target_type).
        self._wildcard_constraints: dict[tuple[str, str], str] = {
            (c.source_type, c.relation_type): getattr(c, "profile", "FORBIDDEN")
            for c in builtin_relation_constraints
            if c.target_type == "*"
        }

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
        change = DictionaryChangelogModel(
            table_name=table_name,
            record_id=record_id,
            action=action,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            changed_by=changed_by,
            source_ref=source_ref,
        )
        self._session.add(change)

    def _ensure_data_type_reference(self, data_type: str) -> str:
        normalized = data_type.strip().upper()
        existing = self._session.get(DictionaryDataTypeModel, normalized)
        if existing is not None:
            if existing.constraint_schema == {}:
                existing.constraint_schema = get_constraint_schema_for_data_type(
                    normalized,
                )
                self._session.flush()
            return normalized

        python_type_hint, description = _DATA_TYPE_HINTS.get(
            normalized,
            ("str", "Autogenerated data type"),
        )
        self._session.add(
            DictionaryDataTypeModel(
                id=normalized,
                display_name=_humanize(normalized),
                python_type_hint=python_type_hint,
                description=description,
                constraint_schema=get_constraint_schema_for_data_type(normalized),
            ),
        )
        self._session.flush()
        return normalized

    def _ensure_domain_context_reference(self, domain_context: str) -> str:
        normalized = DomainContextResolver.normalize(domain_context)
        if normalized is None:
            msg = "domain_context is required"
            raise ValueError(msg)
        self._ensure_builtin_domain_contexts()

        existing = self._session.get(DictionaryDomainContextModel, normalized)
        if existing is None:
            msg = (
                f"Unknown domain_context '{normalized}'. "
                "Use an approved domain context from dictionary_domain_contexts."
            )
            raise ValueError(msg)

        if not existing.is_active:
            msg = f"domain_context '{normalized}' is inactive"
            raise ValueError(msg)

        return normalized

    def _ensure_builtin_domain_contexts(self) -> None:
        for definition in self._builtin_domain_contexts:
            existing = self._session.get(DictionaryDomainContextModel, definition.id)
            if existing is None:
                self._session.add(
                    DictionaryDomainContextModel(
                        id=definition.id,
                        display_name=definition.display_name,
                        description=definition.description,
                    ),
                )
                continue

            existing.display_name = definition.display_name
            existing.description = definition.description
            existing.is_active = True
            existing.valid_to = None
            existing.superseded_by = None
        self._session.flush()

    def list_domain_contexts(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[DictionaryDomainContext]:
        self._ensure_builtin_domain_contexts()
        stmt = select(DictionaryDomainContextModel).order_by(
            DictionaryDomainContextModel.id.asc(),
        )
        if not include_inactive:
            stmt = stmt.where(DictionaryDomainContextModel.is_active.is_(True))
        models = self._session.scalars(stmt).all()
        return [
            DictionaryDomainContext.model_validate(model, from_attributes=True)
            for model in models
        ]

    def create_domain_context(
        self,
        *,
        domain_context_id: str,
        display_name: str,
        description: str | None = None,
        created_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryDomainContext:
        self._ensure_builtin_domain_contexts()
        normalized_id = DomainContextResolver.normalize(domain_context_id)
        if normalized_id is None:
            msg = "domain_context_id is required"
            raise ValueError(msg)
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            msg = "display_name is required"
            raise ValueError(msg)

        existing = self._session.get(DictionaryDomainContextModel, normalized_id)
        if existing is not None:
            return DictionaryDomainContext.model_validate(
                existing,
                from_attributes=True,
            )

        model = DictionaryDomainContextModel(
            id=normalized_id,
            display_name=normalized_display_name,
            description=description,
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=DictionaryDomainContextModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryDomainContext.model_validate(model, from_attributes=True)

    def _ensure_builtin_relation_types(self) -> None:
        self._ensure_builtin_domain_contexts()
        for definition in self._builtin_relation_types:
            normalized_relation_type = definition.relation_type.strip().upper()
            if not normalized_relation_type:
                continue
            existing = self._session.get(
                DictionaryRelationTypeModel,
                normalized_relation_type,
            )
            if existing is not None:
                continue
            self._session.add(
                DictionaryRelationTypeModel(
                    id=normalized_relation_type,
                    display_name=definition.display_name,
                    description=definition.description,
                    domain_context=self._ensure_domain_context_reference(
                        definition.domain_context,
                    ),
                    is_directional=definition.is_directional,
                    inverse_label=definition.inverse_label,
                    created_by="seed",
                    review_status="ACTIVE",
                ),
            )
        self._session.flush()

    def _ensure_builtin_entity_types(self) -> None:
        self._ensure_builtin_domain_contexts()
        for definition in self._builtin_entity_types:
            normalized_entity_type = definition.entity_type.strip().upper()
            if not normalized_entity_type:
                continue
            existing = self._session.get(
                DictionaryEntityTypeModel,
                normalized_entity_type,
            )
            if existing is not None:
                continue
            self._session.add(
                DictionaryEntityTypeModel(
                    id=normalized_entity_type,
                    display_name=definition.display_name,
                    description=definition.description,
                    domain_context=definition.domain_context,
                    expected_properties={},
                    created_by="seed",
                    review_status="ACTIVE",
                ),
            )
        self._session.flush()

    def _ensure_builtin_relation_synonyms(self) -> None:
        self._ensure_builtin_relation_types()
        for definition in self._builtin_relation_synonyms:
            normalized_relation_type = definition.relation_type.strip().upper()
            normalized_synonym = definition.synonym.strip().upper()
            if not normalized_relation_type or not normalized_synonym:
                continue
            existing = self._session.scalars(
                select(DictionaryRelationSynonymModel).where(
                    DictionaryRelationSynonymModel.synonym == normalized_synonym,
                ),
            ).first()
            if existing is not None:
                continue
            self._session.add(
                DictionaryRelationSynonymModel(
                    relation_type=normalized_relation_type,
                    synonym=normalized_synonym,
                    source=definition.source,
                    created_by="seed",
                    review_status="ACTIVE",
                ),
            )
        self._session.flush()

    def _ensure_builtin_relation_constraints(self) -> None:
        self._ensure_builtin_entity_types()
        self._ensure_builtin_relation_types()
        for definition in self._builtin_relation_constraints:
            # Wildcard target_type="*" cannot be stored in the DB (FK to
            # entity_types).  These are checked in-memory by get_triple_profile.
            if definition.target_type == "*":
                continue
            profile = getattr(definition, "profile", "ALLOWED")
            is_allowed = profile != "FORBIDDEN"
            self.create_relation_constraint(
                source_type=definition.source_type,
                relation_type=definition.relation_type,
                target_type=definition.target_type,
                is_allowed=is_allowed,
                requires_evidence=definition.requires_evidence,
                created_by="seed",
                review_status="ACTIVE",
                profile=profile,
            )
        self._session.flush()

    def _ensure_builtin_qualifier_definitions(self) -> None:
        self._ensure_builtin_domain_contexts()
        for definition in self._builtin_qualifier_definitions:
            self.create_variable(
                variable_id=definition.variable_id,
                canonical_name=definition.canonical_name,
                display_name=definition.display_name,
                data_type=definition.data_type,
                description=definition.description,
                constraints=cast("JSONObject | None", definition.constraints),
                domain_context="general",
                sensitivity="NON_SENSITIVE",
                created_by="seed",
                review_status="ACTIVE",
            )
        self._session.flush()

    def seed_builtin_dictionary_entries(self) -> None:
        """Ensure pack-owned dictionary defaults exist in the current session."""
        self._ensure_builtin_domain_contexts()
        self._ensure_builtin_entity_types()
        self._ensure_builtin_relation_types()
        self._ensure_builtin_relation_synonyms()
        self._ensure_builtin_relation_constraints()
        self._ensure_builtin_qualifier_definitions()

    def _ensure_sensitivity_reference(self, sensitivity: str) -> str:
        normalized = sensitivity.strip().upper()
        existing = self._session.get(DictionarySensitivityLevelModel, normalized)
        if existing is not None:
            return normalized

        self._session.add(
            DictionarySensitivityLevelModel(
                id=normalized,
                display_name=_humanize(normalized),
                description=_SENSITIVITY_DESCRIPTIONS.get(
                    normalized,
                    "Autogenerated sensitivity level",
                ),
            ),
        )
        self._session.flush()
        return normalized

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

    def create_entity_type(  # noqa: PLR0913
        self,
        *,
        entity_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        external_ontology_ref: str | None = None,
        expected_properties: JSONObject | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> DictionaryEntityType:
        normalized_entity_type = entity_type.strip().upper()
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )

        existing_entity_type = self._session.get(
            DictionaryEntityTypeModel,
            normalized_entity_type,
        )
        if existing_entity_type is not None:
            return DictionaryEntityType.model_validate(existing_entity_type)

        model = DictionaryEntityTypeModel(
            id=normalized_entity_type,
            display_name=display_name,
            description=description,
            domain_context=normalized_domain_context,
            external_ontology_ref=external_ontology_ref,
            expected_properties=expected_properties or {},
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
            existing_after_conflict = self._session.get(
                DictionaryEntityTypeModel,
                normalized_entity_type,
            )
            if existing_after_conflict is not None:
                return DictionaryEntityType.model_validate(existing_after_conflict)
            raise
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryEntityType.model_validate(model)

    def set_entity_type_embedding(  # noqa: PLR0913
        self,
        entity_type_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryEntityType:
        normalized_entity_type = entity_type_id.strip().upper()
        model = self._session.get(DictionaryEntityTypeModel, normalized_entity_type)
        if model is None:
            msg = f"Entity type '{entity_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return DictionaryEntityType.model_validate(model)

    def find_entity_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryEntityType]:
        self.seed_builtin_dictionary_entries()
        stmt = select(DictionaryEntityTypeModel)
        if not include_inactive:
            stmt = stmt.where(DictionaryEntityTypeModel.is_active.is_(True))
        if domain_context is not None:
            stmt = stmt.where(
                DictionaryEntityTypeModel.domain_context == domain_context,
            )
        stmt = stmt.order_by(DictionaryEntityTypeModel.id)
        models = self._session.scalars(stmt).all()
        return [DictionaryEntityType.model_validate(model) for model in models]

    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryEntityType | None:
        self.seed_builtin_dictionary_entries()
        normalized_entity_type = entity_type_id.strip().upper()
        stmt = select(DictionaryEntityTypeModel).where(
            DictionaryEntityTypeModel.id == normalized_entity_type,
        )
        if not include_inactive:
            stmt = stmt.where(DictionaryEntityTypeModel.is_active.is_(True))
        model = self._session.scalars(stmt).first()
        return DictionaryEntityType.model_validate(model) if model is not None else None

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        normalized_entity_type = entity_type_id.strip().upper()
        model = self._session.get(DictionaryEntityTypeModel, normalized_entity_type)
        if model is None:
            msg = f"Entity type '{entity_type_id}' not found"
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
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return DictionaryEntityType.model_validate(model)

    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryEntityType:
        return self.set_entity_type_review_status(
            entity_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def create_relation_type(  # noqa: PLR0913
        self,
        *,
        relation_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        is_directional: bool = True,
        inverse_label: str | None = None,
        description_embedding: list[float] | None = None,
        embedded_at: datetime | None = None,
        embedding_model: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> DictionaryRelationType:
        self.seed_builtin_dictionary_entries()
        normalized_relation_type = relation_type.strip().upper()
        normalized_domain_context = self._ensure_domain_context_reference(
            domain_context,
        )

        existing_relation_type = self._session.get(
            DictionaryRelationTypeModel,
            normalized_relation_type,
        )
        if existing_relation_type is not None:
            return DictionaryRelationType.model_validate(existing_relation_type)

        model = DictionaryRelationTypeModel(
            id=normalized_relation_type,
            display_name=display_name,
            description=description,
            domain_context=normalized_domain_context,
            is_directional=is_directional,
            inverse_label=inverse_label,
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
            existing_after_conflict = self._session.get(
                DictionaryRelationTypeModel,
                normalized_relation_type,
            )
            if existing_after_conflict is not None:
                return DictionaryRelationType.model_validate(existing_after_conflict)
            raise
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryRelationType.model_validate(model)

    def set_relation_type_embedding(  # noqa: PLR0913
        self,
        relation_type_id: str,
        *,
        description_embedding: list[float] | None,
        embedded_at: datetime,
        embedding_model: str,
        changed_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryRelationType:
        normalized_relation_type = relation_type_id.strip().upper()
        model = self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
        if model is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(model)
        model.description_embedding = description_embedding
        model.embedded_at = embedded_at
        model.embedding_model = embedding_model
        self._session.flush()
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=changed_by,
            source_ref=source_ref,
        )
        return DictionaryRelationType.model_validate(model)

    def find_relation_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationType]:
        self.seed_builtin_dictionary_entries()
        stmt = select(DictionaryRelationTypeModel)
        if not include_inactive:
            stmt = stmt.where(DictionaryRelationTypeModel.is_active.is_(True))
        if domain_context is not None:
            stmt = stmt.where(
                DictionaryRelationTypeModel.domain_context == domain_context,
            )
        stmt = stmt.order_by(DictionaryRelationTypeModel.id)
        models = self._session.scalars(stmt).all()
        return [DictionaryRelationType.model_validate(model) for model in models]

    def get_relation_type(
        self,
        relation_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None:
        self.seed_builtin_dictionary_entries()
        normalized_relation_type = relation_type_id.strip().upper()
        stmt = select(DictionaryRelationTypeModel).where(
            DictionaryRelationTypeModel.id == normalized_relation_type,
        )
        if not include_inactive:
            stmt = stmt.where(DictionaryRelationTypeModel.is_active.is_(True))
        model = self._session.scalars(stmt).first()
        return (
            DictionaryRelationType.model_validate(model) if model is not None else None
        )

    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        normalized_relation_type = relation_type_id.strip().upper()
        model = self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
        if model is None:
            msg = f"Relation type '{relation_type_id}' not found"
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
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=model.id,
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return DictionaryRelationType.model_validate(model)

    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryRelationType:
        return self.set_relation_type_review_status(
            relation_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def resolve_relation_synonym(
        self,
        synonym: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None:
        self.seed_builtin_dictionary_entries()
        normalized_synonym = synonym.strip().upper()
        if not normalized_synonym:
            return None
        stmt = (
            select(DictionaryRelationTypeModel)
            .join(
                DictionaryRelationSynonymModel,
                DictionaryRelationSynonymModel.relation_type
                == DictionaryRelationTypeModel.id,
            )
            .where(
                DictionaryRelationSynonymModel.synonym == normalized_synonym,
            )
        )
        if not include_inactive:
            stmt = stmt.where(
                and_(
                    DictionaryRelationSynonymModel.review_status == "ACTIVE",
                    DictionaryRelationSynonymModel.is_active.is_(True),
                    DictionaryRelationTypeModel.review_status == "ACTIVE",
                    DictionaryRelationTypeModel.is_active.is_(True),
                ),
            )
        stmt = stmt.order_by(
            DictionaryRelationSynonymModel.id.asc(),
            DictionaryRelationTypeModel.id.asc(),
        )
        model = self._session.scalars(stmt).first()
        return (
            DictionaryRelationType.model_validate(model) if model is not None else None
        )

    def create_relation_synonym(  # noqa: C901, PLR0913
        self,
        *,
        relation_type_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
    ) -> DictionaryRelationSynonym:
        self.seed_builtin_dictionary_entries()
        normalized_relation_type = relation_type_id.strip().upper()
        if not normalized_relation_type:
            msg = "relation_type_id is required"
            raise ValueError(msg)
        if (
            self._session.get(DictionaryRelationTypeModel, normalized_relation_type)
            is None
        ):
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        normalized_synonym = synonym.strip().upper()
        if not normalized_synonym:
            msg = "synonym is required"
            raise ValueError(msg)

        normalized_source = source.strip() if isinstance(source, str) else source
        if normalized_source == "":
            normalized_source = None
        if isinstance(normalized_source, str):
            normalized_source = normalized_source[:64]

        conflicting_synonym_stmt = select(DictionaryRelationSynonymModel).where(
            DictionaryRelationSynonymModel.synonym == normalized_synonym,
            DictionaryRelationSynonymModel.relation_type != normalized_relation_type,
            DictionaryRelationSynonymModel.is_active.is_(True),
        )
        conflicting_synonym = self._session.scalars(conflicting_synonym_stmt).first()
        if conflicting_synonym is not None:
            msg = (
                f"Synonym '{normalized_synonym}' is already mapped to relation type "
                f"'{conflicting_synonym.relation_type}'"
            )
            raise ValueError(msg)

        existing_stmt = select(DictionaryRelationSynonymModel).where(
            DictionaryRelationSynonymModel.relation_type == normalized_relation_type,
            DictionaryRelationSynonymModel.synonym == normalized_synonym,
        )
        existing = self._session.scalars(existing_stmt).first()
        if existing is not None:
            return DictionaryRelationSynonym.model_validate(existing)

        model = DictionaryRelationSynonymModel(
            relation_type=normalized_relation_type,
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
                return DictionaryRelationSynonym.model_validate(existing_after_conflict)
            conflicting_after_conflict = self._session.scalars(
                conflicting_synonym_stmt,
            ).first()
            if conflicting_after_conflict is not None:
                msg = (
                    f"Synonym '{normalized_synonym}' is already mapped to relation type "
                    f"'{conflicting_after_conflict.relation_type}'"
                )
                raise ValueError(msg) from exc
            raise
        self._record_change(
            table_name=DictionaryRelationSynonymModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return DictionaryRelationSynonym.model_validate(model)

    def find_relation_synonyms(
        self,
        *,
        relation_type_id: str | None = None,
        review_status: ReviewStatus | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationSynonym]:
        self.seed_builtin_dictionary_entries()
        stmt = select(DictionaryRelationSynonymModel)
        if relation_type_id is not None:
            normalized_relation_type = relation_type_id.strip().upper()
            stmt = stmt.where(
                DictionaryRelationSynonymModel.relation_type
                == normalized_relation_type,
            )
        if review_status is not None:
            stmt = stmt.where(
                DictionaryRelationSynonymModel.review_status == review_status,
            )
        if not include_inactive:
            stmt = stmt.where(DictionaryRelationSynonymModel.is_active.is_(True))
        stmt = stmt.order_by(
            DictionaryRelationSynonymModel.relation_type.asc(),
            DictionaryRelationSynonymModel.synonym.asc(),
            DictionaryRelationSynonymModel.id.asc(),
        )
        models = self._session.scalars(stmt).all()
        return [DictionaryRelationSynonym.model_validate(model) for model in models]

    def set_relation_synonym_review_status(
        self,
        synonym_id: int,
        *,
        review_status: ReviewStatus,
        reviewed_by: str | None = None,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationSynonym:
        model = self._session.get(DictionaryRelationSynonymModel, synonym_id)
        if model is None:
            msg = f"Relation synonym '{synonym_id}' not found"
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
            table_name=DictionaryRelationSynonymModel.__tablename__,
            record_id=str(model.id),
            action="REVOKE" if review_status == "REVOKED" else "UPDATE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(model),
            changed_by=reviewed_by,
            source_ref=model.source_ref,
        )
        return DictionaryRelationSynonym.model_validate(model)

    def revoke_relation_synonym(
        self,
        synonym_id: int,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryRelationSynonym:
        return self.set_relation_synonym_review_status(
            synonym_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def find_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]:
        normalized_limit = max(1, min(limit, 500))
        stmt = select(DictionaryChangelogModel)
        if table_name is not None:
            stmt = stmt.where(DictionaryChangelogModel.table_name == table_name)
        if record_id is not None:
            stmt = stmt.where(DictionaryChangelogModel.record_id == record_id)
        stmt = stmt.order_by(DictionaryChangelogModel.id.desc()).limit(normalized_limit)
        models = self._session.scalars(stmt).all()
        return [DictionaryChangelog.model_validate(model) for model in models]

    def search_dictionary(  # noqa: PLR0913
        self,
        *,
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 50,
        query_embeddings: dict[str, list[float]] | None = None,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        return search_dictionary_entries(
            self._session,
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
            query_embeddings=query_embeddings,
            include_inactive=include_inactive,
        )

    def search_dictionary_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]:
        return search_dictionary_entries_by_domain(
            self._session,
            domain_context=domain_context,
            limit=limit,
            include_inactive=include_inactive,
        )

    # Relation-constraint, transform, and merge helpers are implemented in
    # dedicated mixins to keep this module focused on dictionary CRUD.


SqlAlchemyDictionaryRepository = GraphDictionaryRepository

__all__ = ["GraphDictionaryRepository", "SqlAlchemyDictionaryRepository"]
