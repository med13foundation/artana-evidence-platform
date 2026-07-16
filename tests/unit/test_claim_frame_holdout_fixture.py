"""Structural protections for the sealed TG-03 ClaimFrame holdout v2."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Final, cast

from artana_evidence_api.document_extraction_prompting import (
    LLM_EXTRACTION_SYSTEM_PROMPT,
)

from scripts.validation.claim_frames.fixture import (
    QUALIFIER_FIELDS,
    load_fixture,
)

JsonObject = dict[str, object]
CorrectionGroup = tuple[str, str, tuple[str, ...]]

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_V1_PATH: Final = (
    _REPO_ROOT
    / "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v1.json"
)
_V2_PATH: Final = (
    _REPO_ROOT
    / "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v2.json"
)
_DEV_PATH: Final = (
    _REPO_ROOT
    / "scripts/validation/claim_frames/fixtures/tg03_qualifier_benchmark_v1.json"
)
_LEDGER_PATH: Final = (
    _REPO_ROOT / "docs/validation/reports/tg03-qualified-claim-frame-runs/"
    "tg03-holdout-v1-to-v2-adjudication.json"
)
_EXPECTED_GROUPS: Final[tuple[CorrectionGroup, ...]] = (
    ("holdout_null_margin", "holdout_null_margin_01", ("outcome",)),
    (
        "holdout_intervention_ctdna",
        "holdout_intervention_ctdna_01",
        ("intervention", "treatment_setting", "timeframe"),
    ),
    (
        "holdout_source_measurement_repoterctinib",
        "holdout_source_measurement_repoterctinib_01",
        ("timeframe",),
    ),
)


def _raw(path: Path) -> JsonObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast("JsonObject", payload)


def _cases(payload: JsonObject) -> list[JsonObject]:
    cases = payload["cases"]
    assert isinstance(cases, list)
    return [cast("JsonObject", case) for case in cases]


def _frames(case: JsonObject) -> list[JsonObject]:
    frames = case["expected_frames"]
    assert isinstance(frames, list)
    return [cast("JsonObject", frame) for frame in frames]


def _qualifiers(frame: JsonObject) -> JsonObject:
    qualifiers = frame["qualifiers"]
    assert isinstance(qualifiers, dict)
    return cast("JsonObject", qualifiers)


def _case_map(payload: JsonObject) -> dict[str, JsonObject]:
    return {cast("str", case["case_id"]): case for case in _cases(payload)}


def _frame_map(payload: JsonObject) -> dict[tuple[str, str], JsonObject]:
    return {
        (cast("str", case["case_id"]), cast("str", frame["frame_id"])): frame
        for case in _cases(payload)
        for frame in _frames(case)
    }


def _adjudicated_fields_by_frame() -> dict[tuple[str, str], frozenset[str]]:
    return {
        (case_id, frame_id): frozenset(fields)
        for case_id, frame_id, fields in _EXPECTED_GROUPS
    }


def _normalized_cases(payload: JsonObject) -> list[JsonObject]:
    normalized = copy.deepcopy(_cases(payload))
    fields_by_frame = _adjudicated_fields_by_frame()
    for case in normalized:
        case_id = cast("str", case["case_id"])
        for frame in _frames(case):
            frame_id = cast("str", frame["frame_id"])
            for field in fields_by_frame.get((case_id, frame_id), frozenset()):
                _qualifiers(frame).pop(field, None)
    return normalized


def _qualifier_differences(
    v1_payload: JsonObject,
    v2_payload: JsonObject,
) -> set[tuple[str, str, str]]:
    v1_frames = _frame_map(v1_payload)
    v2_frames = _frame_map(v2_payload)
    assert set(v1_frames) == set(v2_frames)
    differences: set[tuple[str, str, str]] = set()
    for frame_key, v1_frame in v1_frames.items():
        v1_qualifiers = _qualifiers(v1_frame)
        v2_qualifiers = _qualifiers(v2_frames[frame_key])
        for field in QUALIFIER_FIELDS:
            if v1_qualifiers.get(field) != v2_qualifiers.get(field):
                differences.add((*frame_key, field))
    return differences


def test_v2_metadata_records_blind_post_freeze_boundary() -> None:
    v1_payload = _raw(_V1_PATH)
    v2_payload = _raw(_V2_PATH)
    metadata = cast("JsonObject", v2_payload["metadata"])

    assert v1_payload["schema_version"] == "tg03_qualifier_benchmark.v1"
    assert v2_payload["schema_version"] == "tg03_qualifier_benchmark.v2"
    assert metadata["adjudication_status"] == "post-freeze blind-gold-adjudicated"
    assert metadata["prompt_version"] == "document_extraction.llm_extraction.v11"
    assert metadata["prompt_status"] == "v11 unchanged"
    assert metadata["v1_fixture_immutable"] is True
    assert metadata["v1_first_run_immutable"] is True
    assert metadata["production_output_supplied_to_qualifier_adjudicator"] is False
    assert metadata["reviewer_scope"] == (
        "qualifier corrections only; core frame disagreements remain unresolved"
    )


def test_v2_changes_exactly_three_qualifier_correction_groups() -> None:
    v1_payload = _raw(_V1_PATH)
    v2_payload = _raw(_V2_PATH)
    expected_differences = {
        (case_id, frame_id, field)
        for case_id, frame_id, fields in _EXPECTED_GROUPS
        for field in fields
    }

    assert _qualifier_differences(v1_payload, v2_payload) == expected_differences
    assert _normalized_cases(v1_payload) == _normalized_cases(v2_payload)


def test_v2_source_texts_and_core_frames_are_identical_to_v1() -> None:
    v1_payload = _raw(_V1_PATH)
    v2_payload = _raw(_V2_PATH)
    v1_cases = _case_map(v1_payload)
    v2_cases = _case_map(v2_payload)

    assert v1_cases.keys() == v2_cases.keys()
    for case_id, v1_case in v1_cases.items():
        v2_case = v2_cases[case_id]
        assert cast("str", v1_case["source_text"]).encode("utf-8") == cast(
            "str",
            v2_case["source_text"],
        ).encode("utf-8")

    v1_frames = _frame_map(v1_payload)
    v2_frames = _frame_map(v2_payload)
    for frame_key, v1_frame in v1_frames.items():
        v2_frame = v2_frames[frame_key]
        for field in (
            "frame_id",
            "subject",
            "predicate",
            "object",
            "source_span",
            "source_locator",
            "polarity",
            "epistemic_status",
        ):
            assert v1_frame.get(field) == v2_frame.get(field)


def test_v2_corrected_qualifiers_have_exact_adjudicated_values() -> None:
    v1_frames = _frame_map(_raw(_V1_PATH))
    v2_frames = _frame_map(_raw(_V2_PATH))

    assert _qualifiers(v1_frames[("holdout_null_margin", "holdout_null_margin_01")])[
        "outcome"
    ] == {
        "state": "PRESENT",
        "value": "survival advantage",
        "exact_span": "survival advantage",
    }
    assert _qualifiers(v2_frames[("holdout_null_margin", "holdout_null_margin_01")])[
        "outcome"
    ] == {
        "state": "PRESENT",
        "value": "incremental survival advantage",
        "exact_span": "incremental survival advantage",
    }

    intervention = _qualifiers(
        v2_frames[("holdout_intervention_ctdna", "holdout_intervention_ctdna_01")],
    )
    assert intervention["intervention"] == {
        "state": "PRESENT",
        "value": "dostarlimab",
        "exact_span": "dostarlimab",
    }
    assert intervention["treatment_setting"] == {
        "state": "PRESENT",
        "value": "neoadjuvant",
        "exact_span": "neoadjuvant",
    }
    assert intervention["timeframe"] == {
        "state": "PRESENT",
        "value": "four cycles",
        "exact_span": "After four cycles",
    }

    repotrectinib = _qualifiers(
        v2_frames[
            (
                "holdout_source_measurement_repoterctinib",
                "holdout_source_measurement_repoterctinib_01",
            )
        ],
    )
    assert "timeframe" not in repotrectinib


def test_v2_loader_materializes_removed_timeframe_as_not_applicable() -> None:
    fixture = load_fixture(_V2_PATH)
    case = next(
        case
        for case in fixture.cases
        if case.case_id == "holdout_source_measurement_repoterctinib"
    )
    frame = case.frames[0]
    assert frame.qualifiers["timeframe"].state == "NOT_APPLICABLE"
    assert frame.qualifiers["timeframe"].value is None
    assert frame.qualifiers["timeframe"].exact_span is None
    assert fixture.methodology_complete is False
    assert fixture.methodology_incomplete_reason == (
        "legacy fixture lacks explicit adjudication, promotion, and source-measurement gold"
    )
    assert frame.promotion_eligible is None


def test_v2_hashes_and_ledger_bind_the_immutable_transition() -> None:
    ledger = _raw(_LEDGER_PATH)
    from_record = cast("JsonObject", ledger["from"])
    to_record = cast("JsonObject", ledger["to"])

    v1_hash = hashlib.sha256(_V1_PATH.read_bytes()).hexdigest()
    v2_hash = hashlib.sha256(_V2_PATH.read_bytes()).hexdigest()
    assert from_record["path"] == _V1_PATH.relative_to(_REPO_ROOT).as_posix()
    assert from_record["sha256"] == v1_hash
    assert to_record["path"] == _V2_PATH.relative_to(_REPO_ROOT).as_posix()
    assert to_record["sha256"] == v2_hash
    assert cast("JsonObject", ledger["prompt"])["version"] == (
        "document_extraction.llm_extraction.v11"
    )
    assert cast("JsonObject", ledger["prompt"])["unchanged"] is True
    assert cast("JsonObject", ledger["review"])["scope"] == (
        "blind qualifier adjudication only"
    )
    assert (
        cast("JsonObject", ledger["review"])[
            "production_output_supplied_to_qualifier_adjudicator"
        ]
        is False
    )
    assert cast("JsonObject", ledger["review"])[
        "unresolved_core_frame_disagreements"
    ] == [
        "holdout_multi_clause_ret_ntrk_02",
        "holdout_population_futibatinib_01",
    ]


def test_v2_has_no_source_text_or_source_span_overlap_with_prompt_or_dev_fixture() -> (
    None
):
    holdout = load_fixture(_V2_PATH)
    dev = load_fixture(_DEV_PATH)
    dev_source_texts = {case.source_text for case in dev.cases}
    dev_source_spans = {
        frame.source_span for case in dev.cases for frame in case.frames
    }

    for case in holdout.cases:
        assert case.source_text not in dev_source_texts
        assert case.source_text not in LLM_EXTRACTION_SYSTEM_PROMPT
        for frame in case.frames:
            assert frame.source_span not in dev_source_spans
            assert frame.source_span not in LLM_EXTRACTION_SYSTEM_PROMPT
