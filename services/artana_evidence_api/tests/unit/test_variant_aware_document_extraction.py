"""Unit tests for the variant-aware document extraction bridge."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
)
from artana_evidence_api.variant_aware_document_extraction import (
    document_supports_variant_aware_extraction,
    extract_variant_aware_document,
)

from src.domain.agents.contracts.extraction import (
    ExtractedEntityCandidate,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)


class _EmptyGraphGateway:
    def list_entities(
        self,
        *,
        space_id,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)


def _assessment(
    *,
    support_band: SupportBand = SupportBand.STRONG,
    rationale: str = "Exact anchored variant evidence.",
) -> FactAssessment:
    return FactAssessment(
        support_band=support_band,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.RESOLVED,
        speculation_level=SpeculationLevel.DIRECT,
        confidence_rationale=rationale,
    )


def _document(*, text: str, source_type: str = "text") -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Synthetic variant-aware note",
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256="deadbeef",
        byte_size=len(text.encode("utf-8")),
        page_count=None,
        text_content=text,
        text_excerpt=text[:80],
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="not_started",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )


def _single_variant_contract(*, document_id: str) -> ExtractionContract:
    return ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant from the source record.",
        evidence=[],
        source_type="pubmed",
        document_id=document_id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                    "classification": "Likely Pathogenic",
                },
                evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:10-34",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-source-test",
    )


def test_document_supports_variant_aware_extraction_detects_genomics_signals() -> None:
    variant_document = _document(
        text=(
            "Trio exome sequencing identified heterozygous de novo "
            "MED13 NM_015335.6:c.977C>A (p.Thr326Lys)."
        ),
    )
    generic_document = _document(
        text="MED13 associates with cardiomyopathy in one mouse model.",
    )

    assert document_supports_variant_aware_extraction(document=variant_document) is True
    assert (
        document_supports_variant_aware_extraction(document=generic_document) is False
    )


@pytest.mark.parametrize(
    ("document_source_type", "expected_extraction_source_type"),
    [
        ("text", "pubmed"),
        ("pdf", "pubmed"),
        ("pubmed", "pubmed"),
        ("clinvar", "clinvar"),
        ("marrvel", "marrvel"),
    ],
)
def test_extract_variant_aware_document_normalizes_supported_source_types(
    monkeypatch,
    document_source_type: str,
    expected_extraction_source_type: str,
) -> None:
    document = _document(
        text="MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was classified as Likely Pathogenic.",
        source_type=document_source_type,
    )
    seen: dict[str, str] = {}

    async def _fake_extract(self, context):  # noqa: ANN001
        del self
        seen["source_type"] = context.source_type
        return _single_variant_contract(document_id=document.id)

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    assert seen["source_type"] == expected_extraction_source_type
    assert result.extraction_diagnostics["bridge_proposal_count"] >= 1


def test_extract_variant_aware_document_collapses_duplicate_variant_mentions(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Clinical report: MED13 c.977C>A (p.Thr326Lys) was confirmed. "
            "The same report also spelled it as "
            "NM_015335.6:c.977C>A (p.Thr326Lys)."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant and one phenotype relation.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="c.977C>A",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={},
                evidence_excerpt="MED13 c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:10-34",
                assessment=_assessment(),
            ),
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                    "classification": "Likely Pathogenic",
                },
                evidence_excerpt="NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="text_span:52-90",
                assessment=_assessment(),
            ),
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="T326K",
                anchors={},
                metadata={},
                evidence_excerpt="The draft table abbreviated the change as T326K.",
                evidence_locator="text_span:91-110",
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="Short protein alias recovered from a draft table.",
                ),
            ),
        ],
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="CAUSES",
                target_type="PHENOTYPE",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="developmental delay",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt=(
                    "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) was associated "
                    "with developmental delay."
                ),
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    entity_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    ]
    observation_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    ]
    claim_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "candidate_claim"
    ]

    assert len(entity_drafts) == 1
    assert entity_drafts[0].payload["display_label"] == (
        "NM_015335.6:c.977C>A (p.Thr326Lys)"
    )
    assert len(entity_drafts[0].payload["metadata"]["supporting_evidence"]) >= 2
    assert "T326K" in entity_drafts[0].payload["aliases"]
    assert {draft.payload["variable_id"] for draft in observation_drafts} >= {
        "VAR_TRANSCRIPT_ID",
        "VAR_HGVS_CDNA",
        "VAR_HGVS_PROTEIN",
        "VAR_CLINVAR_CLASS",
    }
    assert len(claim_drafts) == 1
    subject_candidate = claim_drafts[0].payload["proposed_subject_entity_candidate"]
    assert subject_candidate["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert result.candidate_discovery["entity_candidate_count"] == 1


def test_extract_variant_aware_document_falls_back_to_deterministic_signals(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "Trio exome sequencing identified heterozygous de novo MED13 "
            "NM_015335.6:c.977C>A (p.Thr326Lys), classified as Likely "
            "Pathogenic in exon 7. The child had developmental delay and "
            "cardiomyopathy concern."
        ),
    )

    contract = ExtractionContract(
        decision="escalate",
        confidence_score=0.0,
        rationale="LLM deferred to deterministic signal extraction.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[],
        observations=[],
        relations=[],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-fallback-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    entity_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "entity_candidate"
    ]
    observation_variable_ids = {
        draft.payload["variable_id"]
        for draft in result.proposal_drafts
        if draft.proposal_type == "observation_candidate"
    }
    review_item_types = {draft.review_type for draft in result.review_item_drafts}

    assert len(entity_drafts) == 1
    assert entity_drafts[0].payload["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert observation_variable_ids >= {
        "VAR_TRANSCRIPT_ID",
        "VAR_HGVS_CDNA",
        "VAR_HGVS_PROTEIN",
        "VAR_ZYGOSITY",
        "VAR_INHERITANCE_MODE",
        "VAR_EXON_INTRON",
        "VAR_CLINVAR_CLASS",
    }
    assert "phenotype_claim_review" in review_item_types
    assert result.extraction_diagnostics["fallback_from_signals"] is True


def test_extract_variant_aware_document_preserves_decomposed_mechanism_claims(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "MED13 NM_015335.6:c.977C>A (p.Thr326Lys) falls in a "
            "phosphodegron-like region, may impair Fbw7-mediated degradation, "
            "and could alter protein stability in a way that helps explain the "
            "neurodevelopmental phenotype."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="Recovered one anchored variant plus decomposed mechanism claims.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={
                    "transcript": "NM_015335.6",
                    "hgvs_cdna": "c.977C>A",
                    "hgvs_protein": "p.Thr326Lys",
                },
                evidence_excerpt="MED13 NM_015335.6:c.977C>A (p.Thr326Lys)",
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="LOCATED_IN",
                target_type="PROTEIN_DOMAIN",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="phosphodegron-like region",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt="The altered residue falls within a phosphodegron-like region.",
                evidence_locator="sentence:1",
                claim_text="The altered residue falls within a phosphodegron-like region.",
                assessment=_assessment(),
            ),
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="AFFECTS",
                target_type="PROCESS",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="Fbw7-mediated degradation",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt="The change may impair Fbw7-mediated degradation.",
                evidence_locator="sentence:2",
                claim_text="The change may impair Fbw7-mediated degradation.",
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="Mechanism wording is evidence-backed but still hedged.",
                ),
            ),
            ExtractedRelation(
                source_type="VARIANT",
                relation_type="EXPLAINS",
                target_type="PHENOTYPE",
                source_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
                target_label="neurodevelopmental phenotype",
                source_anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                evidence_excerpt=(
                    "Altered protein stability could help explain the neurodevelopmental phenotype."
                ),
                evidence_locator="sentence:3",
                claim_text=(
                    "Altered protein stability could help explain the neurodevelopmental phenotype."
                ),
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="Phenotype explanation remains partly speculative.",
                ),
            ),
        ],
        rejected_facts=[],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-mechanism-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    claim_drafts = [
        draft
        for draft in result.proposal_drafts
        if draft.proposal_type == "candidate_claim"
    ]

    assert len(claim_drafts) == 3
    assert result.extraction_diagnostics["relation_count"] == 3
    assert all(len(draft.summary.strip()) < 200 for draft in claim_drafts)
    assert {draft.payload["proposed_claim_type"] for draft in claim_drafts} == {
        "LOCATED_IN",
        "AFFECTS",
        "EXPLAINS",
    }


def test_extract_variant_aware_document_promotes_strong_rejected_relations_to_review_items(
    monkeypatch,
) -> None:
    document = _document(
        text=(
            "MED13 c.977C>A was described near developmental delay, but the model "
            "flagged the relation for review instead of emitting it directly."
        ),
    )

    contract = ExtractionContract(
        decision="generated",
        confidence_score=0.0,
        rationale="One strong but rejected relation should become a review item.",
        evidence=[],
        source_type="pubmed",
        document_id=document.id,
        entities=[
            ExtractedEntityCandidate(
                entity_type="VARIANT",
                label="MED13 c.977C>A",
                anchors={
                    "gene_symbol": "MED13",
                    "hgvs_notation": "c.977C>A",
                },
                metadata={},
                evidence_excerpt="MED13 c.977C>A was noted in the report.",
                evidence_locator="sentence:1",
                assessment=_assessment(),
            ),
        ],
        observations=[],
        relations=[],
        rejected_facts=[
            RejectedFact(
                fact_type="relation",
                reason="Relation needs curator review before proposal staging",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "CAUSES",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "developmental delay",
                    "source_anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "evidence_excerpt": (
                        "The variant appeared in the same paragraph as developmental delay."
                    ),
                    "evidence_locator": "sentence:2",
                },
                assessment=_assessment(
                    support_band=SupportBand.SUPPORTED,
                    rationale="The evidence is strong enough to review, but not auto-stage.",
                ),
            ),
            RejectedFact(
                fact_type="relation",
                reason="Too speculative to review",
                payload={
                    "source_type": "VARIANT",
                    "relation_type": "EXPLAINS",
                    "target_type": "PHENOTYPE",
                    "source_label": "MED13 c.977C>A",
                    "target_label": "cardiomyopathy",
                },
                assessment=_assessment(
                    support_band=SupportBand.TENTATIVE,
                    rationale="This should stay audit-only metadata.",
                ),
            ),
        ],
        pipeline_payloads=[],
        shadow_mode=True,
        agent_run_id="variant-aware-rejected-review-test",
    )

    async def _fake_extract(self, context):  # noqa: ANN001
        del self, context
        return contract

    async def _fake_close(self) -> None:  # noqa: ANN001
        del self

    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.extract",
        _fake_extract,
    )
    monkeypatch.setattr(
        "artana_evidence_api.variant_aware_document_extraction.ArtanaExtractionAdapter.close",
        _fake_close,
    )

    result = asyncio.run(
        extract_variant_aware_document(
            space_id=uuid4(),
            document=document,
            graph_api_gateway=_EmptyGraphGateway(),
        ),
    )

    rejected_review_items = [
        draft
        for draft in result.review_item_drafts
        if draft.review_type == "rejected_relation_review"
    ]

    assert len(rejected_review_items) == 1
    assert rejected_review_items[0].source_family == "document_extraction"
    assert (
        rejected_review_items[0].payload["proposal_draft"]["payload"][
            "proposed_claim_type"
        ]
        == "CAUSES"
    )
    assert any(
        item["kind"] == "rejected_fact"
        and item["reason"] == "Too speculative to review"
        for item in result.skipped_items
    )
