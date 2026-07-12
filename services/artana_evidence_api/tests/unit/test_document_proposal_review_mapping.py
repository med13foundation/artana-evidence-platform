"""Tests for fail-closed proposal-review reference mapping."""

from __future__ import annotations

from typing import cast

import pytest
from artana_evidence_api.document_extraction_contracts import ProposalReviewResultLike
from artana_evidence_api.document_extraction_prompting import (
    build_proposal_review_output_schema,
)
from artana_evidence_api.document_extraction_support.review_policy.proposal_review_mapping import (
    build_proposal_review_draft_refs,
    map_proposal_reviews_by_ref,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft
from pydantic import ValidationError

_FIRST_REF = "draft_111111111111111111111111"
_SECOND_REF = "draft_222222222222222222222222"


def _draft(*, summary: str) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="relation",
        source_kind="text",
        source_key="document:claim",
        title="MED13 activates EGFR",
        summary=summary,
        confidence=0.8,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "ACTIVATES"},
        metadata={},
    )


def _result(*references: str) -> ProposalReviewResultLike:
    schema = build_proposal_review_output_schema()
    result = schema.model_validate(
        {
            "reviews": [
                {
                    "draft_ref": reference,
                    "factual_support": "moderate",
                    "goal_relevance": "direct",
                    "priority": "review",
                    "rationale": f"Review for {reference}.",
                    "factual_rationale": "The excerpt supports the claim.",
                    "relevance_rationale": "The claim addresses the objective.",
                }
                for reference in references
            ],
        },
    )
    return cast("ProposalReviewResultLike", result)


def test_review_mapping_accepts_permuted_exact_references() -> None:
    reviews = map_proposal_reviews_by_ref(
        result=_result(_SECOND_REF, _FIRST_REF),
        expected_refs=(_FIRST_REF, _SECOND_REF),
        model_id="openai:gpt-test",
    )

    assert tuple(reviews) == (_SECOND_REF, _FIRST_REF)
    assert reviews[_FIRST_REF].rationale == f"Review for {_FIRST_REF}."
    assert reviews[_SECOND_REF].rationale == f"Review for {_SECOND_REF}."


def test_draft_reference_is_bound_to_draft_content() -> None:
    first = build_proposal_review_draft_refs(
        document_sha256="document-hash",
        drafts=(_draft(summary="MED13 activates EGFR."),),
    )
    changed = build_proposal_review_draft_refs(
        document_sha256="document-hash",
        drafts=(_draft(summary="MED13 inhibits EGFR."),),
    )

    assert first != changed


def test_review_schema_rejects_whitespace_only_rationale() -> None:
    schema = build_proposal_review_output_schema()

    with pytest.raises(ValidationError, match="rationale"):
        schema.model_validate(
            {
                "reviews": [
                    {
                        "draft_ref": _FIRST_REF,
                        "factual_support": "moderate",
                        "goal_relevance": "direct",
                        "priority": "review",
                        "rationale": "   ",
                        "factual_rationale": "The excerpt supports the claim.",
                        "relevance_rationale": "The claim addresses the objective.",
                    },
                ],
            },
        )


@pytest.mark.parametrize(
    ("returned_refs", "message"),
    [
        ((_FIRST_REF,), "cover every draft"),
        ((_FIRST_REF, _FIRST_REF), "duplicate"),
        (
            (_FIRST_REF, "draft_333333333333333333333333"),
            "missing or unknown",
        ),
    ],
)
def test_review_mapping_rejects_non_exact_coverage(
    returned_refs: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        map_proposal_reviews_by_ref(
            result=_result(*returned_refs),
            expected_refs=(_FIRST_REF, _SECOND_REF),
            model_id="openai:gpt-test",
        )
