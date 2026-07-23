"""Focused custody tests for the tracked V13 exposed panel."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.public_gold.staged_event.generalization import (
    panel as generated_panel,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    FrozenPanelError,
    assert_generated_panel_matches_frozen,
    generated_panel_matches_frozen,
    load_frozen_panel,
)


def test_load_frozen_panel_is_exact_ordered_and_raw_corpus_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        generated_panel,
        "CG_DEVELOPMENT",
        Path("/frozen-loader-must-not-read-raw-corpus"),
    )

    cases = load_frozen_panel()

    assert tuple(case.case_id for case in cases) == CASE_ORDER
    assert all(isinstance(case, GeneralizationCase) for case in cases)
    assert all(isinstance(case.reference.events, tuple) for case in cases)
    assert all(isinstance(case.reference.participants, tuple) for case in cases)
    assert all(isinstance(case.reference.arguments, tuple) for case in cases)
    assert all(isinstance(case.reference.axes, tuple) for case in cases)
    for case in cases:
        assert case.source[case.context_start : case.context_end] == case.local_context
        assert case.source[case.focus_start : case.focus_end] == case.focus_passage


def test_load_frozen_panel_rejects_strict_shape_changes(tmp_path: Path) -> None:
    document = _frozen_document()
    first_case = _case(document, 0)
    del first_case["family"]
    first_case["unexpected"] = "not allowed"
    path = _write_panel(tmp_path, document)

    with pytest.raises(FrozenPanelError, match="fields differ"):
        load_frozen_panel(path)


def test_load_frozen_panel_rejects_source_or_offset_mutation(
    tmp_path: Path,
) -> None:
    source_mutation = _frozen_document()
    _case(source_mutation, 0)["source"] = (
        _string(_case(source_mutation, 0)["source"]) + " mutation"
    )
    with pytest.raises(FrozenPanelError, match="source_sha256"):
        load_frozen_panel(_write_panel(tmp_path, source_mutation, "source.json"))

    offset_mutation = _frozen_document()
    first_case = _case(offset_mutation, 0)
    first_case["focus_end"] = _integer(first_case["focus_end"]) + 1
    with pytest.raises(FrozenPanelError, match="focus_passage"):
        load_frozen_panel(_write_panel(tmp_path, offset_mutation, "offset.json"))


def test_load_frozen_panel_rejects_reference_and_membership_mutation(
    tmp_path: Path,
) -> None:
    reference_mutation = _frozen_document()
    reference = _object(_case(reference_mutation, 0)["reference"])
    first_event = _object(_array(reference["events"])[0])
    first_event["event_type"] = "INFECTION"
    with pytest.raises(FrozenPanelError, match="unsupported value"):
        load_frozen_panel(_write_panel(tmp_path, reference_mutation, "reference.json"))

    membership_mutation = _frozen_document()
    _case(membership_mutation, 1)["case_id"] = CASE_ORDER[0]
    with pytest.raises(FrozenPanelError, match="case IDs must be unique"):
        load_frozen_panel(
            _write_panel(tmp_path, membership_mutation, "membership.json")
        )


def test_current_generator_is_canonically_equal_after_json_normalization() -> None:
    current = generated_panel.panel_json()

    assert generated_panel_matches_frozen(current)
    assert_generated_panel_matches_frozen(current)

    changed = copy.deepcopy(current)
    changed["selection_policy"] = "mutated"
    assert generated_panel_matches_frozen(changed) is False
    with pytest.raises(FrozenPanelError, match="differs"):
        assert_generated_panel_matches_frozen(changed)


def _frozen_document() -> dict[str, object]:
    loaded: object = json.loads(DEFAULT_PATHS.panel.read_text(encoding="utf-8"))
    return _object(loaded)


def _write_panel(
    directory: Path,
    document: dict[str, object],
    filename: str = "panel.json",
) -> Path:
    path = directory / filename
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _case(document: dict[str, object], index: int) -> dict[str, object]:
    return _object(_array(document["cases"])[index])


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return cast("dict[str, object]", value)


def _array(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _string(value: object) -> str:
    assert isinstance(value, str)
    return value


def _integer(value: object) -> int:
    assert type(value) is int
    return value
