"""Exact change controls for the blind-adjudicated TG-03 holdout v2."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Final, cast

from artana_evidence_api.document_extraction_prompting import (
    LLM_EXTRACTION_SYSTEM_PROMPT,
)

from scripts.validation.claim_frames.fixture import load_fixture

_ROOT: Final = Path(__file__).resolve().parents[2]
_V1: Final = (
    _ROOT / "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v1.json"
)
_V2: Final = (
    _ROOT / "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v2.json"
)
_V3: Final = (
    _ROOT / "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v3.json"
)
_LEDGER: Final = (
    _ROOT
    / "docs/validation/reports/tg03-qualified-claim-frame-runs/tg03-holdout-v1-to-v2-adjudication.json"
)
_V3_LEDGER: Final = (
    _ROOT / "docs/validation/reports/tg03-qualified-claim-frame-runs/"
    "tg03-holdout-v2-to-v3-methodology-adjudication.json"
)
_FIXTURE_LOADER: Final = _ROOT / "scripts/validation/claim_frames/fixture.py"


def _payload(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v2_is_bound_to_ledger_and_unchanged_prompt() -> None:
    ledger = _payload(_LEDGER)
    assert ledger["production_output_supplied_to_reviewer"] is False
    assert ledger["prompt_changed"] is False
    assert cast("dict[str, object]", ledger["v1"])["sha256"] == _sha256(_V1)
    assert cast("dict[str, object]", ledger["v2"])["sha256"] == _sha256(_V2)
    assert len(cast("list[object]", ledger["correction_groups"])) == 3


def test_v2_changes_only_the_three_blind_adjudications() -> None:
    v1 = _payload(_V1)
    v2 = _payload(_V2)
    expected = copy.deepcopy(v1)
    expected["schema_version"] = "tg03_qualifier_benchmark.v2"
    expected["metadata"] = v2["metadata"]
    cases = {
        cast("str", case["case_id"]): case
        for case in cast("list[dict[str, object]]", expected["cases"])
    }

    null_frame = _first_frame(cases["holdout_null_margin"])
    _qualifiers(null_frame)["outcome"] = {
        "state": "PRESENT",
        "value": "incremental survival advantage",
        "exact_span": "incremental survival advantage",
    }
    intervention_frame = _first_frame(cases["holdout_intervention_ctdna"])
    intervention_qualifiers = _qualifiers(intervention_frame)
    intervention_qualifiers["intervention"] = {
        "state": "PRESENT",
        "value": "dostarlimab",
        "exact_span": "dostarlimab",
    }
    intervention_qualifiers["treatment_setting"] = {
        "state": "PRESENT",
        "value": "neoadjuvant",
        "exact_span": "neoadjuvant",
    }
    intervention_qualifiers["timeframe"] = {
        "state": "PRESENT",
        "value": "four cycles",
        "exact_span": "After four cycles",
    }
    measurement_frame = _first_frame(
        cases["holdout_source_measurement_repoterctinib"],
    )
    _qualifiers(measurement_frame).pop("timeframe")

    assert expected == v2


def test_v2_loads_and_remains_prompt_blind() -> None:
    fixture = load_fixture(_V2)
    assert len(fixture.cases) == 19
    assert fixture.methodology_complete is False
    assert all(
        case.source_text not in LLM_EXTRACTION_SYSTEM_PROMPT for case in fixture.cases
    )


def test_v3_seals_v2_without_mutating_source_cases() -> None:
    v3_payload = _payload(_V3)
    base = cast("dict[str, object]", v3_payload["base_fixture"])
    ledger = _payload(_V3_LEDGER)

    assert base["path"] == _V2.relative_to(_ROOT).as_posix()
    assert base["sha256"] == _sha256(_V2)
    assert cast("dict[str, object]", ledger["from"])["sha256"] == _sha256(_V2)
    assert cast("dict[str, object]", ledger["to"])["sha256"] == _sha256(_V3)

    v2 = load_fixture(_V2)
    v3 = load_fixture(_V3)
    assert v3.methodology_complete is True
    assert v3.base_fixture_sha256 == v2.sha256
    assert [
        (case.case_id, case.title, case.category, case.source_text) for case in v3.cases
    ] == [
        (case.case_id, case.title, case.category, case.source_text) for case in v2.cases
    ]


def test_v3_explicitly_covers_promotion_and_measurement_gold_for_every_frame() -> None:
    payload = _payload(_V3)
    methodology = cast("list[dict[str, object]]", payload["case_methodology"])
    raw_frames = [
        frame
        for case in methodology
        for frame in cast("list[dict[str, object]]", case["frames"])
    ]

    assert len(raw_frames) == 20
    assert all(
        isinstance(frame.get("promotion_eligible"), bool) for frame in raw_frames
    )
    assert all(
        isinstance(frame.get("expected_source_measurements"), list)
        for frame in raw_frames
    )
    measurement_frames = [
        frame for frame in raw_frames if frame["expected_source_measurements"]
    ]
    assert measurement_frames == [
        {
            "frame_id": "holdout_source_measurement_repoterctinib_01",
            "promotion_eligible": True,
            "expected_source_measurements": [
                {
                    "origin": "source_measurement",
                    "value": "8.7",
                    "source_locator": "normalized_extraction_text",
                    "literal_span": "8.7 months",
                    "field_name": "progression_free_interval",
                    "unit": "months",
                    "extraction_method": "literal",
                },
            ],
        },
    ]


def test_v3_preserves_unresolved_adjudication_outside_quality_denominators() -> None:
    fixture = load_fixture(_V3)
    unresolved = {
        case.case_id: case.unresolved_frame_ids
        for case in fixture.cases
        if case.adjudication_status == "unresolved"
    }

    assert unresolved == {
        "holdout_multi_clause_ret_ntrk": ("holdout_multi_clause_ret_ntrk_02",),
        "holdout_population_futibatinib": ("holdout_population_futibatinib_01",),
    }
    assert all(
        case.included_in_quality_metrics == (case.adjudication_status == "adjudicated")
        for case in fixture.cases
    )


def test_fixture_methodology_has_no_production_semantic_policy_import() -> None:
    source = _FIXTURE_LOADER.read_text(encoding="utf-8")

    assert "artana_evidence_api" not in source
    assert "promotion_eligible" in source


def _first_frame(case: dict[str, object]) -> dict[str, object]:
    return cast("list[dict[str, object]]", case["expected_frames"])[0]


def _qualifiers(frame: dict[str, object]) -> dict[str, object]:
    return cast("dict[str, object]", frame["qualifiers"])
