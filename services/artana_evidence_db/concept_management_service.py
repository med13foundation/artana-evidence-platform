"""Concept Manager application service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from artana_evidence_db.common_types import JSONObject, ResearchSpaceSettings
from artana_evidence_db.concept_models import (
    ConceptAlias,
    ConceptDecision,
    ConceptDecisionProposal,
    ConceptDecisionStatus,
    ConceptDecisionType,
    ConceptHarnessOutcome,
    ConceptHarnessResult,
    ConceptMember,
    ConceptPolicy,
    ConceptPolicyMode,
    ConceptReviewStatus,
    ConceptSet,
)
from artana_evidence_db.governance_ports import ConceptDecisionHarnessPort

_DEFAULT_AGENT_POLICY: ConceptReviewStatus = "ACTIVE"


def _normalize_non_empty(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    msg = f"{field_name} is required"
    raise ValueError(msg)


def _normalize_label(value: str, *, field_name: str) -> str:
    normalized = _normalize_non_empty(value, field_name=field_name)
    return " ".join(normalized.split())


def _normalize_slug(value: str) -> str:
    compact = value.strip().lower()
    if not compact:
        msg = "slug is required"
        raise ValueError(msg)
    normalized = "-".join(part for part in compact.replace("_", "-").split("-") if part)
    if not normalized:
        msg = "slug is required"
        raise ValueError(msg)
    return normalized


def _normalize_identifier(value: str) -> str:
    return _normalize_non_empty(value, field_name="identifier")


def _parse_review_status(value: str) -> ConceptReviewStatus:
    normalized = value.strip().upper()
    if normalized == "ACTIVE":
        return "ACTIVE"
    if normalized == "PENDING_REVIEW":
        return "PENDING_REVIEW"
    if normalized == "REVOKED":
        return "REVOKED"
    msg = f"Unsupported review status '{value}'"
    raise ValueError(msg)


def _parse_policy_mode(value: str) -> ConceptPolicyMode:
    normalized = value.strip().upper()
    if normalized == "PRECISION":
        return "PRECISION"
    if normalized == "BALANCED":
        return "BALANCED"
    if normalized == "DISCOVERY":
        return "DISCOVERY"
    msg = f"Unsupported concept policy mode '{value}'"
    raise ValueError(msg)


def _normalize_pagination(*, offset: int, limit: int) -> tuple[int, int]:
    normalized_offset = max(0, offset)
    normalized_limit = max(1, min(limit, 500))
    return normalized_offset, normalized_limit


class ConceptRepositoryLike(Protocol):
    """Minimal concept-repository surface required by the service."""

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
    ) -> ConceptSet: ...

    def find_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]: ...

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
    ) -> ConceptMember: ...

    def find_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptMember]: ...

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
    ) -> ConceptAlias: ...

    def find_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptAlias]: ...

    def resolve_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        alias_normalized: str,
        include_inactive: bool = False,
    ) -> ConceptMember | None: ...

    def deactivate_active_policies(
        self,
        *,
        research_space_id: str,
    ) -> int: ...

    def create_concept_policy(  # noqa: PLR0913
        self,
        *,
        policy_id: str,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str,
        profile_name: str = "default",
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
        is_active: bool = True,
    ) -> ConceptPolicy: ...

    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None: ...

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
    ) -> ConceptDecision: ...

    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
        harness_outcome: ConceptHarnessOutcome | None = None,
    ) -> ConceptDecision: ...

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
    ) -> ConceptHarnessResult: ...

    def find_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]: ...


class ConceptManagementService:
    """Application service for Concept Manager lifecycle and governance."""

    def __init__(
        self,
        concept_repo: ConceptRepositoryLike,
        concept_harness: ConceptDecisionHarnessPort | None = None,
    ) -> None:
        self._concepts = concept_repo
        self._harness = concept_harness

    def create_concept_set(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptSet:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_name = _normalize_label(name, field_name="name")
        normalized_slug = _normalize_slug(slug)
        normalized_domain_context = _normalize_non_empty(
            domain_context,
            field_name="domain_context",
        )
        normalized_created_by = _normalize_non_empty(
            created_by,
            field_name="created_by",
        )
        return self._concepts.create_concept_set(
            set_id=str(uuid4()),
            research_space_id=normalized_research_space_id,
            name=normalized_name,
            slug=normalized_slug,
            domain_context=normalized_domain_context,
            description=description.strip() if isinstance(description, str) else None,
            created_by=normalized_created_by,
            source_ref=source_ref.strip() if isinstance(source_ref, str) else None,
            review_status="ACTIVE",
        )

    def list_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        return self._concepts.find_concept_sets(
            research_space_id=normalized_research_space_id,
            include_inactive=include_inactive,
        )

    def create_concept_member(  # noqa: PLR0913
        self,
        *,
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
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptMember:
        normalized_set_id = _normalize_identifier(concept_set_id)
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_domain_context = _normalize_non_empty(
            domain_context,
            field_name="domain_context",
        )
        normalized_created_by = _normalize_non_empty(
            created_by,
            field_name="created_by",
        )
        normalized_canonical_label = _normalize_label(
            canonical_label,
            field_name="canonical_label",
        )
        normalized_normalized_label = _normalize_label(
            normalized_label,
            field_name="normalized_label",
        ).lower()
        normalized_sense_key = sense_key.strip()
        normalized_dimension = (
            dictionary_dimension.strip()
            if isinstance(dictionary_dimension, str)
            else None
        )
        normalized_entry_id = (
            dictionary_entry_id.strip()
            if isinstance(dictionary_entry_id, str)
            else None
        )
        review_status = self._resolve_agent_creation_review_status(
            created_by=normalized_created_by,
            research_space_settings=research_space_settings,
        )

        if normalized_dimension is None and normalized_entry_id is not None:
            msg = "dictionary_dimension is required when dictionary_entry_id is set"
            raise ValueError(msg)
        if normalized_dimension is not None and normalized_entry_id is None:
            msg = "dictionary_entry_id is required when dictionary_dimension is set"
            raise ValueError(msg)

        if is_provisional:
            review_status = "PENDING_REVIEW"
        if is_provisional and review_status != "PENDING_REVIEW":
            msg = "Provisional concept members must be created in PENDING_REVIEW status"
            raise ValueError(msg)

        if not is_provisional and normalized_entry_id is None:
            msg = (
                "Concept members without dictionary mapping must be created as provisional "
                "and reviewed explicitly"
            )
            raise ValueError(msg)

        return self._concepts.create_concept_member(
            member_id=str(uuid4()),
            concept_set_id=normalized_set_id,
            research_space_id=normalized_research_space_id,
            domain_context=normalized_domain_context,
            canonical_label=normalized_canonical_label,
            normalized_label=normalized_normalized_label,
            sense_key=normalized_sense_key,
            dictionary_dimension=normalized_dimension,
            dictionary_entry_id=normalized_entry_id,
            is_provisional=is_provisional,
            metadata_payload=metadata_payload or {},
            created_by=normalized_created_by,
            source_ref=source_ref.strip() if isinstance(source_ref, str) else None,
            review_status=review_status,
        )

    def list_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptMember]:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_set_id = (
            _normalize_identifier(concept_set_id)
            if isinstance(concept_set_id, str)
            else None
        )
        normalized_offset, normalized_limit = _normalize_pagination(
            offset=offset,
            limit=limit,
        )
        return self._concepts.find_concept_members(
            research_space_id=normalized_research_space_id,
            concept_set_id=normalized_set_id,
            include_inactive=include_inactive,
            offset=normalized_offset,
            limit=normalized_limit,
        )

    def create_concept_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptAlias:
        normalized_member_id = _normalize_identifier(concept_member_id)
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_domain_context = _normalize_non_empty(
            domain_context,
            field_name="domain_context",
        )
        normalized_alias_label = _normalize_label(alias_label, field_name="alias_label")
        normalized_alias_key = _normalize_label(
            alias_normalized,
            field_name="alias_normalized",
        ).lower()
        normalized_created_by = _normalize_non_empty(
            created_by,
            field_name="created_by",
        )
        return self._concepts.create_concept_alias(
            concept_member_id=normalized_member_id,
            research_space_id=normalized_research_space_id,
            domain_context=normalized_domain_context,
            alias_label=normalized_alias_label,
            alias_normalized=normalized_alias_key,
            source=source.strip() if isinstance(source, str) else None,
            created_by=normalized_created_by,
            source_ref=source_ref.strip() if isinstance(source_ref, str) else None,
            review_status="ACTIVE",
        )

    def list_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptAlias]:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_member_id = (
            _normalize_identifier(concept_member_id)
            if isinstance(concept_member_id, str)
            else None
        )
        normalized_offset, normalized_limit = _normalize_pagination(
            offset=offset,
            limit=limit,
        )
        return self._concepts.find_concept_aliases(
            research_space_id=normalized_research_space_id,
            concept_member_id=normalized_member_id,
            include_inactive=include_inactive,
            offset=normalized_offset,
            limit=normalized_limit,
        )

    def resolve_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        alias_normalized: str,
        include_inactive: bool = False,
    ) -> ConceptMember | None:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_domain_context = _normalize_non_empty(
            domain_context,
            field_name="domain_context",
        )
        normalized_alias = _normalize_label(
            alias_normalized,
            field_name="alias_normalized",
        ).lower()
        return self._concepts.resolve_member_by_alias(
            research_space_id=normalized_research_space_id,
            domain_context=normalized_domain_context,
            alias_normalized=normalized_alias,
            include_inactive=include_inactive,
        )

    def upsert_active_policy(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str,
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
    ) -> ConceptPolicy:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_created_by = _normalize_non_empty(
            created_by,
            field_name="created_by",
        )
        normalized_mode = _parse_policy_mode(mode)
        if minimum_distinct_documents < 1:
            msg = "minimum_distinct_documents must be >= 1"
            raise ValueError(msg)
        if not 0.0 <= minimum_edge_confidence <= 1.0:
            msg = "minimum_edge_confidence must be between 0.0 and 1.0"
            raise ValueError(msg)
        if max_edges_per_document is not None and max_edges_per_document < 1:
            msg = "max_edges_per_document must be >= 1"
            raise ValueError(msg)

        self._concepts.deactivate_active_policies(
            research_space_id=normalized_research_space_id,
        )
        return self._concepts.create_concept_policy(
            policy_id=str(uuid4()),
            research_space_id=normalized_research_space_id,
            mode=normalized_mode,
            created_by=normalized_created_by,
            profile_name="default",
            minimum_edge_confidence=minimum_edge_confidence,
            minimum_distinct_documents=minimum_distinct_documents,
            allow_generic_relations=allow_generic_relations,
            max_edges_per_document=max_edges_per_document,
            policy_payload=policy_payload or {},
            source_ref=source_ref.strip() if isinstance(source_ref, str) else None,
            is_active=True,
        )

    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        return self._concepts.get_active_policy(
            research_space_id=normalized_research_space_id,
        )

    def propose_decision(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        decision_type: ConceptDecisionType,
        proposed_by: str,
        decision_payload: JSONObject | None = None,
        evidence_payload: JSONObject | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        concept_set_id: str | None = None,
        concept_member_id: str | None = None,
        concept_link_id: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptDecision:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_proposed_by = _normalize_non_empty(
            proposed_by,
            field_name="proposed_by",
        )
        initial_status: ConceptDecisionStatus = "PROPOSED"
        decision = self._concepts.create_decision(
            decision_id=str(uuid4()),
            research_space_id=normalized_research_space_id,
            decision_type=decision_type,
            decision_status=initial_status,
            proposed_by=normalized_proposed_by,
            concept_set_id=(
                concept_set_id.strip() if isinstance(concept_set_id, str) else None
            ),
            concept_member_id=(
                concept_member_id.strip()
                if isinstance(concept_member_id, str)
                else None
            ),
            concept_link_id=(
                concept_link_id.strip() if isinstance(concept_link_id, str) else None
            ),
            confidence=confidence,
            rationale=rationale.strip() if isinstance(rationale, str) else None,
            evidence_payload=evidence_payload or {},
            decision_payload=decision_payload or {},
        )

        if not normalized_proposed_by.startswith("agent:"):
            return decision

        auto_apply = self._is_agent_auto_apply_enabled(research_space_settings)
        if self._harness is None:
            return self._concepts.set_decision_status(
                decision.id,
                decision_status="NEEDS_REVIEW",
                decided_by="system:missing_harness",
                harness_outcome="NEEDS_REVIEW",
            )

        verdict = self._harness.evaluate(
            ConceptDecisionProposal(
                research_space_id=normalized_research_space_id,
                decision_type=decision_type,
                proposed_by=normalized_proposed_by,
                confidence=confidence,
                rationale=rationale,
                decision_payload=decision_payload or {},
            ),
        )
        self._concepts.create_harness_result(
            result_id=str(uuid4()),
            research_space_id=normalized_research_space_id,
            harness_name=self._harness.__class__.__name__,
            outcome=verdict.outcome,
            checks_payload={"checks": [check.model_dump() for check in verdict.checks]},
            errors_payload=verdict.errors,
            metadata_payload=verdict.metadata,
            decision_id=decision.id,
            run_id=f"concept_harness:{uuid4()}",
        )

        if verdict.outcome == "PASS" and auto_apply:
            target_status: ConceptDecisionStatus = "APPLIED"
        elif verdict.outcome == "PASS":
            target_status = "NEEDS_REVIEW"
        elif verdict.outcome == "FAIL":
            target_status = "REJECTED"
        else:
            target_status = "NEEDS_REVIEW"

        return self._concepts.set_decision_status(
            decision.id,
            decision_status=target_status,
            decided_by="system:concept_harness",
            harness_outcome=verdict.outcome,
        )

    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
    ) -> ConceptDecision:
        normalized_decision_id = _normalize_identifier(decision_id)
        normalized_decided_by = _normalize_non_empty(
            decided_by,
            field_name="decided_by",
        )
        return self._concepts.set_decision_status(
            normalized_decision_id,
            decision_status=decision_status,
            decided_by=normalized_decided_by,
        )

    def list_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]:
        normalized_research_space_id = _normalize_identifier(research_space_id)
        normalized_offset, normalized_limit = _normalize_pagination(
            offset=offset,
            limit=limit,
        )
        return self._concepts.find_decisions(
            research_space_id=normalized_research_space_id,
            decision_status=decision_status,
            offset=normalized_offset,
            limit=normalized_limit,
        )

    def _resolve_agent_creation_review_status(
        self,
        *,
        created_by: str,
        research_space_settings: ResearchSpaceSettings | None,
    ) -> ConceptReviewStatus:
        if not created_by.startswith("agent:"):
            return "ACTIVE"
        if research_space_settings is None:
            return _DEFAULT_AGENT_POLICY
        raw_policy = research_space_settings.get("concept_agent_creation_policy")
        if not isinstance(raw_policy, str):
            return _DEFAULT_AGENT_POLICY
        try:
            return _parse_review_status(raw_policy)
        except ValueError:
            return _DEFAULT_AGENT_POLICY

    def _is_agent_auto_apply_enabled(
        self,
        research_space_settings: ResearchSpaceSettings | None,
    ) -> bool:
        if research_space_settings is None:
            return True
        raw_policy = research_space_settings.get("concept_agent_creation_policy")
        if not isinstance(raw_policy, str):
            return True
        normalized = raw_policy.strip().upper()
        return normalized == "ACTIVE"

    @staticmethod
    def now() -> datetime:
        """Compatibility helper for deterministic tests."""
        return datetime.now(UTC)


__all__ = ["ConceptManagementService"]
