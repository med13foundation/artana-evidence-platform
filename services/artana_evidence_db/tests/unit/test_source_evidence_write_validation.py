"""Unit tests for graph-owned source-evidence write binding."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
)
from artana_evidence_db.source_provenance.models import (
    SourceEvidenceHandoff,
    SourceEvidenceUpstream,
    SourceIdentity,
)
from artana_evidence_db.validation.source_evidence_write_validation import (
    SourceEvidenceWriteValidationService,
)

_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The exact source sentence supports the relation.",
}


def test_manual_write_without_source_evidence_remains_available() -> None:
    request = KernelRelationClaimCreateRequest(
        source_entity_id=uuid4(),
        target_entity_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        assessment=_ASSESSMENT,
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13",),
        object_names=("Developmental delay",),
    )

    assert issue is None


def test_source_sentence_must_equal_verified_exact_quote() -> None:
    request = _request(
        evidence_sentence="MED13 is associated with developmental delay.",
        exact_quote="MED13 is associated with developmental delay in adults.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13",),
        object_names=("Developmental delay",),
    )

    assert issue is not None
    assert issue.code == "invalid_source_evidence_binding"
    assert "exact_quote" in issue.message


def test_source_quote_requires_complete_endpoint_boundaries() -> None:
    request = _request(
        evidence_sentence="MED13A is associated with developmental delay.",
        exact_quote="MED13A is associated with developmental delay.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13",),
        object_names=("Developmental delay",),
    )

    assert issue is not None
    assert "source endpoint label" in issue.message


def test_source_quote_with_both_endpoint_labels_passes() -> None:
    request = _request(
        evidence_sentence="MED13 is associated with developmental delay.",
        exact_quote="MED13 is associated with developmental delay.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13",),
        object_names=("Developmental delay",),
    )

    assert issue is None


def test_exact_quote_supplies_omitted_evidence_sentence() -> None:
    request = _request(
        evidence_sentence=None,
        exact_quote="MED13 is associated with developmental delay.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13",),
        object_names=("Developmental delay",),
    )

    assert issue is None


def test_endpoint_aliases_can_bind_exact_evidence() -> None:
    request = _request(
        evidence_sentence="THRAP1 is associated with global delay.",
        exact_quote="THRAP1 is associated with global delay.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("MED13", "THRAP1"),
        object_names=("Developmental delay", "global delay"),
    )

    assert issue is None


def test_same_label_endpoints_require_two_distinct_occurrences() -> None:
    request = _request(
        evidence_sentence="Alpha is associated with disease.",
        exact_quote="Alpha is associated with disease.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("Alpha",),
        object_names=("Alpha",),
    )

    assert issue is not None
    assert "distinct, non-overlapping" in issue.message


def test_same_label_endpoints_accept_two_distinct_occurrences() -> None:
    request = _request(
        evidence_sentence="Alpha regulates a second Alpha molecule.",
        exact_quote="Alpha regulates a second Alpha molecule.",
    )

    issue = SourceEvidenceWriteValidationService().validate(
        request,
        subject_names=("Alpha",),
        object_names=("Alpha",),
    )

    assert issue is None


def _request(
    *,
    evidence_sentence: str | None,
    exact_quote: str,
) -> KernelRelationClaimCreateRequest:
    document_id = uuid4()
    source_hash = hashlib.sha256(exact_quote.encode("utf-8")).hexdigest()
    handoff = SourceEvidenceHandoff(
        upstream=SourceEvidenceUpstream(
            research_space_id=uuid4(),
            document_id=document_id,
            attested_at=datetime.now(UTC),
        ),
        identity=SourceIdentity(
            source_kind="pubmed",
            authoritative_identifier="PMID:12345678",
            canonical_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            retrieved_at=datetime.now(UTC),
            content_sha256=source_hash,
            pmid="12345678",
        ),
        canonical_text=exact_quote,
        locator={
            "source_content_sha256": source_hash,
            "char_start": 0,
            "char_end": len(exact_quote),
            "exact_quote": exact_quote,
            "quote_sha256": source_hash,
        },
    )
    return KernelRelationClaimCreateRequest(
        source_entity_id=uuid4(),
        target_entity_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        assessment=_ASSESSMENT,
        evidence_sentence=evidence_sentence,
        source_document_id=document_id,
        source_evidence=handoff,
    )
