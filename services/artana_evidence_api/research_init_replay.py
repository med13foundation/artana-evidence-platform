"""PubMed replay serialization helpers for research-init runs."""

# ruff: noqa: SLF001

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.document_extraction import (
    normalize_text_document,
    sha256_hex,
)
from artana_evidence_api.research_init_helpers import (
    _candidate_key,
    _merge_candidate,
    _PubMedCandidate,
    _PubMedCandidateReview,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.proposal_store import (
        HarnessProposalStore,
    )


from artana_evidence_api.research_init_models import (
    ResearchInitPubMedReplayBundle,
    ResearchInitPubMedReplayDocument,
    ResearchInitPubMedResultRecord,
    ResearchInitStructuredReplayProposal,
    _PubMedQueryExecutionResult,
)

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


def _is_research_init_pubmed_document(record: HarnessDocumentRecord) -> bool:
    """Return whether this document came from the research-init PubMed flow."""
    return record.metadata.get("source") == "research-init-pubmed"


def _collect_pubmed_candidates(
    *,
    query_executions: tuple[_PubMedQueryExecutionResult, ...],
) -> dict[str, _PubMedCandidate]:
    collected_candidates: dict[str, _PubMedCandidate] = {}
    for query_execution in query_executions:
        for candidate in query_execution.candidates:
            normalized_candidate = _clone_pubmed_candidate(candidate)
            candidate_key = _candidate_key(
                pmid=normalized_candidate.pmid,
                title=normalized_candidate.title,
            )
            existing_candidate = collected_candidates.get(candidate_key)
            if existing_candidate is None:
                collected_candidates[candidate_key] = normalized_candidate
            else:
                collected_candidates[candidate_key] = (
                    _merge_candidate(
                        existing_candidate,
                        normalized_candidate,
                    )
                )
    return collected_candidates

def _clone_pubmed_candidate(candidate: object) -> _PubMedCandidate:

    raw_queries = getattr(candidate, "queries", ())
    queries = [
        query for query in raw_queries if isinstance(query, str) and query.strip() != ""
    ]
    return _PubMedCandidate(
        title=str(getattr(candidate, "title", "")),
        text=str(getattr(candidate, "text", "")),
        queries=list(queries),
        pmid=getattr(candidate, "pmid", None),
        doi=getattr(candidate, "doi", None),
        pmc_id=getattr(candidate, "pmc_id", None),
        journal=getattr(candidate, "journal", None),
    )

def _clone_pubmed_candidate_review(review: object) -> object:

    return _PubMedCandidateReview(
        method=getattr(review, "method", "heuristic"),
        label=getattr(review, "label", "relevant"),
        confidence=float(getattr(review, "confidence", 0.0)),
        rationale=str(getattr(review, "rationale", "")),
        agent_run_id=getattr(review, "agent_run_id", None),
        signal_count=int(getattr(review, "signal_count", 0)),
        focus_signal_count=int(getattr(review, "focus_signal_count", 0)),
        query_specificity=int(getattr(review, "query_specificity", 0)),
    )

def _clone_pubmed_query_execution(
    query_execution: _PubMedQueryExecutionResult,
) -> _PubMedQueryExecutionResult:
    return _PubMedQueryExecutionResult(
        query_result=query_execution.query_result,
        candidates=tuple(
            _clone_pubmed_candidate(candidate)
            for candidate in query_execution.candidates
        ),
        errors=tuple(query_execution.errors),
    )

def _clone_selected_pubmed_candidates(
    *,
    selected_candidates: tuple[tuple[object, object], ...],
) -> list[tuple[object, object]]:
    return [
        (
            _clone_pubmed_candidate(candidate),
            _clone_pubmed_candidate_review(review),
        )
        for candidate, review in selected_candidates
    ]

def _serialize_replay_proposal(
    proposal: ResearchInitStructuredReplayProposal,
) -> JSONObject:
    return {
        "proposal_type": proposal.proposal_type,
        "source_kind": proposal.source_kind,
        "source_key": proposal.source_key,
        "title": proposal.title,
        "summary": proposal.summary,
        "confidence": proposal.confidence,
        "ranking_score": proposal.ranking_score,
        "reasoning_path": dict(proposal.reasoning_path),
        "evidence_bundle": list(proposal.evidence_bundle),
        "payload": dict(proposal.payload),
        "metadata": dict(proposal.metadata),
        "source_document_id": proposal.source_document_id,
        "claim_fingerprint": proposal.claim_fingerprint,
    }

def _deserialize_replay_proposal(  # noqa: PLR0911
    payload: object,
) -> ResearchInitStructuredReplayProposal | None:
    if not isinstance(payload, dict):
        return None
    proposal_type = payload.get("proposal_type")
    source_kind = payload.get("source_kind")
    source_key = payload.get("source_key")
    title = payload.get("title")
    summary = payload.get("summary")
    confidence = payload.get("confidence")
    ranking_score = payload.get("ranking_score")
    reasoning_path = payload.get("reasoning_path")
    evidence_bundle = payload.get("evidence_bundle")
    proposal_payload = payload.get("payload")
    metadata = payload.get("metadata")
    source_document_id = payload.get("source_document_id")
    claim_fingerprint = payload.get("claim_fingerprint")
    if not isinstance(proposal_type, str):
        return None
    if not isinstance(source_kind, str):
        return None
    if not isinstance(source_key, str):
        return None
    if not isinstance(title, str):
        return None
    if not isinstance(summary, str):
        return None
    if not isinstance(confidence, int | float) or not isinstance(
        ranking_score,
        int | float,
    ):
        return None
    if not isinstance(reasoning_path, dict):
        return None
    if not isinstance(evidence_bundle, list):
        return None
    if not isinstance(proposal_payload, dict) or not isinstance(metadata, dict):
        return None
    if source_document_id is not None and not isinstance(source_document_id, str):
        return None
    if claim_fingerprint is not None and not isinstance(claim_fingerprint, str):
        return None
    return ResearchInitStructuredReplayProposal(
        proposal_type=proposal_type,
        source_kind=source_kind,
        source_key=source_key,
        title=title,
        summary=summary,
        confidence=float(confidence),
        ranking_score=float(ranking_score),
        reasoning_path=dict(reasoning_path),
        evidence_bundle=[item for item in evidence_bundle if isinstance(item, dict)],
        payload=dict(proposal_payload),
        metadata=dict(metadata),
        source_document_id=source_document_id,
        claim_fingerprint=claim_fingerprint,
    )

def _serialize_pubmed_candidate(candidate: object) -> JSONObject:
    return {
        "title": str(getattr(candidate, "title", "")),
        "text": str(getattr(candidate, "text", "")),
        "queries": [
            query
            for query in getattr(candidate, "queries", ())
            if isinstance(query, str) and query.strip() != ""
        ],
        "pmid": (
            getattr(candidate, "pmid", None)
            if isinstance(getattr(candidate, "pmid", None), str)
            else None
        ),
        "doi": (
            getattr(candidate, "doi", None)
            if isinstance(getattr(candidate, "doi", None), str)
            else None
        ),
        "pmc_id": (
            getattr(candidate, "pmc_id", None)
            if isinstance(getattr(candidate, "pmc_id", None), str)
            else None
        ),
        "journal": (
            getattr(candidate, "journal", None)
            if isinstance(getattr(candidate, "journal", None), str)
            else None
        ),
    }

def _serialize_pubmed_candidate_review(review: object) -> JSONObject:
    return {
        "method": str(getattr(review, "method", "heuristic")),
        "label": str(getattr(review, "label", "relevant")),
        "confidence": float(getattr(review, "confidence", 0.0)),
        "rationale": str(getattr(review, "rationale", "")),
        "agent_run_id": (
            getattr(review, "agent_run_id", None)
            if isinstance(getattr(review, "agent_run_id", None), str)
            else None
        ),
        "signal_count": int(getattr(review, "signal_count", 0)),
        "focus_signal_count": int(getattr(review, "focus_signal_count", 0)),
        "query_specificity": int(getattr(review, "query_specificity", 0)),
    }

def serialize_pubmed_replay_bundle(
    replay_bundle: ResearchInitPubMedReplayBundle,
) -> JSONObject:
    """Serialize one replay bundle so a queued run can reload it later."""
    return {
        "version": 1,
        "query_executions": [
            {
                "query_result": (
                    {
                        "query": query_execution.query_result.query,
                        "total_found": query_execution.query_result.total_found,
                        "abstracts_ingested": (
                            query_execution.query_result.abstracts_ingested
                        ),
                    }
                    if query_execution.query_result is not None
                    else None
                ),
                "candidates": [
                    _serialize_pubmed_candidate(candidate)
                    for candidate in query_execution.candidates
                ],
                "errors": list(query_execution.errors),
            }
            for query_execution in replay_bundle.query_executions
        ],
        "selected_candidates": [
            {
                "candidate": _serialize_pubmed_candidate(candidate),
                "review": _serialize_pubmed_candidate_review(review),
            }
            for candidate, review in replay_bundle.selected_candidates
        ],
        "selection_errors": list(replay_bundle.selection_errors),
        "documents": [
            {
                "source_document_id": document.source_document_id,
                "sha256": document.sha256,
                "title": document.title,
                "extraction_proposals": [
                    _serialize_replay_proposal(proposal)
                    for proposal in document.extraction_proposals
                ],
            }
            for document in replay_bundle.documents
        ],
    }

def _deserialize_pubmed_candidate(payload: object) -> object | None:

    if not isinstance(payload, dict):
        return None
    title = payload.get("title")
    text = payload.get("text")
    raw_queries = payload.get("queries")
    if not isinstance(title, str) or not isinstance(text, str):
        return None
    queries = (
        [
            query
            for query in raw_queries
            if isinstance(query, str) and query.strip() != ""
        ]
        if isinstance(raw_queries, list)
        else []
    )
    pmid = payload.get("pmid")
    doi = payload.get("doi")
    pmc_id = payload.get("pmc_id")
    journal = payload.get("journal")
    return _PubMedCandidate(
        title=title,
        text=text,
        queries=queries,
        pmid=pmid if isinstance(pmid, str) and pmid.strip() != "" else None,
        doi=doi if isinstance(doi, str) and doi.strip() != "" else None,
        pmc_id=pmc_id if isinstance(pmc_id, str) and pmc_id.strip() != "" else None,
        journal=(
            journal if isinstance(journal, str) and journal.strip() != "" else None
        ),
    )

def _deserialize_pubmed_candidate_review(payload: object) -> object | None:

    if not isinstance(payload, dict):
        return None
    method = payload.get("method")
    label = payload.get("label")
    confidence = payload.get("confidence")
    rationale = payload.get("rationale")
    if (
        method not in {"heuristic", "llm"}
        or label not in {"relevant", "non_relevant"}
        or not isinstance(confidence, int | float)
        or not isinstance(rationale, str)
    ):
        return None
    agent_run_id = payload.get("agent_run_id")
    signal_count = payload.get("signal_count", 0)
    focus_signal_count = payload.get("focus_signal_count", 0)
    query_specificity = payload.get("query_specificity", 0)
    return _PubMedCandidateReview(
        method=method,
        label=label,
        confidence=float(confidence),
        rationale=rationale,
        agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
        signal_count=int(signal_count) if isinstance(signal_count, int | float) else 0,
        focus_signal_count=(
            int(focus_signal_count)
            if isinstance(focus_signal_count, int | float)
            else 0
        ),
        query_specificity=(
            int(query_specificity) if isinstance(query_specificity, int | float) else 0
        ),
    )

def deserialize_pubmed_replay_bundle(  # noqa: PLR0911,PLR0912,PLR0915
    payload: object,
) -> ResearchInitPubMedReplayBundle | None:
    """Deserialize one stored replay bundle back into runtime objects."""
    if not isinstance(payload, dict):
        return None
    query_execution_payloads = payload.get("query_executions")
    selected_candidate_payloads = payload.get("selected_candidates")
    selection_errors_payload = payload.get("selection_errors")
    documents_payload = payload.get("documents", [])
    if not isinstance(query_execution_payloads, list):
        return None
    if not isinstance(selected_candidate_payloads, list):
        return None
    if not isinstance(selection_errors_payload, list):
        return None
    if not isinstance(documents_payload, list):
        return None

    query_executions: list[_PubMedQueryExecutionResult] = []
    for query_execution_payload in query_execution_payloads:
        if not isinstance(query_execution_payload, dict):
            return None
        raw_query_result = query_execution_payload.get("query_result")
        query_result: ResearchInitPubMedResultRecord | None = None
        if raw_query_result is not None:
            if not isinstance(raw_query_result, dict):
                return None
            query = raw_query_result.get("query")
            total_found = raw_query_result.get("total_found")
            abstracts_ingested = raw_query_result.get("abstracts_ingested")
            if (
                not isinstance(query, str)
                or not isinstance(total_found, int)
                or not isinstance(abstracts_ingested, int)
            ):
                return None
            query_result = ResearchInitPubMedResultRecord(
                query=query,
                total_found=total_found,
                abstracts_ingested=abstracts_ingested,
            )
        raw_candidates = query_execution_payload.get("candidates")
        raw_errors = query_execution_payload.get("errors")
        if not isinstance(raw_candidates, list) or not isinstance(raw_errors, list):
            return None
        candidates: list[object] = []
        for raw_candidate in raw_candidates:
            candidate = _deserialize_pubmed_candidate(raw_candidate)
            if candidate is None:
                return None
            candidates.append(candidate)
        errors = [
            error for error in raw_errors if isinstance(error, str) and error != ""
        ]
        query_executions.append(
            _PubMedQueryExecutionResult(
                query_result=query_result,
                candidates=tuple(candidates),
                errors=tuple(errors),
            ),
        )

    selected_candidates: list[tuple[object, object]] = []
    for selected_candidate_payload in selected_candidate_payloads:
        if not isinstance(selected_candidate_payload, dict):
            return None
        candidate = _deserialize_pubmed_candidate(
            selected_candidate_payload.get("candidate"),
        )
        review = _deserialize_pubmed_candidate_review(
            selected_candidate_payload.get("review"),
        )
        if candidate is None or review is None:
            return None
        selected_candidates.append((candidate, review))

    selection_errors = [
        error
        for error in selection_errors_payload
        if isinstance(error, str) and error != ""
    ]
    documents: list[ResearchInitPubMedReplayDocument] = []
    for document_payload in documents_payload:
        if not isinstance(document_payload, dict):
            return None
        source_document_id = document_payload.get("source_document_id")
        sha256 = document_payload.get("sha256")
        title = document_payload.get("title")
        raw_extraction_proposals = document_payload.get("extraction_proposals", [])
        if not isinstance(source_document_id, str) or source_document_id == "":
            return None
        if not isinstance(sha256, str) or sha256 == "":
            return None
        if not isinstance(title, str) or title == "":
            return None
        if not isinstance(raw_extraction_proposals, list):
            return None
        extraction_proposals: list[ResearchInitStructuredReplayProposal] = []
        for raw_extraction_proposal in raw_extraction_proposals:
            extraction_proposal = _deserialize_replay_proposal(
                raw_extraction_proposal,
            )
            if extraction_proposal is None:
                return None
            extraction_proposals.append(extraction_proposal)
        documents.append(
            ResearchInitPubMedReplayDocument(
                source_document_id=source_document_id,
                sha256=sha256,
                title=title,
                extraction_proposals=tuple(extraction_proposals),
            ),
        )
    return ResearchInitPubMedReplayBundle(
        query_executions=tuple(query_executions),
        selected_candidates=tuple(selected_candidates),
        selection_errors=tuple(selection_errors),
        documents=tuple(documents),
    )

def store_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    replay_bundle: ResearchInitPubMedReplayBundle,
) -> None:
    """Persist one PubMed replay bundle for queued research-init execution."""
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
        media_type="application/json",
        content=serialize_pubmed_replay_bundle(replay_bundle),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"pubmed_replay_bundle_key": _PUBMED_REPLAY_ARTIFACT_KEY},
    )

def load_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
) -> ResearchInitPubMedReplayBundle | None:
    """Load one persisted PubMed replay bundle for queued research-init runs."""
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
    )
    if artifact is None:
        return None
    return deserialize_pubmed_replay_bundle(artifact.content)

def _pubmed_replay_document_by_sha256(
    replay_bundle: ResearchInitPubMedReplayBundle | None,
    *,
    sha256: str,
) -> ResearchInitPubMedReplayDocument | None:
    if replay_bundle is None:
        return None
    for document in replay_bundle.documents:
        if document.sha256 == sha256:
            return document
    return None

def build_pubmed_replay_bundle_with_document_outputs(
    *,
    replay_bundle: ResearchInitPubMedReplayBundle,
    space_id: UUID,
    run_id: UUID | str,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
) -> ResearchInitPubMedReplayBundle:
    """Attach replayable PubMed document extraction outputs from one baseline run."""
    candidate_sha256s = {
        sha256_hex(
            normalize_text_document(str(getattr(candidate, "text", ""))).encode("utf-8")
        )
        for candidate, _review in replay_bundle.selected_candidates
        if normalize_text_document(str(getattr(candidate, "text", ""))) != ""
    }
    if not candidate_sha256s:
        return replay_bundle

    pubmed_documents_by_id: dict[str, HarnessDocumentRecord] = {}
    for document in document_store.list_documents(space_id=space_id):
        if document.source_type != "pubmed":
            continue
        if not _is_research_init_pubmed_document(document):
            continue
        if document.sha256 not in candidate_sha256s:
            continue
        pubmed_documents_by_id[document.id] = document

    if not pubmed_documents_by_id:
        return replay_bundle

    proposals_by_document_id: dict[str, list[ResearchInitStructuredReplayProposal]] = {
        document_id: [] for document_id in pubmed_documents_by_id
    }
    for proposal in proposal_store.list_proposals(
        space_id=space_id, run_id=str(run_id)
    ):
        if proposal.source_kind != "document_extraction":
            continue
        if proposal.document_id not in pubmed_documents_by_id:
            continue
        proposals_by_document_id[proposal.document_id].append(
            ResearchInitStructuredReplayProposal(
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
            ),
        )

    replay_documents = tuple(
        ResearchInitPubMedReplayDocument(
            source_document_id=document.id,
            sha256=document.sha256,
            title=document.title,
            extraction_proposals=tuple(proposals_by_document_id[document.id]),
        )
        for document in sorted(
            pubmed_documents_by_id.values(),
            key=lambda current: (current.title, current.id),
        )
    )
    return ResearchInitPubMedReplayBundle(
        query_executions=replay_bundle.query_executions,
        selected_candidates=replay_bundle.selected_candidates,
        selection_errors=replay_bundle.selection_errors,
        documents=replay_documents,
    )
