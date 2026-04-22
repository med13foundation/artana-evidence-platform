"""Regression tests for bootstrap structured proposal governance."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from artana_evidence_api.bootstrap_proposal_review import (
    review_bootstrap_enrichment_proposals,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_init_runtime import (
    _store_reviewed_enrichment_proposals,
)


def _draft(
    *,
    source_kind: str,
    relation_type: str = "ASSOCIATED_WITH",
    clinical_significance: str | None = None,
) -> HarnessProposalDraft:
    payload = {
        "proposed_subject_label": "BRCA1",
        "proposed_claim_type": relation_type,
        "proposed_object_label": "breast cancer",
    }
    metadata = {
        "source": source_kind,
        "bootstrap_claim_path": "structured_source_bootstrap_draft",
        "claim_generation_mode": "deterministic_structured_draft_unreviewed",
        "requires_qualitative_review": True,
        "direct_graph_promotion_allowed": False,
    }
    if clinical_significance is not None:
        payload["clinical_significance"] = clinical_significance
        metadata["clinical_significance"] = clinical_significance
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind=source_kind,
        source_key=f"{source_kind}:brca1",
        title=f"{source_kind}: BRCA1 {relation_type} breast cancer",
        summary=f"BRCA1 {relation_type} breast cancer.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={"source": source_kind},
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"{source_kind}:brca1",
                "excerpt": "Structured source record for BRCA1 breast cancer.",
                "relevance": 0.5,
            },
        ],
        payload=payload,
        metadata=metadata,
    )


def test_bootstrap_review_derives_confidence_from_qualitative_assessment() -> None:
    reviewed = review_bootstrap_enrichment_proposals(
        [
            _draft(
                source_kind="clinvar_enrichment",
                relation_type="CAUSES",
                clinical_significance="Pathogenic",
            ),
        ],
        objective="BRCA1 breast cancer pathogenic variants",
    )

    proposal = reviewed[0]
    proposal_review = proposal.metadata["proposal_review"]
    assert isinstance(proposal_review, dict)
    assert proposal_review["method"] == "bootstrap_structured_review_v1"
    assert proposal_review["factual_support"] == "strong"
    assert proposal.confidence == pytest.approx(0.92)
    assert proposal.ranking_score > 0.5
    assert proposal.metadata["direct_graph_promotion_allowed"] is False
    assert proposal.metadata["bootstrap_claim_path"] == (
        "structured_source_bootstrap_reviewed"
    )


def test_clinical_trial_treats_draft_is_tentative_until_reviewed() -> None:
    reviewed = review_bootstrap_enrichment_proposals(
        [
            _draft(
                source_kind="clinicaltrials_enrichment",
                relation_type="TREATS",
            ),
        ],
        objective="BRCA1 breast cancer treatment options",
    )

    proposal = reviewed[0]
    proposal_review = proposal.metadata["proposal_review"]
    assert isinstance(proposal_review, dict)
    assert proposal_review["factual_support"] == "tentative"
    assert proposal.confidence == pytest.approx(0.46)
    assert "does not prove therapeutic effect" in str(
        proposal_review["factual_rationale"],
    )


def test_marrvel_draft_uses_named_qualitative_review_before_score() -> None:
    reviewed = review_bootstrap_enrichment_proposals(
        [
            _draft(
                source_kind="marrvel_omim",
                relation_type="ASSOCIATED_WITH",
            ),
        ],
        objective="BRCA1 breast cancer phenotype associations",
    )

    proposal = reviewed[0]
    proposal_review = proposal.metadata["proposal_review"]
    assert isinstance(proposal_review, dict)
    assert proposal_review["factual_support"] == "moderate"
    assert proposal.confidence == pytest.approx(0.72)
    assert proposal.metadata["claim_generation_mode"] == (
        "deterministic_structured_draft_reviewed"
    )


def test_research_init_stores_reviewed_bootstrap_drafts_without_graph_write() -> None:
    store = HarnessProposalStore()
    space_id = uuid4()
    run_id = uuid4()

    created_count = _store_reviewed_enrichment_proposals(
        proposal_store=store,
        proposals=[
            _draft(
                source_kind="clinicaltrials_enrichment",
                relation_type="TREATS",
            ),
        ],
        space_id=space_id,
        run_id=run_id,
        objective="BRCA1 breast cancer treatment options",
    )

    stored = store.list_proposals(space_id=space_id)
    assert created_count == 1
    assert len(stored) == 1
    assert stored[0].status == "pending_review"
    assert stored[0].metadata["direct_graph_promotion_allowed"] is False
    assert "proposal_review" in stored[0].metadata


def test_research_init_runtime_has_no_direct_enrichment_promotion_helper() -> None:
    runtime_source = Path(
        "services/artana_evidence_api/research_init_runtime.py",
    ).read_text()

    assert "_promote_enrichment_proposals_to_graph" not in runtime_source
    assert "harness_enrichment:" not in runtime_source
