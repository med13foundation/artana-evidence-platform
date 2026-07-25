"""Trust-ladder floors, including the ones that hold only by construction.

This module derives the tier gating trusted-evidence eligibility and had no
tests at all.  Two of its safety properties are load-bearing and currently true
only because of how the code happens to be written, so they are pinned here
rather than left to be rediscovered by an incident:

* the ladder can never return `trusted`, so `trusted_evidence_eligible` is
  always False; and
* claim-verification metadata is subtractive -- supplying it can lower a tier,
  never raise one.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from artana_evidence_api.document_extraction_support.trust_ladder import (
    CandidateTrustFloorFailure,
    assess_candidate_trust,
    candidate_trust_ladder_metadata,
)

_LINKED_ENDPOINTS = {
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
_CLEAN_PAYLOAD: Mapping[str, object] = {"proposed_claim_type": "ASSOCIATED_WITH"}


def _clean_metadata(**overrides: object) -> dict[str, object]:
    """Metadata that clears every floor, so a test can break exactly one."""

    metadata: dict[str, object] = {
        "agent_extraction_completed": True,
        "fallback_output_used": False,
        "evidence_grounding": {
            "grounded": True,
            "subject_present": True,
            "object_present": True,
        },
        "support_verification": {
            "support": "ENTAILS",
            "verification_method": "agent",
        },
        "entity_linking": _LINKED_ENDPOINTS,
    }
    metadata.update(overrides)
    return metadata


def _assess(metadata: Mapping[str, object]):  # noqa: ANN202 - internal dataclass
    return assess_candidate_trust(metadata=metadata, payload=_CLEAN_PAYLOAD)


def test_clean_candidate_reaches_verified_evidence() -> None:
    assessment = _assess(_clean_metadata())

    assert assessment.hard_floor_failures == ()
    assert assessment.tier == "verified_evidence"


def test_the_ladder_can_never_return_trusted() -> None:
    """`trusted_evidence_eligible` is False by construction -- pin it.

    `trusted_evidence_eligible` is `tier == "trusted"`, and no branch returns
    that value.  The DB-side floor reads the flag, so a future edit adding a
    `trusted` branch would quietly open the trusted lane.  This is the test
    that fails first if that happens.
    """

    source = "services/artana_evidence_api/document_extraction_support/trust_ladder.py"
    with open(source, encoding="utf-8") as handle:  # noqa: PTH123
        body = handle.read()

    assert 'return "trusted"' not in body, (
        "the trust ladder must not be able to award the trusted tier; "
        "opening it requires a server-owned support receipt (D6)"
    )
    assert _assess(_clean_metadata()).trusted_evidence_eligible is False


@pytest.mark.parametrize(
    ("override", "expected_failure", "expected_tier"),
    [
        (
            {"agent_extraction_completed": False},
            "agent_extraction_completed",
            "triage_only",
        ),
        ({"fallback_output_used": True}, "no_fallback_output", "triage_only"),
        ({"review_status": "review_only"}, "review_only_candidate", "agent_candidate"),
        (
            {"evidence_grounding": {"grounded": False}},
            "grounded_evidence_sentence",
            "agent_candidate",
        ),
        (
            {"support_verification": {"support": "NEUTRAL"}},
            "support_entails_claim",
            "agent_candidate",
        ),
    ],
)
def test_each_floor_demotes(
    override: dict[str, object],
    expected_failure: CandidateTrustFloorFailure,
    expected_tier: str,
) -> None:
    assessment = _assess(_clean_metadata(**override))

    assert expected_failure in assessment.hard_floor_failures
    assert assessment.tier == expected_tier


def test_entity_linking_failures_are_recorded_but_do_not_demote() -> None:
    """Observed behaviour, pinned because it is surprising.

    `curie_linked_subject` and `curie_linked_object` are absent from the
    `evidence_failures` set in `_trust_tier_for_failures`, so an unlinked
    candidate still reaches `verified_evidence` while carrying both failures.

    That may be deliberate -- grounding quality and identifier resolution are
    different concerns -- but nothing recorded the intent, and a floor that is
    reported without affecting the tier reads as enforcement when it is not.
    This test states the current contract so a change to it has to be a
    decision rather than an accident.
    """

    assessment = _assess(_clean_metadata(entity_linking={}))

    assert "curie_linked_subject" in assessment.hard_floor_failures
    assert "curie_linked_object" in assessment.hard_floor_failures
    assert assessment.tier == "verified_evidence"
    assert assessment.trusted_evidence_eligible is False


def test_caller_supplied_support_alone_does_not_earn_a_tier() -> None:
    """Asserting support must not substitute for grounding or linking."""

    assessment = _assess(
        {
            "agent_extraction_completed": True,
            "fallback_output_used": False,
            "support_verification": {
                "support": "ENTAILS",
                "verification_method": "agent",
            },
        },
    )

    assert assessment.tier == "agent_candidate"
    assert assessment.trusted_evidence_eligible is False


class TestClaimVerificationExpectation:
    """Absence must never score better than a partial attempt (invariant 8)."""

    def test_partial_verification_metadata_demotes(self) -> None:
        assessment = _assess(
            _clean_metadata(
                claim_verification={"initial_verification": {"verdict": "ENTAILED"}},
                claim_verification_lineage_status="missing_or_ambiguous",
                claim_verification_qualification_complete=False,
            ),
        )

        assert "invalid_claim_verification_lineage" in assessment.hard_floor_failures
        assert "scientific_qualification_incomplete" in assessment.hard_floor_failures
        assert assessment.tier == "agent_candidate"

    def test_absence_is_not_better_than_a_partial_attempt(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The inverted incentive this ticket exists to remove.

        With the loop running, a candidate carrying no verification metadata
        must not outrank one that attempted verification and fell short.
        """

        monkeypatch.setenv("ARTANA_CLAIM_VERIFICATION_EXPERIMENT", "true")

        absent = _assess(_clean_metadata())
        partial = _assess(
            _clean_metadata(
                claim_verification={},
                claim_verification_qualification_complete=False,
            ),
        )

        assert "missing_claim_verification" in absent.hard_floor_failures
        assert absent.tier == "agent_candidate"
        assert absent.tier == partial.tier

    def test_absence_is_tolerated_while_the_loop_is_dark(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pre-existing candidates must not all demote before the loop runs."""

        monkeypatch.delenv("ARTANA_CLAIM_VERIFICATION_EXPERIMENT", raising=False)

        assessment = _assess(_clean_metadata())

        assert assessment.hard_floor_failures == ()
        assert assessment.tier == "verified_evidence"

    def test_verification_metadata_is_subtractive_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Model self-verification may lower a tier, never raise one.

        #181 merged a loop that derives support from the model's own judgement,
        which conflicts with D6.  Containment holds because this floor can only
        add failures -- pin that, so an additive branch cannot be introduced
        without a test failing.
        """

        monkeypatch.delenv("ARTANA_CLAIM_VERIFICATION_EXPERIMENT", raising=False)
        weak = _clean_metadata(evidence_grounding={"grounded": False})

        without_verification = _assess(weak)
        with_perfect_verification = _assess(
            {
                **weak,
                "claim_verification": {"initial_verification": {"verdict": "ENTAILED"}},
                "claim_verification_lineage_status": "bound",
                "claim_verification_qualification_complete": True,
            },
        )

        assert with_perfect_verification.tier == without_verification.tier
        assert len(with_perfect_verification.hard_floor_failures) >= len(
            without_verification.hard_floor_failures,
        )


def test_metadata_projection_exposes_the_verifier_owned_fields() -> None:
    metadata = candidate_trust_ladder_metadata(
        metadata=_clean_metadata(),
        payload=_CLEAN_PAYLOAD,
    )

    assert metadata == {
        "trusted_evidence_eligible": False,
        "trust_tier": "verified_evidence",
        "trust_floor_failures": [],
    }
