"""Unit tests for AI-authored relation claim evidence validation."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from artana_evidence_db.validation.claim_ai_evidence_validation import (
    validate_ai_claim_evidence,
)

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The source sentence directly supports the claim.",
}
_AI_PROVENANCE = {
    "model_id": "artana-kernel",
    "model_version": "test",
    "prompt_id": "graph-validation-ai-claim",
    "prompt_version": "v1",
    "input_hash": "input-hash",
    "rationale": "The sentence supports the relation.",
    "evidence_references": ["pmid:123456"],
}
_VALID_GROUNDING = {
    "anchor_start": 0,
    "anchor_end": 47,
    "match_kind": "exact",
    "score": 1.0,
    "subject_present": True,
    "object_present": True,
    "grounded": True,
}
_VALID_SUPPORT_VERIFICATION = {
    "support": "ENTAILS",
    "rationale": "Sentence contains both endpoints in the correct relation.",
    "model_id": "artana-heuristic-support-v1",
}
_VALID_ENTITY_LINKING = {
    "subject": {
        "status": "linked",
        "curie": "HGNC:22474",
        "source": "verified_linker",
        "trusted_identifier": True,
    },
    "object": {
        "status": "linked",
        "curie": "HP:0001263",
        "source": "verified_linker",
        "trusted_identifier": True,
    },
}


def test_ai_claim_requires_provenance_envelope() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            evidence_sentence_source="artana_generated",
            metadata={"origin": "graph_harness"},
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "missing_ai_provenance"
    assert issue.message == "AI-authored claims require ai_provenance audit metadata."


def test_non_ai_claim_does_not_require_structured_grounding() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            evidence_sentence_source="pubmed",
            source_document_ref="pmid:123456",
        ),
        requires_evidence=True,
    )

    assert issue is None


def test_ai_claim_requires_structured_grounding_when_relation_requires_evidence() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "evidence_grounding": {
                    **_VALID_GROUNDING,
                    "object_present": False,
                    "grounded": False,
                },
            },
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "AI-authored claims require structured evidence grounding with "
        "subject and object present."
    )
    assert len(issue.next_actions) == 1
    assert issue.next_actions[0].action == "attach_grounded_evidence"


def test_ai_claim_with_provenance_and_grounding_passes() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": _VALID_SUPPORT_VERIFICATION,
            },
        ),
        requires_evidence=True,
    )

    assert issue is None


def test_ai_claim_requires_entailing_support_verification() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": {
                    **_VALID_SUPPORT_VERIFICATION,
                    "support": "NEUTRAL",
                },
            },
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "AI-authored claims require support verification with support=ENTAILS."
    )
    assert len(issue.next_actions) == 1
    assert issue.next_actions[0].action == "attach_support_verification"


def test_ai_claim_rejects_claimed_trusted_tier_without_linked_entities() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "agent_extraction_completed": True,
                "fallback_output_used": False,
                "trusted_evidence_eligible": True,
                "trust_tier": "trusted",
                "trust_floor_failures": [],
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": _VALID_SUPPORT_VERIFICATION,
                "entity_linking": {
                    "subject": {"status": "abstained", "reason": "missing_curie"},
                    "object": {"status": "linked", "curie": "HP:0001263"},
                },
            },
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "Trusted AI evidence requires linked subject and object entity "
        "identifiers."
    )
    assert len(issue.next_actions) == 1
    assert issue.next_actions[0].action == "attach_entity_links"


def test_ai_claim_rejects_claimed_trusted_tier_from_fallback_output() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "agent_extraction_completed": False,
                "fallback_output_used": True,
                "trusted_evidence_eligible": True,
                "trust_tier": "trusted",
                "trust_floor_failures": [],
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": _VALID_SUPPORT_VERIFICATION,
                "entity_linking": _VALID_ENTITY_LINKING,
                "trust_floor_overrides": {"require_entity_links": False},
            },
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "Trusted AI evidence requires completed agent extraction without "
        "fallback output."
    )


@pytest.mark.parametrize(
    ("metadata_override", "expected_message", "expected_action"),
    [
        (
            {"agent_extraction_completed": False},
            (
                "Trusted AI evidence requires completed agent extraction without "
                "fallback output."
            ),
            "run_agent_extraction",
        ),
        (
            {"fallback_output_used": True},
            (
                "Trusted AI evidence requires completed agent extraction without "
                "fallback output."
            ),
            "run_agent_extraction",
        ),
        (
            {"review_status": "review_only"},
            "Trusted AI evidence cannot use review-only relation evidence.",
            "route_to_human_review",
        ),
        (
            {"review_reason_codes": ["hedged_language", "may_link"]},
            "Trusted AI evidence cannot use weak or hedged review reason codes.",
            "route_to_human_review",
        ),
        (
            {
                "entity_linking": {
                    "subject": {"status": "abstained", "curie": "HGNC:22474"},
                    "object": {
                        "status": "linked",
                        "curie": "HP:0001263",
                        "source": "verified_linker",
                    },
                },
            },
            (
                "Trusted AI evidence requires linked subject and object entity "
                "identifiers."
            ),
            "attach_entity_links",
        ),
        (
            {
                "entity_linking": {
                    "subject": {
                        "status": "linked",
                        "curie": "HGNC:22474",
                        "source": "verified_linker",
                    },
                    "object": {"status": "model_suggested", "curie": "HP:0001263"},
                },
            },
            (
                "Trusted AI evidence requires linked subject and object entity "
                "identifiers."
            ),
            "attach_entity_links",
        ),
        (
            {
                "entity_linking": {
                    "subject": {"status": "linked", "curie": "HGNC:22474"},
                    "object": {
                        "status": "linked",
                        "curie": "HP:0001263",
                        "source": "verified_linker",
                    },
                },
            },
            (
                "Trusted AI evidence requires linked subject and object entity "
                "identifiers."
            ),
            "attach_entity_links",
        ),
        (
            {
                "entity_linking": {
                    "subject": {
                        "status": "linked",
                        "curie": "HGNC:22474",
                        "source": "model",
                    },
                    "object": {
                        "status": "linked",
                        "curie": "HP:0001263",
                        "source": "verified_linker",
                    },
                },
            },
            (
                "Trusted AI evidence requires linked subject and object entity "
                "identifiers."
            ),
            "attach_entity_links",
        ),
        (
            {"support_verification": {**_VALID_SUPPORT_VERIFICATION, "support": "NEUTRAL"}},
            "AI-authored claims require support verification with support=ENTAILS.",
            "attach_support_verification",
        ),
        (
            {"trust_floor_failures": ["review_only_candidate"]},
            "Trusted AI evidence cannot carry failed trust floors.",
            "recompute_trust_tier",
        ),
        (
            {"trust_floor_failures": {"0": "review_only_candidate"}},
            "Trusted AI evidence cannot carry failed trust floors.",
            "recompute_trust_tier",
        ),
        (
            {"trust_floor_failures": [{"code": "review_only_candidate"}]},
            "Trusted AI evidence cannot carry failed trust floors.",
            "recompute_trust_tier",
        ),
        (
            {"review_reason_codes": {"0": "hedged_language"}},
            "Trusted AI evidence cannot use weak or hedged review reason codes.",
            "route_to_human_review",
        ),
        (
            {"review_reason_codes": [{"code": "hedged_language"}]},
            "Trusted AI evidence cannot use weak or hedged review reason codes.",
            "route_to_human_review",
        ),
        (
            {"review_reason_codes": [1]},
            "Trusted AI evidence cannot use weak or hedged review reason codes.",
            "route_to_human_review",
        ),
    ],
)
def test_ai_claim_rejects_every_unsafe_trusted_promotion_floor(
    metadata_override: dict[str, object],
    expected_message: str,
    expected_action: str,
) -> None:
    metadata = _trusted_ai_metadata()
    metadata.update(metadata_override)

    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata=metadata,
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == expected_message
    assert len(issue.next_actions) == 1
    assert issue.next_actions[0].action == expected_action


def test_ai_claim_accepts_claimed_trusted_tier_when_hard_floors_pass() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                "origin": "graph_harness",
                "agent_extraction_completed": True,
                "fallback_output_used": False,
                "trusted_evidence_eligible": True,
                "trust_tier": "trusted",
                "trust_floor_failures": [],
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": _VALID_SUPPORT_VERIFICATION,
                "entity_linking": _VALID_ENTITY_LINKING,
            },
        ),
        requires_evidence=True,
    )

    assert issue is None


def test_ai_claim_accepts_claimed_trusted_tier_with_empty_review_reason_codes() -> None:
    issue = validate_ai_claim_evidence(
        _claim_request(
            agent_run_id="ai-run-1",
            ai_provenance=_AI_PROVENANCE,
            evidence_sentence_source="artana_generated",
            metadata={
                **_trusted_ai_metadata(),
                "review_status": "candidate",
                "review_reason_codes": [],
            },
        ),
        requires_evidence=True,
    )

    assert issue is None


def test_ai_relation_create_requires_structured_grounding() -> None:
    issue = validate_ai_claim_evidence(
        KernelRelationCreateRequest(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            assessment=_SUPPORTED_ASSESSMENT,
            evidence_sentence="MED13 was associated with developmental delay.",
            evidence_sentence_source="artana_generated",
            source_document_ref="harness_proposal:proposal-1",
            metadata={"origin": "graph_harness"},
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "AI-authored claims require structured evidence grounding with "
        "subject and object present."
    )


def test_ai_relation_create_with_structured_grounding_passes() -> None:
    issue = validate_ai_claim_evidence(
        KernelRelationCreateRequest(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            assessment=_SUPPORTED_ASSESSMENT,
            evidence_sentence="MED13 was associated with developmental delay.",
            evidence_sentence_source="artana_generated",
            source_document_ref="harness_proposal:proposal-1",
            metadata={
                "origin": "graph_harness",
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": _VALID_SUPPORT_VERIFICATION,
            },
        ),
        requires_evidence=True,
    )

    assert issue is None


def test_ai_relation_create_requires_entailing_support_verification() -> None:
    issue = validate_ai_claim_evidence(
        KernelRelationCreateRequest(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            assessment=_SUPPORTED_ASSESSMENT,
            evidence_sentence="MED13 was associated with developmental delay.",
            evidence_sentence_source="artana_generated",
            source_document_ref="harness_proposal:proposal-1",
            metadata={
                "origin": "graph_harness",
                "evidence_grounding": _VALID_GROUNDING,
                "support_verification": {
                    **_VALID_SUPPORT_VERIFICATION,
                    "support": "CONTRADICTS",
                },
            },
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "AI-authored claims require support verification with support=ENTAILS."
    )


def test_ai_relation_create_rejects_review_lane_metadata_for_trusted_tier() -> None:
    metadata = _trusted_ai_metadata()
    metadata.update(
        {
            "trusted_evidence_eligible": False,
            "trust_tier": "agent_candidate",
            "review_status": "review_only",
        },
    )

    issue = validate_ai_claim_evidence(
        KernelRelationCreateRequest(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            assessment=_SUPPORTED_ASSESSMENT,
            evidence_sentence="MED13 was associated with developmental delay.",
            evidence_sentence_source="artana_generated",
            source_document_ref="harness_proposal:proposal-1",
            evidence_tier="trusted",
            metadata=metadata,
        ),
        requires_evidence=True,
    )

    assert issue is not None
    assert issue.code == "insufficient_evidence"
    assert issue.message == (
        "Trusted AI evidence cannot use review-only relation evidence."
    )
    assert len(issue.next_actions) == 1
    assert issue.next_actions[0].action == "route_to_human_review"


def _claim_request(**overrides: object) -> KernelRelationClaimCreateRequest:
    payload: dict[str, object] = {
        "source_entity_id": uuid4(),
        "target_entity_id": uuid4(),
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _SUPPORTED_ASSESSMENT,
        "claim_text": "MED13 is associated with developmental delay.",
        "evidence_sentence": "MED13 was associated with developmental delay.",
        "source_document_ref": "pmid:123456",
        "metadata": {},
    }
    payload.update(overrides)
    return KernelRelationClaimCreateRequest.model_validate(payload)


def _trusted_ai_metadata() -> dict[str, object]:
    return {
        "origin": "graph_harness",
        "agent_extraction_completed": True,
        "fallback_output_used": False,
        "trusted_evidence_eligible": True,
        "trust_tier": "trusted",
        "trust_floor_failures": [],
        "evidence_grounding": _VALID_GROUNDING,
        "support_verification": _VALID_SUPPORT_VERIFICATION,
        "entity_linking": _VALID_ENTITY_LINKING,
    }
