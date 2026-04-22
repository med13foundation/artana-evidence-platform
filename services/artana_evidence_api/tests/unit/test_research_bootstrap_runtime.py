"""Unit tests for research-bootstrap runtime behavior."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
)
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphServiceHealthResponse,
)
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.research_bootstrap_runtime import (
    _build_pending_questions,
    _dedupe_proposal_records,
    _load_candidate_entity_display_labels,
    _select_bootstrap_claim_curation_proposals,
    execute_research_bootstrap_run,
)
from artana_evidence_api.research_question_policy import (
    filter_repeated_directional_questions,
    is_evidence_support_question,
    should_allow_directional_follow_up,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.types.graph_contracts import (
    HypothesisListResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
    KernelRelationConflictListResponse,
    KernelRelationSuggestionConstraintCheckResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionScoreBreakdownResponse,
    KernelRelationSuggestionSkippedSourceResponse,
)


def _proposal(
    *,
    title: str,
    summary: str,
    subject: str,
    relation_type: str,
    target: str,
    source_key: str | None = None,
    claim_fingerprint: str | None = None,
) -> HarnessProposalRecord:
    now = datetime.now(UTC)
    return HarnessProposalRecord(
        id=f"proposal:{subject}:{relation_type}:{target}:{source_key or 'default'}",
        space_id="space-1",
        run_id="run-1",
        proposal_type="candidate_claim",
        source_kind="research_bootstrap",
        source_key=source_key or f"{subject}:{relation_type}:{target}",
        document_id=None,
        title=title,
        summary=summary,
        status="pending_review",
        confidence=0.82,
        ranking_score=0.75,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": subject,
            "proposed_claim_type": relation_type,
            "proposed_object": target,
        },
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
        claim_fingerprint=claim_fingerprint,
    )


def _candidate_claim_draft(
    *,
    title: str,
    source_key: str,
    claim_fingerprint: str | None = None,
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title=title,
        summary=f"Evidence summary for {title}",
        confidence=0.88,
        ranking_score=0.91,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": "MED13",
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": title,
        },
        metadata={},
        claim_fingerprint=claim_fingerprint,
    )


def test_load_candidate_entity_display_labels_tolerates_gateways_without_list_entities() -> (
    None
):
    relation = type(
        "_Relation",
        (),
        {
            "source_id": "11111111-1111-1111-1111-111111111111",
            "target_id": "22222222-2222-2222-2222-222222222222",
        },
    )()
    outcome = type("_Outcome", (), {"proposed_relations": [relation]})()
    gateway = _StubGraphApiGateway()

    labels = _load_candidate_entity_display_labels(
        space_id=uuid4(),
        graph_api_gateway=gateway,
        outcomes=[outcome],
    )

    assert labels == {}


def _curatable_candidate_claim_draft(
    *,
    title: str,
    source_key: str,
    subject_id: str,
    object_id: str,
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title=title,
        summary=f"Evidence summary for {title}",
        confidence=0.88,
        ranking_score=0.91,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": subject_id,
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": object_id,
        },
        metadata={},
    )


class _StubGraphApiGateway:
    def __init__(self) -> None:
        self.closed = False
        self.refreshed_entity_ids: list[str] = []
        self.last_refresh_limit: int | None = None

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

    def refresh_entity_embeddings(
        self,
        *,
        space_id: UUID | str,
        request: KernelEntityEmbeddingRefreshRequest,
    ) -> KernelEntityEmbeddingRefreshResponse:
        del space_id
        self.refreshed_entity_ids = [
            str(entity_id) for entity_id in (request.entity_ids or [])
        ]
        self.last_refresh_limit = request.limit
        return KernelEntityEmbeddingRefreshResponse(
            requested=(
                len(self.refreshed_entity_ids)
                if request.entity_ids is not None
                else int(request.limit)
            ),
            processed=(
                len(self.refreshed_entity_ids)
                if request.entity_ids is not None
                else int(request.limit)
            ),
            refreshed=0,
            unchanged=(
                len(self.refreshed_entity_ids)
                if request.entity_ids is not None
                else int(request.limit)
            ),
            failed=0,
            missing_entities=[],
        )

    def list_entity_embedding_status(
        self,
        *,
        space_id: UUID | str,
        entity_ids: list[str] | None = None,
    ) -> KernelEntityEmbeddingStatusListResponse:
        del space_id, entity_ids
        return KernelEntityEmbeddingStatusListResponse(statuses=[], total=0)

    def close(self) -> None:
        self.closed = True


class _DeterministicSuggestionGateway(_StubGraphApiGateway):
    def __init__(self) -> None:
        super().__init__()
        self.suggested_seed_ids: list[str] = []

    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: object,
    ) -> KernelRelationSuggestionListResponse:
        del space_id
        source_entity_ids = request.source_entity_ids
        seed_entity_id = str(source_entity_ids[0])
        self.suggested_seed_ids.append(seed_entity_id)
        return KernelRelationSuggestionListResponse(
            suggestions=[
                KernelRelationSuggestionResponse(
                    source_entity_id=UUID(seed_entity_id),
                    target_entity_id=UUID("22222222-2222-2222-2222-222222222222"),
                    relation_type="ASSOCIATED_WITH",
                    final_score=0.91,
                    score_breakdown=KernelRelationSuggestionScoreBreakdownResponse(
                        vector_score=0.9,
                        graph_overlap_score=0.8,
                        relation_prior_score=0.7,
                    ),
                    constraint_check=KernelRelationSuggestionConstraintCheckResponse(
                        passed=True,
                        source_entity_type="GENE",
                        relation_type="ASSOCIATED_WITH",
                        target_entity_type="DISEASE",
                    ),
                ),
            ],
            total=1,
            limit_per_source=10,
            min_score=0.7,
            incomplete=False,
            skipped_sources=[],
        )

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, offset, limit
        resolved_ids = ids or []
        entities = [
            KernelEntityResponse(
                id=UUID(entity_id),
                research_space_id=uuid4(),
                entity_type="GENE" if index == 0 else "DISEASE",
                display_label="MED13" if index == 0 else "Developmental delay",
                aliases=[],
                metadata={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for index, entity_id in enumerate(resolved_ids)
        ]
        return KernelEntityListResponse(
            entities=entities,
            total=len(entities),
            offset=0,
            limit=max(len(entities), 1),
        )


class _SkippedSuggestionGateway(_StubGraphApiGateway):
    def suggest_relations(
        self,
        *,
        space_id: UUID | str,
        request: object,
    ) -> KernelRelationSuggestionListResponse:
        del space_id
        source_entity_ids = request.source_entity_ids
        seed_entity_id = UUID(str(source_entity_ids[0]))
        return KernelRelationSuggestionListResponse(
            suggestions=[],
            total=0,
            limit_per_source=10,
            min_score=0.7,
            incomplete=True,
            skipped_sources=[
                KernelRelationSuggestionSkippedSourceResponse(
                    entity_id=seed_entity_id,
                    state="pending",
                    reason="embedding_pending",
                ),
            ],
        )

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, offset, limit
        resolved_ids = ids or []
        return KernelEntityListResponse(
            entities=[
                KernelEntityResponse(
                    id=UUID(entity_id),
                    research_space_id=uuid4(),
                    entity_type="GENE",
                    display_label="MED13",
                    aliases=[],
                    metadata={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                for entity_id in resolved_ids
            ],
            total=len(resolved_ids),
            offset=0,
            limit=max(len(resolved_ids), 1),
        )


class _ExplodingRunner:
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        del request
        raise AssertionError("graph_connection_runner should not be used")


class _FallbackRunner:
    def __init__(self) -> None:
        self.seed_entity_ids: list[str] = []

    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        self.seed_entity_ids.append(request.seed_entity_id)
        contract = GraphConnectionContract(
            decision="fallback",
            confidence_score=0.2,
            rationale="Synthetic fallback for empty-graph coverage.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"seed:{request.seed_entity_id}",
                    excerpt="No graph relations available.",
                    relevance=0.2,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=f"graph_connection:{request.seed_entity_id}",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=(),
        )


class _SlowRunner:
    def __init__(self) -> None:
        self.seed_entity_ids: list[str] = []

    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        self.seed_entity_ids.append(request.seed_entity_id)
        await asyncio.sleep(0.05)
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=0.7,
            rationale="This should be timed out before it completes.",
            evidence=[],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=f"graph_connection:{request.seed_entity_id}",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=(),
        )


def _empty_graph_document(*, seed_entity_ids: list[str]) -> KernelGraphDocumentResponse:
    now = datetime.now(UTC)
    seed_entity_id = seed_entity_ids[0] if seed_entity_ids else str(uuid4())
    return KernelGraphDocumentResponse(
        nodes=[
            KernelGraphDocumentNode(
                id="ENTITY:seed",
                resource_id=seed_entity_id,
                kind="ENTITY",
                type_label="GENE",
                label="MED13",
                confidence=None,
                curation_status=None,
                claim_status=None,
                polarity=None,
                canonical_relation_id=None,
                metadata={},
                created_at=now,
                updated_at=now,
            ),
        ],
        edges=[],
        meta=KernelGraphDocumentMeta(
            mode="seeded",
            seed_entity_ids=[UUID(seed_entity_id)],
            requested_depth=2,
            requested_top_k=25,
            pre_cap_entity_node_count=1,
            pre_cap_canonical_edge_count=0,
            truncated_entity_nodes=False,
            truncated_canonical_edges=False,
            included_claims=True,
            included_evidence=True,
            max_claims=250,
            evidence_limit_per_claim=3,
            counts=KernelGraphDocumentCounts(
                entity_nodes=1,
                claim_nodes=0,
                evidence_nodes=0,
                canonical_edges=0,
                claim_participant_edges=0,
                claim_evidence_edges=0,
            ),
        ),
    )


def _stub_runtime_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import research_bootstrap_runtime

    monkeypatch.setattr(
        research_bootstrap_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "append_skill_activity",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "run_capture_graph_snapshot",
        lambda **kwargs: _empty_graph_document(
            seed_entity_ids=list(kwargs["seed_entity_ids"]),
        ).model_dump(mode="json"),
    )
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "run_list_graph_claims",
        lambda **_kwargs: KernelRelationClaimListResponse(
            claims=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "run_list_graph_hypotheses",
        lambda **_kwargs: HypothesisListResponse(
            hypotheses=[],
            total=0,
            offset=0,
            limit=25,
        ),
    )


def test_build_pending_questions_prioritizes_directional_clinical_follow_up() -> None:
    questions = _build_pending_questions(
        objective=(
            "Find new treatment ideas and uncover mechanistic or disease-network "
            "connections for MED13 syndrome"
        ),
        proposals=[
            _proposal(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                summary="MED13 variants are linked to developmental delay phenotypes.",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="developmental delay",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert questions[0].startswith(
        "I finished the initial research pass for MED13 syndrome",
    )
    assert "treatment or repurposing leads" in questions[0]
    assert "disease mechanisms and pathways" in questions[0]
    assert "phenotypes, natural history, or case reports" in questions[0]
    assert "related genes, pathways, and overlapping conditions" in questions[0]


def test_build_pending_questions_uses_basic_biology_directions_for_non_clinical_topics() -> (
    None
):
    questions = _build_pending_questions(
        objective="Map regulatory programs controlled by MED13 in cortical neurons",
        proposals=[
            _proposal(
                title="Candidate claim: MED13 REGULATES glycolysis",
                summary="MED13 shapes neuronal glycolysis in model systems.",
                subject="MED13",
                relation_type="REGULATES",
                target="glycolysis",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert "direct functional evidence" in questions[0]
    assert "mechanisms and pathways" in questions[0]
    assert "perturbation or model-system evidence" in questions[0]
    assert "related genes, proteins, biomarkers, or pathways" in questions[0]


def test_build_pending_questions_prefers_entity_anchor_over_source_branded_anchor() -> (
    None
):
    questions = _build_pending_questions(
        objective="Investigate BRCA1 and PARP inhibitor response.",
        proposals=[
            _proposal(
                title="Candidate claim: ClinVar variant ASSOCIATED_WITH PARP inhibitor",
                summary=(
                    "BRCA1 variant evidence supports sensitivity to PARP inhibitor "
                    "response."
                ),
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="PARP inhibitor response",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert questions[0].startswith(
        "I finished the initial research pass for BRCA1 variant",
    )
    assert "ClinVar variant" not in questions[0]


def test_build_pending_questions_suppresses_directional_follow_up_after_initial_cycle() -> (
    None
):
    questions = _build_pending_questions(
        objective="Investigate MED13 neurodevelopmental disorder mechanisms.",
        proposals=[
            _proposal(
                title="Candidate claim: MED13 ASSOCIATED_WITH developmental delay",
                summary="MED13 variants are linked to developmental delay phenotypes.",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="developmental delay",
            ),
        ],
        max_questions=5,
        allow_directional_question=False,
    )

    assert questions == []
    assert all(
        "Which direction should I deepen next" not in question for question in questions
    )


def test_build_pending_questions_returns_empty_when_directional_follow_up_is_disallowed() -> (
    None
):
    questions = _build_pending_questions(
        objective="Investigate MED13 neurodevelopmental disorder mechanisms.",
        proposals=[],
        max_questions=5,
        allow_directional_question=False,
    )

    assert questions == []


def test_directional_question_policy_allows_only_unanswered_first_pass() -> None:
    assert should_allow_directional_follow_up(
        objective="Investigate MED13 syndrome",
        explored_questions=[],
        last_graph_snapshot_id=None,
    )
    assert not should_allow_directional_follow_up(
        objective="Investigate MED13 syndrome",
        explored_questions=["Investigate MED13 syndrome", "Gene-disease first"],
        last_graph_snapshot_id=None,
    )
    assert not should_allow_directional_follow_up(
        objective="Investigate MED13 syndrome",
        explored_questions=[],
        last_graph_snapshot_id="snapshot-1",
    )


def test_filter_repeated_directional_questions_hides_internal_evidence_prompts() -> (
    None
):
    pending_questions = [
        "I finished the initial research pass for MED13 and already pulled in "
        "starting evidence. Which direction should I deepen next: treatment "
        "or repurposing leads, disease mechanisms and pathways?",
        "What evidence best supports MED13 ASSOCIATED_WITH developmental delay?",
    ]

    assert (
        filter_repeated_directional_questions(
            objective="Investigate MED13 syndrome",
            explored_questions=["Investigate MED13 syndrome", "Gene-disease first"],
            pending_questions=pending_questions,
            last_graph_snapshot_id="snapshot-1",
        )
        == []
    )
    assert (
        filter_repeated_directional_questions(
            objective="Investigate MED13 syndrome",
            explored_questions=["Investigate MED13 syndrome"],
            pending_questions=pending_questions,
            last_graph_snapshot_id="snapshot-1",
        )
        == pending_questions[:1]
    )


def test_build_pending_questions_filters_taxonomic_spillover_for_non_organism_objective() -> (
    None
):
    questions = _build_pending_questions(
        objective="Investigate BRCA1 and PARP inhibitor response.",
        proposals=[
            _proposal(
                title="Candidate claim: BRCA1 EXPRESSED_IN Colletotrichum fioriniae",
                summary="Cross-domain chase spillover that should stay out of follow-up prompts.",
                subject="BRCA1",
                relation_type="EXPRESSED_IN",
                target="Colletotrichum fioriniae",
            ),
            _proposal(
                title="Candidate claim: BRCA1 BIOMARKER_FOR PARP inhibitor response",
                summary="Therapy-relevant signal worth preserving.",
                subject="BRCA1",
                relation_type="BIOMARKER_FOR",
                target="PARP inhibitor response",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert not any(is_evidence_support_question(question) for question in questions)
    assert all("Colletotrichum fioriniae" not in question for question in questions)


def test_build_pending_questions_keeps_taxonomic_expression_question_for_organism_objective() -> (
    None
):
    questions = _build_pending_questions(
        objective="Investigate BRCA1 expression across fungal species and strains.",
        proposals=[
            _proposal(
                title="Candidate claim: BRCA1 EXPRESSED_IN Colletotrichum fioriniae",
                summary="Organism-focused expression comparison.",
                subject="BRCA1",
                relation_type="EXPRESSED_IN",
                target="Colletotrichum fioriniae",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert not any(is_evidence_support_question(question) for question in questions)


def test_build_pending_questions_prefers_labels_over_ids() -> None:
    questions = _build_pending_questions(
        objective="Investigate MED13 and congenital heart disease.",
        proposals=[
            replace(
                _proposal(
                    title="Candidate claim: uuid-subject ASSOCIATED_WITH uuid-target",
                    summary="Supporting evidence",
                    subject="uuid-subject",
                    relation_type="ASSOCIATED_WITH",
                    target="uuid-target",
                ),
                payload={
                    "proposed_subject": "uuid-subject",
                    "proposed_subject_label": "MED13",
                    "proposed_claim_type": "ASSOCIATED_WITH",
                    "proposed_object": "uuid-target",
                    "proposed_object_label": "congenital heart disease",
                },
                metadata={
                    "subject_label": "MED13",
                    "object_label": "congenital heart disease",
                },
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert not any(is_evidence_support_question(question) for question in questions)
    assert all("uuid-subject" not in question for question in questions)
    assert all("uuid-target" not in question for question in questions)


def test_build_pending_questions_filters_low_signal_labels() -> None:
    questions = _build_pending_questions(
        objective="Investigate BRCA1 and PARP inhibitor response.",
        proposals=[
            _proposal(
                title="Candidate claim: BRCA1 ASSOCIATED_WITH result 1",
                summary="Noisy placeholder label from an earlier pass.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="result 1",
            ),
            _proposal(
                title="Candidate claim: BRCA1 CAUSES Uncertain significance",
                summary="Clinical significance bucket, not a good follow-up target.",
                subject="BRCA1",
                relation_type="CAUSES",
                target="Uncertain significance",
            ),
            _proposal(
                title="Candidate claim: BRCA1 CAUSES unspecified condition",
                summary="Generic fallback condition that should not become a question.",
                subject="BRCA1",
                relation_type="CAUSES",
                target="unspecified condition",
            ),
            _proposal(
                title="Candidate claim: c.2410_2413del ASSOCIATED_WITH Pathogenic",
                summary="Bare clinical significance bucket should not become a question.",
                subject="c.2410_2413del",
                relation_type="ASSOCIATED_WITH",
                target="Pathogenic",
            ),
            _proposal(
                title="Candidate claim: BRCA1 ASSOCIATED_WITH Likely benign variants",
                summary="Plural clinical significance bucket should stay out too.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="Likely benign variants",
            ),
            _proposal(
                title=(
                    "Candidate claim: BRCA1 ASSOCIATED_WITH "
                    "BRCA1 PARP inhibitor result 4"
                ),
                summary="Generated composite label carrying an embedded result number.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="BRCA1 PARP inhibitor result 4",
            ),
            _proposal(
                title="Candidate claim: BRCA1 ASSOCIATED_WITH PARP inhibitor response",
                summary="Therapy-relevant signal worth preserving.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="PARP inhibitor response",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert questions
    assert not any(is_evidence_support_question(question) for question in questions)
    assert all("result 1" not in question for question in questions)
    assert all("Uncertain significance" not in question for question in questions)
    assert all("unspecified condition" not in question for question in questions)
    assert all("Pathogenic" not in question for question in questions[1:])
    assert all("Likely benign variants" not in question for question in questions)
    assert all("result 4" not in question for question in questions)


def test_build_pending_questions_filters_underanchored_fragment_labels() -> None:
    questions = _build_pending_questions(
        objective="Investigate BRCA1 and PARP inhibitor response.",
        proposals=[
            _proposal(
                title="Candidate claim: BRCA1 ASSOCIATED_WITH C Terminus domain",
                summary="Bare fragment label without a clear anchor.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="C Terminus domain",
            ),
            _proposal(
                title="Candidate claim: BRCA1 ASSOCIATED_WITH BRCA1 C Terminus domain",
                summary="Anchored fragment label should remain in scope.",
                subject="BRCA1",
                relation_type="ASSOCIATED_WITH",
                target="BRCA1 C Terminus domain",
            ),
        ],
        max_questions=5,
        allow_directional_question=True,
    )

    assert not any(is_evidence_support_question(question) for question in questions)
    assert all("C Terminus domain" not in question for question in questions)


def test_dedupe_proposal_records_prefers_claim_fingerprint_before_source_key() -> None:
    deduped = _dedupe_proposal_records(
        [
            _proposal(
                title="A",
                summary="first",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="developmental delay",
                source_key="doc-a",
                claim_fingerprint="fp-1",
            ),
            _proposal(
                title="B",
                summary="second",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="developmental delay",
                source_key="doc-b",
                claim_fingerprint="fp-1",
            ),
            _proposal(
                title="C",
                summary="third",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="cardiomyopathy",
                source_key="shared-source",
                claim_fingerprint=None,
            ),
            _proposal(
                title="D",
                summary="fourth",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="cardiomyopathy",
                source_key="shared-source",
                claim_fingerprint=None,
            ),
        ],
    )

    assert [proposal.title for proposal in deduped] == ["A", "C"]


def test_select_bootstrap_claim_curation_proposals_preserves_proposal_order() -> None:
    proposals = [
        replace(
            _proposal(
                title="First",
                summary="first",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="phenotype-a",
                source_key="first",
            ),
            run_id="bootstrap-run",
            ranking_score=0.11,
        ),
        replace(
            _proposal(
                title="Second",
                summary="second",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="phenotype-b",
                source_key="second",
            ),
            run_id="bootstrap-run",
            ranking_score=0.99,
        ),
        replace(
            _proposal(
                title="Third",
                summary="third",
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                target="phenotype-c",
                source_key="third",
            ),
            run_id="other-run",
            ranking_score=0.75,
        ),
    ]

    selected = _select_bootstrap_claim_curation_proposals(
        proposals=proposals,
        limit=2,
    )

    assert [proposal.title for proposal in selected] == ["First", "Second"]


@pytest.mark.asyncio
async def test_execute_research_bootstrap_reuses_staged_proposals_and_softens_graph_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import research_bootstrap_runtime

    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                source_key="pubmed:1",
            ),
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID duplicate",
                source_key="pubmed:1",
                claim_fingerprint=None,
            ),
        ),
    )
    runner = _FallbackRunner()
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=[
            "11111111-1111-1111-1111-111111111111",
            "11111111-1111-1111-1111-111111111111",
        ],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=runner,
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert runner.seed_entity_ids == ["11111111-1111-1111-1111-111111111111"]
    assert len(result.proposal_records) == 1
    assert result.source_inventory["linked_proposal_count"] == 1
    assert result.source_inventory["bootstrap_generated_proposal_count"] == 0
    assert result.source_inventory["graph_connection_fallback_seed_ids"] == [
        "11111111-1111-1111-1111-111111111111",
    ]

    candidate_pack = artifact_store.get_artifact(
        space_id=space_id,
        run_id=result.run.id,
        artifact_key="candidate_claim_pack",
    )
    assert candidate_pack is not None
    assert candidate_pack.content["proposal_count"] == 1
    assert candidate_pack.content["linked_proposal_count"] == 1
    assert candidate_pack.content["proposals"][0]["candidate_source"] == (
        "staged_proposal"
    )

    staged_context = artifact_store.get_artifact(
        space_id=space_id,
        run_id=result.run.id,
        artifact_key="staged_proposal_context",
    )
    assert staged_context is not None
    assert staged_context.content["selection_strategy"] == "current_parent_run"
    assert staged_context.content["linked_proposal_count"] == 1

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=result.run.id)
    assert workspace is not None
    assert workspace.snapshot["proposal_count"] == 1
    assert workspace.snapshot["linked_proposal_count"] == 1
    assert workspace.snapshot["bootstrap_generated_proposal_count"] == 0
    assert workspace.snapshot["graph_connection_timeout_count"] == 0
    assert workspace.snapshot["graph_connection_fallback_seed_ids"] == [
        "11111111-1111-1111-1111-111111111111",
    ]
    assert workspace.snapshot["last_staged_proposal_context_key"] == (
        "staged_proposal_context"
    )

    assert research_bootstrap_runtime.normalize_bootstrap_seed_entity_ids(
        ["11111111-1111-1111-1111-111111111111"] * 2,
    ) == ["11111111-1111-1111-1111-111111111111"]


@pytest.mark.asyncio
async def test_execute_research_bootstrap_suppresses_directional_question_after_prior_cycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    parent_run_id = "research-init-follow-up"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH developmental delay",
                source_key="pubmed:follow-up",
            ),
        ),
    )
    research_state_store = HarnessResearchStateStore()
    research_state_store.upsert_state(
        space_id=space_id,
        objective="Investigate MED13 syndrome",
        explored_questions=[
            "Investigate MED13 syndrome",
            "disease mechanisms and pathways",
        ],
        pending_questions=[],
        last_graph_snapshot_id="prior-snapshot",
    )

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=research_state_store,
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert result.pending_questions == []
    assert all(
        "Which direction should I deepen next" not in question
        for question in result.pending_questions
    )
    assert all(
        "treatment or repurposing leads" not in question
        for question in result.pending_questions
    )


@pytest.mark.asyncio
async def test_execute_research_bootstrap_suppresses_directional_question_after_user_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    parent_run_id = "research-init-after-onboarding-guidance"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH developmental delay",
                source_key="pubmed:guided",
            ),
        ),
    )
    research_state_store = HarnessResearchStateStore()
    research_state_store.upsert_state(
        space_id=space_id,
        objective="Investigate MED13 syndrome",
        explored_questions=[
            "What is the first evidence slice to prioritize for MED13?",
            "Investigate MED13 syndrome",
        ],
        pending_questions=[],
        last_graph_snapshot_id=None,
    )

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=research_state_store,
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert result.pending_questions == []
    assert all(
        "Which direction should I deepen next" not in question
        for question in result.pending_questions
    )
    assert all(
        "treatment or repurposing leads" not in question
        for question in result.pending_questions
    )


@pytest.mark.asyncio
async def test_execute_research_bootstrap_keeps_embedding_refresh_failures_as_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                source_key="pubmed:1",
            ),
        ),
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()

    class _RefreshTimeoutGateway(_StubGraphApiGateway):
        def refresh_entity_embeddings(
            self,
            *,
            space_id: UUID | str,
            request: KernelEntityEmbeddingRefreshRequest,
        ) -> KernelEntityEmbeddingRefreshResponse:
            del space_id, request
            raise GraphServiceClientError("refresh failed", detail="timed out")

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_RefreshTimeoutGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=result.run.id)

    assert result.errors == []
    assert workspace is not None
    assert workspace.snapshot["bootstrap_diagnostics"] == [
        "Failed to refresh bootstrap candidate embeddings: timed out",
    ]


@pytest.mark.asyncio
async def test_execute_research_bootstrap_skips_graph_snapshot_when_only_staged_proposals_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import research_bootstrap_runtime

    _stub_runtime_helpers(monkeypatch)
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "run_capture_graph_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("graph snapshot should not run without seed entities"),
        ),
    )
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                source_key="pubmed:1",
            ),
        ),
    )

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=[],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert len(result.proposal_records) == 1
    assert result.source_inventory["linked_proposal_count"] == 1
    assert result.source_inventory["bootstrap_generated_proposal_count"] == 0
    assert result.source_inventory["graph_connection_fallback_seed_ids"] == []


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_execute_research_bootstrap_requests_candidate_pool_refresh_before_readiness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    gateway = _StubGraphApiGateway()

    await execute_research_bootstrap_run(
        space_id=uuid4(),
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=gateway,
        graph_connection_runner=_FallbackRunner(),
        proposal_store=HarnessProposalStore(),
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id="research-init-parent",
    )

    assert gateway.refreshed_entity_ids == []
    assert gateway.last_refresh_limit == 50


@pytest.mark.asyncio
async def test_execute_research_bootstrap_scales_candidate_pool_refresh_limit_from_staged_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    gateway = _StubGraphApiGateway()
    proposal_store = HarnessProposalStore()
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=tuple(
            _candidate_claim_draft(
                title=f"Candidate claim: MED13 ASSOCIATED_WITH phenotype-{index}",
                source_key=f"pubmed:{index}",
            )
            for index in range(75)
        ),
    )

    await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=gateway,
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert gateway.last_refresh_limit == 75


@pytest.mark.asyncio
async def test_execute_research_bootstrap_records_graph_connection_timeouts_without_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import research_bootstrap_runtime

    _stub_runtime_helpers(monkeypatch)
    monkeypatch.setattr(
        research_bootstrap_runtime,
        "_GRAPH_CONNECTION_TIMEOUT_SECONDS",
        0.01,
    )
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                source_key="pubmed:1",
            ),
        ),
    )

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_SlowRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert result.source_inventory["graph_connection_timeout_count"] == 1
    assert result.source_inventory["graph_connection_timeout_seed_ids"] == [
        "11111111-1111-1111-1111-111111111111",
    ]
    assert result.source_inventory["graph_connection_fallback_seed_ids"] == []


@pytest.mark.asyncio
async def test_execute_research_bootstrap_uses_deterministic_graph_suggestions_before_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    gateway = _DeterministicSuggestionGateway()

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=gateway,
        graph_connection_runner=_ExplodingRunner(),
        proposal_store=HarnessProposalStore(),
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id="research-init-parent",
    )

    assert result.errors == []
    assert gateway.suggested_seed_ids == ["11111111-1111-1111-1111-111111111111"]
    assert len(result.proposal_records) == 1
    assert result.source_inventory["linked_proposal_count"] == 0
    assert result.source_inventory["bootstrap_generated_proposal_count"] == 1
    assert result.source_inventory["graph_connection_fallback_seed_ids"] == []
    assert result.proposal_records[0].source_kind == "research_bootstrap"
    assert (
        result.proposal_records[0].title
        == "Candidate claim: MED13 ASSOCIATED_WITH Developmental delay"
    )
    assert (
        result.proposal_records[0].payload["proposed_claim_type"] == "ASSOCIATED_WITH"
    )
    assert result.proposal_records[0].payload["proposed_subject_label"] == "MED13"
    assert (
        result.proposal_records[0].payload["proposed_object_label"]
        == "Developmental delay"
    )
    assert result.proposal_records[0].claim_fingerprint == compute_claim_fingerprint(
        "MED13",
        "ASSOCIATED_WITH",
        "Developmental delay",
    )


@pytest.mark.asyncio
async def test_execute_research_bootstrap_auto_queues_governed_claim_curation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_runtime, claim_curation_workflow

    _stub_runtime_helpers(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_relation_conflicts",
        lambda **_kwargs: KernelRelationConflictListResponse(
            conflicts=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_claims_by_entity",
        lambda **_kwargs: KernelRelationClaimListResponse(
            claims=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )

    space_id = uuid4()
    parent_run_id = "research-init-parent"
    subject_id = str(uuid4())
    object_id = str(uuid4())
    proposal_store = HarnessProposalStore()
    parent_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _curatable_candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH phenotype-a",
                source_key="pubmed:1",
                subject_id=subject_id,
                object_id=object_id,
            ),
        ),
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()
    approval_store = HarnessApprovalStore()

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=[],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        approval_store=approval_store,
        claim_curation_graph_api_gateway_factory=_StubGraphApiGateway,
        auto_queue_claim_curation=True,
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert len(result.proposal_records) == 1
    assert result.proposal_records[0].run_id == parent_run_id
    assert result.claim_curation is not None
    assert result.claim_curation.status == "paused"
    assert result.claim_curation.run_id is not None
    assert result.claim_curation.proposal_ids == (parent_records[0].id,)
    assert result.claim_curation.proposal_count == 1
    assert result.claim_curation.pending_approval_count == 1

    child_run = run_registry.get_run(
        space_id=space_id,
        run_id=result.claim_curation.run_id,
    )
    assert child_run is not None
    assert child_run.harness_id == "claim-curation"
    assert child_run.status == "paused"
    assert child_run.input_payload["proposal_ids"] == [parent_records[0].id]
    assert child_run.input_payload["blocked_proposal_ids"] == []

    approvals = approval_store.list_approvals(
        space_id=space_id,
        run_id=result.claim_curation.run_id,
    )
    assert len(approvals) == 1

    child_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=result.claim_curation.run_id,
    )
    assert child_workspace is not None
    assert child_workspace.snapshot["status"] == "paused"
    assert child_workspace.snapshot["resume_point"] == "approval_gate"
    assert child_workspace.snapshot["pending_approvals"] == 1

    bootstrap_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=result.run.id,
    )
    assert bootstrap_workspace is not None
    assert bootstrap_workspace.snapshot["claim_curation_run_id"] == (
        result.claim_curation.run_id
    )
    assert bootstrap_workspace.snapshot["claim_curation"]["proposal_ids"] == [
        parent_records[0].id,
    ]


@pytest.mark.asyncio
async def test_execute_research_bootstrap_skips_claim_curation_without_orphan_child_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_runtime, claim_curation_workflow

    _stub_runtime_helpers(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_relation_conflicts",
        lambda **_kwargs: KernelRelationConflictListResponse(
            conflicts=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_claims_by_entity",
        lambda **_kwargs: KernelRelationClaimListResponse(
            claims=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )

    space_id = uuid4()
    parent_run_id = "research-init-parent"
    subject_id = str(uuid4())
    object_id = str(uuid4())
    proposal_store = HarnessProposalStore()
    promoted_record = proposal_store.create_proposals(
        space_id=space_id,
        run_id="already-promoted",
        proposals=(
            _curatable_candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH phenotype-a",
                source_key="pubmed:1",
                subject_id=subject_id,
                object_id=object_id,
            ),
        ),
    )[0]
    decided_promoted = proposal_store.decide_proposal(
        space_id=space_id,
        proposal_id=promoted_record.id,
        status="promoted",
        decision_reason="Already accepted",
    )
    assert decided_promoted is not None

    parent_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _curatable_candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH phenotype-a",
                source_key="pubmed:1",
                subject_id=subject_id,
                object_id=object_id,
            ),
        ),
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()
    approval_store = HarnessApprovalStore()

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=[],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        approval_store=approval_store,
        claim_curation_graph_api_gateway_factory=_StubGraphApiGateway,
        auto_queue_claim_curation=True,
        parent_run_id=parent_run_id,
    )

    assert len(result.proposal_records) == 1
    assert result.proposal_records[0].run_id == parent_run_id
    assert result.claim_curation is not None
    assert result.claim_curation.status == "skipped"
    assert result.claim_curation.run_id is None
    assert result.claim_curation.proposal_ids == (parent_records[0].id,)
    assert result.claim_curation.proposal_count == 1
    assert result.claim_curation.blocked_proposal_count == 1
    assert result.claim_curation.pending_approval_count == 0
    assert result.claim_curation.reason is not None
    assert (
        "No eligible proposals remain for claim curation"
        in result.claim_curation.reason
    )
    assert any(
        error.startswith("claim_curation:No eligible proposals remain")
        for error in result.errors
    )

    runs = run_registry.list_runs(space_id=space_id)
    assert len(runs) == 1
    assert runs[0].id == result.run.id
    assert all(run.harness_id != "claim-curation" for run in runs)

    bootstrap_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=result.run.id,
    )
    assert bootstrap_workspace is not None
    assert bootstrap_workspace.snapshot["claim_curation"]["status"] == "skipped"
    assert bootstrap_workspace.snapshot["claim_curation"]["proposal_ids"] == [
        parent_records[0].id,
    ]
    assert bootstrap_workspace.snapshot["claim_curation_run_id"] is None


@pytest.mark.asyncio
async def test_execute_research_bootstrap_cleans_orphan_claim_curation_run_after_init_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_runtime, claim_curation_workflow

    _stub_runtime_helpers(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_relation_conflicts",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "Tool 'list_relation_conflicts' ended with unknown outcome "
                "and requires reconciliation.",
            ),
        ),
    )

    space_id = uuid4()
    parent_run_id = "research-init-parent"
    subject_id = str(uuid4())
    object_id = str(uuid4())
    proposal_store = HarnessProposalStore()
    parent_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _curatable_candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH phenotype-a",
                source_key="pubmed:1",
                subject_id=subject_id,
                object_id=object_id,
            ),
        ),
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()
    approval_store = HarnessApprovalStore()

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=[],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        graph_connection_runner=_FallbackRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        approval_store=approval_store,
        claim_curation_graph_api_gateway_factory=_StubGraphApiGateway,
        auto_queue_claim_curation=True,
        parent_run_id=parent_run_id,
    )

    assert result.claim_curation is not None
    assert result.claim_curation.status == "failed"
    assert result.claim_curation.run_id is None
    assert result.claim_curation.proposal_ids == (parent_records[0].id,)
    assert result.claim_curation.reason is not None
    assert "requires reconciliation" in result.claim_curation.reason
    assert any(
        error.startswith("claim_curation:Failed to initialize claim curation:")
        for error in result.errors
    )

    runs = run_registry.list_runs(space_id=space_id)
    assert len(runs) == 1
    assert runs[0].id == result.run.id
    assert all(run.harness_id != "claim-curation" for run in runs)
    assert artifact_store.get_workspace(space_id=space_id, run_id=result.run.id) is not None


@pytest.mark.asyncio
async def test_execute_research_bootstrap_keeps_skipped_graph_suggestions_as_diagnostics_when_staged_proposals_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_runtime_helpers(monkeypatch)
    space_id = uuid4()
    parent_run_id = "research-init-parent"
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=parent_run_id,
        proposals=(
            _candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH DD/ID",
                source_key="pubmed:1",
            ),
        ),
    )

    result = await execute_research_bootstrap_run(
        space_id=space_id,
        title="Research Bootstrap Harness",
        objective="Investigate MED13 syndrome",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_hypotheses=5,
        model_id=None,
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        graph_api_gateway=_SkippedSuggestionGateway(),
        graph_connection_runner=_ExplodingRunner(),
        proposal_store=proposal_store,
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        runtime=object(),
        parent_run_id=parent_run_id,
    )

    assert result.errors == []
    assert len(result.proposal_records) == 1
    assert result.source_inventory["linked_proposal_count"] == 1
    assert result.source_inventory["bootstrap_generated_proposal_count"] == 0
    assert result.source_inventory["graph_connection_fallback_seed_ids"] == [
        "11111111-1111-1111-1111-111111111111",
    ]
