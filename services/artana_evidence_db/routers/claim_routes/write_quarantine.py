"""HTTP enforcement for TG03 AI-authored claim write quarantine."""

from __future__ import annotations

from typing import NoReturn

from artana_evidence_db.auth import graph_write_authorship_for_user
from artana_evidence_db.claim_relation_models import KernelClaimRelation
from artana_evidence_db.graph_api_schemas.governance.authorship import (
    GraphWriteAuthorship,
)
from artana_evidence_db.kernel_domain_models import KernelRelationClaim
from artana_evidence_db.service_contracts import (
    ClaimRelationCreateRequest,
    KernelRelationClaimCreateRequest,
)
from artana_evidence_db.user_models import User
from artana_evidence_db.validation.ai_persistence_quarantine import (
    AIPersistenceQuarantineViolation,
    GraphAIPersistenceQuarantinePolicy,
)
from fastapi import HTTPException, status

_AI_PERSISTENCE_QUARANTINE = GraphAIPersistenceQuarantinePolicy()


def effective_authorship_for_request(
    *,
    current_user: User,
    requested_authorship: GraphWriteAuthorship,
) -> GraphWriteAuthorship:
    """Resolve caller authority before classifying a graph write."""

    return graph_write_authorship_for_user(
        current_user,
        requested_authorship=requested_authorship,
    )


def ensure_ai_claim_persistence_not_ready(
    request: KernelRelationClaimCreateRequest | ClaimRelationCreateRequest,
) -> None:
    """Reject AI-authored claim writes until lossless persistence exists."""

    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_request(request),
    )


def ensure_claim_update_not_quarantined(
    *,
    current_user: User,
    claim: KernelRelationClaim,
) -> None:
    """Reject updates by AI actors or to quarantined claim lineage."""

    _ensure_update_actor_not_quarantined(current_user)
    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_claim(claim),
    )


def ensure_claim_relation_update_not_quarantined(
    *,
    current_user: User,
    relation: KernelClaimRelation,
) -> None:
    """Reject updates by AI actors or to quarantined claim-relation lineage."""

    _ensure_update_actor_not_quarantined(current_user)
    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_claim_relation(relation),
    )


def _ensure_update_actor_not_quarantined(current_user: User) -> None:
    _raise_ai_persistence_quarantine(
        _AI_PERSISTENCE_QUARANTINE.violation_for_authorship_signals(
            authorship=effective_authorship_for_request(
                current_user=current_user,
                requested_authorship="MANUAL",
            ),
            agent_run_id=None,
            metadata={},
        ),
    )


def _raise_ai_persistence_quarantine(
    violation: AIPersistenceQuarantineViolation | None,
) -> None:
    if violation is not None:
        raise_ai_persistence_violation(violation)


def raise_ai_persistence_violation(
    violation: AIPersistenceQuarantineViolation,
) -> NoReturn:
    """Translate one domain quarantine violation to its stable HTTP envelope."""

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=violation.as_detail(),
    )


__all__ = [
    "effective_authorship_for_request",
    "ensure_ai_claim_persistence_not_ready",
    "ensure_claim_relation_update_not_quarantined",
    "ensure_claim_update_not_quarantined",
    "raise_ai_persistence_violation",
]
