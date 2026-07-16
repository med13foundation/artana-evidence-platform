"""Cross-service contract parity for source provenance handoff fields."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_api.types.graph_contracts import (
    KernelClaimEvidenceResponse as ApiClaimEvidenceResponse,
)
from artana_evidence_api.types.graph_contracts import (
    KernelRelationClaimCreateRequest as ApiClaimCreateRequest,
)
from artana_evidence_api.types.source_provenance import (
    ExactEvidenceLocator as ApiEvidenceLocator,
)
from artana_evidence_api.types.source_provenance import (
    SourceEvidenceHandoff as ApiSourceEvidenceHandoff,
)
from artana_evidence_api.types.source_provenance import (
    SourceEvidenceUpstream as ApiSourceEvidenceUpstream,
)
from artana_evidence_api.types.source_provenance import (
    SourceIdentity as ApiSourceIdentity,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelClaimEvidenceResponse as GraphClaimEvidenceResponse,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest as GraphClaimCreateRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationTripleValidationRequest as GraphTripleValidationRequest,
)
from artana_evidence_db.source_provenance.models import (
    ExactEvidenceLocator as GraphEvidenceLocator,
)
from artana_evidence_db.source_provenance.models import (
    SourceEvidenceHandoff as GraphSourceEvidenceHandoff,
)
from artana_evidence_db.source_provenance.models import (
    SourceEvidenceUpstream as GraphSourceEvidenceUpstream,
)
from artana_evidence_db.source_provenance.models import (
    SourceIdentity as GraphSourceIdentity,
)


def test_source_identity_and_locator_fields_match_across_services() -> None:
    assert _property_names(ApiSourceIdentity) == _property_names(GraphSourceIdentity)
    assert _property_names(ApiEvidenceLocator) == _property_names(GraphEvidenceLocator)
    assert _property_names(ApiSourceEvidenceUpstream) == _property_names(
        GraphSourceEvidenceUpstream,
    )
    assert _property_names(ApiSourceEvidenceHandoff) == _property_names(
        GraphSourceEvidenceHandoff,
    )


def test_claim_handoff_exposes_same_snapshot_proof_fields() -> None:
    required_handoff = {
        "source_document_id",
        "source_evidence",
    }

    assert required_handoff <= set(ApiClaimCreateRequest.model_fields)
    assert required_handoff <= set(GraphClaimCreateRequest.model_fields)
    assert required_handoff <= set(GraphTripleValidationRequest.model_fields)


def test_graph_evidence_response_round_trips_through_api_contract() -> None:
    text = "MED13 is associated with cardiomyopathy."
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    graph_response = GraphClaimEvidenceResponse(
        id=uuid4(),
        claim_id=uuid4(),
        source_document_id=uuid4(),
        source_document_ref="PMID:12345678",
        source_snapshot_id=uuid4(),
        source_identity=GraphSourceIdentity(
            source_kind="pubmed",
            authoritative_identifier="PMID:12345678",
            canonical_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            retrieved_at=now,
            content_sha256=content_hash,
            pmid="12345678",
        ),
        evidence_locator=GraphEvidenceLocator(
            source_content_sha256=content_hash,
            char_start=0,
            char_end=len(text),
            exact_quote=text,
            quote_sha256=content_hash,
        ),
        provenance_status="VERIFIED",
        provenance_reason_codes=["verified"],
        sentence=text,
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.9,
        metadata={},
        created_at=now,
    )

    parsed = ApiClaimEvidenceResponse.model_validate_json(
        graph_response.model_dump_json(),
    )

    assert parsed.provenance_status == "VERIFIED"
    assert parsed.source_snapshot_id == graph_response.source_snapshot_id
    assert parsed.source_identity is not None
    assert parsed.source_identity.authoritative_identifier == "PMID:12345678"
    assert parsed.evidence_locator is not None
    assert parsed.evidence_locator.exact_quote == text


def _property_names(model: type) -> set[str]:
    return set(model.model_json_schema()["properties"])
