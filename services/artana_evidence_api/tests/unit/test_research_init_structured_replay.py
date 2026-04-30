"""Unit tests for structured-enrichment replay helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from artana_evidence_api import (
    research_init_observation_bridge,
    research_init_structured_replay,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_init_models import (
    ResearchInitPubMedReplayBundle,
    ResearchInitPubMedReplayDocument,
    ResearchInitStructuredEnrichmentReplayBundle,
    ResearchInitStructuredEnrichmentReplaySource,
    ResearchInitStructuredReplayDocument,
    ResearchInitStructuredReplayProposal,
)
from artana_evidence_api.run_registry import HarnessRunRecord


def test_build_structured_enrichment_replay_bundle_groups_outputs_directly() -> None:
    space_id = uuid4()
    run_id = str(uuid4())
    child_run_id = str(uuid4())
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    structured_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="DrugBank: PCSK9 inhibitor",
        source_type="drugbank",
        filename=None,
        media_type="application/json",
        sha256="drugbank-sha",
        byte_size=128,
        page_count=None,
        text_content="DrugBank structured payload",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=child_run_id,
        last_enrichment_run_id=child_run_id,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={"source": "drugbank"},
    )
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="drugbank_enrichment",
                source_key="drugbank:pcsk9",
                title="DrugBank: PCSK9 inhibitor TARGETS PCSK9",
                summary="DrugBank summary",
                confidence=0.5,
                ranking_score=0.5,
                reasoning_path={"source": "drugbank"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "PCSK9 inhibitor"},
                metadata={"source": "drugbank"},
                document_id=structured_document.id,
                claim_fingerprint="fingerprint-1",
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="document:drugbank:pcsk9",
                title="DrugBank document says inhibitor lowers PCSK9",
                summary="Document extraction summary",
                confidence=0.6,
                ranking_score=0.6,
                reasoning_path={"source": "document_extraction"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "PCSK9 inhibitor"},
                metadata={"source": "document_extraction"},
                document_id=structured_document.id,
                claim_fingerprint="fingerprint-2",
            ),
        ),
    )

    bundle = research_init_structured_replay.build_structured_enrichment_replay_bundle(
        space_id=space_id,
        run_id=run_id,
        document_store=document_store,
        proposal_store=proposal_store,
        workspace_snapshot={
            "source_results": {
                "drugbank": {
                    "records_processed": 3,
                    "errors": ["warning", 42],
                },
            },
        },
    )

    replay_source = research_init_structured_replay.structured_enrichment_replay_source(
        bundle,
        "drugbank",
    )
    assert replay_source is not None
    assert replay_source.records_processed == 3
    assert replay_source.errors == ("warning",)
    assert replay_source.documents[0].source_document_id == structured_document.id
    assert replay_source.proposals[0].claim_fingerprint == "fingerprint-1"
    assert (
        replay_source.document_extraction_proposals[0].claim_fingerprint
        == "fingerprint-2"
    )
    assert (
        research_init_structured_replay.structured_enrichment_replay_source(
            bundle,
            "clinvar",
        )
        is None
    )


def test_replay_structured_enrichment_result_rehydrates_current_run_scope() -> None:
    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    parent_run = HarnessRunRecord(
        id="current-run",
        space_id=str(space_id),
        harness_id="research_init",
        title="Research init",
        status="running",
        input_payload={},
        graph_service_status="ok",
        graph_service_version="test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    replay_source = ResearchInitStructuredEnrichmentReplaySource(
        source_key="drugbank",
        documents=(
            ResearchInitStructuredReplayDocument(
                source_document_id="source-doc-1",
                created_by=owner_id,
                title="DrugBank structured payload",
                source_type="drugbank",
                filename=None,
                media_type="application/json",
                sha256="sha-1",
                byte_size=128,
                page_count=None,
                text_content="Structured payload text",
                raw_storage_key=None,
                enriched_storage_key=None,
                enrichment_status="completed",
                extraction_status="not_started",
                metadata={"source": "drugbank"},
            ),
        ),
        proposals=(
            ResearchInitStructuredReplayProposal(
                proposal_type="candidate_claim",
                source_kind="drugbank_enrichment",
                source_key="drugbank:pcsk9",
                title="PCSK9 inhibitor targets PCSK9",
                summary="DrugBank summary",
                confidence=0.8,
                ranking_score=0.8,
                reasoning_path={"source": "drugbank"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "PCSK9 inhibitor"},
                metadata={"source": "drugbank"},
                source_document_id="source-doc-1",
                claim_fingerprint="fingerprint-1",
            ),
        ),
        document_extraction_proposals=(),
        records_processed=1,
        errors=(),
    )

    result = research_init_structured_replay.replay_structured_enrichment_result(
        replay_source=replay_source,
        space_id=space_id,
        document_store=document_store,
        parent_run=parent_run,
    )

    assert result.source_key == "drugbank"
    assert result.records_processed == 1
    assert len(result.documents_created) == 1
    replayed_document = result.documents_created[0]
    assert replayed_document.ingestion_run_id == parent_run.id
    assert replayed_document.last_enrichment_run_id == parent_run.id
    assert replayed_document.metadata["replayed_source_document_id"] == "source-doc-1"
    assert len(result.proposals_created) == 1
    assert result.proposals_created[0].document_id == replayed_document.id


def test_store_replayed_document_extraction_proposals_maps_replayed_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    run_id = str(uuid4())
    existing_subject_id = str(uuid4())
    existing_object_id = str(uuid4())
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    replayed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="DrugBank structured payload",
        source_type="drugbank",
        filename=None,
        media_type="application/json",
        sha256="sha-1",
        byte_size=128,
        page_count=None,
        text_content="Structured payload text",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run_id,
        last_enrichment_run_id=run_id,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={"replayed_source_document_id": "source-doc-1"},
    )
    replay_bundle = ResearchInitStructuredEnrichmentReplayBundle(
        sources=(
            ResearchInitStructuredEnrichmentReplaySource(
                source_key="drugbank",
                documents=(),
                proposals=(),
                document_extraction_proposals=(
                    _replay_proposal(source_document_id="source-doc-1"),
                    _replay_proposal(source_document_id="missing-source-doc"),
                ),
                records_processed=0,
                errors=(),
            ),
        ),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "resolve_graph_entity_label",
        _label_resolver(
            {
                "MED13": existing_subject_id,
                "CDK8": existing_object_id,
            },
        ),
    )

    result = (
        research_init_structured_replay.store_replayed_document_extraction_proposals(
            replay_bundle=replay_bundle,
            enrichment_documents=(replayed_document,),
            proposal_store=proposal_store,
            space_id=space_id,
            run_id=run_id,
            graph_api_gateway=_ResolvingGraphGateway(),
        )
    )

    created_proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    assert result.proposal_count == 1
    assert result.errors == ()
    assert result.surfaced_entity_ids == (existing_subject_id, existing_object_id)
    assert created_proposals[0].document_id == replayed_document.id
    assert created_proposals[0].payload["proposed_subject"] == existing_subject_id
    assert created_proposals[0].payload["proposed_object"] == existing_object_id


def test_store_replayed_document_extraction_proposals_skips_without_mapping() -> None:
    result = (
        research_init_structured_replay.store_replayed_document_extraction_proposals(
            replay_bundle=ResearchInitStructuredEnrichmentReplayBundle(
                sources=(
                    ResearchInitStructuredEnrichmentReplaySource(
                        source_key="drugbank",
                        documents=(),
                        proposals=(),
                        document_extraction_proposals=(
                            _replay_proposal(source_document_id="source-doc-1"),
                        ),
                        records_processed=0,
                        errors=(),
                    ),
                ),
            ),
            enrichment_documents=(),
            proposal_store=HarnessProposalStore(),
            space_id=uuid4(),
            run_id=str(uuid4()),
            graph_api_gateway=_ResolvingGraphGateway(),
        )
    )

    assert result.proposal_count == 0


def test_store_replayed_pubmed_document_extraction_proposals_filters_pubmed_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    run_id = str(uuid4())
    existing_subject_id = str(uuid4())
    existing_object_id = str(uuid4())
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    valid_pubmed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="MED13 PubMed abstract",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-sha-1",
        byte_size=128,
        page_count=None,
        text_content="MED13 regulates CDK8.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run_id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "replayed_source_document_id": "pubmed-source-doc-1",
        },
    )
    invalid_pubmed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Manual PubMed abstract",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-sha-2",
        byte_size=128,
        page_count=None,
        text_content="Manual PubMed content.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=run_id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"replayed_source_document_id": "pubmed-source-doc-2"},
    )
    replay_bundle = ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=(),
        documents=(
            ResearchInitPubMedReplayDocument(
                source_document_id="pubmed-source-doc-1",
                sha256="pubmed-sha-1",
                title="MED13 PubMed abstract",
                extraction_proposals=(
                    _replay_proposal(
                        source_document_id="pubmed-source-doc-1",
                        source_key="pubmed:1",
                    ),
                ),
            ),
            ResearchInitPubMedReplayDocument(
                source_document_id="pubmed-source-doc-2",
                sha256="pubmed-sha-2",
                title="Manual PubMed abstract",
                extraction_proposals=(
                    _replay_proposal(
                        source_document_id="pubmed-source-doc-2",
                        source_key="pubmed:2",
                    ),
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "resolve_graph_entity_label",
        _label_resolver(
            {
                "MED13": existing_subject_id,
                "CDK8": existing_object_id,
            },
        ),
    )

    result = research_init_structured_replay.store_replayed_pubmed_document_extraction_proposals(
        replay_bundle=replay_bundle,
        ingested_documents=(valid_pubmed_document, invalid_pubmed_document),
        proposal_store=proposal_store,
        space_id=space_id,
        run_id=run_id,
        graph_api_gateway=_ResolvingGraphGateway(),
    )

    created_proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    assert result.proposal_count == 1
    assert result.errors == ()
    assert result.surfaced_entity_ids == (existing_subject_id, existing_object_id)
    assert created_proposals[0].document_id == valid_pubmed_document.id
    assert created_proposals[0].source_key == "pubmed:1"


class _ResolvingGraphGateway:
    pass


def _label_resolver(
    labels: dict[str, str],
) -> Any:
    def _resolve_graph_entity_label(
        *,
        space_id: object,
        label: str,
        graph_api_gateway: object,
    ) -> dict[str, str] | None:
        del space_id, graph_api_gateway
        entity_id = labels.get(label)
        if entity_id is None:
            return None
        return {"id": entity_id}

    return _resolve_graph_entity_label


def _replay_proposal(
    *,
    source_document_id: str,
    source_key: str = "document:drugbank:pcsk9",
) -> ResearchInitStructuredReplayProposal:
    return ResearchInitStructuredReplayProposal(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title="MED13 regulates CDK8",
        summary="Replay summary",
        confidence=0.8,
        ranking_score=0.8,
        reasoning_path={"source": "document_extraction"},
        evidence_bundle=[],
        payload={
            "proposed_subject": str(uuid4()),
            "proposed_subject_label": "MED13",
            "proposed_object": str(uuid4()),
            "proposed_object_label": "CDK8",
        },
        metadata={"source": "document_extraction"},
        source_document_id=source_document_id,
        claim_fingerprint=f"fingerprint-{source_key}",
    )
