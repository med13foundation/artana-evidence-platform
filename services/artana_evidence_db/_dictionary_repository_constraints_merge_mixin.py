"""Constraint and merge helpers for the graph-service dictionary repository."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryEntityTypeModel,
    DictionaryRelationSynonymModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
    VariableDefinitionModel,
)
from artana_evidence_db.kernel_domain_models import (
    DictionaryEntityType,
    DictionaryRelationType,
    RelationConstraint,
    VariableDefinition,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from sqlalchemy import and_, inspect, select, update
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


class GraphDictionaryRepositoryConstraintsMergeMixin:
    """Provide relation-constraint and merge lifecycle repository operations."""

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

    def create_relation_constraint(  # noqa: PLR0913
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        is_allowed: bool = True,
        requires_evidence: bool = True,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: ReviewStatus = "ACTIVE",
        profile: str = "ALLOWED",
    ) -> RelationConstraint:
        normalized_source_type = source_type.strip().upper()
        if not normalized_source_type:
            msg = "source_type is required"
            raise ValueError(msg)
        normalized_relation_type = relation_type.strip().upper()
        if not normalized_relation_type:
            msg = "relation_type is required"
            raise ValueError(msg)
        normalized_target_type = target_type.strip().upper()
        if not normalized_target_type:
            msg = "target_type is required"
            raise ValueError(msg)

        existing_stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == normalized_source_type,
                RelationConstraintModel.relation_type == normalized_relation_type,
                RelationConstraintModel.target_type == normalized_target_type,
            ),
        )
        existing_constraint = self._session.scalars(existing_stmt).first()
        if existing_constraint is not None:
            if existing_constraint.review_status != review_status:
                before_snapshot = _snapshot_model(existing_constraint)
                existing_constraint.review_status = review_status
                if review_status == "ACTIVE":
                    existing_constraint.reviewed_by = created_by
                    existing_constraint.reviewed_at = datetime.now(UTC)
                    existing_constraint.revocation_reason = None
                elif review_status == "PENDING_REVIEW":
                    existing_constraint.reviewed_by = None
                    existing_constraint.reviewed_at = None
                    existing_constraint.revocation_reason = None
                self._session.flush()
                self._record_change(
                    table_name=RelationConstraintModel.__tablename__,
                    record_id=str(existing_constraint.id),
                    action="UPDATE",
                    before_snapshot=before_snapshot,
                    after_snapshot=_snapshot_model(existing_constraint),
                    changed_by=created_by,
                    source_ref=source_ref,
                )
            return RelationConstraint.model_validate(existing_constraint)

        model = RelationConstraintModel(
            source_type=normalized_source_type,
            relation_type=normalized_relation_type,
            target_type=normalized_target_type,
            is_allowed=is_allowed,
            requires_evidence=requires_evidence,
            profile=profile,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        try:
            self._session.add(model)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing_after_conflict = self._session.scalars(existing_stmt).first()
            if existing_after_conflict is not None:
                return RelationConstraint.model_validate(existing_after_conflict)
            raise
        self._record_change(
            table_name=RelationConstraintModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=created_by,
            source_ref=source_ref,
        )
        return RelationConstraint.model_validate(model)

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[RelationConstraint]:
        stmt = select(RelationConstraintModel)
        if not include_inactive:
            stmt = stmt.where(RelationConstraintModel.is_active.is_(True))
        if source_type is not None:
            stmt = stmt.where(RelationConstraintModel.source_type == source_type)
        if relation_type is not None:
            stmt = stmt.where(RelationConstraintModel.relation_type == relation_type)
        return [
            RelationConstraint.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def is_triple_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        profile = self.get_triple_profile(source_type, relation_type, target_type)
        return profile != "FORBIDDEN"

    def _check_wildcard_profile(
        self,
        source_type: str,
        relation_type: str,
    ) -> str | None:
        """Check in-memory wildcard constraints (target_type='*').

        Wildcard constraints cannot be stored in the DB (FK on target_type)
        so they are checked from the builtin config loaded at init time.
        Returns the profile string if a match is found, None otherwise.
        """
        wildcard_constraints = getattr(self, "_wildcard_constraints", None)
        if wildcard_constraints is None:
            return None
        return wildcard_constraints.get((source_type, relation_type))

    def get_triple_profile(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> str:
        """Return the enforcement profile for a triple.

        Returns one of: EXPECTED, ALLOWED, REVIEW_ONLY, FORBIDDEN.
        Defaults to ALLOWED for unregistered triples (open-world).

        Exact DB matches take priority over in-memory wildcard entries.
        """
        # 1. Check exact match in DB
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
                RelationConstraintModel.review_status == "ACTIVE",
                RelationConstraintModel.is_active.is_(True),
            ),
        )
        constraint = self._session.scalars(stmt).first()
        if constraint is not None:
            profile = getattr(constraint, "profile", None)
            if profile and profile in (
                "EXPECTED",
                "ALLOWED",
                "REVIEW_ONLY",
                "FORBIDDEN",
            ):
                return profile
            return "ALLOWED" if constraint.is_allowed else "FORBIDDEN"
        # 2. Fallback to in-memory wildcard
        wildcard_profile = self._check_wildcard_profile(source_type, relation_type)
        if wildcard_profile is not None:
            return wildcard_profile
        return "ALLOWED"

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        stmt = select(RelationConstraintModel).where(
            and_(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
                RelationConstraintModel.review_status == "ACTIVE",
                RelationConstraintModel.is_active.is_(True),
            ),
        )
        constraint = self._session.scalars(stmt).first()
        if constraint is not None:
            return constraint.requires_evidence
        # Check wildcard — all wildcard forbidden constraints have
        # requires_evidence=False, so if a wildcard match exists return False.
        if self._check_wildcard_profile(source_type, relation_type) is not None:
            return False
        # If no constraint exists, default to requiring evidence
        return True

    def merge_variable_definition(
        self,
        source_variable_id: str,
        target_variable_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> VariableDefinition:
        source = self._session.get(VariableDefinitionModel, source_variable_id)
        if source is None:
            msg = f"Variable '{source_variable_id}' not found"
            raise ValueError(msg)
        target = self._session.get(VariableDefinitionModel, target_variable_id)
        if target is None:
            msg = f"Variable '{target_variable_id}' not found"
            raise ValueError(msg)
        if not target.is_active:
            msg = f"Variable '{target_variable_id}' must be active for merge"
            raise ValueError(msg)

        before_snapshot = _snapshot_model(source)
        source.review_status = "REVOKED"
        source.reviewed_by = reviewed_by
        source.reviewed_at = datetime.now(UTC)
        source.revocation_reason = reason
        source.is_active = False
        source.valid_to = datetime.now(UTC)
        source.superseded_by = target.id
        self._session.flush()
        self._record_change(
            table_name=VariableDefinitionModel.__tablename__,
            record_id=source.id,
            action="MERGE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(source),
            changed_by=reviewed_by,
            source_ref=source.source_ref,
        )
        return VariableDefinition.model_validate(source)

    def merge_entity_type(
        self,
        source_entity_type_id: str,
        target_entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryEntityType:
        normalized_source = source_entity_type_id.strip().upper()
        normalized_target = target_entity_type_id.strip().upper()
        source = self._session.get(DictionaryEntityTypeModel, normalized_source)
        if source is None:
            msg = f"Entity type '{source_entity_type_id}' not found"
            raise ValueError(msg)
        target = self._session.get(DictionaryEntityTypeModel, normalized_target)
        if target is None:
            msg = f"Entity type '{target_entity_type_id}' not found"
            raise ValueError(msg)
        if not target.is_active:
            msg = f"Entity type '{target_entity_type_id}' must be active for merge"
            raise ValueError(msg)
        if source.id == target.id:
            msg = "source and target entity types must differ"
            raise ValueError(msg)

        for entity in self._session.scalars(
            select(EntityModel).where(EntityModel.entity_type == source.id),
        ).all():
            entity.entity_type = target.id
        self._session.flush()

        before_snapshot = _snapshot_model(source)
        source.review_status = "REVOKED"
        source.reviewed_by = reviewed_by
        source.reviewed_at = datetime.now(UTC)
        source.revocation_reason = reason
        source.is_active = False
        source.valid_to = datetime.now(UTC)
        source.superseded_by = target.id
        self._session.flush()
        self._record_change(
            table_name=DictionaryEntityTypeModel.__tablename__,
            record_id=source.id,
            action="MERGE",
            before_snapshot=before_snapshot,
            after_snapshot=_snapshot_model(source),
            changed_by=reviewed_by,
            source_ref=source.source_ref,
        )
        return DictionaryEntityType.model_validate(source)

    def merge_relation_type(  # noqa: C901, PLR0915
        self,
        source_relation_type_id: str,
        target_relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str | None = None,
    ) -> DictionaryRelationType:
        normalized_source = source_relation_type_id.strip().upper()
        normalized_target = target_relation_type_id.strip().upper()
        source = self._session.get(DictionaryRelationTypeModel, normalized_source)
        if source is None:
            msg = f"Relation type '{source_relation_type_id}' not found"
            raise ValueError(msg)
        target = self._session.get(DictionaryRelationTypeModel, normalized_target)
        if target is None:
            msg = f"Relation type '{target_relation_type_id}' not found"
            raise ValueError(msg)
        if not target.is_active:
            msg = f"Relation type '{target_relation_type_id}' must be active for merge"
            raise ValueError(msg)
        if source.id == target.id:
            msg = "source and target relation types must differ"
            raise ValueError(msg)

        source_relations = list(
            self._session.scalars(
                select(RelationModel).where(RelationModel.relation_type == source.id),
            ).all(),
        )
        affected_relation_ids: set[UUID] = set()
        for source_relation in source_relations:
            target_relation = self._session.scalars(
                select(RelationModel).where(
                    and_(
                        RelationModel.research_space_id
                        == source_relation.research_space_id,
                        RelationModel.source_id == source_relation.source_id,
                        RelationModel.target_id == source_relation.target_id,
                        RelationModel.relation_type == target.id,
                    ),
                ),
            ).first()
            if target_relation is None:
                source_relation.relation_type = target.id
                affected_relation_ids.add(source_relation.id)
                continue

            self._session.execute(
                update(RelationEvidenceModel)
                .where(RelationEvidenceModel.relation_id == source_relation.id)
                .values(relation_id=target_relation.id),
            )
            self._session.delete(source_relation)
            affected_relation_ids.add(target_relation.id)

        connection = self._session.connection()
        if inspect(connection).has_table("dictionary_relation_synonyms"):
            source_synonyms = list(
                self._session.scalars(
                    select(DictionaryRelationSynonymModel).where(
                        DictionaryRelationSynonymModel.relation_type == source.id,
                    ),
                ).all(),
            )
            for synonym in source_synonyms:
                conflicting_synonym = self._session.scalars(
                    select(DictionaryRelationSynonymModel).where(
                        and_(
                            DictionaryRelationSynonymModel.relation_type == target.id,
                            DictionaryRelationSynonymModel.synonym == synonym.synonym,
                            DictionaryRelationSynonymModel.is_active.is_(True),
                        ),
                    ),
                ).first()
                if conflicting_synonym is not None:
                    self._session.delete(synonym)
                    continue
                synonym.relation_type = target.id

        self._session.flush()
        for relation_id in affected_relation_ids:
            self._recompute_relation_aggregate(relation_id)

        source_id = source.id
        source_ref = source.source_ref
        before_snapshot = _snapshot_model(source)
        revoked_at = datetime.now(UTC)
        self._session.execute(
            update(DictionaryRelationTypeModel)
            .where(DictionaryRelationTypeModel.id == source_id)
            .values(
                review_status="REVOKED",
                reviewed_by=reviewed_by,
                reviewed_at=revoked_at,
                revocation_reason=reason,
                is_active=False,
                valid_to=revoked_at,
                superseded_by=target.id,
            ),
        )
        self._session.flush()
        after_snapshot = dict(before_snapshot)
        after_snapshot["review_status"] = "REVOKED"
        after_snapshot["reviewed_by"] = reviewed_by
        after_snapshot["reviewed_at"] = _to_json_value(revoked_at)
        after_snapshot["revocation_reason"] = reason
        after_snapshot["is_active"] = False
        after_snapshot["valid_to"] = _to_json_value(revoked_at)
        after_snapshot["superseded_by"] = target.id
        self._record_change(
            table_name=DictionaryRelationTypeModel.__tablename__,
            record_id=source_id,
            action="MERGE",
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            changed_by=reviewed_by,
            source_ref=source_ref,
        )
        return DictionaryRelationType.model_validate(after_snapshot)

    def _recompute_relation_aggregate(self, relation_id: UUID) -> None:
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return

        evidences = list(
            self._session.scalars(
                select(RelationEvidenceModel).where(
                    RelationEvidenceModel.relation_id == relation_id,
                ),
            ).all(),
        )
        if not evidences:
            relation_model.aggregate_confidence = 0.0
            relation_model.source_count = 0
            relation_model.highest_evidence_tier = None
            relation_model.updated_at = datetime.now(UTC)
            return

        rank_by_tier = {
            "EXPERT_CURATED": 6,
            "CLINICAL": 5,
            "EXPERIMENTAL": 4,
            "LITERATURE": 3,
            "STRUCTURED_DATA": 2,
            "COMPUTATIONAL": 1,
        }
        product = 1.0
        highest_tier: str | None = None
        highest_rank = 0
        for evidence in evidences:
            confidence = float(evidence.confidence)
            confidence = max(confidence, 0.0)
            confidence = min(confidence, 1.0)
            product *= 1.0 - confidence

            tier = evidence.evidence_tier.strip().upper()
            rank = rank_by_tier.get(tier, 0)
            if rank > highest_rank:
                highest_rank = rank
                highest_tier = tier

        aggregate_confidence = 1.0 - product
        aggregate_confidence = max(aggregate_confidence, 0.0)
        aggregate_confidence = min(aggregate_confidence, 1.0)

        relation_model.aggregate_confidence = aggregate_confidence
        relation_model.source_count = len(evidences)
        relation_model.highest_evidence_tier = highest_tier
        relation_model.updated_at = datetime.now(UTC)


__all__ = ["GraphDictionaryRepositoryConstraintsMergeMixin"]
