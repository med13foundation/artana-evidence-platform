"""Write-phase relation candidate persistence flow extracted for file-size limits."""

from __future__ import annotations

# ruff: noqa: SLF001
import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from src.application.agents.services._extraction_relation_auto_resolve_helpers import (
    _FULL_AUTO_CONFIDENCE_THRESHOLD,
)
from src.application.agents.services._extraction_relation_concept_helpers import (
    _ensure_concept_member,
    _normalize_sense_key,
    _resolve_document_domain_context,
    _resolve_or_create_concept_set,
)
from src.application.agents.services._relation_persistence_payload_helpers import (
    candidate_payload,
    normalize_run_id,
)
from src.application.services.claim_first_metrics import increment_metric

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import (
        ClaimParticipantRole,
        RelationClaimStatus,
    )

    from src.application.agents.services._extraction_relation_persistence_helpers import (
        _ExtractionRelationPersistenceHelpers,
    )
    from src.application.agents.services._extraction_relation_policy_helpers import (
        RelationGovernanceMode,
        _ResolvedRelationCandidate,
    )
    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
    )
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings
else:
    JSONObject = dict[str, object]  # Runtime type stub

_PER_CANDIDATE_LOG_THRESHOLD = 25
_PER_CANDIDATE_LOG_INTERVAL = 10
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PersistCandidatesResult:
    persisted_relations_count: int = 0
    pending_review_relations_count: int = 0
    relation_claims_count: int = 0
    claim_evidence_rows_created_count: int = 0
    relation_claims_queued_for_review_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_relations_count: int = 0
    undefined_relations_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    evidence_span_missing_count: int = 0
    rejected_relation_reasons: tuple[str, ...] = ()
    rejected_relation_details: tuple[JSONObject, ...] = ()
    persistence_failed_count: int = 0
    full_auto_retry_skipped_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass
class _CandidateLoopState:
    persisted_count: int = 0
    pending_count: int = 0
    relation_claims_count: int = 0
    claim_evidence_rows_created_count: int = 0
    relation_claims_queued_for_review_count: int = 0
    non_persistable_claims_count: int = 0
    forbidden_count: int = 0
    undefined_count: int = 0
    concept_members_created_count: int = 0
    concept_aliases_created_count: int = 0
    concept_decisions_proposed_count: int = 0
    evidence_span_missing_count: int = 0
    persistence_failed_count: int = 0
    full_auto_retry_skipped_count: int = 0
    rejected_reasons: list[str] = field(default_factory=list)
    rejected_details: list[JSONObject] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    concept_set_cache: dict[tuple[str, str], str] = field(default_factory=dict)
    concept_member_cache: dict[tuple[str, str, str], str] = field(default_factory=dict)
    concept_alias_cache: set[tuple[str, str, str]] = field(default_factory=set)
    concept_alias_scope_cache: dict[tuple[str, str], str] = field(default_factory=dict)


@dataclass(frozen=True)
class _PersistRunContext:
    helper: _ExtractionRelationPersistenceHelpers
    document: SourceDocument
    run_id: str | None
    relation_governance_mode: RelationGovernanceMode
    research_space_settings: ResearchSpaceSettings
    research_space_id: str
    total_candidates: int
    constraint_lookup: dict[tuple[str, str, str], RelationConstraintProposal]
    mapping_lookup: dict[tuple[str, str, str], RelationTypeMappingProposal]
    relation_type_settings: ResearchSpaceSettings
    relation_source_ref: str
    concept_source_ref: str
    policy_run_id: str | None
    dictionary_fingerprint: str
    full_auto_retry_index: dict[tuple[str, str, str, str, str], str]


@dataclass(frozen=True)
class _PreparedCandidateWrite:
    candidate: _ResolvedRelationCandidate
    payload: JSONObject
    candidate_signature: tuple[str, str, str, str, str]
    evidence_summary: str
    evidence_sentence: str | None
    evidence_sentence_source: str | None
    evidence_sentence_confidence: str | None
    evidence_sentence_rationale: str | None
    relation_evidence_metadata: JSONObject
    relation_evidence_failure: str | None


def _should_log_candidate(*, total_candidates: int, index: int) -> bool:
    return (
        total_candidates <= _PER_CANDIDATE_LOG_THRESHOLD
        or index in {1, total_candidates}
        or index % _PER_CANDIDATE_LOG_INTERVAL == 0
    )


def _enqueue_claim_review(
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    claim_id: str | None,
    candidate: _ResolvedRelationCandidate,
    priority: str | None = None,
) -> None:
    if claim_id is None:
        return
    context.helper._enqueue_review_item(
        entity_type="relation_claim",
        entity_id=claim_id,
        research_space_id=context.research_space_id,
        priority=(
            priority
            if priority is not None
            else context.helper._review_priority_for_candidate(candidate=candidate)
        ),
    )
    state.relation_claims_queued_for_review_count += 1


def _apply_full_auto_claim_status(
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    claim_status: RelationClaimStatus,
) -> None:
    if claim_id is None:
        return
    status_errors = context.helper._set_claim_system_status(
        claim_id=claim_id,
        claim_status=claim_status,
    )
    state.errors.extend(status_errors)
    if claim_status == "NEEDS_MAPPING":
        context.full_auto_retry_index[candidate_signature] = (
            context.dictionary_fingerprint
        )


def _resolve_effective_candidate(
    *,
    context: _PersistRunContext,
    candidate: _ResolvedRelationCandidate,
    index: int,
    should_log_candidate: bool,
) -> tuple[
    _ResolvedRelationCandidate,
    RelationTypeMappingProposal | None,
    JSONObject | None,
]:
    proposal_key = (
        candidate.source_type,
        candidate.relation_type,
        candidate.target_type,
    )
    mapping_proposal = context.mapping_lookup.get(proposal_key)
    effective_candidate = candidate
    canonicalization_metadata: JSONObject | None = None
    if effective_candidate.persistability == "PERSISTABLE":
        started_at = datetime.now(UTC)
        if should_log_candidate:
            logger.info(
                "Persist relation candidate canonicalization started",
                extra={
                    "document_id": str(context.document.id),
                    "run_id": context.run_id,
                    "candidate_index": index,
                    "candidate_total": context.total_candidates,
                    "source_type": effective_candidate.source_type,
                    "relation_type": effective_candidate.relation_type,
                    "target_type": effective_candidate.target_type,
                },
            )
        effective_candidate, canonicalization_metadata = (
            context.helper._canonicalize_relation_candidate(
                candidate=effective_candidate,
                mapping_proposal=mapping_proposal,
                document=context.document,
            )
        )
        validation_state, validation_reason = (
            context.helper._resolve_relation_validation_state(
                source_type=effective_candidate.source_type,
                relation_type=effective_candidate.relation_type,
                target_type=effective_candidate.target_type,
            )
        )
        constraint_profile = context.helper._resolve_constraint_profile(
            source_type=effective_candidate.source_type,
            relation_type=effective_candidate.relation_type,
            target_type=effective_candidate.target_type,
        )
        effective_candidate = replace(
            effective_candidate,
            validation_state=validation_state,
            validation_reason=validation_reason,
            constraint_profile=constraint_profile,
        )
        if should_log_candidate:
            logger.info(
                "Persist relation candidate canonicalization finished",
                extra={
                    "document_id": str(context.document.id),
                    "run_id": context.run_id,
                    "candidate_index": index,
                    "candidate_total": context.total_candidates,
                    "duration_ms": int(
                        (datetime.now(UTC) - started_at).total_seconds() * 1000,
                    ),
                    "validation_state": effective_candidate.validation_state,
                    "persistability": effective_candidate.persistability,
                    "relation_type": effective_candidate.relation_type,
                },
            )
    if (
        effective_candidate.validation_state == "UNDEFINED"
        and context.relation_governance_mode == "FULL_AUTO"
    ):
        effective_candidate = context.helper._resolve_full_auto_candidate(
            candidate=effective_candidate,
            mapping_proposal=mapping_proposal,
            source_ref=f"source_document:{context.document.id}:full_auto_persist",
        )
    return effective_candidate, mapping_proposal, canonicalization_metadata


def _maybe_skip_candidate_for_retry_fingerprint(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    candidate_signature: tuple[str, str, str, str, str],
    index: int,
    should_log_candidate: bool,
) -> bool:
    if context.relation_governance_mode != "FULL_AUTO":
        return False
    existing_retry_key = context.full_auto_retry_index.get(candidate_signature)
    if existing_retry_key != context.dictionary_fingerprint:
        return False
    state.full_auto_retry_skipped_count += 1
    if should_log_candidate:
        logger.info(
            "Persist relation candidate skipped: unchanged dictionary fingerprint",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "relation_type": candidate.relation_type,
                "dictionary_fingerprint": context.dictionary_fingerprint,
            },
        )
    return True


def _prepare_candidate_write(
    *,
    context: _PersistRunContext,
    candidate: _ResolvedRelationCandidate,
    candidate_signature: tuple[str, str, str, str, str],
    mapping_proposal: RelationTypeMappingProposal | None,
    canonicalization_metadata: JSONObject | None,
) -> _PreparedCandidateWrite:
    payload = candidate_payload(candidate)
    if canonicalization_metadata is not None:
        payload["canonicalization"] = canonicalization_metadata
    if context.relation_governance_mode == "FULL_AUTO":
        payload["auto_resolve_mode"] = "FULL_AUTO"
        payload["auto_resolve_policy_run_id"] = context.policy_run_id
        payload["auto_resolve_dictionary_fingerprint"] = context.dictionary_fingerprint
        payload["auto_resolve_confidence_threshold"] = _FULL_AUTO_CONFIDENCE_THRESHOLD
        payload["auto_resolve_confidence_passed"] = (
            candidate.confidence >= _FULL_AUTO_CONFIDENCE_THRESHOLD
        )
        payload["auto_resolve_retry_on_dictionary_change_only"] = True
    effective_constraint_proposal = context.constraint_lookup.get(
        (candidate.source_type, candidate.relation_type, candidate.target_type),
    )
    requires_evidence_span = context.helper._should_require_relation_evidence_span(
        document=context.document,
        candidate=candidate,
        research_space_settings=context.research_space_settings,
    )
    (
        relation_evidence_summary,
        relation_evidence_metadata,
        relation_evidence_failure,
    ) = context.helper._prepare_relation_evidence_summary(
        document=context.document,
        candidate=candidate,
        relation_governance_mode=context.relation_governance_mode,
        constraint_proposal=effective_constraint_proposal,
        mapping_proposal=mapping_proposal,
        requires_evidence_span=requires_evidence_span,
    )
    relation_evidence_sentence: str | None = None
    relation_evidence_sentence_source: str | None = None
    relation_evidence_sentence_confidence: str | None = None
    relation_evidence_sentence_rationale: str | None = None
    span_text_value = relation_evidence_metadata.get("span_text")
    if isinstance(span_text_value, str):
        normalized_span_text = span_text_value.strip()
        if normalized_span_text:
            relation_evidence_sentence = normalized_span_text[:2000]
            relation_evidence_sentence_source = "verbatim_span"
            relation_evidence_sentence_confidence = "high"
            relation_evidence_metadata["evidence_sentence_source"] = (
                relation_evidence_sentence_source
            )
            relation_evidence_metadata["evidence_sentence_confidence"] = (
                relation_evidence_sentence_confidence
            )
    elif not requires_evidence_span:
        generated_sentence = (
            context.helper._generate_optional_relation_evidence_sentence(
                document=context.document,
                candidate=candidate,
                evidence_summary=relation_evidence_summary,
                relation_evidence_metadata=relation_evidence_metadata,
                run_id=context.run_id,
            )
        )
        if generated_sentence.outcome == "generated":
            relation_evidence_sentence = generated_sentence.sentence
            relation_evidence_sentence_source = generated_sentence.source
            relation_evidence_sentence_confidence = generated_sentence.confidence
            relation_evidence_sentence_rationale = generated_sentence.rationale
            relation_evidence_metadata["evidence_sentence_source"] = (
                relation_evidence_sentence_source
            )
            relation_evidence_metadata["evidence_sentence_confidence"] = (
                relation_evidence_sentence_confidence
            )
            relation_evidence_metadata["evidence_sentence_rationale"] = (
                relation_evidence_sentence_rationale
            )
            if generated_sentence.metadata:
                relation_evidence_metadata["evidence_sentence_generation"] = (
                    generated_sentence.metadata
                )
        else:
            relation_evidence_metadata["evidence_sentence_failure_reason"] = (
                generated_sentence.failure_reason
                or "evidence_sentence_generation_failed"
            )
            if generated_sentence.metadata:
                relation_evidence_metadata["evidence_sentence_generation"] = (
                    generated_sentence.metadata
                )
    payload["relation_evidence"] = relation_evidence_metadata
    relation_evidence_metadata["assessment"] = candidate.assessment
    relation_evidence_metadata["derived_confidence"] = candidate.confidence
    return _PreparedCandidateWrite(
        candidate=candidate,
        payload=payload,
        candidate_signature=candidate_signature,
        evidence_summary=relation_evidence_summary,
        evidence_sentence=relation_evidence_sentence,
        evidence_sentence_source=relation_evidence_sentence_source,
        evidence_sentence_confidence=relation_evidence_sentence_confidence,
        evidence_sentence_rationale=relation_evidence_sentence_rationale,
        relation_evidence_metadata=relation_evidence_metadata,
        relation_evidence_failure=relation_evidence_failure,
    )


def _attach_concept_refs(  # noqa: C901, PLR0912
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    payload: JSONObject,
) -> None:
    if context.helper._concepts is None or candidate.persistability != "PERSISTABLE":
        return
    domain_context = _resolve_document_domain_context(context.document)
    concept_set_id = _resolve_or_create_concept_set(
        concept_service=context.helper._concepts,
        research_space_id=context.research_space_id,
        domain_context=domain_context,
        source_ref=context.concept_source_ref,
        cache=state.concept_set_cache,
    )
    if concept_set_id is None:
        state.errors.append("concept_set_unavailable")
        return
    source_concept = _ensure_concept_member(
        concept_service=context.helper._concepts,
        concept_set_id=concept_set_id,
        research_space_id=context.research_space_id,
        domain_context=domain_context,
        candidate_label=candidate.source_label,
        sense_key=_normalize_sense_key(candidate.source_type),
        source_ref=context.concept_source_ref,
        alias_source=context.document.source_type.value,
        research_space_settings=context.research_space_settings,
        member_cache=state.concept_member_cache,
        alias_cache=state.concept_alias_cache,
        alias_scope_cache=state.concept_alias_scope_cache,
        mapping_judge_agent=context.helper._concept_merge_judge,
    )
    target_concept = _ensure_concept_member(
        concept_service=context.helper._concepts,
        concept_set_id=concept_set_id,
        research_space_id=context.research_space_id,
        domain_context=domain_context,
        candidate_label=candidate.target_label,
        sense_key=_normalize_sense_key(candidate.target_type),
        source_ref=context.concept_source_ref,
        alias_source=context.document.source_type.value,
        research_space_settings=context.research_space_settings,
        member_cache=state.concept_member_cache,
        alias_cache=state.concept_alias_cache,
        alias_scope_cache=state.concept_alias_scope_cache,
        mapping_judge_agent=context.helper._concept_merge_judge,
    )
    state.concept_members_created_count += (
        source_concept.members_created_count + target_concept.members_created_count
    )
    state.concept_aliases_created_count += (
        source_concept.aliases_created_count + target_concept.aliases_created_count
    )
    state.concept_decisions_proposed_count += (
        source_concept.decisions_proposed_count
        + target_concept.decisions_proposed_count
    )
    state.errors.extend(source_concept.errors)
    state.errors.extend(target_concept.errors)
    source_refs = source_concept.concept_refs
    target_refs = target_concept.concept_refs
    source_member_id = None
    target_member_id = None
    if source_refs is not None:
        source_value = source_refs.get("concept_member_id")
        if isinstance(source_value, str) and source_value.strip():
            source_member_id = source_value
    if target_refs is not None:
        target_value = target_refs.get("concept_member_id")
        if isinstance(target_value, str) and target_value.strip():
            target_member_id = target_value
    decision_ids: list[str] = []
    for refs in (source_refs, target_refs):
        if refs is None:
            continue
        raw_decision_ids = refs.get("decision_ids")
        if not isinstance(raw_decision_ids, list):
            continue
        for raw_decision_id in raw_decision_ids:
            if not isinstance(raw_decision_id, str):
                continue
            normalized_decision_id = raw_decision_id.strip()
            if not normalized_decision_id:
                continue
            if normalized_decision_id in decision_ids:
                continue
            decision_ids.append(normalized_decision_id)
    concept_refs: JSONObject = {
        "domain_context": domain_context,
        "concept_set_id": concept_set_id,
        "source_member_id": source_member_id,
        "target_member_id": target_member_id,
    }
    if decision_ids:
        concept_refs["decision_ids"] = decision_ids
    payload["concept_refs"] = concept_refs


def _create_relation_claim(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    payload: JSONObject,
    relation_evidence_metadata: JSONObject,
    evidence_sentence: str | None,
    evidence_sentence_source: str | None,
    evidence_sentence_confidence: str | None,
    evidence_sentence_rationale: str | None,
    index: int,
    should_log_candidate: bool,
) -> str | None:
    if context.helper._relation_claims is None:
        return None
    if context.helper._claim_participants is None:
        error_code = "relation_claim_persistence_missing_claim_participant_repository"
        state.errors.append(error_code)
        if should_log_candidate:
            logger.warning(
                "Persist relation candidate participant repository missing",
                extra={
                    "document_id": str(context.document.id),
                    "run_id": context.run_id,
                    "candidate_index": index,
                    "candidate_total": context.total_candidates,
                    "relation_type": candidate.relation_type,
                    "error_code": error_code,
                },
            )
        return None
    try:
        created_claim = context.helper._relation_claims.create(
            research_space_id=context.research_space_id,
            source_document_id=str(context.document.id),
            agent_run_id=context.run_id,
            source_type=candidate.source_type,
            relation_type=candidate.relation_type,
            target_type=candidate.target_type,
            source_label=candidate.source_label,
            target_label=candidate.target_label,
            confidence=candidate.confidence,
            validation_state=candidate.validation_state,
            validation_reason=candidate.validation_reason,
            persistability=candidate.persistability,
            assertion_class="SOURCE_BACKED",
            claim_status=(
                "REVIEW_REQUIRED"
                if candidate.constraint_profile == "REVIEW_ONLY"
                else "OPEN"
            ),
            polarity=candidate.polarity,
            claim_text=candidate.claim_text,
            claim_section=candidate.claim_section,
            linked_relation_id=None,
            metadata={
                **payload,
                "constraint_profile": candidate.constraint_profile,
            },
        )
        _create_claim_participant_if_anchor_present(
            context=context,
            claim_id=str(created_claim.id),
            role="SUBJECT",
            label=candidate.source_label,
            entity_id=candidate.source_entity_id,
            position=0,
        )
        _create_claim_participant_if_anchor_present(
            context=context,
            claim_id=str(created_claim.id),
            role="OBJECT",
            label=candidate.target_label,
            entity_id=candidate.target_entity_id,
            position=1,
        )
        state.relation_claims_count += 1
        increment_metric(
            "claims_by_polarity_total",
            tags={
                "research_space_id": context.research_space_id,
                "source_document_id": str(context.document.id),
                "polarity": candidate.polarity,
            },
        )
        claim_evidence_errors = context.helper._create_claim_evidence_record(
            claim_id=str(created_claim.id),
            document=context.document,
            run_id=context.run_id,
            relation_evidence_metadata=relation_evidence_metadata,
            evidence_sentence=evidence_sentence,
            evidence_sentence_source=evidence_sentence_source,
            evidence_sentence_confidence=evidence_sentence_confidence,
            evidence_sentence_rationale=evidence_sentence_rationale,
            candidate_confidence=candidate.confidence,
        )
        if not claim_evidence_errors:
            state.claim_evidence_rows_created_count += 1
        state.errors.extend(claim_evidence_errors)
        return str(created_claim.id)
    except (RuntimeError, TypeError, ValueError, SQLAlchemyError) as exc:
        context.helper._rollback_after_persistence_error(
            context="relation_claim_create",
        )
        error_code = context.helper._map_relation_write_error_code(exc)
        state.errors.append(
            f"relation_claim_create_failed:{error_code}:{candidate.relation_type}",
        )
        if should_log_candidate:
            logger.warning(
                "Persist relation candidate claim creation failed",
                extra={
                    "document_id": str(context.document.id),
                    "run_id": context.run_id,
                    "candidate_index": index,
                    "candidate_total": context.total_candidates,
                    "relation_type": candidate.relation_type,
                    "error_code": error_code,
                    "error": str(exc),
                },
            )
        return None


def _create_claim_participant_if_anchor_present(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    claim_id: str,
    role: ClaimParticipantRole,
    label: str | None,
    entity_id: str | None,
    position: int,
) -> None:
    if context.helper._claim_participants is None:
        return
    normalized_label = label.strip() if isinstance(label, str) else ""
    normalized_entity_id = entity_id.strip() if isinstance(entity_id, str) else ""
    if not normalized_label and not normalized_entity_id:
        return
    qualifiers = getattr(context, "_participant_qualifiers", None)
    if qualifiers:
        from artana_evidence_db.qualifier_registry import validate_qualifiers

        errors = validate_qualifiers(qualifiers)
        if errors:
            logger.warning(
                "Invalid participant qualifiers dropped",
                extra={"errors": errors, "claim_id": claim_id},
            )
            qualifiers = None
    context.helper._claim_participants.create(
        claim_id=claim_id,
        research_space_id=context.research_space_id,
        role=role,
        label=normalized_label or None,
        entity_id=normalized_entity_id or None,
        position=position,
        qualifiers=qualifiers,
    )


def _handle_non_persistable_candidate(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    index: int,
    should_log_candidate: bool,
) -> bool:
    if candidate.persistability == "PERSISTABLE":
        return False
    state.non_persistable_claims_count += 1
    if context.relation_governance_mode == "FULL_AUTO":
        terminal_status = context.helper._resolve_full_auto_terminal_status(
            candidate=candidate,
        )
        _apply_full_auto_claim_status(
            context=context,
            state=state,
            claim_id=claim_id,
            candidate_signature=candidate_signature,
            claim_status=terminal_status,
        )
    _enqueue_claim_review(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate=candidate,
    )
    if should_log_candidate:
        logger.info(
            "Persist relation candidate completed as non-persistable",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "validation_state": candidate.validation_state,
                "claim_id": claim_id,
            },
        )
    return True


def _handle_non_allowed_governance(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    index: int,
    should_log_candidate: bool,
) -> bool:
    if candidate.validation_state == "ALLOWED":
        return False
    if context.relation_governance_mode == "HUMAN_IN_LOOP":
        _enqueue_claim_review(
            context=context,
            state=state,
            claim_id=claim_id,
            candidate=candidate,
        )
        if should_log_candidate:
            logger.info(
                "Persist relation candidate deferred by governance mode",
                extra={
                    "document_id": str(context.document.id),
                    "run_id": context.run_id,
                    "candidate_index": index,
                    "candidate_total": context.total_candidates,
                    "relation_governance_mode": context.relation_governance_mode,
                    "validation_state": candidate.validation_state,
                    "claim_id": claim_id,
                },
            )
        return True
    terminal_status = context.helper._resolve_full_auto_terminal_status(
        candidate=candidate,
    )
    _apply_full_auto_claim_status(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate_signature=candidate_signature,
        claim_status=terminal_status,
    )
    _enqueue_claim_review(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate=candidate,
    )
    if should_log_candidate:
        logger.info(
            "Persist relation candidate stopped: full-auto unresolved validation",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "validation_state": candidate.validation_state,
                "validation_reason": candidate.validation_reason,
                "claim_id": claim_id,
            },
        )
    return True


def _handle_evidence_span_failure(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    relation_evidence_failure: str | None,
    relation_evidence_metadata: JSONObject,
    payload: JSONObject,
    index: int,
    should_log_candidate: bool,
) -> bool:
    if relation_evidence_failure is None:
        return False
    state.evidence_span_missing_count += 1
    state.non_persistable_claims_count += 1
    context.helper._record_rejected_relation(
        reasons=state.rejected_reasons,
        details=state.rejected_details,
        reason="relation_evidence_span_missing",
        payload=payload,
        metadata={
            "validation_state": "EVIDENCE_SPAN_MISSING",
            "validation_reason": relation_evidence_failure,
            "relation_evidence": relation_evidence_metadata,
        },
    )
    if context.relation_governance_mode == "FULL_AUTO":
        _apply_full_auto_claim_status(
            context=context,
            state=state,
            claim_id=claim_id,
            candidate_signature=candidate_signature,
            claim_status="NEEDS_MAPPING",
        )
    _enqueue_claim_review(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate=candidate,
        priority="high",
    )
    if should_log_candidate:
        logger.info(
            "Persist relation candidate blocked by evidence-span requirement",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "relation_type": candidate.relation_type,
                "validation_reason": relation_evidence_failure,
                "claim_id": claim_id,
            },
        )
    return True


def _handle_missing_endpoint_entity_ids(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    index: int,
    should_log_candidate: bool,
) -> bool:
    if (
        candidate.source_entity_id is not None
        and candidate.target_entity_id is not None
    ):
        return False
    state.non_persistable_claims_count += 1
    if context.relation_governance_mode == "FULL_AUTO":
        _apply_full_auto_claim_status(
            context=context,
            state=state,
            claim_id=claim_id,
            candidate_signature=candidate_signature,
            claim_status="NEEDS_MAPPING",
        )
    _enqueue_claim_review(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate=candidate,
        priority="high",
    )
    state.errors.append("relation_persistence_missing_endpoint_entity_id")
    if should_log_candidate:
        logger.warning(
            "Persist relation candidate missing endpoint entity id",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "validation_state": candidate.validation_state,
                "claim_id": claim_id,
            },
        )
    return True


def _handle_relation_type_activation_failure(  # noqa: PLR0913
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    claim_id: str | None,
    candidate_signature: tuple[str, str, str, str, str],
    index: int,
    should_log_candidate: bool,
) -> bool:
    relation_type_ready = context.helper._ensure_relation_type_exists(
        relation_type=candidate.relation_type,
        source_ref=context.relation_source_ref,
        policy_settings=context.relation_type_settings,
    )
    if relation_type_ready:
        return False
    state.persistence_failed_count += 1
    state.errors.append(
        (
            "relation_persistence_failed:"
            "relation_type_invalid_or_inactive:"
            f"{candidate.relation_type}"
        ),
    )
    if context.relation_governance_mode == "FULL_AUTO":
        _apply_full_auto_claim_status(
            context=context,
            state=state,
            claim_id=claim_id,
            candidate_signature=candidate_signature,
            claim_status="NEEDS_MAPPING",
        )
    _enqueue_claim_review(
        context=context,
        state=state,
        claim_id=claim_id,
        candidate=candidate,
        priority="high",
    )
    if should_log_candidate:
        logger.warning(
            "Persist relation candidate relation type activation failed",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "relation_type": candidate.relation_type,
            },
        )
    return True


def _process_candidate(
    *,
    context: _PersistRunContext,
    state: _CandidateLoopState,
    candidate: _ResolvedRelationCandidate,
    index: int,
) -> None:
    should_log_candidate = _should_log_candidate(
        total_candidates=context.total_candidates,
        index=index,
    )
    if should_log_candidate:
        logger.info(
            "Persist relation candidate started",
            extra={
                "document_id": str(context.document.id),
                "run_id": context.run_id,
                "candidate_index": index,
                "candidate_total": context.total_candidates,
                "source_type": candidate.source_type,
                "relation_type": candidate.relation_type,
                "target_type": candidate.target_type,
                "validation_state": candidate.validation_state,
                "persistability": candidate.persistability,
                "confidence": candidate.confidence,
            },
        )
    effective_candidate, mapping_proposal, canonicalization_metadata = (
        _resolve_effective_candidate(
            context=context,
            candidate=candidate,
            index=index,
            should_log_candidate=should_log_candidate,
        )
    )
    if effective_candidate.validation_state == "FORBIDDEN":
        state.forbidden_count += 1
    if effective_candidate.validation_state == "UNDEFINED":
        state.undefined_count += 1
    candidate_signature = context.helper._candidate_signature(effective_candidate)
    if _maybe_skip_candidate_for_retry_fingerprint(
        context=context,
        state=state,
        candidate=effective_candidate,
        candidate_signature=candidate_signature,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    prepared = _prepare_candidate_write(
        context=context,
        candidate=effective_candidate,
        candidate_signature=candidate_signature,
        mapping_proposal=mapping_proposal,
        canonicalization_metadata=canonicalization_metadata,
    )
    _attach_concept_refs(
        context=context,
        state=state,
        candidate=effective_candidate,
        payload=prepared.payload,
    )
    claim_id = _create_relation_claim(
        context=context,
        state=state,
        candidate=effective_candidate,
        payload=prepared.payload,
        relation_evidence_metadata=prepared.relation_evidence_metadata,
        evidence_sentence=prepared.evidence_sentence,
        evidence_sentence_source=prepared.evidence_sentence_source,
        evidence_sentence_confidence=prepared.evidence_sentence_confidence,
        evidence_sentence_rationale=prepared.evidence_sentence_rationale,
        index=index,
        should_log_candidate=should_log_candidate,
    )
    if _handle_non_persistable_candidate(
        context=context,
        state=state,
        candidate=effective_candidate,
        claim_id=claim_id,
        candidate_signature=prepared.candidate_signature,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    if _handle_non_allowed_governance(
        context=context,
        state=state,
        candidate=effective_candidate,
        claim_id=claim_id,
        candidate_signature=prepared.candidate_signature,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    if _handle_evidence_span_failure(
        context=context,
        state=state,
        candidate=effective_candidate,
        claim_id=claim_id,
        candidate_signature=prepared.candidate_signature,
        relation_evidence_failure=prepared.relation_evidence_failure,
        relation_evidence_metadata=prepared.relation_evidence_metadata,
        payload=prepared.payload,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    if _handle_missing_endpoint_entity_ids(
        context=context,
        state=state,
        candidate=effective_candidate,
        claim_id=claim_id,
        candidate_signature=prepared.candidate_signature,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    if _handle_relation_type_activation_failure(
        context=context,
        state=state,
        candidate=effective_candidate,
        claim_id=claim_id,
        candidate_signature=prepared.candidate_signature,
        index=index,
        should_log_candidate=should_log_candidate,
    ):
        return
    write_outcome = context.helper._persist_candidate_relation(
        document=context.document,
        run_id=context.run_id,
        research_space_id=context.research_space_id,
        relation_governance_mode=context.relation_governance_mode,
        effective_candidate=effective_candidate,
        evidence_summary=prepared.evidence_summary,
        evidence_sentence=prepared.evidence_sentence,
        evidence_sentence_source=prepared.evidence_sentence_source,
        evidence_sentence_confidence=prepared.evidence_sentence_confidence,
        evidence_sentence_rationale=prepared.evidence_sentence_rationale,
        relation_evidence_metadata=prepared.relation_evidence_metadata,
        claim_id=claim_id,
        payload=prepared.payload,
        candidate_signature=prepared.candidate_signature,
        full_auto_retry_index=context.full_auto_retry_index,
        dictionary_fingerprint=context.dictionary_fingerprint,
        index=index,
        total_candidates=context.total_candidates,
        should_log_candidate=should_log_candidate,
    )
    state.persisted_count += write_outcome.persisted_relations_count
    state.pending_count += write_outcome.pending_review_relations_count
    state.relation_claims_count += write_outcome.relation_claims_count_delta
    state.claim_evidence_rows_created_count += (
        write_outcome.claim_evidence_rows_created_count_delta
    )
    state.relation_claims_queued_for_review_count += (
        write_outcome.relation_claims_queued_for_review_count
    )
    state.persistence_failed_count += write_outcome.persistence_failed_count
    state.errors.extend(write_outcome.errors)


def persist_relation_candidates(  # noqa: PLR0913
    *,
    helper: _ExtractionRelationPersistenceHelpers,
    document: SourceDocument,
    run_id: str | None,
    candidates: tuple[_ResolvedRelationCandidate, ...],
    policy_contract: ExtractionPolicyContract | None,
    relation_governance_mode: RelationGovernanceMode,
    research_space_settings: ResearchSpaceSettings,
) -> _PersistCandidatesResult:
    if helper._relations is None:
        return _PersistCandidatesResult(errors=("relation_persistence_unavailable",))
    started_at = datetime.now(UTC)
    research_space_id = (
        str(document.research_space_id)
        if document.research_space_id is not None
        else ""
    )
    total_candidates = len(candidates)
    context = _PersistRunContext(
        helper=helper,
        document=document,
        run_id=run_id,
        relation_governance_mode=relation_governance_mode,
        research_space_settings=research_space_settings,
        research_space_id=research_space_id,
        total_candidates=total_candidates,
        constraint_lookup=helper._index_constraint_proposals(policy_contract),
        mapping_lookup=helper._index_mapping_proposals(policy_contract),
        relation_type_settings={"dictionary_agent_creation_policy": "ACTIVE"},
        relation_source_ref=f"source_document:{document.id}:relation_persist",
        concept_source_ref=f"source_document:{document.id}:concept_persist",
        policy_run_id=normalize_run_id(
            policy_contract.agent_run_id if policy_contract is not None else None,
        ),
        dictionary_fingerprint=helper._resolve_dictionary_fingerprint(),
        full_auto_retry_index=helper._load_full_auto_retry_index(
            research_space_id=research_space_id,
            source_document_id=str(document.id),
            relation_governance_mode=relation_governance_mode,
        ),
    )
    state = _CandidateLoopState()
    logger.info(
        "Persist relation candidates started",
        extra={
            "document_id": str(document.id),
            "run_id": run_id,
            "research_space_id": research_space_id,
            "candidate_count": total_candidates,
            "relation_governance_mode": relation_governance_mode,
        },
    )
    for index, candidate in enumerate(candidates, start=1):
        _process_candidate(
            context=context,
            state=state,
            candidate=candidate,
            index=index,
        )
    logger.info(
        "Persist relation candidates finished",
        extra={
            "document_id": str(document.id),
            "run_id": run_id,
            "duration_ms": int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            "candidate_count": total_candidates,
            "persisted_relations_count": state.persisted_count,
            "pending_review_relations_count": state.pending_count,
            "relation_claims_count": state.relation_claims_count,
            "claim_evidence_rows_created_count": (
                state.claim_evidence_rows_created_count
            ),
            "relation_claims_queued_for_review_count": (
                state.relation_claims_queued_for_review_count
            ),
            "non_persistable_claims_count": state.non_persistable_claims_count,
            "evidence_span_missing_count": state.evidence_span_missing_count,
            "forbidden_relations_count": state.forbidden_count,
            "undefined_relations_count": state.undefined_count,
            "concept_members_created_count": state.concept_members_created_count,
            "concept_aliases_created_count": state.concept_aliases_created_count,
            "concept_decisions_proposed_count": state.concept_decisions_proposed_count,
            "persistence_failed_count": state.persistence_failed_count,
            "full_auto_retry_skipped_count": state.full_auto_retry_skipped_count,
            "error_count": len(state.errors),
        },
    )
    return _PersistCandidatesResult(
        persisted_relations_count=state.persisted_count,
        pending_review_relations_count=state.pending_count,
        relation_claims_count=state.relation_claims_count,
        claim_evidence_rows_created_count=state.claim_evidence_rows_created_count,
        relation_claims_queued_for_review_count=(
            state.relation_claims_queued_for_review_count
        ),
        non_persistable_claims_count=state.non_persistable_claims_count,
        forbidden_relations_count=state.forbidden_count,
        undefined_relations_count=state.undefined_count,
        concept_members_created_count=state.concept_members_created_count,
        concept_aliases_created_count=state.concept_aliases_created_count,
        concept_decisions_proposed_count=state.concept_decisions_proposed_count,
        evidence_span_missing_count=state.evidence_span_missing_count,
        rejected_relation_reasons=tuple(state.rejected_reasons),
        rejected_relation_details=tuple(state.rejected_details),
        persistence_failed_count=state.persistence_failed_count,
        full_auto_retry_skipped_count=state.full_auto_retry_skipped_count,
        errors=tuple(state.errors),
    )


__all__ = ["_PersistCandidatesResult", "persist_relation_candidates"]
