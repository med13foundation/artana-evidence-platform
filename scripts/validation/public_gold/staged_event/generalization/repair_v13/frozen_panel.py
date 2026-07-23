"""Strict tracked-panel custody for V13 execution.

The V13 runtime must be able to reconstruct the exposed cases from the tracked
panel artifact without consulting the source corpus used to generate it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.panel import (
    ExpectedArgument,
    ExpectedAxes,
    ExpectedEvent,
    ExpectedParticipant,
    GeneralizationCase,
    GeneralizationReference,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        ArgumentRole,
        AuthorInterpretation,
        Comparison,
        Direction,
        EntityType,
        EventType,
        Polarity,
        StatisticalType,
        TargetKind,
        Uncertainty,
    )

_EVENT_TYPES = frozenset(
    {
        "REGULATION",
        "POSITIVE_REGULATION",
        "NEGATIVE_REGULATION",
        "GENE_EXPRESSION",
        "COMPARISON",
        "ASSOCIATION",
        "CLASSIFICATION",
        "OBSERVATION",
    }
)
_ENTITY_TYPES = frozenset(
    {
        "POPULATION",
        "OUTCOME",
        "EXPOSURE",
        "VARIANT",
        "GENE_OR_PROTEIN",
        "CANCER",
        "SIMPLE_CHEMICAL",
        "MEASUREMENT",
    }
)
_ARGUMENT_ROLES = frozenset(
    {
        "AFFECTED_ENTITY",
        "CAUSAL_AGENT",
        "STIMULUS_OR_OBJECT",
        "POPULATION",
        "COMPARATOR",
        "OUTCOME",
        "EXPOSURE",
        "MEASUREMENT",
        "CONTEXTUAL_PARTICIPANT",
        "EFFECT_EVENT",
    }
)
_TARGET_KINDS = frozenset({"PARTICIPANT", "EVENT"})
_DIRECTIONS = frozenset(
    {
        "INCREASED",
        "DECREASED",
        "NO_DIFFERENCE",
        "NO_ASSOCIATION",
        "ENABLES",
        "OBSERVED",
        "NOT_APPLICABLE",
    }
)
_COMPARISONS = frozenset({"GREATER", "LESS", "NO_DIFFERENCE", "NOT_APPLICABLE"})
_POLARITIES = frozenset({"AFFIRMED", "NEGATED", "NULL_RESULT"})
_UNCERTAINTIES = frozenset({"ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS"})
_STATISTICAL_TYPES = frozenset(
    {"P_VALUE", "CONFIDENCE_INTERVAL", "EFFECT_ESTIMATE", "NONE"}
)
_AUTHOR_INTERPRETATIONS = frozenset({"SIGNIFICANT", "NOT_SIGNIFICANT", "NOT_CLAIMED"})

_PANEL_FIELDS = frozenset(
    {
        "exposed_only",
        "selection_policy",
        "canary_case_id",
        "case_count",
        "cases",
    }
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "family",
        "source_id",
        "source_sha256",
        "source",
        "context_start",
        "context_end",
        "local_context",
        "focus_start",
        "focus_end",
        "focus_passage",
        "reference",
    }
)
_REFERENCE_FIELDS = frozenset(
    {
        "events",
        "participants",
        "arguments",
        "axes",
        "root_event_key",
        "reference_basis",
    }
)
_EVENT_FIELDS = frozenset({"event_key", "event_type", "acceptable_triggers"})
_PARTICIPANT_FIELDS = frozenset({"participant_key", "entity_type", "acceptable_texts"})
_ARGUMENT_FIELDS = frozenset({"event_key", "role", "target_kind", "target_key"})
_AXES_FIELDS = frozenset(
    {
        "event_key",
        "direction",
        "comparison",
        "polarity",
        "uncertainty",
        "statistical_type",
        "acceptable_statistical_texts",
        "author_interpretation",
    }
)


class FrozenPanelError(ValueError):
    """The tracked V13 panel is malformed or no longer canonical."""


def load_frozen_panel(
    path: Path = DEFAULT_PATHS.panel,
) -> tuple[GeneralizationCase, ...]:
    """Load and validate the tracked panel in frozen V13 execution order."""

    document = _read_document(path)
    cases = _parse_panel(document)
    by_id = {case.case_id: case for case in cases}
    return tuple(by_id[case_id] for case_id in CASE_ORDER)


def generated_panel_matches_frozen(
    generated: Mapping[str, object],
    path: Path = DEFAULT_PATHS.panel,
) -> bool:
    """Compare generated panel JSON to the validated artifact canonically."""

    frozen = _read_document(path)
    _parse_panel(frozen)
    return _canonical_json(generated) == _canonical_json(frozen)


def assert_generated_panel_matches_frozen(
    generated: Mapping[str, object],
    path: Path = DEFAULT_PATHS.panel,
) -> None:
    """Fail closed when generated panel JSON differs from the tracked artifact."""

    if not generated_panel_matches_frozen(generated, path):
        raise FrozenPanelError("generated panel differs from the tracked V13 panel")


def _read_document(path: Path) -> dict[str, object]:
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrozenPanelError(f"cannot read frozen panel: {path}") from exc
    return _object(loaded, "panel")


def _parse_panel(document: dict[str, object]) -> tuple[GeneralizationCase, ...]:
    _require_fields(document, _PANEL_FIELDS, "panel")
    if document["exposed_only"] is not True:
        raise FrozenPanelError("panel.exposed_only must be true")
    _nonempty_string(document["selection_policy"], "panel.selection_policy")
    if document["canary_case_id"] != CASE_ORDER[0]:
        raise FrozenPanelError("panel canary does not match CASE_ORDER")

    records = _array(document["cases"], "panel.cases")
    case_count = _integer(document["case_count"], "panel.case_count")
    if case_count != len(records):
        raise FrozenPanelError("panel.case_count does not match panel.cases")

    cases = tuple(
        _parse_case(_object(value, f"panel.cases[{index}]"))
        for index, value in enumerate(records)
    )
    case_ids = tuple(case.case_id for case in cases)
    if len(case_ids) != len(set(case_ids)):
        raise FrozenPanelError("panel case IDs must be unique")
    if set(case_ids) != set(CASE_ORDER) or len(case_ids) != len(CASE_ORDER):
        raise FrozenPanelError("panel membership does not match CASE_ORDER exactly")
    return cases


def _parse_case(record: dict[str, object]) -> GeneralizationCase:
    case_id = _nonempty_string(record.get("case_id"), "case.case_id")
    where = f"case[{case_id}]"
    _require_fields(record, _CASE_FIELDS, where)
    source = _string(record["source"], f"{where}.source")
    source_sha256 = _string(record["source_sha256"], f"{where}.source_sha256")
    expected_sha256 = hashlib.sha256(source.encode()).hexdigest()
    if source_sha256 != expected_sha256:
        raise FrozenPanelError(f"{where}.source_sha256 does not match source")

    context_start = _integer(record["context_start"], f"{where}.context_start")
    context_end = _integer(record["context_end"], f"{where}.context_end")
    focus_start = _integer(record["focus_start"], f"{where}.focus_start")
    focus_end = _integer(record["focus_end"], f"{where}.focus_end")
    if not (
        0 <= context_start <= focus_start < focus_end <= context_end <= len(source)
    ):
        raise FrozenPanelError(f"{where} offsets are invalid or focus leaves context")

    local_context = _string(record["local_context"], f"{where}.local_context")
    focus_passage = _nonempty_string(
        record["focus_passage"],
        f"{where}.focus_passage",
    )
    if source[context_start:context_end] != local_context:
        raise FrozenPanelError(f"{where}.local_context does not resolve in source")
    if source[focus_start:focus_end] != focus_passage:
        raise FrozenPanelError(f"{where}.focus_passage does not resolve in source")

    return GeneralizationCase(
        case_id=case_id,
        family=_nonempty_string(record["family"], f"{where}.family"),
        source_id=_nonempty_string(record["source_id"], f"{where}.source_id"),
        source_sha256=source_sha256,
        source=source,
        context_start=context_start,
        context_end=context_end,
        local_context=local_context,
        focus_start=focus_start,
        focus_end=focus_end,
        focus_passage=focus_passage,
        reference=_parse_reference(
            _object(record["reference"], f"{where}.reference"),
            where,
        ),
    )


def _parse_reference(
    record: dict[str, object],
    case_where: str,
) -> GeneralizationReference:
    where = f"{case_where}.reference"
    _require_fields(record, _REFERENCE_FIELDS, where)
    events = tuple(
        _parse_event(_object(value, f"{where}.events[{index}]"), where)
        for index, value in enumerate(_array(record["events"], f"{where}.events"))
    )
    participants = tuple(
        _parse_participant(
            _object(value, f"{where}.participants[{index}]"),
            where,
        )
        for index, value in enumerate(
            _array(record["participants"], f"{where}.participants")
        )
    )
    arguments = tuple(
        _parse_argument(_object(value, f"{where}.arguments[{index}]"), where)
        for index, value in enumerate(_array(record["arguments"], f"{where}.arguments"))
    )
    axes = tuple(
        _parse_axes(_object(value, f"{where}.axes[{index}]"), where)
        for index, value in enumerate(_array(record["axes"], f"{where}.axes"))
    )
    _validate_reference_graph(events, participants, arguments, axes, where)

    root_event_key = _nonempty_string(
        record["root_event_key"],
        f"{where}.root_event_key",
    )
    if root_event_key not in {event.event_key for event in events}:
        raise FrozenPanelError(f"{where}.root_event_key is absent from events")
    return GeneralizationReference(
        events=events,
        participants=participants,
        arguments=arguments,
        axes=axes,
        root_event_key=root_event_key,
        reference_basis=_nonempty_string(
            record["reference_basis"],
            f"{where}.reference_basis",
        ),
    )


def _parse_event(record: dict[str, object], parent: str) -> ExpectedEvent:
    where = f"{parent}.event"
    _require_fields(record, _EVENT_FIELDS, where)
    return ExpectedEvent(
        event_key=_nonempty_string(record["event_key"], f"{where}.event_key"),
        event_type=cast(
            "EventType",
            _literal(record["event_type"], _EVENT_TYPES, f"{where}.event_type"),
        ),
        acceptable_triggers=_string_tuple(
            record["acceptable_triggers"],
            f"{where}.acceptable_triggers",
            require_nonempty=True,
        ),
    )


def _parse_participant(
    record: dict[str, object],
    parent: str,
) -> ExpectedParticipant:
    where = f"{parent}.participant"
    _require_fields(record, _PARTICIPANT_FIELDS, where)
    return ExpectedParticipant(
        participant_key=_nonempty_string(
            record["participant_key"],
            f"{where}.participant_key",
        ),
        entity_type=cast(
            "EntityType",
            _literal(
                record["entity_type"],
                _ENTITY_TYPES,
                f"{where}.entity_type",
            ),
        ),
        acceptable_texts=_string_tuple(
            record["acceptable_texts"],
            f"{where}.acceptable_texts",
            require_nonempty=True,
        ),
    )


def _parse_argument(record: dict[str, object], parent: str) -> ExpectedArgument:
    where = f"{parent}.argument"
    _require_fields(record, _ARGUMENT_FIELDS, where)
    return ExpectedArgument(
        event_key=_nonempty_string(record["event_key"], f"{where}.event_key"),
        role=cast(
            "ArgumentRole",
            _literal(record["role"], _ARGUMENT_ROLES, f"{where}.role"),
        ),
        target_kind=cast(
            "TargetKind",
            _literal(
                record["target_kind"],
                _TARGET_KINDS,
                f"{where}.target_kind",
            ),
        ),
        target_key=_nonempty_string(record["target_key"], f"{where}.target_key"),
    )


def _parse_axes(record: dict[str, object], parent: str) -> ExpectedAxes:
    where = f"{parent}.axes"
    _require_fields(record, _AXES_FIELDS, where)
    statistical_type = cast(
        "StatisticalType",
        _literal(
            record["statistical_type"],
            _STATISTICAL_TYPES,
            f"{where}.statistical_type",
        ),
    )
    acceptable_statistical_texts = _string_tuple(
        record["acceptable_statistical_texts"],
        f"{where}.acceptable_statistical_texts",
        require_nonempty=statistical_type != "NONE",
    )
    if statistical_type == "NONE" and acceptable_statistical_texts:
        raise FrozenPanelError(
            f"{where}.acceptable_statistical_texts must be empty for NONE"
        )
    return ExpectedAxes(
        event_key=_nonempty_string(record["event_key"], f"{where}.event_key"),
        direction=cast(
            "Direction",
            _literal(record["direction"], _DIRECTIONS, f"{where}.direction"),
        ),
        comparison=cast(
            "Comparison",
            _literal(record["comparison"], _COMPARISONS, f"{where}.comparison"),
        ),
        polarity=cast(
            "Polarity",
            _literal(record["polarity"], _POLARITIES, f"{where}.polarity"),
        ),
        uncertainty=cast(
            "Uncertainty",
            _literal(
                record["uncertainty"],
                _UNCERTAINTIES,
                f"{where}.uncertainty",
            ),
        ),
        statistical_type=statistical_type,
        acceptable_statistical_texts=acceptable_statistical_texts,
        author_interpretation=cast(
            "AuthorInterpretation",
            _literal(
                record["author_interpretation"],
                _AUTHOR_INTERPRETATIONS,
                f"{where}.author_interpretation",
            ),
        ),
    )


def _validate_reference_graph(
    events: tuple[ExpectedEvent, ...],
    participants: tuple[ExpectedParticipant, ...],
    arguments: tuple[ExpectedArgument, ...],
    axes: tuple[ExpectedAxes, ...],
    where: str,
) -> None:
    if not events:
        raise FrozenPanelError(f"{where}.events must not be empty")
    event_keys = tuple(event.event_key for event in events)
    participant_keys = tuple(item.participant_key for item in participants)
    if len(event_keys) != len(set(event_keys)):
        raise FrozenPanelError(f"{where}.event keys must be unique")
    if len(participant_keys) != len(set(participant_keys)):
        raise FrozenPanelError(f"{where}.participant keys must be unique")
    if set(event_keys) & set(participant_keys):
        raise FrozenPanelError(f"{where} event and participant keys overlap")

    axes_keys = tuple(item.event_key for item in axes)
    if len(axes_keys) != len(set(axes_keys)) or set(axes_keys) != set(event_keys):
        raise FrozenPanelError(f"{where}.axes must cover each event exactly once")
    for argument in arguments:
        if argument.event_key not in event_keys:
            raise FrozenPanelError(f"{where}.argument references an unknown event")
        targets = (
            participant_keys if argument.target_kind == "PARTICIPANT" else event_keys
        )
        if argument.target_key not in targets:
            raise FrozenPanelError(f"{where}.argument target is absent or mismatched")


def _require_fields(
    record: dict[str, object],
    expected: frozenset[str],
    where: str,
) -> None:
    present = set(record)
    if present != expected:
        missing = sorted(expected - present)
        extra = sorted(present - expected)
        raise FrozenPanelError(
            f"{where} fields differ; missing={missing}, extra={extra}"
        )


def _object(value: object, where: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise FrozenPanelError(f"{where} must be an object with string keys")
    return cast("dict[str, object]", value)


def _array(value: object, where: str) -> list[object]:
    if not isinstance(value, list):
        raise FrozenPanelError(f"{where} must be an array")
    return cast("list[object]", value)


def _string(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise FrozenPanelError(f"{where} must be a string")
    return value


def _nonempty_string(value: object, where: str) -> str:
    result = _string(value, where)
    if not result:
        raise FrozenPanelError(f"{where} must not be empty")
    return result


def _integer(value: object, where: str) -> int:
    if type(value) is not int:
        raise FrozenPanelError(f"{where} must be an integer")
    return value


def _literal(value: object, allowed: frozenset[str], where: str) -> str:
    result = _string(value, where)
    if result not in allowed:
        raise FrozenPanelError(f"{where} contains unsupported value: {result}")
    return result


def _string_tuple(
    value: object,
    where: str,
    *,
    require_nonempty: bool,
) -> tuple[str, ...]:
    values = tuple(
        _nonempty_string(item, f"{where}[{index}]")
        for index, item in enumerate(_array(value, where))
    )
    if require_nonempty and not values:
        raise FrozenPanelError(f"{where} must not be empty")
    if len(values) != len(set(values)):
        raise FrozenPanelError(f"{where} values must be unique")
    return values


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise FrozenPanelError("panel value is not canonical JSON") from exc


__all__ = [
    "FrozenPanelError",
    "assert_generated_panel_matches_frozen",
    "generated_panel_matches_frozen",
    "load_frozen_panel",
]
