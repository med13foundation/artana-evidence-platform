"""Tests for authoritative source identity and exact locator construction."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.graph_integration.source_provenance import (
    SourceProvenanceError,
    bind_source_provenance_to_drafts,
    exact_locator_for_quote,
    source_identity_for_document,
    source_provenance_for_proposal,
    verify_persisted_source_provenance,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
)
from artana_evidence_api.types.source_provenance import ClaimSourceProvenance


def _document(
    *,
    text: str = "Background. MED13 was associated with cardiomyopathy.",
    metadata: dict[str, object] | None = None,
) -> HarnessDocumentRecord:
    now = datetime(2026, 7, 14, 12, 30, tzinfo=UTC)
    return HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="MED13 study",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        byte_size=len(text.encode("utf-8")),
        page_count=None,
        text_content=text,
        text_excerpt=text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata=(
            {
                "pubmed": {
                    "pmid": "12345678",
                    "pmc_id": "PMC7654321",
                    "doi": "10.1000/example",
                },
                "source_capture": {
                    "source_key": "pubmed",
                    "external_id": "12345678",
                    "retrieved_at": "2026-07-14T12:00:00+00:00",
                    "provenance": {"version": "efetch-2026-07-14"},
                },
            }
            if metadata is None
            else metadata
        ),
        created_at=now,
        updated_at=now,
    )


def _proposal(
    *,
    document: HarnessDocumentRecord,
    quote: str = "MED13 was associated with cardiomyopathy.",
    locator: str | None = None,
) -> HarnessProposalRecord:
    now = datetime(2026, 7, 14, 12, 45, tzinfo=UTC)
    quote_start = document.text_content.index(quote)
    resolved_locator = locator or f"char:{quote_start}-{quote_start + len(quote)}"
    return HarnessProposalRecord(
        id=str(uuid4()),
        space_id=document.space_id,
        run_id=str(uuid4()),
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=f"{document.id}:relation:0",
        document_id=document.id,
        title="Extracted claim",
        summary=quote,
        status="pending_review",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={"claim_section": "Results"},
        evidence_bundle=[
            {
                "source_type": "pubmed",
                "locator": resolved_locator,
                "excerpt": quote,
            },
        ],
        payload={
            "proposed_subject": str(uuid4()),
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": str(uuid4()),
        },
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def test_source_identity_preserves_all_pubmed_identifiers_and_snapshot_hash() -> None:
    document = _document()

    identity = source_identity_for_document(document)

    assert identity.source_kind == "pubmed"
    assert identity.authoritative_identifier == "PMID:12345678"
    assert identity.canonical_url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert identity.pmid == "12345678"
    assert identity.pmcid == "PMC7654321"
    assert identity.doi == "10.1000/example"
    assert identity.content_sha256 == hashlib.sha256(
        document.text_content.encode("utf-8"),
    ).hexdigest()
    assert identity.artifact_sha256 == document.sha256
    assert identity.version == "efetch-2026-07-14"
    assert identity.retrieved_at == datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def test_source_identity_treats_sql_document_timestamp_as_utc() -> None:
    document = replace(
        _document(
            metadata={
                "pubmed": {"pmid": "12345678"},
                "source_capture": {
                    "source_key": "pubmed",
                    "external_id": "12345678",
                },
            },
        ),
        created_at=datetime(2026, 7, 14, 12, 30, tzinfo=UTC).replace(tzinfo=None),
    )

    identity = source_identity_for_document(document)

    assert identity.retrieved_at == datetime(2026, 7, 14, 12, 30, tzinfo=UTC)


def test_source_identity_uses_pmc_when_stored_text_came_from_pmc() -> None:
    document = _document()
    document = replace(
        document,
        metadata={**document.metadata, "content_source_kind": "pmc"},
    )

    identity = source_identity_for_document(document)

    assert identity.source_kind == "pmc"
    assert identity.authoritative_identifier == "PMCID:PMC7654321"


def test_internal_document_reference_is_not_an_authoritative_identity() -> None:
    document = _document(
        metadata={
            "source_capture": {
                "source_key": "pubmed",
                "locator": f"harness_proposal:{uuid4()}",
                "retrieved_at": "2026-07-14T12:00:00+00:00",
            },
        },
    )

    with pytest.raises(SourceProvenanceError) as exc_info:
        source_identity_for_document(document)

    assert exc_info.value.reason_code == "missing_authoritative_source_identifier"


def test_clinical_trials_handoff_uses_external_nct_identifier() -> None:
    document = _document(
        metadata={
            "source_capture": {
                "source_key": "clinical_trials",
                "external_id": "NCT01234567",
                "retrieved_at": "2026-07-14T12:00:00+00:00",
            },
        },
    )

    identity = source_identity_for_document(document)

    assert identity.source_kind == "clinicaltrials"
    assert identity.authoritative_identifier == "NCT:NCT01234567"


def test_exact_locator_uses_python_character_offsets_for_unicode() -> None:
    source_text = "Résumé. β-catenin activates MYC. End."
    quote = "β-catenin activates MYC."
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    locator = exact_locator_for_quote(
        source_text=source_text,
        exact_quote=quote,
        source_content_sha256=source_hash,
        section="Results",
    )

    assert source_text[locator.char_start : locator.char_end] == quote
    assert locator.char_start == source_text.index(quote)
    assert locator.section == "Results"
    assert locator.sentence_index == 1


def test_repeated_quote_requires_and_honors_an_exact_range() -> None:
    quote = "MED13 was associated with disease."
    source_text = f"{quote} Other result. {quote}"
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    with pytest.raises(SourceProvenanceError) as exc_info:
        exact_locator_for_quote(
            source_text=source_text,
            exact_quote=quote,
            source_content_sha256=source_hash,
        )
    assert exc_info.value.reason_code == "ambiguous_repeated_quote"

    second_start = source_text.rindex(quote)
    locator = exact_locator_for_quote(
        source_text=source_text,
        exact_quote=quote,
        source_content_sha256=source_hash,
        legacy_locator=f"chars={second_start}-{second_start + len(quote)}",
    )
    assert locator.char_start == second_start
    assert source_text[locator.char_start : locator.char_end] == quote


def test_source_or_quote_mutation_invalidates_locator() -> None:
    source_text = "MED13 was associated with cardiomyopathy."
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    with pytest.raises(SourceProvenanceError) as source_exc:
        exact_locator_for_quote(
            source_text=f"Changed. {source_text}",
            exact_quote=source_text,
            source_content_sha256=source_hash,
        )
    assert source_exc.value.reason_code == "source_content_hash_mismatch"

    with pytest.raises(SourceProvenanceError) as quote_exc:
        exact_locator_for_quote(
            source_text=source_text,
            exact_quote="MED13 causes cardiomyopathy.",
            source_content_sha256=source_hash,
        )
    assert quote_exc.value.reason_code == "quote_not_in_source_snapshot"


def test_proposal_provenance_round_trips_authority_quote_and_section() -> None:
    document = _document()
    proposal = _proposal(document=document)

    provenance = source_provenance_for_proposal(
        document=document,
        proposal=proposal,
    )

    assert provenance.source_identity.authoritative_identifier == "PMID:12345678"
    assert provenance.evidence_locator.exact_quote == proposal.summary
    assert provenance.evidence_locator.section == "Results"
    assert (
        document.text_content[
            provenance.evidence_locator.char_start : provenance.evidence_locator.char_end
        ]
        == proposal.summary
    )


def test_draft_binding_freezes_proposal_time_source_snapshot() -> None:
    document = _document()
    quote = "MED13 was associated with cardiomyopathy."
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=f"{document.id}:relation:0",
        document_id=document.id,
        title="Extracted claim",
        summary="Agent-authored summary.",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={"claim_section": "Results"},
        evidence_bundle=[{"excerpt": quote}],
        payload={"proposed_claim_type": "ASSOCIATED_WITH"},
        metadata={},
    )

    (bound,) = bind_source_provenance_to_drafts(document=document, drafts=(draft,))

    assert bound.source_provenance is not None
    assert bound.source_provenance.status == "verified"
    assert bound.source_provenance.evidence_locator is not None
    assert bound.source_provenance.evidence_locator.exact_quote == quote


def test_mutated_document_cannot_establish_a_new_valid_snapshot_at_promotion() -> None:
    document = _document()
    proposal = _proposal(document=document)
    resolved = source_provenance_for_proposal(document=document, proposal=proposal)
    proposal = replace(
        proposal,
        source_provenance=ClaimSourceProvenance(
            status="verified",
            source_identity=resolved.source_identity,
            evidence_locator=resolved.evidence_locator,
        ),
    )
    mutated_document = replace(
        document,
        text_content=f"Changed after extraction. {document.text_content}",
    )

    with pytest.raises(SourceProvenanceError) as exc_info:
        verify_persisted_source_provenance(
            document=mutated_document,
            proposal=proposal,
        )

    assert exc_info.value.reason_code == "source_identity_snapshot_mismatch"
