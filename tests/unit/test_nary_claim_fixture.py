"""Focused contract tests for the TG-04 n-ary claim fixture loader."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Final, cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventType,
)

from scripts.validation.claim_events.bionlp_import import build_bionlp_fixture
from scripts.validation.claim_events.contracts import (
    BenchmarkEventType,
    ValueStatus,
    validate_event_type_parity,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    SCHEMA_VERSION,
    load_fixture,
    require_frozen_development_fixture,
)

JsonObject = dict[str, object]
_EVENT_TYPES: Final = {
    "EXPRESSION",
    "TRANSCRIPTION",
    "DEGRADATION",
    "PHOSPHORYLATION",
    "LOCALIZATION",
    "BINDING",
    "REGULATION",
    "POSITIVE_REGULATION",
    "NEGATIVE_REGULATION",
    "INCREASE",
    "DECREASE",
    "ASSOCIATION",
    "TREATMENT_RESPONSE",
    "NO_EFFECT",
    "OTHER_EXPLICIT",
}


def test_repository_development_fixture_is_frozen_and_expert_derived() -> None:
    fixture = load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH)

    require_frozen_development_fixture(fixture)
    assert len(fixture.eligible_events) == 53
    assert len(fixture.cases) == 40
    assert len(fixture.metadata.empty_control_document_ids) == 23
    assert len(fixture.metadata.true_negative_control_document_ids) == 5
    assert len(fixture.metadata.representability_stress_document_ids) == 18
    assert len(fixture.metadata.event_exclusions) == 419
    assert len(fixture.eligible_events) + len(fixture.metadata.event_exclusions) == 472
    assert len(
        {
            (item.document_id, item.event_id)
            for item in fixture.metadata.event_exclusions
        },
    ) == len(fixture.metadata.event_exclusions)
    assert (
        sum(
            reference.startswith("M")
            for item in fixture.metadata.event_exclusions
            for reference in item.annotation_references
        )
        == 67
    )
    assert len(fixture.metadata.selected_document_ids) == 40
    assert {case.source.corpus for case in fixture.cases} == {"BioNLP-ST-2011-GE"}
    assert fixture.valuable_recall_events == ()
    assert all(
        event.projections.included_in_projection_metrics is False
        for event in fixture.eligible_events
    )


def test_loads_hash_bound_immutable_multi_event_case(tmp_path: Path) -> None:
    path, raw_bytes = _write_fixture(tmp_path, _payload())

    fixture = load_fixture(path)
    event = fixture.cases[0].events[0]

    assert fixture.sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert len(event.arguments) == 3
    assert event.value.status is ValueStatus.UNADJUDICATED
    assert fixture.valuable_recall_events == ()
    assert event.projections.supported == ()
    with pytest.raises(FrozenInstanceError):
        fixture.cases[0].case_id = "changed"  # type: ignore[misc]


def test_loader_accepts_primary_corpus_adapter_shape(tmp_path: Path) -> None:
    text = "Kinase A increased expression of protein B."
    (tmp_path / "PMID-test.txt").write_text(text, encoding="utf-8")
    (tmp_path / "PMID-test.a1").write_text(
        "T1\tProtein 0 8\tKinase A\nT2\tProtein 33 42\tprotein B\n",
        encoding="utf-8",
    )
    (tmp_path / "PMID-test.a2").write_text(
        "T3\tPositive_regulation 9 18\tincreased\n"
        "E1\tPositive_regulation:T3 Cause:T1 Theme:T2\n",
        encoding="utf-8",
    )
    payload = build_bionlp_fixture(
        root=tmp_path,
        document_ids=("PMID-test",),
        archive_sha256="a" * 64,
        source_url="https://example.test/corpus",
    )
    path, _ = _write_fixture(tmp_path, payload)

    fixture = load_fixture(path)

    assert (
        fixture.cases[0].events[0].event_type is BenchmarkEventType.POSITIVE_REGULATION
    )


def test_event_type_contract_has_exact_production_parity() -> None:
    assert {item.value for item in BenchmarkEventType} == _EVENT_TYPES
    validate_event_type_parity(item.value for item in ClaimEventType)
    with pytest.raises(ValueError, match="event type parity mismatch"):
        validate_event_type_parity(_EVENT_TYPES - {"BINDING"})


@pytest.mark.parametrize(
    "field",
    [
        "event_type",
        "polarity",
        "epistemic_status",
        "framing_decision",
        "value_status",
        "projection_adjudication",
    ],
)
def test_rejects_unknown_event_categories(tmp_path: Path, field: str) -> None:
    payload = _payload()
    _first_event(payload)[field] = "UNKNOWN_CATEGORY"
    path, _ = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match=f"unknown {field} category"):
        load_fixture(path)


def test_rejects_unknown_argument_or_provenance_category(tmp_path: Path) -> None:
    for index, (container, field) in enumerate(
        (
            ("argument", "event_role"),
            ("argument", "participant_role"),
            ("provenance", "annotation_status"),
        ),
    ):
        payload = _payload()
        event = _first_event(payload)
        target = (
            _object(_array(event["arguments"])[0])
            if container == "argument"
            else _object(event["annotation_provenance"])
        )
        target[field] = "UNKNOWN_CATEGORY"
        path, _ = _write_fixture(tmp_path, payload, f"category-{index}.json")
        with pytest.raises(ValueError, match=f"unknown {field} category"):
            load_fixture(path)


def test_rejects_duplicate_arguments_events_and_cases(tmp_path: Path) -> None:
    duplicate_argument = _payload()
    arguments = _array(_first_event(duplicate_argument)["arguments"])
    arguments.append(copy.deepcopy(arguments[0]))
    path, _ = _write_fixture(tmp_path, duplicate_argument, "arguments.json")
    with pytest.raises(ValueError, match="arguments must be unique"):
        load_fixture(path)

    duplicate_event = _payload()
    events = _array(_first_case(duplicate_event)["events"])
    events.append(copy.deepcopy(events[0]))
    path, _ = _write_fixture(tmp_path, duplicate_event, "events.json")
    with pytest.raises(ValueError, match="event IDs must be unique"):
        load_fixture(path)

    duplicate_case = _payload()
    cases = _array(duplicate_case["cases"])
    cases.append(copy.deepcopy(cases[0]))
    path, _ = _write_fixture(tmp_path, duplicate_case, "cases.json")
    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_fixture(path)


def test_rejects_unbound_source_trigger_or_argument_span(tmp_path: Path) -> None:
    mutations = (
        ("source_span", "not in the source"),
        ("trigger_span", "not in the source region"),
        ("argument", "not in the source region"),
    )
    for index, (target, value) in enumerate(mutations):
        payload = _payload()
        event = _first_event(payload)
        if target == "argument":
            _object(_array(event["arguments"])[0])["exact_span"] = value
        else:
            event[target] = value
        path, _ = _write_fixture(tmp_path, payload, f"unbound-{index}.json")
        with pytest.raises(ValueError, match="not bind|not bound"):
            load_fixture(path)


def test_rejects_missing_or_non_independent_provenance(tmp_path: Path) -> None:
    missing = _payload()
    _first_event(missing).pop("annotation_provenance")
    path, _ = _write_fixture(tmp_path, missing, "missing.json")
    with pytest.raises(ValueError, match=r"missing=\['annotation_provenance'\]"):
        load_fixture(path)

    fabricated = _payload()
    event = _first_event(fabricated)
    event["value_status"] = "VALUABLE"
    event["value_reason"] = "Informs a treatment choice."
    _object(event["annotation_provenance"])["annotation_status"] = (
        "development_annotation"
    )
    path, _ = _write_fixture(tmp_path, fabricated, "fabricated.json")
    with pytest.raises(ValueError, match="independent provenance"):
        load_fixture(path)


def test_adjudicated_value_requires_reason(tmp_path: Path) -> None:
    payload = _payload()
    event = _first_event(payload)
    event["value_status"] = "VALUABLE"
    event["value_reason"] = None
    path, _ = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="independent reason"):
        load_fixture(path)


def test_unadjudicated_value_and_empty_projections_are_excluded(tmp_path: Path) -> None:
    path, _ = _write_fixture(tmp_path, _payload())

    event = load_fixture(path).cases[0].events[0]

    assert event.value.included_in_valuable_recall is False
    assert event.projections.included_in_projection_metrics is False
    assert event.projections.supported == ()


def test_rejects_fixture_with_zero_eligible_events(tmp_path: Path) -> None:
    payload = _payload()
    _first_event(payload)["eligible_for_event_metrics"] = False
    path, _ = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="at least one eligible event"):
        load_fixture(path)


def _payload() -> JsonObject:
    source_text = "Osimertinib reduced EGFR phosphorylation in tumors."
    return {
        "schema_version": SCHEMA_VERSION,
        "metadata": {
            "purpose": "development contract test",
            "selection_method": "synthetic tmp_path payload",
            "value_labels": "unadjudicated",
            "projection_labels": "unadjudicated",
            "production_semantic_policy_imported": False,
            "selected_document_ids": ["source-1"],
            "excluded_nested_document_ids": [],
            "excluded_no_eligible_document_ids": [],
            "empty_control_document_ids": [],
            "true_negative_control_document_ids": [],
            "representability_stress_document_ids": [],
            "event_exclusions": [],
        },
        "cases": [
            {
                "case_id": "phosphorylation-1",
                "title": "Synthetic contract case",
                "source": {
                    "corpus": "test-only",
                    "document_id": "source-1",
                    "source_url": "https://example.test/source-1",
                    "archive_sha256": "a" * 64,
                    "mapping_version": "test.v1",
                },
                "source_text": source_text,
                "events": [
                    {
                        "event_id": "source-1:E1",
                        "source_span": source_text[:-1],
                        "source_locator": f"char:0-{len(source_text) - 1}",
                        "trigger_span": "phosphorylation",
                        "trigger_source_start": source_text.index("phosphorylation"),
                        "event_type": "PHOSPHORYLATION",
                        "polarity": "SUPPORT",
                        "epistemic_status": "ASSERTED",
                        "arguments": [
                            _argument("T1", "CAUSE", "INTERVENTION", "Osimertinib", 0),
                            _argument("T2", "THEME", "GENE_OR_PROTEIN", "EGFR", 20),
                            _argument("T3", "CONTEXT", "ANATOMY", "tumors", 44),
                        ],
                        "value_status": "UNADJUDICATED",
                        "value_reason": "Source corpus has no Artana value label.",
                        "framing_decision": "UNADJUDICATED",
                        "projection_adjudication": "UNADJUDICATED",
                        "supported_projections": [],
                        "annotation_provenance": {
                            "event_annotation_id": "E1",
                            "trigger_annotation_id": "T4",
                            "argument_annotation_ids": ["T1", "T2", "T3"],
                            "annotation_status": "expert_corpus",
                        },
                        "eligible_for_event_metrics": True,
                    },
                ],
                "control_status": "EVENT_GOLD",
            },
        ],
    }


def _argument(
    argument_id: str,
    event_role: str,
    participant_role: str,
    exact_span: str,
    source_start: int,
) -> JsonObject:
    return {
        "argument_id": argument_id,
        "event_role": event_role,
        "participant_role": participant_role,
        "exact_span": exact_span,
        "source_start": source_start,
    }


def _write_fixture(
    tmp_path: Path,
    payload: JsonObject,
    filename: str = "fixture.json",
) -> tuple[Path, bytes]:
    raw_bytes = json.dumps(payload, indent=2).encode("utf-8")
    path = tmp_path / filename
    path.write_bytes(raw_bytes)
    return path, raw_bytes


def _first_case(payload: JsonObject) -> JsonObject:
    return _object(_array(payload["cases"])[0])


def _first_event(payload: JsonObject) -> JsonObject:
    return _object(_array(_first_case(payload)["events"])[0])


def _object(value: object) -> JsonObject:
    assert isinstance(value, dict)
    return cast("JsonObject", value)


def _array(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)
