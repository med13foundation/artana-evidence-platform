"""Hypothesis workflow routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.claim_metrics import increment_metric
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_concept_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.kernel_services import (
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.semantic_ports import ConceptPort
from artana_evidence_db.service_contracts import (
    CreateManualHypothesisRequest,
    HypothesisListResponse,
    HypothesisResponse,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["hypotheses"])


@router.get(
    "/{space_id}/hypotheses",
    response_model=HypothesisListResponse,
    summary="List hypothesis claims in one graph space",
)
def list_hypotheses(
    space_id: UUID,
    *,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> HypothesisListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    hypotheses = relation_claim_service.list_by_research_space(
        str(space_id),
        polarity="HYPOTHESIS",
        limit=limit,
        offset=offset,
    )
    total = relation_claim_service.count_by_research_space(
        str(space_id),
        polarity="HYPOTHESIS",
    )
    return HypothesisListResponse(
        hypotheses=[HypothesisResponse.from_claim(claim) for claim in hypotheses],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/hypotheses/manual",
    response_model=HypothesisResponse,
    summary="Create one manual hypothesis claim",
)
def create_manual_hypothesis(  # noqa: PLR0912,PLR0915
    space_id: UUID,
    request: CreateManualHypothesisRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    session: Session = Depends(get_session),
) -> HypothesisResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    try:
        normalized_statement = request.statement.strip()
        normalized_rationale = request.rationale.strip()
        if not normalized_statement:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="statement is required",
            )
        if not normalized_rationale:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rationale is required",
            )

        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
        (
            participant_seed_entity_ids,
            unresolved_seed_entity_ids,
        ) = _resolve_seed_entities_for_participants(
            seed_entity_ids=seed_entity_ids,
            space_id=space_id,
            entity_service=entity_service,
        )
        normalized_source_type = request.source_type.strip()

        concept_set_id = _resolve_hypothesis_concept_set_id(
            concept_service=concept_service,
            space_id=space_id,
        )
        concept_decision_id: str | None = None
        concept_decision_error: str | None = None

        decision_payload: JSONObject = {
            "workflow": "hypothesis",
            "statement": normalized_statement,
            "rationale": normalized_rationale,
            "seed_entity_ids": seed_entity_ids,
            "participant_seed_entity_ids": participant_seed_entity_ids,
            "source_type": normalized_source_type,
        }
        if unresolved_seed_entity_ids:
            decision_payload["unresolved_seed_entity_ids"] = unresolved_seed_entity_ids
        if concept_set_id is not None:
            try:
                concept_decision = concept_service.propose_decision(
                    research_space_id=str(space_id),
                    decision_type="CREATE",
                    proposed_by=f"manual:{current_user.id}",
                    decision_payload=decision_payload,
                    evidence_payload={"origin": "manual"},
                    confidence=None,
                    rationale=normalized_rationale,
                    concept_set_id=concept_set_id,
                )
                concept_decision_id = concept_decision.id
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                concept_decision_error = str(exc)
        else:
            concept_decision_error = "missing_concept_set"

        metadata_payload: JSONObject = {
            "workflow": "hypothesis",
            "origin": "manual",
            "statement": normalized_statement,
            "rationale": normalized_rationale,
            "seed_entity_ids": participant_seed_entity_ids,
            "requested_seed_entity_ids": seed_entity_ids,
            "source_type": normalized_source_type,
            "actor_user_id": str(current_user.id),
        }
        if unresolved_seed_entity_ids:
            metadata_payload["unresolved_seed_entity_ids"] = unresolved_seed_entity_ids
            metadata_payload["manual_warnings"] = [
                "some_seed_entity_ids_not_found_in_space",
            ]
        if concept_decision_id is not None:
            metadata_payload["concept_decision_id"] = concept_decision_id
        if concept_decision_error is not None:
            metadata_payload["concept_decision_error"] = concept_decision_error

        claim = relation_claim_service.create_hypothesis_claim(
            research_space_id=str(space_id),
            source_document_id=None,
            agent_run_id=None,
            source_type="HYPOTHESIS",
            relation_type="PROPOSES",
            target_type="HYPOTHESIS",
            source_label="Manual hypothesis",
            target_label=None,
            confidence=0.5,
            validation_state="UNDEFINED",
            validation_reason="manual_hypothesis_submission",
            persistability="NON_PERSISTABLE",
            claim_text=normalized_statement,
            metadata=metadata_payload,
            claim_status="OPEN",
        )
        if participant_seed_entity_ids:
            for index, seed_entity_id in enumerate(participant_seed_entity_ids):
                claim_participant_service.create_participant(
                    claim_id=str(claim.id),
                    research_space_id=str(space_id),
                    role="SUBJECT",
                    label=None,
                    entity_id=seed_entity_id,
                    position=index,
                    qualifiers=None,
                )
        else:
            claim_participant_service.create_participant(
                claim_id=str(claim.id),
                research_space_id=str(space_id),
                role="SUBJECT",
                label=normalized_statement,
                entity_id=None,
                position=0,
                qualifiers=None,
            )

        increment_metric(
            "hypotheses_manual_created_total",
            tags={"research_space_id": str(space_id)},
        )
        session.commit()
        return HypothesisResponse.from_claim(claim)
    except HTTPException:
        session.rollback()
        raise
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        message = f"Manual hypothesis creation failed: {exc!s}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=message,
        ) from exc


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in seed_entity_ids:
        trimmed = value.strip()
        if not trimmed:
            continue
        canonical = str(UUID(trimmed))
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)
    return normalized


def _resolve_hypothesis_concept_set_id(
    *,
    concept_service: ConceptPort,
    space_id: UUID,
) -> str | None:
    existing_sets = concept_service.list_concept_sets(
        research_space_id=str(space_id),
        include_inactive=True,
    )
    if existing_sets:
        return existing_sets[0].id
    return None


def _resolve_seed_entities_for_participants(
    *,
    seed_entity_ids: list[str],
    space_id: UUID,
    entity_service: KernelEntityService,
) -> tuple[list[str], list[str]]:
    resolved: list[str] = []
    unresolved: list[str] = []
    for entity_id in seed_entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None:
            unresolved.append(entity_id)
            continue
        if str(entity.research_space_id) != str(space_id):
            unresolved.append(entity_id)
            continue
        resolved.append(str(entity.id))
    return resolved, unresolved


__all__ = [
    "create_manual_hypothesis",
    "list_hypotheses",
    "router",
]
