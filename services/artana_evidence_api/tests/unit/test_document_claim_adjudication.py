"""Regression tests for categorical document-claim adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDecision,
    ClaimAdjudicationDiagnostics,
    ClaimAdjudicationOutput,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.runtime import (
    with_claim_adjudication_diagnostics,
)
from artana_evidence_api.document_extraction_support.claim_adjudication.service import (
    adjudicate_document_claims,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft


@dataclass
class _Agent:
    output: ClaimAdjudicationOutput
    model_id: str = "test:categorical-reviewer"

    async def adjudicate(self, *, prompt: str) -> ClaimAdjudicationOutput:
        assert "Never return confidence" in prompt
        return self.output


@dataclass
class _BatchAgent:
    spans_by_ref: dict[str, str]
    relationship_target_by_ref: dict[str, str] | None = None
    model_id: str = "test:batched-categorical-reviewer"
    call_count: int = 0

    async def adjudicate(self, *, prompt: str) -> ClaimAdjudicationOutput:
        self.call_count += 1
        claim_refs = [
            line.removeprefix("Claim reference: ")
            for line in prompt.splitlines()
            if line.startswith("Claim reference: ")
        ]
        return ClaimAdjudicationOutput(
            decisions=[
                _decision(
                    claim_ref=claim_ref,
                    span=self.spans_by_ref[claim_ref],
                    relationship=(
                        "SAME_AS"
                        if self.relationship_target_by_ref
                        and claim_ref in self.relationship_target_by_ref
                        else "CANONICAL"
                    ),
                    target=(
                        self.relationship_target_by_ref.get(claim_ref)
                        if self.relationship_target_by_ref
                        else None
                    ),
                )
                for claim_ref in claim_refs
            ],
        )


def _document(text: str) -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id="document-1",
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Claim adjudication source",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="source-sha",
        byte_size=len(text.encode()),
        page_count=None,
        text_content=text,
        text_excerpt=text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="completed",
        metadata={},
        created_at=now,
        updated_at=now,
    )


def _draft(
    *,
    subject: str,
    relation: str,
    object_: str,
    sentence: str,
    review_status: str = "candidate",
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=f"document-1:{subject}:{relation}:{object_}",
        title=f"{subject} {relation} {object_}",
        summary=sentence,
        confidence=0.8,
        ranking_score=0.7,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject_label": subject,
            "proposed_claim_type": relation,
            "proposed_object_label": object_,
        },
        metadata={
            "subject_label": subject,
            "resolved_subject_label": subject,
            "object_label": object_,
            "resolved_object_label": object_,
            "review_status": review_status,
            "review_reason_codes": (
                ["semantic_inventory_incomplete"]
                if review_status == "review_only"
                else []
            ),
        },
    )


def _decision(
    *,
    claim_ref: str,
    span: str,
    atomicity: str = "ATOMIC",
    support: str = "ENTAILED",
    relationship: str = "CANONICAL",
    target: str | None = None,
) -> ClaimAdjudicationDecision:
    return ClaimAdjudicationDecision.model_validate(
        {
            "claim_ref": claim_ref,
            "atomicity": atomicity,
            "source_support": support,
            "relationship": relationship,
            "target_claim_ref": target,
            "evidence_spans": [span] if support == "ENTAILED" else [],
            "reasoning": "The exact source supports this categorical decision.",
            "falsification": "A source statement with the opposite relation would falsify it.",
        },
    )


@pytest.mark.asyncio
async def test_entailed_atomic_claim_gets_agent_support_without_numeric_judgment() -> (
    None
):
    sentence = "GATA3 represses FOXP3."
    draft = _draft(
        subject="GATA3",
        relation="INHIBITS",
        object_="FOXP3",
        sentence=sentence,
    )

    (updated,), diagnostics = await adjudicate_document_claims(
        document=_document(sentence),
        drafts=(draft,),
        agent=_Agent(
            ClaimAdjudicationOutput(
                decisions=[_decision(claim_ref="claim-0001", span=sentence)],
            ),
        ),
    )

    assert diagnostics.status == "completed"
    assert diagnostics.metrics == {
        "total_claims": 1,
        "atomic_claims": 1,
        "bundled_claims": 0,
        "atomicity_abstentions": 0,
        "entailed_claims": 1,
        "contradicted_claims": 0,
        "insufficient_claims": 0,
        "support_abstentions": 0,
        "canonical_claims": 1,
        "same_as_claims": 0,
        "refining_claims": 0,
        "generalizing_claims": 0,
        "claim_contradictions": 0,
        "relationship_abstentions": 0,
    }
    assert updated.metadata["review_status"] == "candidate"
    assert updated.metadata["support_verification"] == {
        "support": "ENTAILS",
        "rationale": "The exact source supports this categorical decision.",
        "model_id": "test:categorical-reviewer",
        "verification_method": "agent",
        "evidence_spans": [sentence],
        "falsification": "A source statement with the opposite relation would falsify it.",
    }
    adjudication = updated.metadata["claim_semantic_adjudication"]
    assert isinstance(adjudication, dict)
    assert "confidence" not in adjudication
    assert updated.confidence == draft.confidence


@pytest.mark.asyncio
async def test_incomplete_inventory_stays_review_only_after_positive_adjudication() -> (
    None
):
    sentence = "TGF-beta down-regulates CD25."
    draft = _draft(
        subject="TGF-beta",
        relation="INHIBITS",
        object_="CD25",
        sentence=sentence,
        review_status="review_only",
    )

    (updated,), _ = await adjudicate_document_claims(
        document=_document(sentence),
        drafts=(draft,),
        agent=_Agent(
            ClaimAdjudicationOutput(
                decisions=[_decision(claim_ref="claim-0001", span=sentence)],
            ),
        ),
    )

    assert updated.metadata["review_status"] == "review_only"
    assert updated.metadata["review_reason_codes"] == [
        "semantic_inventory_incomplete",
    ]


@pytest.mark.asyncio
async def test_same_claim_is_preserved_as_review_only_relation() -> None:
    first = "TGF-beta down-regulates CD25."
    second = "CD25 is suppressed by TGF-beta."
    drafts = (
        _draft(
            subject="TGF-beta",
            relation="INHIBITS",
            object_="CD25",
            sentence=first,
        ),
        _draft(
            subject="TGF-beta",
            relation="INHIBITS",
            object_="CD25",
            sentence=second,
        ),
    )
    output = ClaimAdjudicationOutput(
        decisions=[
            _decision(claim_ref="claim-0001", span=first),
            _decision(
                claim_ref="claim-0002",
                span=second,
                relationship="SAME_AS",
                target="claim-0001",
            ),
        ],
    )

    updated, _ = await adjudicate_document_claims(
        document=_document(f"{first} {second}"),
        drafts=drafts,
        agent=_Agent(output),
    )

    assert updated[0].metadata["review_status"] == "candidate"
    assert updated[1].metadata["review_status"] == "review_only"
    assert "claim_relationship_same_as" in updated[1].metadata["review_reason_codes"]
    assert (
        updated[1].metadata["claim_semantic_adjudication"]["target_claim_ref"]
        == "claim-0001"
    )
    assert updated[1].metadata["claim_relation_proposal"] == {
        "relation_type": "SAME_AS",
        "target_source_key": drafts[0].source_key,
        "target_claim_fingerprint": None,
        "evidence_summary": "The exact source supports this categorical decision.",
        "review_status": "PROPOSED",
    }


@pytest.mark.asyncio
async def test_bundled_or_unverified_claims_fail_closed_deterministically() -> None:
    sentence = "IL-4 inhibits FOXP3 without interfering with TGF-beta signaling."
    draft = _draft(
        subject="IL-4",
        relation="INHIBITS",
        object_="FOXP3",
        sentence=sentence,
    )
    output = ClaimAdjudicationOutput(
        decisions=[
            _decision(
                claim_ref="claim-0001",
                span=sentence,
                atomicity="BUNDLED",
                support="INSUFFICIENT",
                relationship="ABSTAIN",
            ),
        ],
    )

    (updated,), _ = await adjudicate_document_claims(
        document=_document(sentence),
        drafts=(draft,),
        agent=_Agent(output),
    )

    assert updated.metadata["review_status"] == "review_only"
    assert "claim_atomicity_bundled" in updated.metadata["review_reason_codes"]
    assert updated.metadata["support_verification"]["support"] == "NEUTRAL"
    assert updated.confidence == 0.25
    assert updated.ranking_score == 0.25


@pytest.mark.asyncio
async def test_invalid_agent_coverage_marks_every_claim_review_only() -> None:
    sentence = "GATA3 represses FOXP3."
    draft = _draft(
        subject="GATA3",
        relation="INHIBITS",
        object_="FOXP3",
        sentence=sentence,
    )

    (updated,), diagnostics = await adjudicate_document_claims(
        document=_document(sentence),
        drafts=(draft,),
        agent=_Agent(ClaimAdjudicationOutput(decisions=[])),
    )

    assert diagnostics.status == "unavailable"
    assert updated.metadata["review_status"] == "review_only"
    assert "claim_adjudication_unavailable" in updated.metadata["review_reason_codes"]
    assert updated.metadata["support_verification"]["verification_method"] == (
        "unavailable"
    )


@pytest.mark.asyncio
async def test_unknown_relationship_target_fails_closed() -> None:
    sentence = "GATA3 represses FOXP3."
    draft = _draft(
        subject="GATA3",
        relation="INHIBITS",
        object_="FOXP3",
        sentence=sentence,
    )
    decision = _decision(
        claim_ref="claim-0001",
        span=sentence,
        relationship="SAME_AS",
        target="claim-9999",
    )

    (updated,), diagnostics = await adjudicate_document_claims(
        document=_document(sentence),
        drafts=(draft,),
        agent=_Agent(ClaimAdjudicationOutput(decisions=[decision])),
    )

    assert diagnostics.status == "unavailable"
    assert diagnostics.error == "claim relationship target is not in this document"
    assert updated.metadata["review_status"] == "review_only"
    assert "claim_adjudication_unavailable" in updated.metadata["review_reason_codes"]


@pytest.mark.asyncio
async def test_evidence_from_another_claim_cannot_entail_this_claim() -> None:
    first = "GATA3 represses FOXP3."
    second = "IL-4 activates STAT6."
    drafts = (
        _draft(
            subject="GATA3",
            relation="INHIBITS",
            object_="FOXP3",
            sentence=first,
        ),
        _draft(
            subject="IL-4",
            relation="ACTIVATES",
            object_="STAT6",
            sentence=second,
        ),
    )
    output = ClaimAdjudicationOutput(
        decisions=[
            _decision(claim_ref="claim-0001", span=second),
            _decision(claim_ref="claim-0002", span=second),
        ],
    )

    updated, diagnostics = await adjudicate_document_claims(
        document=_document(f"{first} {second}"),
        drafts=drafts,
        agent=_Agent(output),
    )

    assert diagnostics.status == "unavailable"
    assert diagnostics.error == (
        "claim evidence span is outside the adjudicated claim excerpt"
    )
    assert all(draft.metadata["review_status"] == "review_only" for draft in updated)


def test_research_init_draft_preserves_adjudication_diagnostics() -> None:
    draft = _draft(
        subject="GATA3",
        relation="INHIBITS",
        object_="FOXP3",
        sentence="GATA3 represses FOXP3.",
    )

    (updated,) = with_claim_adjudication_diagnostics(
        drafts=(draft,),
        diagnostics=ClaimAdjudicationDiagnostics(
            status="unavailable",
            model_id="openai:gpt-5.6-luna",
            error="provider timeout",
        ),
    )

    assert updated.metadata["claim_adjudication_diagnostics"] == {
        "status": "unavailable",
        "decision_count": 0,
        "model_id": "openai:gpt-5.6-luna",
        "error": "provider timeout",
    }


@pytest.mark.asyncio
async def test_adjudication_batches_large_candidate_sets_in_source_order() -> None:
    sentences = tuple(f"GENE{i} activates TARGET{i}." for i in range(13))
    drafts = tuple(
        _draft(
            subject=f"GENE{index}",
            relation="ACTIVATES",
            object_=f"TARGET{index}",
            sentence=sentence,
        )
        for index, sentence in enumerate(sentences)
    )
    agent = _BatchAgent(
        spans_by_ref={
            f"claim-{index:04d}": sentence
            for index, sentence in enumerate(sentences, start=1)
        },
    )

    updated, diagnostics = await adjudicate_document_claims(
        document=_document(" ".join(sentences)),
        drafts=drafts,
        agent=agent,
    )

    assert agent.call_count == 2
    assert diagnostics.status == "completed"
    assert diagnostics.decision_count == 13
    assert all("claim_semantic_adjudication" in draft.metadata for draft in updated)


@pytest.mark.asyncio
async def test_batch_cannot_target_prior_claim_outside_visible_context() -> None:
    sentences = tuple(f"GENE{i} activates TARGET{i}." for i in range(37))
    drafts = tuple(
        _draft(
            subject=f"GENE{index}",
            relation="ACTIVATES",
            object_=f"TARGET{index}",
            sentence=sentence,
        )
        for index, sentence in enumerate(sentences)
    )
    agent = _BatchAgent(
        spans_by_ref={
            f"claim-{index:04d}": sentence
            for index, sentence in enumerate(sentences, start=1)
        },
        relationship_target_by_ref={"claim-0037": "claim-0001"},
    )

    updated, diagnostics = await adjudicate_document_claims(
        document=_document(" ".join(sentences)),
        drafts=drafts,
        agent=agent,
    )

    assert diagnostics.status == "unavailable"
    assert diagnostics.error == (
        "claim relationship target is outside the adjudication context"
    )
    assert all(draft.metadata["review_status"] == "review_only" for draft in updated)
