"""Manual relation persistence routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from artana_evidence_db.auth import (
    get_current_active_user,
    graph_service_capability_for_user,
    graph_source_attestation_service_for_user,
    graph_write_authorship_for_user,
    is_graph_service_admin,
)
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_dictionary_service,
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_materialization_service,
    get_kernel_relation_projection_source_service,
    get_kernel_relation_service,
    get_source_provenance_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationProjectionMaterializationService,
    KernelRelationProjectionSourceService,
    KernelRelationService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.relation_projection_materialization_support import (
    RelationProjectionMaterializationError,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationResponse,
    KernelRelationTripleValidationRequest,
)
from artana_evidence_db.source_provenance.http import require_verified_source_snapshot
from artana_evidence_db.source_provenance.service import (
    SourceProvenanceService,
    claim_evidence_provenance_status,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from artana_evidence_db.validation.ai_persistence_quarantine import (
    AIPersistenceQuarantineViolation,
    GraphAIPersistenceQuarantinePolicy,
)
from artana_evidence_db.validation.source_evidence_write_validation import (
    SourceEvidenceWriteValidationService,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter()

_CANONICAL_CURATION_STATUSES = frozenset(
    {"APPROVED", "UNDER_REVIEW", "DRAFT", "REJECTED", "RETRACTED"},
)
_SOURCE_EVIDENCE_WRITE_VALIDATION = SourceEvidenceWriteValidationService()
_AI_PERSISTENCE_QUARANTINE = GraphAIPersistenceQuarantinePolicy()


def _ensure_ai_claim_persistence_not_ready(
    request: KernelRelationCreateRequest,
) -> None:
    violation = _AI_PERSISTENCE_QUARANTINE.violation_for_request(request)
    _raise_ai_persistence_quarantine(violation)


def _raise_ai_persistence_quarantine(
    violation: AIPersistenceQuarantineViolation | None,
) -> None:
    if violation is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=violation.as_detail(),
    )


def _validate_source_evidence_write_or_raise(
    request: KernelRelationCreateRequest,
    *,
    subject_names: tuple[str, ...],
    object_names: tuple[str, ...],
) -> None:
    issue = _SOURCE_EVIDENCE_WRITE_VALIDATION.validate(
        request,
        subject_names=subject_names,
        object_names=object_names,
    )
    if issue is None:
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": issue.code,
            "message": issue.message,
            "persistability": "NON_PERSISTABLE",
        },
    )


def _normalize_curation_status_update(status_value: str) -> str:
    normalized = status_value.strip().upper()
    if normalized not in _CANONICAL_CURATION_STATUSES:
        msg = "curation_status must be one of: " + ", ".join(
            sorted(_CANONICAL_CURATION_STATUSES),
        )
        raise ValueError(msg)
    return normalized


def _normalize_claim_evidence_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None


def _manual_relation_claim_text(
    *,
    evidence_summary: str | None,
    evidence_sentence: str | None,
    relation_type: str,
    source_label: str | None,
    target_label: str | None,
) -> str:
    if evidence_sentence is not None and evidence_sentence.strip():
        return evidence_sentence.strip()[:2000]
    if evidence_summary is not None and evidence_summary.strip():
        return evidence_summary.strip()[:2000]
    source_text = source_label.strip() if source_label is not None else ""
    target_text = target_label.strip() if target_label is not None else ""
    if source_text and target_text:
        return f"{source_text} {relation_type} {target_text}"
    if source_text:
        return f"{source_text} {relation_type}"
    if target_text:
        return f"{relation_type} {target_text}"
    return relation_type


def _build_validation_error_detail(validation: object) -> dict[str, object]:
    next_actions = getattr(validation, "next_actions", [])
    serialized_next_actions = [
        action.model_dump(mode="json") for action in next_actions
    ]
    return {
        "code": getattr(validation, "code", "validation_failed"),
        "message": getattr(validation, "message", "Relation validation failed."),
        "severity": getattr(validation, "severity", "blocking"),
        "validation_state": getattr(validation, "validation_state", None),
        "persistability": getattr(validation, "persistability", None),
        "next_actions": serialized_next_actions,
    }


@router.post(
    "/{space_id}/relations",
    response_model=KernelRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one canonical relation from a manual support claim",
)
def create_relation(  # noqa: PLR0915
    space_id: UUID,
    request: KernelRelationCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
    source_provenance_service: SourceProvenanceService = Depends(
        get_source_provenance_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    if not is_graph_service_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "POST /relations requires graph-service admin access. Create or "
                "resolve claims to materialize canonical relations."
            ),
        )
    request = request.model_copy(
        update={
            "authorship": graph_write_authorship_for_user(
                current_user,
                requested_authorship=request.authorship,
            ),
        },
    )
    _ensure_ai_claim_persistence_not_ready(request)

    try:
        source_entity = entity_service.get_entity(str(request.source_id))
        target_entity = entity_service.get_entity(str(request.target_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != str(space_id)
            or str(target_entity.research_space_id) != str(space_id)
        ):
            msg = "Source or target entity not found"
            raise ValueError(msg)

        validation_service = GraphValidationService(
            entity_service=entity_service,
            dictionary_service=dictionary_service,
        )
        validation = validation_service.validate_triple(
            space_id=str(space_id),
            request=KernelRelationTripleValidationRequest(
                source_entity_id=request.source_id,
                target_entity_id=request.target_id,
                relation_type=request.relation_type,
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                source_document_id=request.source_document_id,
                source_evidence=request.source_evidence,
                source_document_ref=request.source_document_ref,
            ),
        )
        canonical_relation_type = validation.normalized_relation_type
        if not canonical_relation_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="relation_type is required",
            )
        if (
            not validation.valid
            or validation.persistability != "PERSISTABLE"
            or validation.code != "allowed"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_build_validation_error_detail(validation),
            )
        ai_validation = validation_service.validate_ai_authored_relation_request(
            request=request,
            triple_validation=validation,
        )
        if ai_validation is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_build_validation_error_detail(ai_validation),
            )
        _validate_source_evidence_write_or_raise(
            request,
            subject_names=tuple(
                name
                for name in [source_entity.display_label, *source_entity.aliases]
                if name is not None
            ),
            object_names=tuple(
                name
                for name in [target_entity.display_label, *target_entity.aliases]
                if name is not None
            ),
        )
        provenance_submission = source_provenance_service.verify_and_snapshot(
            research_space_id=space_id,
            source_document_id=request.source_document_id,
            source_evidence=request.source_evidence,
            source_attestation_capability=graph_service_capability_for_user(
                current_user,
                "source_provenance_submit",
            ),
            authenticated_attestation_service=(
                graph_source_attestation_service_for_user(current_user)
            ),
        )
        source_snapshot = require_verified_source_snapshot(provenance_submission)
        confidence_metadata = fact_assessment_metadata(request.assessment)
        derived_confidence = request.derived_confidence
        manual_claim = relation_claim_service.create_claim(
            research_space_id=str(space_id),
            source_document_id=(
                str(request.source_document_id)
                if request.source_document_id is not None
                else None
            ),
            source_document_ref=request.source_document_ref,
            authorship=request.authorship,
            agent_run_id=None,
            source_type=source_entity.entity_type,
            relation_type=canonical_relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=derived_confidence,
            validation_state="ALLOWED",
            validation_reason="Created via canonical relation API",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text=_manual_relation_claim_text(
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                relation_type=canonical_relation_type,
                source_label=source_entity.display_label,
                target_label=target_entity.display_label,
            ),
            claim_section=None,
            linked_relation_id=None,
            metadata={
                **request.metadata,
                "authorship": request.authorship,
                "origin": "manual_relation_api",
                "source_entity_id": str(request.source_id),
                "target_entity_id": str(request.target_id),
                **confidence_metadata,
                "provenance_id": (
                    str(request.provenance_id)
                    if request.provenance_id is not None
                    else None
                ),
            },
        )
        claim_id = str(manual_claim.id)
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "manual_relation_api"},
        )
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="OBJECT",
            label=target_entity.display_label,
            entity_id=str(target_entity.id),
            position=1,
            qualifiers={"origin": "manual_relation_api"},
        )
        claim_evidence_service.create_evidence(
            claim_id=claim_id,
            source_document_id=(
                str(request.source_document_id)
                if request.source_document_id is not None
                else None
            ),
            source_document_ref=request.source_document_ref,
            source_snapshot_id=str(source_snapshot.id),
            agent_run_id=None,
            sentence=(
                request.evidence_sentence
                or (
                    request.source_evidence.locator.exact_quote
                    if request.source_evidence is not None
                    else None
                )
            ),
            sentence_source=_normalize_claim_evidence_sentence_source(
                request.evidence_sentence_source,
            ),
            sentence_confidence=_normalize_claim_evidence_sentence_confidence(
                request.evidence_sentence_confidence,
            ),
            sentence_rationale=request.evidence_sentence_rationale,
            figure_reference=(
                request.source_evidence.locator.figure_reference
                if request.source_evidence is not None
                else None
            ),
            table_reference=(
                request.source_evidence.locator.table_reference
                if request.source_evidence is not None
                else None
            ),
            confidence=derived_confidence,
            evidence_locator=(
                request.source_evidence.locator
                if request.source_evidence is not None
                else None
            ),
            provenance_status=claim_evidence_provenance_status(
                provenance_submission.verification,
            ),
            provenance_reason_codes=provenance_submission.verification.reason_codes,
            metadata={
                **request.metadata,
                "authorship": request.authorship,
                "origin": "manual_relation_api",
                "evidence_summary": request.evidence_summary,
                "evidence_tier": request.evidence_tier or "COMPUTATIONAL",
                **confidence_metadata,
                "provenance_id": (
                    str(request.provenance_id)
                    if request.provenance_id is not None
                    else None
                ),
            },
        )
        materialized = (
            relation_projection_materialization_service.materialize_support_claim(
                claim_id=claim_id,
                research_space_id=str(space_id),
                projection_origin="MANUAL_RELATION",
                reviewed_by=str(current_user.id),
            )
        )
        relation = materialized.relation
        if relation is None:
            msg = "Manual relation claim did not materialize a canonical relation"
            raise ValueError(msg)
        session.commit()
        return KernelRelationResponse.from_model(
            relation,
            source_claim_id=claim_id,
        )
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation write conflicts with dictionary constraints, "
                "research-space isolation, or required evidence checks"
            ),
        ) from exc
    except RelationProjectionMaterializationError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relation: {exc!s}",
        ) from exc


@router.put(
    "/{space_id}/relations/{relation_id}",
    response_model=KernelRelationResponse,
    summary="Update one relation curation status",
)
def update_relation_curation_status(
    space_id: UUID,
    relation_id: UUID,
    request: KernelRelationCurationUpdateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    relation_projection_source_service: KernelRelationProjectionSourceService = Depends(
        get_kernel_relation_projection_source_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )

    existing = relation_service.get_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation not found",
        )
    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_authorship_signals(
            authorship=graph_write_authorship_for_user(
                current_user,
                requested_authorship="MANUAL",
            ),
            agent_run_id=None,
            metadata={},
        ),
    )
    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_relation_lineage(
            projection_sources=relation_projection_source_service.list_for_relation(
                str(relation_id),
            ),
            evidence_rows=relation_service.list_evidence_for_relation(
                research_space_id=str(space_id),
                relation_id=str(relation_id),
            ),
        ),
    )

    try:
        normalized_status = _normalize_curation_status_update(request.curation_status)
        updated = relation_service.update_curation_status(
            str(relation_id),
            curation_status=normalized_status,
            reviewed_by=str(current_user.id),
        )
        session.commit()
        return KernelRelationResponse.from_model(updated)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update relation: {exc!s}",
        ) from exc


__all__ = ["create_relation", "router", "update_relation_curation_status"]
