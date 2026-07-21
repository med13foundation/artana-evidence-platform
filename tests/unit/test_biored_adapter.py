from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.public_gold.biored_adapter import (
    load_biored_split,
    write_development_projection,
)


def _bioc_document() -> dict[str, object]:
    return {
        "id": "doc-1",
        "passages": [
            {
                "offset": 0,
                "text": "GeneA causes DiseaseB.",
                "annotations": [
                    {
                        "id": "1",
                        "infons": {"identifier": "1", "type": "GeneOrGeneProduct"},
                        "text": "GeneA",
                        "locations": [{"offset": 0, "length": 5}],
                    },
                    {
                        "id": "2",
                        "infons": {
                            "identifier": "D1",
                            "type": "DiseaseOrPhenotypicFeature",
                        },
                        "text": "DiseaseB",
                        "locations": [{"offset": 13, "length": 8}],
                    },
                ],
            }
        ],
        "relations": [
            {
                "id": "R1",
                "infons": {
                    "entity1": "1",
                    "entity2": "D1",
                    "type": "Cause",
                    "novel": "Novel",
                },
            }
        ],
    }


def test_development_projection_preserves_offsets_and_novelty(tmp_path: Path) -> None:
    source = tmp_path / "Dev.BioC.JSON"
    source.write_text(json.dumps({"documents": [_bioc_document()]}))
    output = tmp_path / "projection.json"

    payload = write_development_projection(source, output)

    assert payload["split"] == "Dev"
    relation = payload["documents"][0]["relations"][0]
    assert relation["novelty"] == "NOVEL"
    assert relation["relation_type"] == "Cause"
    entity = payload["documents"][0]["entities"][1]
    assert entity["start"] == 13
    assert entity["end"] == 21


def test_test_split_is_sealed_by_default(tmp_path: Path) -> None:
    source = tmp_path / "Test.BioC.JSON"
    source.write_text(json.dumps({"documents": [_bioc_document()]}))

    with pytest.raises(ValueError, match="sealed"):
        load_biored_split(source, split="Test")


def test_unknown_novelty_label_fails_closed(tmp_path: Path) -> None:
    document = _bioc_document()
    document["relations"][0]["infons"]["novel"] = "Yes"
    source = tmp_path / "Dev.BioC.JSON"
    source.write_text(json.dumps({"documents": [document]}))

    with pytest.raises(ValueError, match="unsupported BioRED relation novelty"):
        load_biored_split(source, split="Dev")
