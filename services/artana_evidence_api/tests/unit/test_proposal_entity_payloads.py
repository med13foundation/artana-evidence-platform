"""Unit tests for governed entity candidate resolution labels."""

from artana_evidence_api.proposal_entity_payloads import candidate_resolution_labels


def test_candidate_resolution_labels_ignore_arbitrary_anchor_values() -> None:
    labels = candidate_resolution_labels(
        {
            "label": "MED13 c.977C>A",
            "aliases": [],
            "anchors": {
                "gene_symbol": "MED13",
                "hgvs_notation": "c.977C>A",
                "source_span_start": "12345",
            },
        },
    )

    assert labels == ["MED13 c.977C>A", "MED13", "c.977C>A"]
    assert "12345" not in labels
