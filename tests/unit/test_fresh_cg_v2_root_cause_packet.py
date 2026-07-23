"""Integrity checks for the neutral Fresh-CG V2 root-cause packet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parents[2]
PACKET = (
    REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-root-cause-dispute-packet-v1.json"
)
SELECTION = REPO / "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v2.json"


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _objects(value: object) -> list[dict[str, object]]:
    return [_object(item) for item in cast("list[object]", value)]


def _load(path: Path) -> dict[str, object]:
    return _object(json.loads(path.read_text(encoding="utf-8")))


def test_packet_pins_every_historical_input_byte_for_byte() -> None:
    packet = _load(PACKET)
    pins = _object(packet["artifact_pins"])

    for relative_path, expected in pins.items():
        actual = hashlib.sha256((REPO / relative_path).read_bytes()).hexdigest()
        assert actual == expected


def test_packet_offsets_reproduce_the_frozen_source() -> None:
    packet = _load(PACKET)
    selection = _load(SELECTION)
    cases = _objects(selection["cases"])
    case = next(item for item in cases if item["case_id"] == packet["case_id"])
    source = cast("str", case["source_text"])
    frozen_context = _object(_object(packet["frozen_source"])["context"])
    start = cast("int", frozen_context["start"])
    end = cast("int", frozen_context["end"])

    assert source[start:end] == frozen_context["text"]

    candidate_groups = _object(packet["candidate_interpretations"])
    for raw_group in candidate_groups.values():
        group = _object(raw_group)
        for raw_candidate in group.values():
            candidates = (
                cast("list[object]", raw_candidate)
                if isinstance(raw_candidate, list)
                else [raw_candidate]
            )
            for raw_item in candidates:
                if not isinstance(raw_item, dict):
                    continue
                item = _object(raw_item)
                span = _object(item["mention"]) if "mention" in item else item
                if {"start", "end", "text"} <= set(span):
                    span_start = cast("int", span["start"])
                    span_end = cast("int", span["end"])
                    assert source[span_start:span_end] == span["text"]


def test_packet_is_neutral_and_fail_closed() -> None:
    packet = _load(PACKET)
    governance = _object(packet["governance"])
    issues = _objects(packet["failed_fields_to_classify"])
    labels = cast("list[str]", packet["classification_labels"])

    assert packet["v2_observed_output_candidates_are_anonymized"] is True
    assert governance == {
        "fresh_cases_remaining_and_uncalled": 7,
        "graph_writes_allowed": False,
        "qualification_credit": False,
        "scientific_provider_calls_allowed": False,
        "sealed_v1_v2_mutation_allowed": False,
    }
    assert len(issues) == 8
    assert len({cast("str", item["issue_id"]) for item in issues}) == len(issues)
    assert labels == [
        "MODEL_ERROR",
        "REFERENCE_ERROR",
        "EVALUATOR_MAPPING_ERROR",
        "TAXONOMY_AMBIGUITY",
        "UNRESOLVED_EXPERT_REVIEW_REQUIRED",
    ]


def test_packet_exposes_cascade_and_terminal_mapping_without_rescoring() -> None:
    packet = _load(PACKET)
    mappings = _object(packet["evaluator_mappings"])
    attachment = _object(mappings["attachment"])
    unsupported = _object(mappings["unsupported_count"])
    terminal = _object(mappings["terminal"])

    assert "iterates over link.arguments twice" in cast(
        "str", attachment["implementation_observation"]
    )
    assert unsupported["reported_count"] == 4
    assert len(cast("list[object]", unsupported["case_trace"])) == 4
    assert terminal == {
        "contradiction_count": 0,
        "selection_rule": (
            "CONTRADICTION_OR_UNSUPPORTED is selected when contradiction_count "
            "is nonzero OR unsupported_claim_count is nonzero."
        ),
        "terminal_stage": "CONTRADICTION_OR_UNSUPPORTED",
        "unsupported_claim_count": 4,
    }
