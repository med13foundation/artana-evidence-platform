"""Graph-owned quarantine policy for AI-authored persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from artana_evidence_db.claim_relation_models import KernelClaimRelation
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_api_schemas.claim_graph_schemas import (
    ClaimRelationCreateRequest,
)
from artana_evidence_db.graph_api_schemas.governance.authorship import (
    GraphWriteAuthorship,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from artana_evidence_db.kernel_domain_models import KernelRelationClaim
from artana_evidence_db.relation_projection_source_model import (
    KernelRelationProjectionSource,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from artana_evidence_db.claim_evidence_models import KernelClaimEvidence
    from artana_evidence_db.graph_core_models import KernelRelationEvidence

GraphAuthoredWriteRequest = (
    KernelRelationClaimCreateRequest
    | KernelRelationCreateRequest
    | ClaimRelationCreateRequest
)


class AuthoredClaimLike(Protocol):
    """Anything carrying the two fields that decide claim authorship."""

    agent_run_id: str | None
    metadata_payload: JSONObject


@dataclass(frozen=True, slots=True)
class AIPersistenceQuarantineViolation:
    """Stable failure returned whenever an AI graph write reaches TG-03."""

    code: str = "qualified_claim_persistence_not_ready"
    message: str = (
        "AI-authored claim/relation persistence is quarantined until TG04 adds "
        "lossless ClaimFrame persistence."
    )
    persistability: str = "NON_PERSISTABLE"

    def as_detail(self) -> dict[str, str]:
        """Return the public API error envelope."""

        return {
            "code": self.code,
            "message": self.message,
            "persistability": self.persistability,
        }


class AIPersistenceQuarantineError(RuntimeError):
    """Internal fail-closed error for non-HTTP persistence boundaries."""

    def __init__(self, violation: AIPersistenceQuarantineViolation) -> None:
        super().__init__(f"{violation.code}: {violation.message}")
        self.violation = violation


class GraphAIPersistenceQuarantinePolicy:
    """Classify authorship once and fail closed across graph mutation paths."""

    def violation_for_request(
        self,
        request: GraphAuthoredWriteRequest,
    ) -> AIPersistenceQuarantineViolation | None:
        """Return the TG-03 quarantine violation for an AI-authored request."""

        if not self.is_agent_authored_request(request):
            return None
        return AIPersistenceQuarantineViolation()

    def violation_for_authorship_signals(
        self,
        *,
        authorship: GraphWriteAuthorship,
        agent_run_id: str | None,
        metadata: JSONObject,
    ) -> AIPersistenceQuarantineViolation | None:
        """Protect lower-level services that do not receive an API request model."""

        if (
            authorship == "AGENT"
            or _has_text(agent_run_id)
            or _metadata_is_agent_authored(metadata)
        ):
            return AIPersistenceQuarantineViolation()
        return None

    def is_agent_authored_request(self, request: GraphAuthoredWriteRequest) -> bool:
        """Use typed authorship first, then conservative legacy signals."""

        if request.authorship == "AGENT":
            return True
        if isinstance(
            request,
            KernelRelationClaimCreateRequest | ClaimRelationCreateRequest,
        ) and _has_text(request.agent_run_id):
            return True
        if (
            isinstance(request, KernelRelationClaimCreateRequest)
            and request.ai_provenance is not None
        ):
            return True
        if _metadata_is_agent_authored(request.metadata):
            return True
        if isinstance(
            request,
            KernelRelationClaimCreateRequest | KernelRelationCreateRequest,
        ):
            return _normalized(request.evidence_sentence_source) in _AI_MARKERS
        return False

    def violation_for_claim(
        self,
        claim: AuthoredClaimLike,
    ) -> AIPersistenceQuarantineViolation | None:
        """Protect legacy claim update and materialization paths.

        Typed structurally: this reads two attributes, and callers legitimately
        hold either the domain `KernelRelationClaim` or the ORM
        `GraphRelationClaimModel` depending on how they loaded the claim.  The
        per-space and global participant backfills are one such pair (#186), and
        requiring the domain type there would mean converting rows purely to
        satisfy a signature.
        """

        if _has_text(claim.agent_run_id) or _metadata_is_agent_authored(
            claim.metadata_payload,
        ):
            return AIPersistenceQuarantineViolation()
        return None

    def violation_for_claim_relation(
        self,
        relation: KernelClaimRelation,
    ) -> AIPersistenceQuarantineViolation | None:
        """Protect legacy claim-relation review paths."""

        if _has_text(relation.agent_run_id) or _metadata_is_agent_authored(
            relation.metadata_payload,
        ):
            return AIPersistenceQuarantineViolation()
        return None

    def violation_for_projection_claim_lineage(
        self,
        *,
        claim: KernelRelationClaim,
        projection_source: KernelRelationProjectionSource,
        evidence_rows: Iterable[KernelClaimEvidence],
    ) -> AIPersistenceQuarantineViolation | None:
        """Classify one claim lineage before rebuilding a canonical projection."""

        if self.violation_for_claim(claim) is not None:
            return AIPersistenceQuarantineViolation()
        if _projection_source_is_agent_authored(projection_source):
            return AIPersistenceQuarantineViolation()
        if any(_claim_evidence_is_agent_authored(row) for row in evidence_rows):
            return AIPersistenceQuarantineViolation()
        return None

    def violation_for_relation_lineage(
        self,
        *,
        projection_sources: Iterable[KernelRelationProjectionSource],
        evidence_rows: Iterable[KernelRelationEvidence],
    ) -> AIPersistenceQuarantineViolation | None:
        """Protect legacy canonical relations using their persisted lineage."""

        if any(_projection_source_is_agent_authored(row) for row in projection_sources):
            return AIPersistenceQuarantineViolation()
        if any(
            _has_text(evidence.agent_run_id)
            or _normalized(evidence.evidence_sentence_source) in _AI_MARKERS
            for evidence in evidence_rows
        ):
            return AIPersistenceQuarantineViolation()
        return None


def _projection_source_is_agent_authored(
    source: KernelRelationProjectionSource,
) -> bool:
    return _has_text(source.agent_run_id) or _metadata_is_agent_authored(
        source.metadata_payload,
    )


def _claim_evidence_is_agent_authored(evidence: KernelClaimEvidence) -> bool:
    return (
        _has_text(evidence.agent_run_id)
        or _metadata_is_agent_authored(evidence.metadata_payload)
        or _normalized(evidence.sentence_source) in _AI_MARKERS
    )


def _metadata_is_agent_authored(metadata: JSONObject) -> bool:
    for key in _AI_METADATA_KEYS:
        value = metadata.get(key)
        if value is not None and value is not False:
            return True
    for key in _AUTHORSHIP_METADATA_FIELDS:
        marker = metadata.get(key)
        if isinstance(marker, str) and _is_ai_marker(marker):
            return True
    return False


def _is_ai_marker(value: str) -> bool:
    normalized = _normalized(value)
    if normalized is None:
        return False
    return normalized in _AI_MARKERS or normalized.startswith(("agent:", "ai:"))


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


_AI_METADATA_KEYS = frozenset(
    {
        "agent_run_id",
        "ai_provenance",
        "artana_idempotency_key",
        "extraction_agent_run_id",
        "harness_run_id",
    },
)
_AUTHORSHIP_METADATA_FIELDS = frozenset(
    {"authorship", "origin", "source", "author_type", "created_by"},
)
_AI_MARKERS = frozenset(
    {
        "agent",
        "ai",
        "ai_generated",
        "artana",
        "artana_generated",
        "artana_kernel",
        "document_extraction",
        "graph_harness",
        "llm",
        "llm_generated",
    },
)

__all__ = [
    "AIPersistenceQuarantineError",
    "AIPersistenceQuarantineViolation",
    "GraphAIPersistenceQuarantinePolicy",
]
