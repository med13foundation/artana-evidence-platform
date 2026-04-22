"""Unit tests for fuzzy near-duplicate claim detection."""

from __future__ import annotations

from artana_evidence_api.fuzzy_claim_matcher import find_near_duplicates


def _claim(
    source: str,
    relation: str,
    target: str,
    *,
    claim_id: str = "claim-1",
    status: str = "OPEN",
    claim_text: str | None = None,
) -> dict[str, object]:
    return {
        "id": claim_id,
        "claim_status": status,
        "source_label": source,
        "target_label": target,
        "relation_type": relation,
        "claim_text": claim_text or f"{source} {relation} {target}",
    }


class TestExactMatchExcluded:
    """Exact duplicates should NOT be returned — fingerprint dedup handles them."""

    def test_exact_match_not_returned(self) -> None:
        claims = [_claim("MED13", "ASSOCIATED_WITH", "intellectual disability")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        assert len(result) == 0

    def test_exact_match_case_insensitive_not_returned(self) -> None:
        claims = [_claim("med13", "associated_with", "Intellectual Disability")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        assert len(result) == 0


class TestTypoCaught:
    """Typos in entity labels should be caught as near-duplicates."""

    def test_single_char_typo_in_object(self) -> None:
        claims = [_claim("MED13", "ASSOCIATED_WITH", "intellectual disabiilty")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        assert len(result) == 1
        assert result[0].object_similarity >= 0.85

    def test_single_char_typo_in_subject(self) -> None:
        claims = [_claim("MED133", "INHIBITS", "Pol II")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="INHIBITS",
            proposal_object="Pol II",
            existing_claims=claims,
        )
        assert len(result) == 1
        assert result[0].subject_similarity >= 0.85


class TestRelationTypeMustMatch:
    """Same entities but different relation type should not match."""

    def test_different_relation_not_matched(self) -> None:
        claims = [_claim("MED13", "INHIBITS", "Pol II")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ACTIVATES",
            proposal_object="Pol II",
            existing_claims=claims,
        )
        assert len(result) == 0


class TestThresholdRespected:
    """Below-threshold similarities should not be returned."""

    def test_below_threshold_not_returned(self) -> None:
        claims = [_claim("alpha-synuclein", "ASSOCIATED_WITH", "neurodegeneration")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
            threshold=0.85,
        )
        assert len(result) == 0

    def test_custom_threshold(self) -> None:
        claims = [_claim("MED13 IDR", "INHIBITS", "Pol II release")]
        result = find_near_duplicates(
            proposal_subject="MED13 IDR",
            proposal_relation="INHIBITS",
            proposal_object="Pol II",
            existing_claims=claims,
            threshold=0.95,  # Very high threshold
        )
        # "Pol II" vs "Pol II release" is ~0.72, below 0.95
        assert len(result) == 0

    def test_moderate_threshold_catches_partial(self) -> None:
        claims = [_claim("MED13 IDR", "INHIBITS", "Pol II release")]
        result = find_near_duplicates(
            proposal_subject="MED13 IDR",
            proposal_relation="INHIBITS",
            proposal_object="Pol II",
            existing_claims=claims,
            threshold=0.60,  # Low threshold
        )
        assert len(result) == 1


class TestDifferentClaimsNotMatched:
    """Completely unrelated claims should never match."""

    def test_unrelated_claims(self) -> None:
        claims = [
            _claim("patisiran", "TREATS", "transthyretin amyloidosis"),
            _claim("deferoxamine", "INHIBITS", "neurodegeneration"),
        ]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        assert len(result) == 0


class TestCommutativity:
    """Subject/object swap should still be detected."""

    def test_swapped_subject_object_detected(self) -> None:
        claims = [_claim("intellectual disability", "ASSOCIATED_WITH", "MED133")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        # MED13 vs MED133 should be caught (subject_similarity ~0.9)
        assert len(result) == 1


class TestSortingAndMetadata:
    """Results should be sorted by similarity and include metadata."""

    def test_sorted_by_combined_similarity(self) -> None:
        claims = [
            _claim(
                "MED133",
                "ASSOCIATED_WITH",
                "intellectual disabiilty",
                claim_id="c1",
            ),
            _claim(
                "MED13x",
                "ASSOCIATED_WITH",
                "intellectual disability",
                claim_id="c2",
            ),
        ]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="ASSOCIATED_WITH",
            proposal_object="intellectual disability",
            existing_claims=claims,
        )
        assert len(result) >= 1
        # Higher combined similarity should come first
        if len(result) == 2:
            combined_0 = result[0].subject_similarity + result[0].object_similarity
            combined_1 = result[1].subject_similarity + result[1].object_similarity
            assert combined_0 >= combined_1

    def test_includes_claim_status(self) -> None:
        claims = [_claim("MED133", "INHIBITS", "Pol II", status="PROMOTED")]
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="INHIBITS",
            proposal_object="Pol II",
            existing_claims=claims,
        )
        assert len(result) == 1
        assert result[0].claim_status == "PROMOTED"

    def test_empty_claims_returns_empty(self) -> None:
        result = find_near_duplicates(
            proposal_subject="MED13",
            proposal_relation="INHIBITS",
            proposal_object="Pol II",
            existing_claims=[],
        )
        assert result == []
