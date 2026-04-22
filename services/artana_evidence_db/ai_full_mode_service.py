"""Application service for DB-owned AI Full Mode governance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from artana_evidence_db.ai_full_mode_models import (
    AIDecision,
    AIDecisionAction,
    AIDecisionRiskTier,
    AIPolicyOutcome,
    ConceptProposal,
    ConceptProposalDecision,
    ConceptProposalStatus,
    ConnectorProposal,
    ConnectorProposalStatus,
    GraphChangeProposal,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    AIDecisionModel,
    ConceptProposalModel,
    ConnectorProposalModel,
    GraphChangeProposalModel,
)
from artana_evidence_db.common_types import AIFullModeSettings, JSONObject, JSONValue
from artana_evidence_db.concept_repository import GraphConceptRepository
from artana_evidence_db.decision_confidence import (
    DecisionConfidenceAssessment,
    decision_confidence_assessment_payload,
    score_decision_confidence,
)
from artana_evidence_db.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from artana_evidence_db.kernel_dictionary_models import DictionaryChangelogModel
from artana_evidence_db.kernel_domain_models import ConceptMember
from artana_evidence_db.kernel_services import KernelRelationClaimService
from artana_evidence_db.relation_claim_models import KernelRelationClaim
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.space_models import GraphSpaceModel
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

_REVIEWABLE_CONCEPT_STATUSES = frozenset(
    {"SUBMITTED", "DUPLICATE_CANDIDATE", "CHANGES_REQUESTED", "APPROVED"},
)
_REVIEWABLE_GRAPH_CHANGE_STATUSES = frozenset(
    {"READY_FOR_REVIEW", "CHANGES_REQUESTED"},
)
_REVIEWABLE_CONNECTOR_STATUSES = frozenset({"SUBMITTED", "CHANGES_REQUESTED"})
_DEFAULT_MIN_AI_CONFIDENCE = 0.9


@dataclass(frozen=True)
class ConceptResolution:
    """Deterministic duplicate-resolution result for a proposed concept."""

    candidate_decision: ConceptProposalDecision
    existing_concept_member_id: str | None
    duplicate_checks: JSONObject
    warnings: list[str]


def _as_uuid(value: str) -> UUID:
    return UUID(value)


def _uuid_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    msg = f"{field_name} is required"
    raise ValueError(msg)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_domain_context(value: str) -> str:
    return _normalize_required_text(value, field_name="domain_context").lower()


def _normalize_entity_type(value: str) -> str:
    return _normalize_required_text(value, field_name="entity_type").upper()


def _normalize_label(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="label")
    return " ".join(normalized.split())


def _normalize_alias_key(value: str) -> str:
    return _normalize_label(value).lower()


def _normalize_slug(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    parts = [part for part in normalized.split("-") if part]
    if not parts:
        msg = "connector_slug is required"
        raise ValueError(msg)
    return "-".join(parts)


def _manual_actor(actor: str) -> str:
    normalized = _normalize_required_text(actor, field_name="actor")
    if normalized.startswith(("manual:", "agent:", "system:")):
        return normalized
    return f"manual:{normalized}"


def resolve_ai_full_source_ref(
    *,
    request_source_ref: str | None,
    idempotency_key: str | None,
    actor: str,
) -> str | None:
    """Resolve actor-scoped source_ref/idempotency key for Phase 9 writes."""
    source_ref = _normalize_optional_text(request_source_ref)
    key = _normalize_optional_text(idempotency_key)
    if source_ref is not None and key is not None:
        msg = "Provide either source_ref or Idempotency-Key, not both"
        raise ValueError(msg)
    if source_ref is not None:
        return source_ref
    if key is not None:
        return f"idempotency-key:{_manual_actor(actor)}:{key}"
    return None


def _to_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    return str(value)


def _model_payload(model: object) -> dict[str, object]:
    table = getattr(model, "__table__", None)
    if table is None:
        msg = "SQLAlchemy model is missing __table__ metadata"
        raise TypeError(msg)
    payload: dict[str, object] = {}
    for column in table.columns:
        value = getattr(model, column.name)
        payload[column.name] = str(value) if isinstance(value, UUID) else value
    return payload


def _snapshot_model(model: object) -> JSONObject:
    return {
        key: _to_json_value(value)
        for key, value in _model_payload(model).items()
        if key not in {"created_at", "updated_at"}
    }


def _hash_payload(payload: JSONObject) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal_hash(model: ConceptProposalModel | GraphChangeProposalModel) -> str:
    snapshot = _snapshot_model(model)
    snapshot.pop("proposal_hash", None)
    return _hash_payload(snapshot)


def _concept_from_model(model: ConceptProposalModel) -> ConceptProposal:
    return ConceptProposal.model_validate(_model_payload(model))


def _graph_change_from_model(model: GraphChangeProposalModel) -> GraphChangeProposal:
    return GraphChangeProposal.model_validate(_model_payload(model))


def _ai_decision_from_model(model: AIDecisionModel) -> AIDecision:
    return AIDecision.model_validate(_model_payload(model))


def _connector_from_model(model: ConnectorProposalModel) -> ConnectorProposal:
    return ConnectorProposal.model_validate(_model_payload(model))


def _json_str(value: JSONValue | None, *, field_name: str) -> str:
    if isinstance(value, str):
        return _normalize_required_text(value, field_name=field_name)
    msg = f"{field_name} must be a string"
    raise ValueError(msg)


def _json_optional_str(value: JSONValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_optional_text(value)
    return None


def _json_float(value: JSONValue | None, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


def _json_mapping(value: JSONValue | None) -> JSONObject:
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    return {}


def _json_sequence(value: JSONValue | None) -> list[JSONValue]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    return []


def _normalize_external_refs(external_refs: list[JSONObject]) -> list[JSONObject]:
    normalized_refs: list[JSONObject] = []
    seen: set[str] = set()
    for item in external_refs:
        namespace = _json_str(item.get("namespace"), field_name="external_ref.namespace")
        identifier = _json_str(item.get("identifier"), field_name="external_ref.identifier")
        normalized_namespace = namespace.strip().lower()
        normalized_identifier = identifier.strip()
        key = f"{normalized_namespace}:{normalized_identifier}".lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_refs.append(
            {
                "namespace": normalized_namespace,
                "identifier": normalized_identifier,
                "key": key,
            },
        )
    return normalized_refs


def _external_ref_alias(ref: JSONObject) -> tuple[str, str, str]:
    namespace = _json_str(ref.get("namespace"), field_name="external_ref.namespace")
    identifier = _json_str(ref.get("identifier"), field_name="external_ref.identifier")
    label = f"{namespace}:{identifier}"
    return label, label.lower(), f"external_ref:{namespace.lower()}"


def _member_entity_type(member: ConceptMemberModel | ConceptMember) -> str | None:
    payload = getattr(member, "metadata_payload", None)
    if isinstance(member, ConceptMember):
        payload = member.metadata_payload
    if not isinstance(payload, Mapping):
        return None
    raw_value = payload.get("entity_type")
    if not isinstance(raw_value, str):
        return None
    return raw_value.strip().upper() or None


def _member_matches_entity_type(
    member: ConceptMemberModel | ConceptMember,
    *,
    entity_type: str,
) -> bool:
    member_entity_type = _member_entity_type(member)
    return member_entity_type is None or member_entity_type == entity_type


class AIFullModeService:
    """Owns AI Full Mode proposal, duplicate, and decision workflows."""

    def __init__(
        self,
        *,
        session: Session,
        dictionary_service: DictionaryPort,
        relation_claim_service: KernelRelationClaimService | None = None,
    ) -> None:
        self._session = session
        self._dictionary = dictionary_service
        self._concepts = GraphConceptRepository(session)
        self._relation_claim_service = relation_claim_service

    def propose_concept(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        canonical_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
        evidence_payload: JSONObject,
        rationale: str | None,
        proposed_by: str,
        source_ref: str | None = None,
    ) -> ConceptProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_domain = _normalize_domain_context(domain_context)
        normalized_entity_type = _normalize_entity_type(entity_type)
        normalized_label = _normalize_label(canonical_label)
        normalized_alias = _normalize_alias_key(normalized_label)
        normalized_synonyms = self._normalize_synonyms(synonyms, canonical_label=normalized_label)
        normalized_external_refs = _normalize_external_refs(external_refs)
        normalized_actor = _manual_actor(proposed_by)
        normalized_source_ref = _normalize_optional_text(source_ref)

        existing_replay = self._get_concept_proposal_by_source_ref(
            research_space_id=normalized_space_id,
            source_ref=normalized_source_ref,
        )
        if existing_replay is not None:
            self._assert_concept_replay_matches(
                existing_replay,
                domain_context=normalized_domain,
                entity_type=normalized_entity_type,
                normalized_label=normalized_alias,
                synonyms=normalized_synonyms,
                external_refs=normalized_external_refs,
            )
            return _concept_from_model(existing_replay)

        resolution = self.resolve_concept_candidate(
            research_space_id=normalized_space_id,
            domain_context=normalized_domain,
            entity_type=normalized_entity_type,
            normalized_label=normalized_alias,
            synonyms=normalized_synonyms,
            external_refs=normalized_external_refs,
        )
        status: ConceptProposalStatus = (
            "DUPLICATE_CANDIDATE"
            if resolution.candidate_decision != "CREATE_NEW"
            else "SUBMITTED"
        )
        model = ConceptProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status=status,
            candidate_decision=resolution.candidate_decision,
            domain_context=normalized_domain,
            entity_type=normalized_entity_type,
            canonical_label=normalized_label,
            normalized_label=normalized_alias,
            existing_concept_member_id=(
                _as_uuid(resolution.existing_concept_member_id)
                if resolution.existing_concept_member_id is not None
                else None
            ),
            synonyms_payload=normalized_synonyms,
            external_refs_payload=normalized_external_refs,
            evidence_payload=evidence_payload,
            duplicate_checks_payload=resolution.duplicate_checks,
            warnings_payload=resolution.warnings,
            decision_payload={"recommended_action": resolution.candidate_decision},
            rationale=_normalize_optional_text(rationale),
            proposed_by=normalized_actor,
            source_ref=normalized_source_ref,
            proposal_hash="pending",
        )
        self._session.add(model)
        self._session.flush()
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=normalized_actor,
            source_ref=normalized_source_ref,
        )
        return _concept_from_model(model)

    def list_concept_proposals(
        self,
        *,
        research_space_id: str,
        status: ConceptProposalStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptProposal]:
        stmt = select(ConceptProposalModel).where(
            ConceptProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(ConceptProposalModel.status == status)
        stmt = stmt.order_by(ConceptProposalModel.created_at.desc()).offset(offset).limit(limit)
        return [_concept_from_model(model) for model in self._session.scalars(stmt).all()]

    def get_concept_proposal(self, proposal_id: str) -> ConceptProposal:
        return _concept_from_model(self._get_concept_model(proposal_id))

    def reject_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        self._require_concept_reviewable(model)
        before = _snapshot_model(model)
        now = datetime.now(UTC)
        model.status = "REJECTED"
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = now
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="REJECT",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def request_concept_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        self._require_concept_reviewable(model)
        before = _snapshot_model(model)
        model.status = "CHANGES_REQUESTED"
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="REQUEST_CHANGES",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def approve_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        if model.status == "APPLIED":
            return _concept_from_model(model)
        self._require_concept_reviewable(model)
        if model.candidate_decision != "CREATE_NEW":
            msg = "Duplicate concept proposals must be merged, rejected, or changed"
            raise ValueError(msg)
        before = _snapshot_model(model)
        set_id = self._ensure_ai_concept_set(
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            entity_type=model.entity_type,
            created_by=_manual_actor(reviewed_by),
        )
        member = self._concepts.create_concept_member(
            member_id=str(uuid4()),
            concept_set_id=set_id,
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            canonical_label=model.canonical_label,
            normalized_label=model.normalized_label,
            sense_key=model.entity_type.lower(),
            dictionary_dimension="AI_CONCEPT",
            dictionary_entry_id=f"proposal:{model.id}",
            is_provisional=False,
            metadata_payload={
                "entity_type": model.entity_type,
                "proposal_id": str(model.id),
                "synonyms": list(model.synonyms_payload),
                "external_refs": list(model.external_refs_payload),
            },
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}",
            review_status="ACTIVE",
        )
        self._ensure_alias(
            concept_member_id=member.id,
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            alias_label=model.canonical_label,
            alias_normalized=model.normalized_label,
            source="canonical",
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}:canonical",
        )
        self._ensure_proposed_aliases(model, target_member_id=member.id, actor=reviewed_by)
        self._finalize_concept_model(
            model,
            status="APPLIED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            applied_member_id=member.id,
        )
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="APPLY",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def merge_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        target_concept_member_id: str,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        if model.status == "MERGED":
            return _concept_from_model(model)
        self._require_concept_reviewable(model)
        target = self._get_concept_member_model(target_concept_member_id)
        if str(target.research_space_id) != str(model.research_space_id):
            msg = "Merge target belongs to a different graph space"
            raise ValueError(msg)
        before = _snapshot_model(model)
        self._ensure_alias(
            concept_member_id=str(target.id),
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            alias_label=model.canonical_label,
            alias_normalized=model.normalized_label,
            source="merged_label",
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}:merged-label",
        )
        self._ensure_proposed_aliases(model, target_member_id=str(target.id), actor=reviewed_by)
        self._finalize_concept_model(
            model,
            status="MERGED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            applied_member_id=str(target.id),
        )
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="MERGE",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def resolve_concept_candidate(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
    ) -> ConceptResolution:
        exact_member = self._find_member_by_normalized_label(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            normalized_label=normalized_label,
        )
        if exact_member is not None:
            return ConceptResolution(
                candidate_decision="MATCH_EXISTING",
                existing_concept_member_id=str(exact_member.id),
                duplicate_checks={
                    "exact_label": {
                        "matched": True,
                        "concept_member_id": str(exact_member.id),
                    },
                },
                warnings=[],
            )

        external_ref_member = self._find_member_by_external_refs(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            external_refs=external_refs,
        )
        if external_ref_member is not None:
            return ConceptResolution(
                candidate_decision="EXTERNAL_REF_MATCH",
                existing_concept_member_id=str(external_ref_member.id),
                duplicate_checks={
                    "external_ref": {
                        "matched": True,
                        "concept_member_id": str(external_ref_member.id),
                    },
                },
                warnings=[],
            )

        synonym_members = self._find_members_by_synonyms(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            synonyms=synonyms,
        )
        if len(synonym_members) == 1:
            target_member_id = next(iter(synonym_members))
            return ConceptResolution(
                candidate_decision="MERGE_AS_SYNONYM",
                existing_concept_member_id=target_member_id,
                duplicate_checks={
                    "synonyms": {
                        "matched": True,
                        "concept_member_ids": [target_member_id],
                    },
                },
                warnings=[],
            )
        if len(synonym_members) > 1:
            sorted_member_ids = sorted(synonym_members)
            return ConceptResolution(
                candidate_decision="SYNONYM_COLLISION",
                existing_concept_member_id=None,
                duplicate_checks={
                    "synonyms": {
                        "matched": True,
                        "concept_member_ids": sorted_member_ids,
                    },
                },
                warnings=[
                    "Synonyms match more than one existing concept; human review is required.",
                ],
            )
        return ConceptResolution(
            candidate_decision="CREATE_NEW",
            existing_concept_member_id=None,
            duplicate_checks={
                "exact_label": {"matched": False},
                "external_ref": {"matched": False},
                "synonyms": {"matched": False},
            },
            warnings=[],
        )

    def propose_graph_change(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        proposal_payload: JSONObject,
        proposed_by: str,
        source_ref: str | None,
    ) -> GraphChangeProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_actor = _manual_actor(proposed_by)
        normalized_source_ref = _normalize_optional_text(source_ref)
        existing_replay = self._get_graph_change_by_source_ref(
            research_space_id=normalized_space_id,
            source_ref=normalized_source_ref,
        )
        if existing_replay is not None:
            if existing_replay.proposal_payload != proposal_payload:
                msg = "source_ref is already bound to a different graph-change proposal"
                raise ValueError(msg)
            return _graph_change_from_model(existing_replay)

        resolution_plan, warnings = self.build_graph_change_resolution_plan(
            research_space_id=normalized_space_id,
            proposal_payload=proposal_payload,
        )
        errors = [
            item
            for item in _json_sequence(resolution_plan.get("errors"))
            if isinstance(item, str)
        ]
        if errors:
            msg = "; ".join(errors)
            raise ValueError(msg)
        model = GraphChangeProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status="READY_FOR_REVIEW",
            proposal_payload=proposal_payload,
            resolution_plan_payload=resolution_plan,
            warnings_payload=warnings,
            error_payload=[],
            proposed_by=normalized_actor,
            source_ref=normalized_source_ref,
            proposal_hash="pending",
        )
        self._session.add(model)
        self._session.flush()
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=normalized_actor,
            source_ref=normalized_source_ref,
        )
        return _graph_change_from_model(model)

    def get_graph_change_proposal(self, proposal_id: str) -> GraphChangeProposal:
        return _graph_change_from_model(self._get_graph_change_model(proposal_id))

    def list_graph_change_proposals(
        self,
        *,
        research_space_id: str,
        status: Literal[
            "READY_FOR_REVIEW",
            "CHANGES_REQUESTED",
            "REJECTED",
            "APPLIED",
        ]
        | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[GraphChangeProposal]:
        stmt = select(GraphChangeProposalModel).where(
            GraphChangeProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(GraphChangeProposalModel.status == status)
        stmt = stmt.order_by(GraphChangeProposalModel.created_at.desc()).offset(offset).limit(limit)
        return [
            _graph_change_from_model(model)
            for model in self._session.scalars(stmt).all()
        ]

    def reject_graph_change_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> GraphChangeProposal:
        return self._set_graph_change_status(
            proposal_id,
            research_space_id=research_space_id,
            status="REJECTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REJECT",
        )

    def request_graph_change_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> GraphChangeProposal:
        return self._set_graph_change_status(
            proposal_id,
            research_space_id=research_space_id,
            status="CHANGES_REQUESTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REQUEST_CHANGES",
        )

    def build_graph_change_resolution_plan(
        self,
        *,
        research_space_id: str,
        proposal_payload: JSONObject,
    ) -> tuple[JSONObject, list[str]]:
        concepts = self._parse_graph_change_concepts(proposal_payload)
        claims = self._parse_graph_change_claims(proposal_payload)
        warnings: list[str] = []
        errors: list[str] = []
        concept_steps: list[JSONValue] = []
        concept_index: dict[str, JSONObject] = {}
        for concept in concepts:
            local_id = _json_str(concept.get("local_id"), field_name="concept.local_id")
            domain_context = _normalize_domain_context(
                _json_str(concept.get("domain_context"), field_name="concept.domain_context"),
            )
            entity_type = _normalize_entity_type(
                _json_str(concept.get("entity_type"), field_name="concept.entity_type"),
            )
            label = _normalize_label(
                _json_str(concept.get("canonical_label"), field_name="concept.canonical_label"),
            )
            synonyms = [
                _normalize_label(item)
                for item in _json_sequence(concept.get("synonyms"))
                if isinstance(item, str)
            ]
            external_refs = [
                _json_mapping(item)
                for item in _json_sequence(concept.get("external_refs"))
                if isinstance(item, Mapping)
            ]
            resolution = self.resolve_concept_candidate(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                normalized_label=_normalize_alias_key(label),
                synonyms=self._normalize_synonyms(synonyms, canonical_label=label),
                external_refs=_normalize_external_refs(external_refs),
            )
            if resolution.candidate_decision == "SYNONYM_COLLISION":
                errors.extend(resolution.warnings)
            step: JSONObject = {
                "local_id": local_id,
                "action": resolution.candidate_decision,
                "existing_concept_member_id": resolution.existing_concept_member_id,
                "domain_context": domain_context,
                "entity_type": entity_type,
                "canonical_label": label,
            }
            concept_steps.append(step)
            concept_index[local_id] = step

        claim_steps: list[JSONValue] = []
        for position, claim in enumerate(claims):
            claim_step = self._build_claim_plan_step(
                position=position,
                claim=claim,
                concept_index=concept_index,
            )
            claim_errors = [
                item
                for item in _json_sequence(claim_step.get("errors"))
                if isinstance(item, str)
            ]
            errors.extend(claim_errors)
            claim_steps.append(claim_step)
        return (
            {
                "concept_steps": concept_steps,
                "claim_steps": claim_steps,
                "errors": errors,
            },
            warnings,
        )

    def submit_ai_decision(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
        action: AIDecisionAction,
        ai_principal: str,
        authenticated_ai_principal: str | None,
        confidence_assessment: DecisionConfidenceAssessment | None,
        risk_tier: AIDecisionRiskTier,
        input_hash: str,
        evidence_payload: JSONObject,
        decision_payload: JSONObject,
        created_by: str,
    ) -> AIDecision:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_principal = _normalize_required_text(
            ai_principal,
            field_name="ai_principal",
        )
        settings = self._get_ai_full_mode_settings(normalized_space_id)
        if confidence_assessment is None:
            msg = "Decision confidence assessment is required for AI decisions"
            raise ValueError(msg)
        if confidence_assessment.risk_tier != risk_tier:
            msg = "Decision confidence assessment risk_tier must match decision risk_tier"
            raise ValueError(msg)
        confidence_result = score_decision_confidence(confidence_assessment)
        computed_confidence = confidence_result.computed_confidence
        confidence_payload = decision_confidence_assessment_payload(
            confidence_assessment,
        )
        confidence_result_payload = confidence_result.to_payload()
        rejection_reason = self._validate_ai_decision_envelope(
            settings=settings,
            research_space_id=normalized_space_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            ai_principal=normalized_principal,
            authenticated_ai_principal=authenticated_ai_principal,
            computed_confidence=computed_confidence,
            confidence_blocking_reasons=confidence_result.blocking_reasons,
            confidence_human_review_reasons=confidence_result.human_review_reasons,
            risk_tier=risk_tier,
            input_hash=input_hash,
            evidence_payload=evidence_payload,
        )
        policy_outcome = self._policy_outcome(
            settings=settings,
            risk_tier=risk_tier,
            rejection_reason=rejection_reason,
        )
        model = AIDecisionModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            target_type=target_type,
            target_id=_as_uuid(target_id),
            action=action,
            status="REJECTED" if rejection_reason is not None else "SUBMITTED",
            ai_principal=normalized_principal,
            confidence=computed_confidence,
            computed_confidence=computed_confidence,
            confidence_assessment_payload=confidence_payload,
            confidence_model_version=confidence_result.confidence_model_version,
            risk_tier=risk_tier,
            input_hash=input_hash,
            policy_outcome=policy_outcome,
            evidence_payload=evidence_payload,
            decision_payload={
                **decision_payload,
                "confidence_result": confidence_result_payload,
            },
            rejection_reason=rejection_reason,
            created_by=_manual_actor(created_by),
        )
        self._session.add(model)
        self._session.flush()
        if rejection_reason is not None:
            self._record_ai_decision(model)
            raise ValueError(rejection_reason)

        if target_type == "concept_proposal":
            self._apply_concept_ai_decision(
                research_space_id=normalized_space_id,
                target_id=target_id,
                action=action,
                decision_payload=decision_payload,
                actor=normalized_principal,
            )
        else:
            self._apply_graph_change_ai_decision(
                research_space_id=normalized_space_id,
                target_id=target_id,
                action=action,
                actor=normalized_principal,
                decision_reason="AI Full Mode applied this graph-change proposal.",
            )
        model.status = "APPLIED"
        model.applied_at = datetime.now(UTC)
        self._session.flush()
        self._record_ai_decision(model)
        return _ai_decision_from_model(model)

    def list_ai_decisions(
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"] | None = None,
        target_id: str | None = None,
    ) -> list[AIDecision]:
        stmt = select(AIDecisionModel).where(
            AIDecisionModel.research_space_id == _as_uuid(research_space_id),
        )
        if target_type is not None:
            stmt = stmt.where(AIDecisionModel.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AIDecisionModel.target_id == _as_uuid(target_id))
        stmt = stmt.order_by(AIDecisionModel.created_at.desc())
        return [_ai_decision_from_model(model) for model in self._session.scalars(stmt).all()]

    def propose_connector(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        connector_slug: str,
        display_name: str,
        connector_kind: str,
        domain_context: str,
        metadata_payload: JSONObject,
        mapping_payload: JSONObject,
        rationale: str | None,
        evidence_payload: JSONObject,
        proposed_by: str,
        source_ref: str | None,
    ) -> ConnectorProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_slug = _normalize_slug(connector_slug)
        normalized_domain = _normalize_domain_context(domain_context)
        validation_payload = self._validate_connector_mapping(
            domain_context=normalized_domain,
            mapping_payload=mapping_payload,
        )
        model = ConnectorProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status="SUBMITTED",
            connector_slug=normalized_slug,
            display_name=_normalize_label(display_name),
            connector_kind=_normalize_required_text(
                connector_kind,
                field_name="connector_kind",
            ),
            domain_context=normalized_domain,
            metadata_payload=metadata_payload,
            mapping_payload=mapping_payload,
            validation_payload=validation_payload,
            approval_payload={},
            rationale=_normalize_optional_text(rationale),
            evidence_payload=evidence_payload,
            proposed_by=_manual_actor(proposed_by),
            source_ref=_normalize_optional_text(source_ref),
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ConnectorProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=model.proposed_by,
            source_ref=model.source_ref,
        )
        return _connector_from_model(model)

    def approve_connector(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str | None,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="APPROVED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="APPROVE",
        )

    def reject_connector(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="REJECTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REJECT",
        )

    def request_connector_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="CHANGES_REQUESTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REQUEST_CHANGES",
        )

    def get_connector_proposal(self, proposal_id: str) -> ConnectorProposal:
        return _connector_from_model(self._get_connector_model(proposal_id))

    def list_connector_proposals(
        self,
        *,
        research_space_id: str,
        status: ConnectorProposalStatus | None = None,
    ) -> list[ConnectorProposal]:
        stmt = select(ConnectorProposalModel).where(
            ConnectorProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(ConnectorProposalModel.status == status)
        stmt = stmt.order_by(ConnectorProposalModel.created_at.desc())
        return [_connector_from_model(model) for model in self._session.scalars(stmt).all()]

    def _normalize_synonyms(self, synonyms: list[str], *, canonical_label: str) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = {_normalize_alias_key(canonical_label)}
        for item in synonyms:
            label = _normalize_label(item)
            key = _normalize_alias_key(label)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(label)
        return normalized

    def _get_concept_model(self, proposal_id: str) -> ConceptProposalModel:
        model = self._session.get(ConceptProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Concept proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _get_graph_change_model(self, proposal_id: str) -> GraphChangeProposalModel:
        model = self._session.get(GraphChangeProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Graph-change proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _get_connector_model(self, proposal_id: str) -> ConnectorProposalModel:
        model = self._session.get(ConnectorProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Connector proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _assert_model_in_space(
        self,
        model: ConceptProposalModel | GraphChangeProposalModel | ConnectorProposalModel,
        *,
        research_space_id: str | None,
        resource_name: str,
    ) -> None:
        if research_space_id is None:
            return
        if str(model.research_space_id) != str(_as_uuid(research_space_id)):
            msg = f"{resource_name} '{model.id}' not found in graph space"
            raise ValueError(msg)

    def _get_concept_member_model(self, concept_member_id: str) -> ConceptMemberModel:
        model = self._session.get(ConceptMemberModel, _as_uuid(concept_member_id))
        if model is None:
            msg = f"Concept member '{concept_member_id}' not found"
            raise ValueError(msg)
        return model

    def _get_concept_proposal_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str | None,
    ) -> ConceptProposalModel | None:
        if source_ref is None:
            return None
        stmt = select(ConceptProposalModel).where(
            ConceptProposalModel.research_space_id == _as_uuid(research_space_id),
            ConceptProposalModel.source_ref == source_ref,
        )
        return self._session.scalar(stmt.limit(1))

    def _get_graph_change_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str | None,
    ) -> GraphChangeProposalModel | None:
        if source_ref is None:
            return None
        stmt = select(GraphChangeProposalModel).where(
            GraphChangeProposalModel.research_space_id == _as_uuid(research_space_id),
            GraphChangeProposalModel.source_ref == source_ref,
        )
        return self._session.scalar(stmt.limit(1))

    def _assert_concept_replay_matches(
        self,
        model: ConceptProposalModel,
        *,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
    ) -> None:
        if (
            model.domain_context != domain_context
            or model.entity_type != entity_type
            or model.normalized_label != normalized_label
            or list(model.synonyms_payload) != synonyms
            or list(model.external_refs_payload) != external_refs
        ):
            msg = "source_ref is already bound to a different concept proposal"
            raise ValueError(msg)

    def _require_concept_reviewable(self, model: ConceptProposalModel) -> None:
        if model.status not in _REVIEWABLE_CONCEPT_STATUSES:
            msg = f"Concept proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)

    def _find_member_by_normalized_label(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
    ) -> ConceptMemberModel | None:
        stmt = select(ConceptMemberModel).where(
            ConceptMemberModel.research_space_id == _as_uuid(research_space_id),
            ConceptMemberModel.domain_context == domain_context,
            ConceptMemberModel.normalized_label == normalized_label,
            ConceptMemberModel.is_active.is_(True),
        )
        for model in self._session.scalars(stmt).all():
            if _member_matches_entity_type(model, entity_type=entity_type):
                return model
        return None

    def _find_member_by_external_refs(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        external_refs: list[JSONObject],
    ) -> ConceptMemberModel | None:
        for ref in external_refs:
            _, alias_normalized, _ = _external_ref_alias(ref)
            member = self._find_member_by_alias(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                alias_normalized=alias_normalized,
            )
            if member is not None:
                return member
        return None

    def _find_members_by_synonyms(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        synonyms: list[str],
    ) -> set[str]:
        matches: set[str] = set()
        for synonym in synonyms:
            member = self._find_member_by_alias(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                alias_normalized=_normalize_alias_key(synonym),
            )
            if member is not None:
                matches.add(str(member.id))
        return matches

    def _find_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        alias_normalized: str,
    ) -> ConceptMemberModel | None:
        stmt = (
            select(ConceptMemberModel)
            .join(ConceptAliasModel, ConceptAliasModel.concept_member_id == ConceptMemberModel.id)
            .where(
                ConceptAliasModel.research_space_id == _as_uuid(research_space_id),
                ConceptAliasModel.domain_context == domain_context,
                ConceptAliasModel.alias_normalized == alias_normalized,
                ConceptAliasModel.is_active.is_(True),
                ConceptMemberModel.is_active.is_(True),
            )
        )
        for model in self._session.scalars(stmt).all():
            if _member_matches_entity_type(model, entity_type=entity_type):
                return model
        return None

    def _ensure_ai_concept_set(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        created_by: str,
    ) -> str:
        slug = f"ai-full-{domain_context}-{entity_type.lower()}"
        stmt = select(ConceptSetModel).where(
            ConceptSetModel.research_space_id == _as_uuid(research_space_id),
            ConceptSetModel.slug == slug,
            ConceptSetModel.is_active.is_(True),
        )
        existing = self._session.scalar(stmt.limit(1))
        if existing is not None:
            return str(existing.id)
        concept_set = self._concepts.create_concept_set(
            set_id=str(uuid4()),
            research_space_id=research_space_id,
            name=f"AI Full Mode {entity_type} Concepts",
            slug=slug,
            domain_context=domain_context,
            description="Concept set managed by DB-owned AI Full Mode governance.",
            created_by=created_by,
            source_ref=f"ai-full-mode:{domain_context}:{entity_type}",
            review_status="ACTIVE",
        )
        return concept_set.id

    def _ensure_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str,
        created_by: str,
        source_ref: str,
    ) -> None:
        existing = self._concepts.resolve_member_by_alias(
            research_space_id=research_space_id,
            domain_context=domain_context,
            alias_normalized=alias_normalized,
            include_inactive=False,
        )
        if existing is not None:
            if existing.id == concept_member_id:
                return
            msg = f"Alias '{alias_label}' already belongs to another concept"
            raise ValueError(msg)
        self._concepts.create_concept_alias(
            concept_member_id=concept_member_id,
            research_space_id=research_space_id,
            domain_context=domain_context,
            alias_label=alias_label,
            alias_normalized=alias_normalized,
            source=source,
            created_by=created_by,
            source_ref=source_ref,
            review_status="ACTIVE",
        )

    def _ensure_proposed_aliases(
        self,
        model: ConceptProposalModel,
        *,
        target_member_id: str,
        actor: str,
    ) -> None:
        for synonym in model.synonyms_payload:
            self._ensure_alias(
                concept_member_id=target_member_id,
                research_space_id=str(model.research_space_id),
                domain_context=model.domain_context,
                alias_label=synonym,
                alias_normalized=_normalize_alias_key(synonym),
                source="synonym",
                created_by=_manual_actor(actor),
                source_ref=f"concept-proposal:{model.id}:synonym:{_normalize_alias_key(synonym)}",
            )
        for ref in model.external_refs_payload:
            label, alias_normalized, source = _external_ref_alias(ref)
            self._ensure_alias(
                concept_member_id=target_member_id,
                research_space_id=str(model.research_space_id),
                domain_context=model.domain_context,
                alias_label=label,
                alias_normalized=alias_normalized,
                source=source,
                created_by=_manual_actor(actor),
                source_ref=f"concept-proposal:{model.id}:external-ref:{alias_normalized}",
            )

    def _finalize_concept_model(
        self,
        model: ConceptProposalModel,
        *,
        status: ConceptProposalStatus,
        reviewed_by: str,
        decision_reason: str | None,
        applied_member_id: str,
    ) -> None:
        model.status = status
        model.applied_concept_member_id = _as_uuid(applied_member_id)
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_optional_text(decision_reason)
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()

    def _parse_graph_change_concepts(self, proposal_payload: JSONObject) -> list[JSONObject]:
        concepts = _json_sequence(proposal_payload.get("concepts"))
        parsed = [_json_mapping(item) for item in concepts if isinstance(item, Mapping)]
        if not parsed:
            msg = "graph-change proposal must include at least one concept"
            raise ValueError(msg)
        return parsed

    def _parse_graph_change_claims(self, proposal_payload: JSONObject) -> list[JSONObject]:
        return [
            _json_mapping(item)
            for item in _json_sequence(proposal_payload.get("claims"))
            if isinstance(item, Mapping)
        ]

    def _build_claim_plan_step(
        self,
        *,
        position: int,
        claim: JSONObject,
        concept_index: dict[str, JSONObject],
    ) -> JSONObject:
        errors: list[JSONValue] = []
        source_local_id = _json_optional_str(claim.get("source_local_id"))
        target_local_id = _json_optional_str(claim.get("target_local_id"))
        relation_type = _normalize_required_text(
            _json_str(claim.get("relation_type"), field_name="claim.relation_type"),
            field_name="claim.relation_type",
        ).upper()
        source_step = concept_index.get(source_local_id or "")
        target_step = concept_index.get(target_local_id or "")
        if source_step is None:
            errors.append(f"claim[{position}] source_local_id does not resolve")
        if target_step is None:
            errors.append(f"claim[{position}] target_local_id does not resolve")
        evidence_payload = _json_mapping(claim.get("evidence_payload"))
        claim_text = _json_optional_str(claim.get("claim_text"))
        has_evidence = bool(evidence_payload) or claim_text is not None
        try:
            FactAssessment.model_validate(claim.get("assessment"))
        except ValidationError:
            errors.append(f"claim[{position}] requires qualitative assessment")
        source_type = (
            _json_str(source_step.get("entity_type"), field_name="source.entity_type")
            if source_step is not None
            else "UNKNOWN"
        )
        target_type = (
            _json_str(target_step.get("entity_type"), field_name="target.entity_type")
            if target_step is not None
            else "UNKNOWN"
        )
        validation_state: Literal["ALLOWED", "FORBIDDEN", "UNDEFINED"] = "UNDEFINED"
        persistability: Literal["PERSISTABLE", "NON_PERSISTABLE"] = "NON_PERSISTABLE"
        requires_evidence = True
        if source_step is not None and target_step is not None:
            constraints = self._dictionary.get_constraints(
                source_type=source_type,
                relation_type=relation_type,
                include_inactive=False,
            )
            matching_constraint = next(
                (
                    constraint
                    for constraint in constraints
                    if constraint.target_type == target_type
                ),
                None,
            )
            if matching_constraint is None:
                errors.append(
                    f"claim[{position}] has no active relation constraint for "
                    f"{source_type}-{relation_type}-{target_type}",
                )
            elif not matching_constraint.is_allowed:
                validation_state = "FORBIDDEN"
                errors.append(
                    f"claim[{position}] relation is forbidden by active constraints",
                )
            else:
                validation_state = "ALLOWED"
                persistability = "PERSISTABLE"
                requires_evidence = matching_constraint.requires_evidence
        if requires_evidence and not has_evidence:
            errors.append(f"claim[{position}] requires evidence")
            persistability = "NON_PERSISTABLE"
        return {
            "position": position,
            "action": "CREATE_CLAIM",
            "source_local_id": source_local_id,
            "target_local_id": target_local_id,
            "source_type": source_type,
            "target_type": target_type,
            "relation_type": relation_type,
            "validation_state": validation_state,
            "persistability": persistability,
            "requires_evidence": requires_evidence,
            "errors": errors,
        }

    def _get_ai_full_mode_settings(self, research_space_id: str) -> AIFullModeSettings:
        space = self._session.get(GraphSpaceModel, _as_uuid(research_space_id))
        if space is None:
            return {}
        settings = space.settings
        ai_settings = settings.get("ai_full_mode")
        if isinstance(ai_settings, Mapping):
            return cast("AIFullModeSettings", dict(ai_settings))
        return {}

    def _validate_ai_decision_envelope(  # noqa: PLR0911, PLR0913
        self,
        *,
        settings: AIFullModeSettings,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
        action: AIDecisionAction,
        ai_principal: str,
        authenticated_ai_principal: str | None,
        computed_confidence: float,
        confidence_blocking_reasons: list[str],
        confidence_human_review_reasons: list[str],
        risk_tier: AIDecisionRiskTier,
        input_hash: str,
        evidence_payload: JSONObject,
    ) -> str | None:
        expected_hash = self._target_hash(
            research_space_id=research_space_id,
            target_type=target_type,
            target_id=target_id,
        )
        trusted = settings.get("trusted_principals", [])
        normalized_authenticated = _normalize_optional_text(authenticated_ai_principal)
        if normalized_authenticated is None:
            return "Authenticated AI principal is required for AI decisions"
        if normalized_authenticated != ai_principal:
            return "AI decision principal does not match authenticated AI principal"
        if ai_principal not in trusted:
            return "AI principal is not trusted for this graph space"
        if not evidence_payload:
            return "AI decision evidence_payload is required"
        if confidence_blocking_reasons:
            return "AI decision confidence assessment is blocked: " + ", ".join(
                confidence_blocking_reasons,
            )
        if confidence_human_review_reasons:
            return "AI decision confidence assessment requires human review: " + ", ".join(
                confidence_human_review_reasons,
            )
        if computed_confidence < float(
            settings.get("min_confidence", _DEFAULT_MIN_AI_CONFIDENCE),
        ):
            return (
                "AI decision computed confidence is below policy threshold; "
                "human review required"
            )
        if input_hash != expected_hash:
            return "AI decision input_hash does not match current proposal snapshot"
        mode = settings.get("governance_mode", "human_review")
        if mode != "ai_full":
            return "AI Full Mode is not enabled for this graph space"
        if risk_tier == "high" and not bool(settings.get("allow_high_risk_actions", False)):
            return "High-risk AI decisions require human review"
        if target_type == "concept_proposal" and action not in {"APPROVE", "MERGE", "REJECT"}:
            return "Unsupported AI action for concept proposal"
        if target_type == "graph_change_proposal" and action != "APPLY_RESOLUTION_PLAN":
            return "Unsupported AI action for graph-change proposal"
        return None

    def _policy_outcome(
        self,
        *,
        settings: AIFullModeSettings,
        risk_tier: AIDecisionRiskTier,
        rejection_reason: str | None,
    ) -> AIPolicyOutcome:
        if rejection_reason is not None:
            if "human review" in rejection_reason or "not enabled" in rejection_reason:
                return "human_required"
            return "blocked"
        if risk_tier == "low":
            return "ai_allowed_when_low_risk"
        if bool(settings.get("allow_high_risk_actions", False)):
            return "ai_allowed"
        return "human_required"

    def _target_hash(
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
    ) -> str:
        if target_type == "concept_proposal":
            model = self._get_concept_model(target_id)
            self._assert_model_in_space(
                model,
                research_space_id=research_space_id,
                resource_name="AI decision target",
            )
            return model.proposal_hash
        model = self._get_graph_change_model(target_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="AI decision target",
        )
        return model.proposal_hash

    def _apply_concept_ai_decision(
        self,
        *,
        research_space_id: str,
        target_id: str,
        action: AIDecisionAction,
        decision_payload: JSONObject,
        actor: str,
    ) -> None:
        if action == "APPROVE":
            self.approve_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode approved this concept proposal.",
            )
            return
        if action == "MERGE":
            target_member_id = _json_str(
                decision_payload.get("target_concept_member_id"),
                field_name="target_concept_member_id",
            )
            self.merge_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                target_concept_member_id=target_member_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode merged this concept proposal.",
            )
            return
        if action == "REJECT":
            self.reject_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode rejected this concept proposal.",
            )
            return
        msg = "Unsupported AI concept action"
        raise ValueError(msg)

    def _apply_graph_change_ai_decision(
        self,
        *,
        research_space_id: str,
        target_id: str,
        action: AIDecisionAction,
        actor: str,
        decision_reason: str,
    ) -> None:
        if action != "APPLY_RESOLUTION_PLAN":
            msg = "Unsupported AI graph-change action"
            raise ValueError(msg)
        if self._relation_claim_service is None:
            msg = "Relation claim service is required to apply graph-change proposals"
            raise ValueError(msg)
        model = self._get_graph_change_model(target_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Graph-change proposal",
        )
        if model.status == "APPLIED":
            return
        if model.status not in _REVIEWABLE_GRAPH_CHANGE_STATUSES:
            msg = f"Graph-change proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        concept_ids = self._apply_graph_change_concepts(model, actor=actor)
        claim_ids = self._apply_graph_change_claims(model, actor=actor)
        model.status = "APPLIED"
        model.applied_concept_member_ids_payload = concept_ids
        model.applied_claim_ids_payload = claim_ids
        model.reviewed_by = actor
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = decision_reason
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action="APPLY",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=actor,
            source_ref=model.source_ref,
        )

    def apply_graph_change_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> GraphChangeProposal:
        """Apply one graph-change proposal through the normal governed service path."""
        self._apply_graph_change_ai_decision(
            research_space_id=research_space_id,
            target_id=proposal_id,
            action="APPLY_RESOLUTION_PLAN",
            actor=reviewed_by,
            decision_reason=decision_reason
            or "Batch review applied this graph-change proposal.",
        )
        return self.get_graph_change_proposal(proposal_id)

    def _set_graph_change_status(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None,
        status: Literal["CHANGES_REQUESTED", "REJECTED"],
        reviewed_by: str,
        decision_reason: str,
        action: str,
    ) -> GraphChangeProposal:
        model = self._get_graph_change_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Graph-change proposal",
        )
        if model.status not in _REVIEWABLE_GRAPH_CHANGE_STATUSES:
            msg = f"Graph-change proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        model.status = status
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action=action,
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _graph_change_from_model(model)

    def _apply_graph_change_concepts(
        self,
        model: GraphChangeProposalModel,
        *,
        actor: str,
    ) -> list[str]:
        proposal_payload = cast("JSONObject", model.proposal_payload)
        concepts = self._parse_graph_change_concepts(proposal_payload)
        concept_member_ids: list[str] = []
        for concept in concepts:
            proposal = self.propose_concept(
                research_space_id=str(model.research_space_id),
                domain_context=_json_str(concept.get("domain_context"), field_name="concept.domain_context"),
                entity_type=_json_str(concept.get("entity_type"), field_name="concept.entity_type"),
                canonical_label=_json_str(
                    concept.get("canonical_label"),
                    field_name="concept.canonical_label",
                ),
                synonyms=[
                    item
                    for item in _json_sequence(concept.get("synonyms"))
                    if isinstance(item, str)
                ],
                external_refs=[
                    _json_mapping(item)
                    for item in _json_sequence(concept.get("external_refs"))
                    if isinstance(item, Mapping)
                ],
                evidence_payload=_json_mapping(concept.get("evidence_payload")),
                rationale=_json_optional_str(concept.get("rationale")),
                proposed_by=actor,
                source_ref=f"graph-change:{model.id}:concept:{_json_str(concept.get('local_id'), field_name='concept.local_id')}",
            )
            if proposal.candidate_decision == "CREATE_NEW":
                applied = self.approve_concept_proposal(
                    proposal.id,
                    research_space_id=str(model.research_space_id),
                    reviewed_by=actor,
                    decision_reason="Applied as part of graph-change proposal.",
                )
                if applied.applied_concept_member_id is not None:
                    concept_member_ids.append(applied.applied_concept_member_id)
            elif proposal.existing_concept_member_id is not None:
                merged = self.merge_concept_proposal(
                    proposal.id,
                    research_space_id=str(model.research_space_id),
                    target_concept_member_id=proposal.existing_concept_member_id,
                    reviewed_by=actor,
                    decision_reason="Merged as part of graph-change proposal.",
                )
                if merged.applied_concept_member_id is not None:
                    concept_member_ids.append(merged.applied_concept_member_id)
        return concept_member_ids

    def _apply_graph_change_claims(
        self,
        model: GraphChangeProposalModel,
        *,
        actor: str,
    ) -> list[str]:
        if self._relation_claim_service is None:
            return []
        proposal_payload = cast("JSONObject", model.proposal_payload)
        claims = self._parse_graph_change_claims(proposal_payload)
        claim_ids: list[str] = []
        for position, claim in enumerate(claims):
            source_ref = f"graph-change:{model.id}:claim:{position}"
            existing = self._relation_claim_service.get_by_source_ref(
                research_space_id=str(model.research_space_id),
                source_ref=source_ref,
            )
            if existing is not None:
                claim_ids.append(str(existing.id))
                continue
            created = self._create_graph_change_claim(
                model=model,
                claim=claim,
                source_ref=source_ref,
                actor=actor,
            )
            claim_ids.append(str(created.id))
        return claim_ids

    def _create_graph_change_claim(
        self,
        *,
        model: GraphChangeProposalModel,
        claim: JSONObject,
        source_ref: str,
        actor: str,
    ) -> KernelRelationClaim:
        if self._relation_claim_service is None:
            msg = "Relation claim service is required"
            raise ValueError(msg)
        payload = cast("JSONObject", model.proposal_payload)
        concept_index = {
            _json_str(item.get("local_id"), field_name="concept.local_id"): item
            for item in self._parse_graph_change_concepts(payload)
        }
        source = concept_index[
            _json_str(claim.get("source_local_id"), field_name="claim.source_local_id")
        ]
        target = concept_index[
            _json_str(claim.get("target_local_id"), field_name="claim.target_local_id")
        ]
        assessment = FactAssessment.model_validate(claim.get("assessment"))
        derived_confidence = assessment_confidence(assessment)
        confidence_metadata = fact_assessment_metadata(assessment)
        return self._relation_claim_service.create_claim(
            research_space_id=str(model.research_space_id),
            source_document_id=None,
            source_document_ref=_json_optional_str(claim.get("source_document_ref")),
            source_ref=source_ref,
            agent_run_id=actor,
            source_type=_normalize_entity_type(
                _json_str(source.get("entity_type"), field_name="source.entity_type"),
            ),
            relation_type=_normalize_entity_type(
                _json_str(claim.get("relation_type"), field_name="claim.relation_type"),
            ),
            target_type=_normalize_entity_type(
                _json_str(target.get("entity_type"), field_name="target.entity_type"),
            ),
            source_label=_json_str(
                source.get("canonical_label"),
                field_name="source.canonical_label",
            ),
            target_label=_json_str(
                target.get("canonical_label"),
                field_name="target.canonical_label",
            ),
            confidence=derived_confidence,
            validation_state="ALLOWED",
            validation_reason="ai_full_mode:validated_resolution_plan",
            persistability="PERSISTABLE",
            assertion_class="COMPUTATIONAL",
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=_json_optional_str(claim.get("claim_text")),
            claim_section=None,
            linked_relation_id=None,
            metadata={
                "origin": "ai_full_mode_graph_change",
                "graph_change_proposal_id": str(model.id),
                "evidence_payload": _json_mapping(claim.get("evidence_payload")),
                **confidence_metadata,
            },
        )

    def _record_ai_decision(self, model: AIDecisionModel) -> None:
        self._record_change(
            table_name=AIDecisionModel.__tablename__,
            record_id=str(model.id),
            action=model.status,
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=model.created_by,
            source_ref=f"ai-decision:{model.target_type}:{model.target_id}",
        )

    def _validate_connector_mapping(
        self,
        *,
        domain_context: str,
        mapping_payload: JSONObject,
    ) -> JSONObject:
        errors: list[JSONValue] = []
        mappings = _json_sequence(mapping_payload.get("field_mappings"))
        for index, raw_mapping in enumerate(mappings):
            mapping = _json_mapping(raw_mapping)
            dimension = _json_optional_str(mapping.get("target_dimension"))
            target_id = _json_optional_str(mapping.get("target_id"))
            if dimension is None or target_id is None:
                errors.append(f"field_mappings[{index}] needs target_dimension and target_id")
                continue
            normalized_dimension = dimension.lower()
            if normalized_dimension == "entity_type":
                entity_type = self._dictionary.get_entity_type(
                    target_id,
                    include_inactive=False,
                )
                if entity_type is None or entity_type.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] entity_type is not active in domain")
            elif normalized_dimension == "relation_type":
                relation_type = self._dictionary.get_relation_type(
                    target_id,
                    include_inactive=False,
                )
                if relation_type is None or relation_type.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] relation_type is not active in domain")
            elif normalized_dimension == "variable":
                variable = self._dictionary.get_variable(target_id)
                if variable is None or variable.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] variable is not active in domain")
            else:
                errors.append(f"field_mappings[{index}] target_dimension is unsupported")
        return {"valid": not errors, "errors": errors, "execution_enabled": False}

    def _set_connector_status(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None,
        status: ConnectorProposalStatus,
        reviewed_by: str,
        decision_reason: str | None,
        action: str,
    ) -> ConnectorProposal:
        model = self._get_connector_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Connector proposal",
        )
        if model.status not in _REVIEWABLE_CONNECTOR_STATUSES:
            msg = f"Connector proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        if status == "APPROVED" and not bool(model.validation_payload.get("valid", False)):
            msg = "Connector proposal mappings must be valid before approval"
            raise ValueError(msg)
        model.status = status
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_optional_text(decision_reason)
        model.approval_payload = {
            "approved_metadata_only": status == "APPROVED",
            "connector_runtime_executed": False,
        }
        self._session.flush()
        self._record_change(
            table_name=ConnectorProposalModel.__tablename__,
            record_id=str(model.id),
            action=action,
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _connector_from_model(model)

    def _record_change(
        self,
        *,
        table_name: str,
        record_id: str,
        action: str,
        before_snapshot: JSONObject | None,
        after_snapshot: JSONObject,
        changed_by: str | None,
        source_ref: str | None,
    ) -> None:
        self._session.add(
            DictionaryChangelogModel(
                table_name=table_name,
                record_id=record_id,
                action=action,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                changed_by=changed_by,
                source_ref=source_ref,
            ),
        )
        self._session.flush()


__all__ = ["AIFullModeService", "resolve_ai_full_source_ref"]
