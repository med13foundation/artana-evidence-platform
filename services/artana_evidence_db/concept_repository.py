"""Service-local SQLAlchemy repository for graph concept governance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptDecisionModel,
    ConceptHarnessResultModel,
    ConceptLinkModel,
    ConceptMemberModel,
    ConceptPolicyModel,
    ConceptSetModel,
)
from artana_evidence_db.kernel_domain_models import (
    ConceptAlias,
    ConceptDecision,
    ConceptDecisionStatus,
    ConceptDecisionType,
    ConceptHarnessOutcome,
    ConceptHarnessResult,
    ConceptLink,
    ConceptMember,
    ConceptPolicy,
    ConceptPolicyMode,
    ConceptSet,
)
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_uuid(value: str) -> UUID:
    return UUID(value)


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _normalize_model_value(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    return value


def _column_payload(model: object) -> dict[str, object]:
    table = getattr(model, "__table__", None)
    if table is None:
        msg = "SQLAlchemy model is missing __table__ metadata"
        raise TypeError(msg)
    payload: dict[str, object] = {}
    for column in table.columns:
        payload[column.name] = _normalize_model_value(getattr(model, column.name))
    return payload


class GraphConceptRepository:
    """Service-local SQLAlchemy implementation for concept-governance tables."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_concept_set(  # noqa: PLR0913
        self,
        *,
        set_id: str,
        research_space_id: str,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptSet:
        model = ConceptSetModel(
            id=_as_uuid(set_id),
            research_space_id=_as_uuid(research_space_id),
            name=name,
            slug=slug,
            domain_context=domain_context,
            description=description,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptSet.model_validate(_column_payload(model))

    def get_concept_set(self, set_id: str) -> ConceptSet | None:
        model = self._session.get(ConceptSetModel, _as_uuid(set_id))
        if model is None:
            return None
        return ConceptSet.model_validate(_column_payload(model))

    def find_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]:
        stmt = select(ConceptSetModel).where(
            ConceptSetModel.research_space_id == _as_uuid(research_space_id),
        )
        if not include_inactive:
            stmt = stmt.where(ConceptSetModel.is_active.is_(True))
        stmt = stmt.order_by(ConceptSetModel.created_at.desc())
        return [
            ConceptSet.model_validate(_column_payload(model))
            for model in self._session.scalars(stmt).all()
        ]

    def find_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptMember]:
        stmt = select(ConceptMemberModel).where(
            ConceptMemberModel.research_space_id == _as_uuid(research_space_id),
        )
        if concept_set_id is not None:
            stmt = stmt.where(
                ConceptMemberModel.concept_set_id == _as_uuid(concept_set_id),
            )
        if not include_inactive:
            stmt = stmt.where(ConceptMemberModel.is_active.is_(True))
        stmt = (
            stmt.order_by(ConceptMemberModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            ConceptMember.model_validate(_column_payload(model))
            for model in self._session.scalars(stmt).all()
        ]

    def create_concept_member(  # noqa: PLR0913
        self,
        *,
        member_id: str,
        concept_set_id: str,
        research_space_id: str,
        domain_context: str,
        canonical_label: str,
        normalized_label: str,
        sense_key: str = "",
        dictionary_dimension: str | None = None,
        dictionary_entry_id: str | None = None,
        is_provisional: bool = False,
        metadata_payload: JSONObject | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptMember:
        model = ConceptMemberModel(
            id=_as_uuid(member_id),
            concept_set_id=_as_uuid(concept_set_id),
            research_space_id=_as_uuid(research_space_id),
            domain_context=domain_context,
            canonical_label=canonical_label,
            normalized_label=normalized_label,
            sense_key=sense_key,
            dictionary_dimension=dictionary_dimension,
            dictionary_entry_id=dictionary_entry_id,
            is_provisional=is_provisional,
            metadata_payload=metadata_payload or {},
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptMember.model_validate(_column_payload(model))

    def create_concept_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptAlias:
        model = ConceptAliasModel(
            concept_member_id=_as_uuid(concept_member_id),
            research_space_id=_as_uuid(research_space_id),
            domain_context=domain_context,
            alias_label=alias_label,
            alias_normalized=alias_normalized,
            source=source,
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptAlias.model_validate(_column_payload(model))

    def find_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptAlias]:
        stmt = select(ConceptAliasModel).where(
            ConceptAliasModel.research_space_id == _as_uuid(research_space_id),
        )
        if concept_member_id is not None:
            stmt = stmt.where(
                ConceptAliasModel.concept_member_id == _as_uuid(concept_member_id),
            )
        if not include_inactive:
            stmt = stmt.where(ConceptAliasModel.is_active.is_(True))
        stmt = (
            stmt.order_by(ConceptAliasModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            ConceptAlias.model_validate(_column_payload(model))
            for model in self._session.scalars(stmt).all()
        ]

    def resolve_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        alias_normalized: str,
        include_inactive: bool = False,
    ) -> ConceptMember | None:
        stmt = (
            select(ConceptMemberModel)
            .join(
                ConceptAliasModel,
                ConceptAliasModel.concept_member_id == ConceptMemberModel.id,
            )
            .where(
                ConceptAliasModel.research_space_id == _as_uuid(research_space_id),
                ConceptAliasModel.domain_context == domain_context,
                ConceptAliasModel.alias_normalized == alias_normalized,
            )
        )
        if not include_inactive:
            stmt = stmt.where(
                ConceptAliasModel.is_active.is_(True),
                ConceptMemberModel.is_active.is_(True),
            )
        model = self._session.scalar(stmt.limit(1))
        if model is None:
            return None
        return ConceptMember.model_validate(_column_payload(model))

    def create_concept_link(  # noqa: PLR0913
        self,
        *,
        link_id: str,
        research_space_id: str,
        source_member_id: str,
        target_member_id: str,
        link_type: str,
        confidence: float = 1.0,
        metadata_payload: JSONObject | None = None,
        created_by: str = "seed",
        source_ref: str | None = None,
        review_status: str = "ACTIVE",
    ) -> ConceptLink:
        model = ConceptLinkModel(
            id=_as_uuid(link_id),
            research_space_id=_as_uuid(research_space_id),
            source_member_id=_as_uuid(source_member_id),
            target_member_id=_as_uuid(target_member_id),
            link_type=link_type,
            confidence=confidence,
            metadata_payload=metadata_payload or {},
            created_by=created_by,
            source_ref=source_ref,
            review_status=review_status,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptLink.model_validate(_column_payload(model))

    def deactivate_active_policies(
        self,
        *,
        research_space_id: str,
    ) -> int:
        stmt = select(ConceptPolicyModel).where(
            ConceptPolicyModel.research_space_id == _as_uuid(research_space_id),
            ConceptPolicyModel.is_active.is_(True),
        )
        models = self._session.scalars(stmt).all()
        now = datetime.now(UTC)
        for model in models:
            model.is_active = False
            model.updated_at = now
        self._session.flush()
        return len(models)

    def create_concept_policy(  # noqa: PLR0913
        self,
        *,
        policy_id: str,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str = "seed",
        profile_name: str = "default",
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
        is_active: bool = True,
    ) -> ConceptPolicy:
        model = ConceptPolicyModel(
            id=_as_uuid(policy_id),
            research_space_id=_as_uuid(research_space_id),
            profile_name=profile_name,
            mode=mode,
            minimum_edge_confidence=minimum_edge_confidence,
            minimum_distinct_documents=minimum_distinct_documents,
            allow_generic_relations=allow_generic_relations,
            max_edges_per_document=max_edges_per_document,
            policy_payload=policy_payload or {},
            created_by=created_by,
            source_ref=source_ref,
            is_active=is_active,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptPolicy.model_validate(_column_payload(model))

    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None:
        stmt = (
            select(ConceptPolicyModel)
            .where(
                ConceptPolicyModel.research_space_id == _as_uuid(research_space_id),
                ConceptPolicyModel.is_active.is_(True),
            )
            .order_by(ConceptPolicyModel.created_at.desc())
            .limit(1)
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        return ConceptPolicy.model_validate(_column_payload(model))

    def create_decision(  # noqa: PLR0913
        self,
        *,
        decision_id: str,
        research_space_id: str,
        decision_type: ConceptDecisionType,
        decision_status: ConceptDecisionStatus,
        proposed_by: str,
        concept_set_id: str | None = None,
        concept_member_id: str | None = None,
        concept_link_id: str | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        evidence_payload: JSONObject | None = None,
        decision_payload: JSONObject | None = None,
        harness_outcome: ConceptHarnessOutcome | None = None,
        decided_by: str | None = None,
    ) -> ConceptDecision:
        model = ConceptDecisionModel(
            id=_as_uuid(decision_id),
            research_space_id=_as_uuid(research_space_id),
            concept_set_id=_try_as_uuid(concept_set_id),
            concept_member_id=_try_as_uuid(concept_member_id),
            concept_link_id=_try_as_uuid(concept_link_id),
            decision_type=decision_type,
            decision_status=decision_status,
            proposed_by=proposed_by,
            decided_by=decided_by,
            confidence=confidence,
            rationale=rationale,
            evidence_payload=evidence_payload or {},
            decision_payload=decision_payload or {},
            harness_outcome=harness_outcome,
        )
        self._session.add(model)
        self._session.flush()
        return ConceptDecision.model_validate(_column_payload(model))

    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
        harness_outcome: ConceptHarnessOutcome | None = None,
    ) -> ConceptDecision:
        model = self._session.get(ConceptDecisionModel, _as_uuid(decision_id))
        if model is None:
            msg = f"Concept decision {decision_id} not found"
            raise ValueError(msg)
        model.decision_status = decision_status
        model.decided_by = decided_by
        model.harness_outcome = harness_outcome
        now = datetime.now(UTC)
        model.decided_at = now
        model.updated_at = now
        self._session.flush()
        return ConceptDecision.model_validate(_column_payload(model))

    def find_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]:
        stmt = select(ConceptDecisionModel).where(
            ConceptDecisionModel.research_space_id == _as_uuid(research_space_id),
        )
        if decision_status is not None:
            stmt = stmt.where(ConceptDecisionModel.decision_status == decision_status)
        stmt = (
            stmt.order_by(ConceptDecisionModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            ConceptDecision.model_validate(_column_payload(model))
            for model in self._session.scalars(stmt).all()
        ]

    def create_harness_result(  # noqa: PLR0913
        self,
        *,
        result_id: str,
        research_space_id: str,
        harness_name: str,
        outcome: ConceptHarnessOutcome,
        checks_payload: JSONObject | None = None,
        errors_payload: list[str] | None = None,
        metadata_payload: JSONObject | None = None,
        decision_id: str | None = None,
        harness_version: str | None = None,
        run_id: str | None = None,
    ) -> ConceptHarnessResult:
        model = ConceptHarnessResultModel(
            id=_as_uuid(result_id),
            research_space_id=_as_uuid(research_space_id),
            decision_id=_try_as_uuid(decision_id),
            harness_name=harness_name,
            harness_version=harness_version,
            run_id=run_id,
            outcome=outcome,
            checks_payload=checks_payload or {},
            errors_payload=errors_payload or [],
            metadata_payload=metadata_payload or {},
        )
        self._session.add(model)
        self._session.flush()
        return ConceptHarnessResult.model_validate(_column_payload(model))


SqlAlchemyConceptRepository = GraphConceptRepository

__all__ = ["GraphConceptRepository", "SqlAlchemyConceptRepository"]
