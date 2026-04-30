"""Structured-enrichment replay helpers for research-init runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.research_init_document_selection import (
    is_research_init_pubmed_document as _is_research_init_pubmed_document,
)
from artana_evidence_api.research_init_models import (
    ResearchInitPubMedReplayBundle,
    ResearchInitStructuredEnrichmentReplayBundle,
    ResearchInitStructuredEnrichmentReplaySource,
    ResearchInitStructuredReplayDocument,
    ResearchInitStructuredReplayProposal,
    _StoredReplayProposalResult,
)
from artana_evidence_api.research_init_observation_bridge import (
    _ground_replay_candidate_claim_drafts,
)
from artana_evidence_api.types.common import JSONObject, json_string_list

__all__ = [
    "build_structured_enrichment_replay_bundle",
    "replay_structured_enrichment_result",
    "store_replayed_document_extraction_proposals",
    "store_replayed_pubmed_document_extraction_proposals",
    "structured_enrichment_replay_source",
]

if TYPE_CHECKING:
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord

_STRUCTURED_REPLAY_SOURCE_KEYS = frozenset(
    {
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY = {
    "clinvar_enrichment": "clinvar",
    "drugbank_enrichment": "drugbank",
    "alphafold_enrichment": "alphafold",
    "clinicaltrials_enrichment": "clinical_trials",
    "mgi_enrichment": "mgi",
    "zfin_enrichment": "zfin",
    "marrvel_enrichment": "marrvel",
}


def build_structured_enrichment_replay_bundle(
    *,
    space_id: UUID,
    run_id: UUID | str,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    workspace_snapshot: JSONObject | None = None,
) -> ResearchInitStructuredEnrichmentReplayBundle:
    """Capture structured enrichment outputs from one completed research-init run."""
    normalized_run_id = str(run_id)
    normalized_workspace = (
        workspace_snapshot if isinstance(workspace_snapshot, dict) else {}
    )
    raw_source_results = normalized_workspace.get("source_results")
    source_results = raw_source_results if isinstance(raw_source_results, dict) else {}
    proposals_for_run = tuple(
        proposal_store.list_proposals(
            space_id=space_id,
            run_id=normalized_run_id,
        ),
    )
    referenced_document_ids = {
        proposal.document_id
        for proposal in proposals_for_run
        if proposal.document_id is not None
    }
    documents_by_source: dict[str, list[ResearchInitStructuredReplayDocument]] = {
        source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS
    }
    document_source_keys: dict[str, str] = {}
    for document in document_store.list_documents(space_id=space_id):
        if document.source_type not in _STRUCTURED_REPLAY_SOURCE_KEYS:
            continue
        if (
            document.ingestion_run_id != normalized_run_id
            and document.id not in referenced_document_ids
        ):
            continue
        document_source_keys[document.id] = document.source_type
        documents_by_source[document.source_type].append(
            ResearchInitStructuredReplayDocument(
                source_document_id=document.id,
                created_by=document.created_by,
                title=document.title,
                source_type=document.source_type,
                filename=document.filename,
                media_type=document.media_type,
                sha256=document.sha256,
                byte_size=document.byte_size,
                page_count=document.page_count,
                text_content=document.text_content,
                raw_storage_key=document.raw_storage_key,
                enriched_storage_key=document.enriched_storage_key,
                enrichment_status=document.enrichment_status,
                extraction_status=document.extraction_status,
                metadata=dict(document.metadata),
            ),
        )

    proposals_by_source: dict[str, list[ResearchInitStructuredReplayProposal]] = {
        source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS
    }
    extraction_proposals_by_source: dict[
        str, list[ResearchInitStructuredReplayProposal]
    ] = {source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS}
    for proposal in proposals_for_run:
        source_key = _STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY.get(proposal.source_kind)
        if source_key is None and proposal.source_kind == "document_extraction":
            source_key = (
                None
                if proposal.document_id is None
                else document_source_keys.get(proposal.document_id)
            )
        if source_key is None:
            continue
        replay_proposal = ResearchInitStructuredReplayProposal(
            proposal_type=proposal.proposal_type,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            title=proposal.title,
            summary=proposal.summary,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            reasoning_path=dict(proposal.reasoning_path),
            evidence_bundle=list(proposal.evidence_bundle),
            payload=dict(proposal.payload),
            metadata=dict(proposal.metadata),
            source_document_id=proposal.document_id,
            claim_fingerprint=proposal.claim_fingerprint,
        )
        if proposal.source_kind == "document_extraction":
            extraction_proposals_by_source[source_key].append(replay_proposal)
            continue
        proposals_by_source[source_key].append(replay_proposal)

    replay_sources: list[ResearchInitStructuredEnrichmentReplaySource] = []
    for source_key in sorted(_STRUCTURED_REPLAY_SOURCE_KEYS):
        raw_source_summary = source_results.get(source_key)
        source_summary = (
            raw_source_summary if isinstance(raw_source_summary, dict) else {}
        )
        records_processed = int(source_summary.get("records_processed", 0) or 0)
        source_errors = json_string_list(source_summary.get("errors"))
        if (
            not documents_by_source[source_key]
            and not proposals_by_source[source_key]
            and not extraction_proposals_by_source[source_key]
            and records_processed == 0
            and not source_errors
        ):
            continue
        replay_sources.append(
            ResearchInitStructuredEnrichmentReplaySource(
                source_key=source_key,
                documents=tuple(documents_by_source[source_key]),
                proposals=tuple(proposals_by_source[source_key]),
                document_extraction_proposals=tuple(
                    extraction_proposals_by_source[source_key],
                ),
                records_processed=records_processed,
                errors=tuple(source_errors),
            ),
        )
    return ResearchInitStructuredEnrichmentReplayBundle(sources=tuple(replay_sources))


def structured_enrichment_replay_source(
    replay_bundle: ResearchInitStructuredEnrichmentReplayBundle | None,
    source_key: str,
) -> ResearchInitStructuredEnrichmentReplaySource | None:
    """Return one source replay payload by source key."""
    if replay_bundle is None:
        return None
    for replay_source in replay_bundle.sources:
        if replay_source.source_key == source_key:
            return replay_source
    return None


def replay_structured_enrichment_result(
    *,
    replay_source: ResearchInitStructuredEnrichmentReplaySource,
    space_id: UUID,
    document_store: HarnessDocumentStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Rehydrate one structured enrichment source into the current run scope."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )

    document_id_map: dict[str, str] = {}
    replayed_documents: list[HarnessDocumentRecord] = []
    for replay_document in replay_source.documents:
        metadata = dict(replay_document.metadata)
        metadata.setdefault(
            "replayed_source_document_id",
            replay_document.source_document_id,
        )
        if replay_source.document_extraction_proposals:
            metadata.setdefault("document_extraction_replayed", True)
        replayed_document = document_store.create_document(
            space_id=space_id,
            created_by=replay_document.created_by,
            title=replay_document.title,
            source_type=replay_document.source_type,
            filename=replay_document.filename,
            media_type=replay_document.media_type,
            sha256=replay_document.sha256,
            byte_size=replay_document.byte_size,
            page_count=replay_document.page_count,
            text_content=replay_document.text_content,
            raw_storage_key=replay_document.raw_storage_key,
            enriched_storage_key=replay_document.enriched_storage_key,
            ingestion_run_id=parent_run.id,
            last_enrichment_run_id=parent_run.id,
            enrichment_status=replay_document.enrichment_status,
            extraction_status=replay_document.extraction_status,
            metadata=metadata,
        )
        document_id_map[replay_document.source_document_id] = replayed_document.id
        replayed_documents.append(replayed_document)

    replayed_proposals = [
        HarnessProposalDraft(
            proposal_type=proposal.proposal_type,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            title=proposal.title,
            summary=proposal.summary,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            reasoning_path=dict(proposal.reasoning_path),
            evidence_bundle=list(proposal.evidence_bundle),
            payload=dict(proposal.payload),
            metadata=dict(proposal.metadata),
            document_id=(
                None
                if proposal.source_document_id is None
                else document_id_map.get(proposal.source_document_id)
            ),
            claim_fingerprint=proposal.claim_fingerprint,
        )
        for proposal in replay_source.proposals
    ]
    return SourceEnrichmentResult(
        source_key=replay_source.source_key,
        documents_created=replayed_documents,
        proposals_created=replayed_proposals,
        records_processed=replay_source.records_processed,
        errors=replay_source.errors,
    )


def store_replayed_document_extraction_proposals(
    *,
    replay_bundle: ResearchInitStructuredEnrichmentReplayBundle | None,
    enrichment_documents: Sequence[HarnessDocumentRecord],
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: str,
    graph_api_gateway: GraphTransportBundle,
) -> _StoredReplayProposalResult:
    """Persist replayed document-extraction proposals for replayed structured docs."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    if replay_bundle is None:
        return _StoredReplayProposalResult(proposal_count=0)

    document_id_map: dict[str, str] = {}
    for document in enrichment_documents:
        replayed_source_document_id = document.metadata.get(
            "replayed_source_document_id"
        )
        if isinstance(replayed_source_document_id, str) and replayed_source_document_id:
            document_id_map[replayed_source_document_id] = document.id

    if not document_id_map:
        return _StoredReplayProposalResult(proposal_count=0)

    replayed_drafts: list[HarnessProposalDraft] = []
    for replay_source in replay_bundle.sources:
        for proposal in replay_source.document_extraction_proposals:
            mapped_document_id = (
                None
                if proposal.source_document_id is None
                else document_id_map.get(proposal.source_document_id)
            )
            if proposal.source_document_id is not None and mapped_document_id is None:
                continue
            replayed_drafts.append(
                HarnessProposalDraft(
                    proposal_type=proposal.proposal_type,
                    source_kind=proposal.source_kind,
                    source_key=proposal.source_key,
                    title=proposal.title,
                    summary=proposal.summary,
                    confidence=proposal.confidence,
                    ranking_score=proposal.ranking_score,
                    reasoning_path=dict(proposal.reasoning_path),
                    evidence_bundle=list(proposal.evidence_bundle),
                    payload=dict(proposal.payload),
                    metadata=dict(proposal.metadata),
                    document_id=mapped_document_id,
                    claim_fingerprint=proposal.claim_fingerprint,
                ),
            )

    if not replayed_drafts:
        return _StoredReplayProposalResult(proposal_count=0)
    (
        grounded_drafts,
        surfaced_entity_ids,
        created_entity_ids,
        grounding_errors,
    ) = _ground_replay_candidate_claim_drafts(
        space_id=space_id,
        drafts=tuple(replayed_drafts),
        graph_api_gateway=graph_api_gateway,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=grounded_drafts,
    )
    return _StoredReplayProposalResult(
        proposal_count=len(created_records),
        surfaced_entity_ids=surfaced_entity_ids,
        created_entity_ids=created_entity_ids,
        errors=grounding_errors,
    )


def store_replayed_pubmed_document_extraction_proposals(
    *,
    replay_bundle: ResearchInitPubMedReplayBundle | None,
    ingested_documents: Sequence[HarnessDocumentRecord],
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: str,
    graph_api_gateway: GraphTransportBundle,
) -> _StoredReplayProposalResult:
    """Persist replayed document-extraction proposals for replayed PubMed docs."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    if replay_bundle is None:
        return _StoredReplayProposalResult(proposal_count=0)

    document_id_map: dict[str, str] = {}
    for document in ingested_documents:
        replayed_source_document_id = document.metadata.get(
            "replayed_source_document_id"
        )
        if (
            not isinstance(replayed_source_document_id, str)
            or replayed_source_document_id == ""
        ):
            continue
        if document.source_type != "pubmed":
            continue
        if not _is_research_init_pubmed_document(document):
            continue
        document_id_map[replayed_source_document_id] = document.id

    if not document_id_map:
        return _StoredReplayProposalResult(proposal_count=0)

    replayed_drafts: list[HarnessProposalDraft] = []
    for replay_document in replay_bundle.documents:
        for proposal in replay_document.extraction_proposals:
            mapped_document_id = document_id_map.get(replay_document.source_document_id)
            if mapped_document_id is None:
                continue
            replayed_drafts.append(
                HarnessProposalDraft(
                    proposal_type=proposal.proposal_type,
                    source_kind=proposal.source_kind,
                    source_key=proposal.source_key,
                    title=proposal.title,
                    summary=proposal.summary,
                    confidence=proposal.confidence,
                    ranking_score=proposal.ranking_score,
                    reasoning_path=dict(proposal.reasoning_path),
                    evidence_bundle=list(proposal.evidence_bundle),
                    payload=dict(proposal.payload),
                    metadata=dict(proposal.metadata),
                    document_id=mapped_document_id,
                    claim_fingerprint=proposal.claim_fingerprint,
                ),
            )

    if not replayed_drafts:
        return _StoredReplayProposalResult(proposal_count=0)
    (
        grounded_drafts,
        surfaced_entity_ids,
        created_entity_ids,
        grounding_errors,
    ) = _ground_replay_candidate_claim_drafts(
        space_id=space_id,
        drafts=tuple(replayed_drafts),
        graph_api_gateway=graph_api_gateway,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=grounded_drafts,
    )
    return _StoredReplayProposalResult(
        proposal_count=len(created_records),
        surfaced_entity_ids=surfaced_entity_ids,
        created_entity_ids=created_entity_ids,
        errors=grounding_errors,
    )
