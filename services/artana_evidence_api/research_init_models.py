"""Research-init runtime data models and observer protocols."""

# ruff: noqa: SLF001

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorFilteredChaseCandidate,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
    )
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord


_TOTAL_PROGRESS_STEPS = 5
_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT = 4
_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 30.0
_PUBMED_QUERY_CONCURRENCY_LIMIT = 2
_MIN_CHASE_ENTITIES = 3
_MAX_CHASE_CANDIDATES = 10
_OBSERVATION_BRIDGE_AGENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_EXTRACTION_STAGE_TIMEOUT_SECONDS = 120.0
_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS = 45.0
_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_BATCH_SIZE = 3
_PUBMED_REPLAY_ARTIFACT_KEY = "research_init_pubmed_replay_bundle"
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
_MIN_GENE_FAMILY_TOKEN_LENGTH = 4



@dataclass(frozen=True, slots=True)
class ResearchInitPubMedResultRecord:
    """Compact summary of one PubMed query family."""

    query: str
    total_found: int
    abstracts_ingested: int

@dataclass(frozen=True, slots=True)
class ResearchInitExecutionResult:
    """Terminal result for one research-init worker run."""

    run: HarnessRunRecord
    pubmed_results: tuple[ResearchInitPubMedResultRecord, ...]
    documents_ingested: int
    proposal_count: int
    research_state: JSONObject | None
    pending_questions: list[str]
    errors: list[str]
    claim_curation: JSONObject | None = None
    research_brief_markdown: str | None = None

@dataclass(frozen=True, slots=True)
class _PreparedDocumentExtraction:
    """Prepared extraction output for one selected workset document."""

    document: HarnessDocumentRecord
    drafts: tuple[HarnessProposalDraft, ...]
    errors: tuple[str, ...]
    failed: bool = False

@dataclass(frozen=True, slots=True)
class _PubMedQueryExecutionResult:
    """One completed PubMed query family plus ordered candidate outputs."""

    query_result: ResearchInitPubMedResultRecord | None
    candidates: tuple[object, ...]
    errors: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ResearchInitPubMedReplayBundle:
    """Replayable PubMed inputs captured before document ingestion."""

    query_executions: tuple[_PubMedQueryExecutionResult, ...]
    selected_candidates: tuple[tuple[object, object], ...]
    selection_errors: tuple[str, ...]
    documents: tuple[ResearchInitPubMedReplayDocument, ...] = ()

@dataclass(frozen=True, slots=True)
class ResearchInitPubMedReplayDocument:
    """Replayable PubMed document outputs captured from a baseline run."""

    source_document_id: str
    sha256: str
    title: str
    extraction_proposals: tuple[ResearchInitStructuredReplayProposal, ...] = ()

@dataclass(frozen=True, slots=True)
class ResearchInitStructuredReplayDocument:
    """Replayable structured-source document payload."""

    source_document_id: str
    created_by: str
    title: str
    source_type: str
    filename: str | None
    media_type: str
    sha256: str
    byte_size: int
    page_count: int | None
    text_content: str
    raw_storage_key: str | None
    enriched_storage_key: str | None
    enrichment_status: str
    extraction_status: str
    metadata: JSONObject

@dataclass(frozen=True, slots=True)
class ResearchInitStructuredReplayProposal:
    """Replayable structured-source proposal payload."""

    proposal_type: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    source_document_id: str | None = None
    claim_fingerprint: str | None = None

@dataclass(frozen=True, slots=True)
class ResearchInitStructuredEnrichmentReplaySource:
    """Replayable outputs for one structured enrichment source."""

    source_key: str
    documents: tuple[ResearchInitStructuredReplayDocument, ...]
    proposals: tuple[ResearchInitStructuredReplayProposal, ...]
    document_extraction_proposals: tuple[ResearchInitStructuredReplayProposal, ...] = ()
    records_processed: int = 0
    errors: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ResearchInitStructuredEnrichmentReplayBundle:
    """Replayable structured enrichment outputs captured from a prior run."""

    sources: tuple[ResearchInitStructuredEnrichmentReplaySource, ...]

@dataclass(frozen=True, slots=True)
class _StoredReplayProposalResult:
    """One replay-proposal storage result plus surfaced current-space entities."""

    proposal_count: int
    surfaced_entity_ids: tuple[str, ...] = ()
    created_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class _PubMedObservationSyncResult:
    """Outcome of mirroring one harness PubMed document into shared ingestion."""

    source_document_id: str
    status: str
    observations_created: int
    entities_created: int
    seed_entity_ids: tuple[str, ...]
    errors: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class _ObservationBridgeBatchResult:
    """Batch result for one shared observation-bridge run."""

    document_results: dict[str, _PubMedObservationSyncResult]
    seed_entity_ids: tuple[str, ...]
    errors: tuple[str, ...] = ()

class _NoOpPipelineRunEventRepository:
    """Drop pipeline trace events for transient observation-bridge runs."""

    def append(self, event: object) -> object:
        return event

    def list_events(  # noqa: PLR0913
        self,
        *,
        research_space_id: UUID | None = None,
        source_id: UUID | None = None,
        pipeline_run_id: str | None = None,
        stage: str | None = None,
        level: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
        agent_kind: str | None = None,
        limit: int = 200,
    ) -> list[object]:
        del (
            research_space_id,
            source_id,
            pipeline_run_id,
            stage,
            level,
            scope_kind,
            scope_id,
            agent_kind,
            limit,
        )
        return []

class ResearchInitProgressObserver(Protocol):
    """Observer notified whenever research-init advances one major phase."""

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None: ...

@dataclass(frozen=True, slots=True)
class _ChaseRoundResult:
    """Result of one entity chase round."""

    new_seed_terms: list[str]
    documents_created: int
    proposals_created: int
    errors: list[str]

@dataclass(frozen=True, slots=True)
class _ChaseRoundPreparation:
    """Derived candidate set plus the deterministic chase selection."""

    candidates: tuple[ResearchOrchestratorChaseCandidate, ...]
    filtered_candidates: tuple[ResearchOrchestratorFilteredChaseCandidate, ...]
    deterministic_selection: ResearchOrchestratorChaseSelection
    errors: list[str]
