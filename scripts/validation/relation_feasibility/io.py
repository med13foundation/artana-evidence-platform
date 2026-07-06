"""Input and output helpers for relation feasibility benchmark cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    GoldRelation,
    RelationReviewStatus,
    ValueLevel,
)

_VALID_VALUE_LEVELS = frozenset({"high", "medium", "low", "reject"})
_VALID_REVIEW_STATUSES = frozenset({"candidate", "review_only"})


def load_benchmark_cases(path: Path) -> tuple[BenchmarkCase, ...]:
    """Load benchmark cases from a JSON fixture file."""

    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        msg = f"Benchmark file must contain a JSON object: {path}"
        raise TypeError(msg)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        msg = f"Benchmark file must contain a cases list: {path}"
        raise TypeError(msg)
    return tuple(_parse_case(raw_case, path=path) for raw_case in raw_cases)


def _parse_case(raw_case: object, *, path: Path) -> BenchmarkCase:
    if not isinstance(raw_case, dict):
        msg = f"Benchmark case must be an object in {path}"
        raise TypeError(msg)
    case_id = _required_string(raw_case, "case_id", path=path)
    title = _required_string(raw_case, "title", path=path)
    category = _required_string(raw_case, "category", path=path)
    text = _required_string(raw_case, "text", path=path)
    raw_relations = raw_case.get("gold_relations", [])
    if not isinstance(raw_relations, list):
        msg = f"gold_relations must be a list for case {case_id}"
        raise TypeError(msg)
    return BenchmarkCase(
        case_id=case_id,
        title=title,
        category=category,
        text=text,
        gold_relations=tuple(
            _parse_gold_relation(raw_relation, case_id=case_id, path=path)
            for raw_relation in raw_relations
        ),
    )


def _parse_gold_relation(
    raw_relation: object,
    *,
    case_id: str,
    path: Path,
) -> GoldRelation:
    if not isinstance(raw_relation, dict):
        msg = f"Gold relation must be an object for case {case_id} in {path}"
        raise TypeError(msg)
    value_level = _required_string(raw_relation, "value_level", path=path)
    if value_level not in _VALID_VALUE_LEVELS:
        msg = (
            f"value_level for case {case_id} must be one of "
            f"{sorted(_VALID_VALUE_LEVELS)}"
        )
        raise ValueError(msg)
    return GoldRelation(
        subject=_required_string(raw_relation, "subject", path=path),
        relation_type=_required_string(raw_relation, "relation_type", path=path),
        object=_required_string(raw_relation, "object", path=path),
        support_sentence=_required_string(raw_relation, "support_sentence", path=path),
        value_level=cast("ValueLevel", value_level),
        rationale=_required_string(raw_relation, "rationale", path=path),
        subject_curie=_optional_str(raw_relation.get("subject_curie")),
        object_curie=_optional_str(raw_relation.get("object_curie")),
        requires_entailment=bool(raw_relation.get("requires_entailment", True)),
        review_status=_parse_review_status(raw_relation, case_id=case_id, path=path),
    )


def _parse_review_status(
    raw_relation: dict[str, object],
    *,
    case_id: str,
    path: Path,
) -> RelationReviewStatus:
    review_status = _optional_str(raw_relation.get("review_status")) or "candidate"
    if review_status not in _VALID_REVIEW_STATUSES:
        msg = (
            f"review_status for case {case_id} in {path} must be one of "
            f"{sorted(_VALID_REVIEW_STATUSES)}"
        )
        raise ValueError(msg)
    return cast("RelationReviewStatus", review_status)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_string(payload: dict[str, object], key: str, *, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or value.strip() == "":
        msg = f"Missing required string field '{key}' in {path}"
        raise ValueError(msg)
    return value.strip()
