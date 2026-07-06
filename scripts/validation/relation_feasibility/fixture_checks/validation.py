"""Validation helpers for relation feasibility benchmark fixtures."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    review_only_record_for_label,
)

JSONObject = dict[str, object]
_LONG_DOCUMENT_MIN_CHARACTERS = 600
_LONG_DOCUMENT_MIN_SENTENCES = 5
_NEAR_MISS_MIN_ENTITY_COUNT = 2
_NEGATED_RELATION_PHRASES = (
    "no evidence",
    "no relation",
    "not significant",
    "did not",
    "without",
    "not establish",
    "no sentence asserts",
)
_VALID_REVIEW_STATUSES = frozenset({"candidate", "review_only"})


@dataclass(frozen=True, slots=True)
class FixtureValidationIssue:
    """One structural fixture validation issue."""

    code: str
    message: str
    case_id: str | None = None


@dataclass(frozen=True, slots=True)
class FixtureCoverage:
    """Coverage counts for one relation feasibility fixture."""

    issue_count: int
    case_count: int
    high_value_specific_case_count: int
    low_value_review_case_count: int
    negative_control_case_count: int
    topic_counts: dict[str, int]


def validate_fixture_file(path: Path) -> tuple[FixtureValidationIssue, ...]:
    """Validate one fixture JSON file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_fixture_payload(payload)


def validate_fixture_payload(payload: object) -> tuple[FixtureValidationIssue, ...]:
    """Return structural validation issues for a fixture payload."""

    if not isinstance(payload, Mapping):
        return (
            FixtureValidationIssue(
                code="fixture_not_object",
                message="Fixture root must be a JSON object.",
            ),
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        return (
            FixtureValidationIssue(
                code="cases_not_list",
                message="Fixture root must contain a cases list.",
            ),
        )
    issues: list[FixtureValidationIssue] = []
    seen_case_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            issues.append(
                FixtureValidationIssue(
                    code="case_not_object",
                    message="Each fixture case must be an object.",
                ),
            )
            continue
        case_id = _string_field(raw_case, "case_id")
        if case_id is None:
            issues.append(
                FixtureValidationIssue(
                    code="missing_case_id",
                    message="Fixture case is missing case_id.",
                ),
            )
        elif case_id in seen_case_ids:
            issues.append(
                FixtureValidationIssue(
                    code="duplicate_case_id",
                    message=f"Duplicate case_id: {case_id}",
                    case_id=case_id,
                ),
            )
        else:
            seen_case_ids.add(case_id)
        issues.extend(_case_issues(raw_case, case_id=case_id))
    return tuple(issues)


def fixture_coverage(path: Path) -> FixtureCoverage:
    """Return validation and coverage counts for one fixture path."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_fixture_payload(payload)
    cases = _case_list(payload)
    topic_counts: Counter[str] = Counter()
    for case in cases:
        topic_counts.update(_case_topics(case))
    return FixtureCoverage(
        issue_count=len(issues),
        case_count=len(cases),
        high_value_specific_case_count=sum(
            1 for case in cases if _has_high_value_specific_gold(case)
        ),
        low_value_review_case_count=sum(
            1 for case in cases if _has_low_value_review_gold(case)
        ),
        negative_control_case_count=sum(1 for case in cases if _is_negative_case(case)),
        topic_counts=dict(topic_counts),
    )


def _case_issues(
    raw_case: Mapping[str, object],
    *,
    case_id: str | None,
) -> tuple[FixtureValidationIssue, ...]:
    issues: list[FixtureValidationIssue] = []
    raw_relations = raw_case.get("gold_relations")
    if raw_relations is None:
        raw_relations = []
    if not isinstance(raw_relations, list):
        return (
            FixtureValidationIssue(
                code="gold_relations_not_list",
                message="gold_relations must be a list when present.",
                case_id=case_id,
            ),
        )
    if _is_negative_case(raw_case) and raw_relations:
        issues.append(
            FixtureValidationIssue(
                code="negative_control_has_gold_relations",
                message="Negative-control cases must not contain gold relations.",
                case_id=case_id,
            ),
        )
    issues.extend(_topic_issues(raw_case, raw_relations, case_id=case_id))
    for raw_relation in raw_relations:
        if not isinstance(raw_relation, Mapping):
            issues.append(
                FixtureValidationIssue(
                    code="gold_relation_not_object",
                    message="Gold relation must be an object.",
                    case_id=case_id,
                ),
            )
            continue
        issues.extend(_relation_issues(raw_case, raw_relation, case_id=case_id))
    return tuple(issues)


def _relation_issues(
    raw_case: Mapping[str, object],
    raw_relation: Mapping[str, object],
    *,
    case_id: str | None,
) -> tuple[FixtureValidationIssue, ...]:
    issues: list[FixtureValidationIssue] = []
    for field in ("subject", "relation_type", "object"):
        if _string_field(raw_relation, field) is None:
            issues.append(
                FixtureValidationIssue(
                    code="missing_gold_relation_field",
                    message=f"Gold relation is missing {field}.",
                    case_id=case_id,
                ),
            )
    if _string_field(raw_relation, "support_sentence") is None:
        issues.append(
            FixtureValidationIssue(
                code="missing_support_sentence",
                message="Gold relation is missing support_sentence.",
                case_id=case_id,
            ),
        )
    value_level = _string_field(raw_relation, "value_level")
    review_status = _string_field(raw_relation, "review_status")
    if review_status is not None and review_status not in _VALID_REVIEW_STATUSES:
        issues.append(
            FixtureValidationIssue(
                code="invalid_review_status",
                message=(
                    "Gold relation review_status must be one of "
                    f"{sorted(_VALID_REVIEW_STATUSES)}."
                ),
                case_id=case_id,
            ),
        )
    if _is_weak_case(raw_case) and value_level is None:
        issues.append(
            FixtureValidationIssue(
                code="low_value_case_missing_value_level",
                message="Weak low-value cases must mark gold value_level.",
                case_id=case_id,
            ),
        )
    if _is_weak_case(raw_case):
        if _string_field(raw_relation, "review_status") != "review_only":
            issues.append(
                FixtureValidationIssue(
                    code="weak_case_not_review_only",
                    message="Weak low-value gold rows must be review-only.",
                    case_id=case_id,
                ),
            )
        if _bool_field(raw_relation, "requires_entailment") is not False:
            issues.append(
                FixtureValidationIssue(
                    code="weak_case_requires_entailment",
                    message="Weak low-value rows must not require trusted entailment.",
                    case_id=case_id,
                ),
            )
    if (
        value_level == "high"
        and _string_field(raw_relation, "review_status") != "review_only"
        and (
            _string_field(raw_relation, "subject_curie") is None
            or _string_field(raw_relation, "object_curie") is None
        )
    ):
        issues.append(
            FixtureValidationIssue(
                code="trusted_high_value_missing_curie",
                message=(
                    "Trusted high-value gold rows must include subject and object "
                    "CURIEs unless they are review-only."
                ),
                case_id=case_id,
            ),
        )
    if (
        value_level == "high"
        and _string_field(raw_relation, "review_status") != "review_only"
        and _bool_field(raw_relation, "requires_entailment") is not True
    ):
        issues.append(
            FixtureValidationIssue(
                code="trusted_high_value_missing_entailment_requirement",
                message="Trusted high-value gold rows must require entailment.",
                case_id=case_id,
            ),
        )
    issues.extend(_review_only_endpoint_curie_issues(raw_relation, case_id))
    if (
        value_level in {"high", "medium"}
        and _string_field(raw_relation, "review_status") != "review_only"
    ):
        issues.extend(_trusted_relation_review_only_endpoint_issues(raw_relation, case_id))
    return tuple(issues)


def _review_only_endpoint_curie_issues(
    raw_relation: Mapping[str, object],
    case_id: str | None,
) -> tuple[FixtureValidationIssue, ...]:
    issues: list[FixtureValidationIssue] = []
    for endpoint_field in ("subject", "object"):
        label = _string_field(raw_relation, endpoint_field)
        curie = _string_field(raw_relation, f"{endpoint_field}_curie")
        if (
            label is None
            or curie is None
            or review_only_record_for_label(label) is None
        ):
            continue
        issues.append(
            FixtureValidationIssue(
                code="review_only_endpoint_has_curie",
                message=(
                    "Gold endpoint labels governed as review-only must not keep "
                    f"trusted CURIEs: {endpoint_field}={label}"
                ),
                case_id=case_id,
            ),
        )
    return tuple(issues)


def _trusted_relation_review_only_endpoint_issues(
    raw_relation: Mapping[str, object],
    case_id: str | None,
) -> tuple[FixtureValidationIssue, ...]:
    issues: list[FixtureValidationIssue] = []
    for endpoint_field in ("subject", "object"):
        label = _string_field(raw_relation, endpoint_field)
        if label is None or review_only_record_for_label(label) is None:
            continue
        issues.append(
            FixtureValidationIssue(
                code="trusted_gold_uses_review_only_endpoint",
                message=(
                    "Trusted high/medium gold rows must not use endpoint labels "
                    f"that grounding policy marks review-only: {endpoint_field}={label}"
                ),
                case_id=case_id,
            ),
        )
    return tuple(issues)


def _topic_issues(
    raw_case: Mapping[str, object],
    raw_relations: Sequence[object],
    *,
    case_id: str | None,
) -> tuple[FixtureValidationIssue, ...]:
    issues: list[FixtureValidationIssue] = []
    topics = set(_case_topics(raw_case))
    text = _string_field(raw_case, "text") or ""
    if "long_document_chunking" in topics and (
        len(text) < _LONG_DOCUMENT_MIN_CHARACTERS
        or _sentence_count(text) < _LONG_DOCUMENT_MIN_SENTENCES
    ):
        issues.append(
            FixtureValidationIssue(
                code="long_document_case_too_short",
                message=(
                    "Long-document chunking cases must contain enough text and "
                    "sentences to stress chunk-local extraction."
                ),
                case_id=case_id,
            ),
        )
    if "adversarial_negated_near_miss" in topics:
        if not _has_negated_relation_phrase(text):
            issues.append(
                FixtureValidationIssue(
                    code="near_miss_missing_negation",
                    message=(
                        "Adversarial near-miss cases must contain negated "
                        "relation language."
                    ),
                    case_id=case_id,
                ),
            )
        near_miss_entities = _string_sequence_field(raw_case, "near_miss_entities")
        lowered_text = text.lower()
        if len(near_miss_entities) < _NEAR_MISS_MIN_ENTITY_COUNT or any(
            entity.lower() not in lowered_text for entity in near_miss_entities
        ):
            issues.append(
                FixtureValidationIssue(
                    code="near_miss_entities_missing",
                    message=(
                        "Adversarial near-miss cases must list at least two "
                        "co-mentioned entities that appear in the text."
                    ),
                    case_id=case_id,
                ),
            )
        if raw_relations:
            issues.append(
                FixtureValidationIssue(
                    code="near_miss_has_gold_relations",
                    message="Adversarial near-miss cases must not contain gold relations.",
                    case_id=case_id,
                ),
            )
    return tuple(issues)


def _case_list(payload: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(payload, Mapping):
        return ()
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        return ()
    return tuple(case for case in raw_cases if isinstance(case, Mapping))


def _relation_list(case: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw_relations = case.get("gold_relations")
    if not isinstance(raw_relations, list):
        return ()
    return tuple(
        relation for relation in raw_relations if isinstance(relation, Mapping)
    )


def _case_topics(case: Mapping[str, object]) -> tuple[str, ...]:
    raw_topics = case.get("topics")
    if not isinstance(raw_topics, Sequence) or isinstance(raw_topics, str):
        return ()
    return tuple(topic.strip() for topic in raw_topics if isinstance(topic, str))


def _string_sequence_field(
    payload: Mapping[str, object],
    field: str,
) -> tuple[str, ...]:
    raw_value = payload.get(field)
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, str):
        return ()
    return tuple(
        value.strip() for value in raw_value if isinstance(value, str) and value.strip()
    )


def _is_negative_case(case: Mapping[str, object]) -> bool:
    category = _string_field(case, "category")
    return category == "negative_control" or "negative_control" in _case_topics(case)


def _is_weak_case(case: Mapping[str, object]) -> bool:
    category = _string_field(case, "category") or ""
    return category.startswith("weak") or "low_value_review" in _case_topics(case)


def _has_high_value_specific_gold(case: Mapping[str, object]) -> bool:
    if _is_negative_case(case) or _is_weak_case(case):
        return False
    return any(
        _string_field(relation, "value_level") == "high"
        for relation in _relation_list(case)
    )


def _has_low_value_review_gold(case: Mapping[str, object]) -> bool:
    return any(
        _string_field(relation, "value_level") == "low"
        or _string_field(relation, "review_status") == "review_only"
        for relation in _relation_list(case)
    )


def _string_field(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _bool_field(payload: Mapping[str, object], field: str) -> bool | None:
    value = payload.get(field)
    return value if isinstance(value, bool) else None


def _sentence_count(text: str) -> int:
    return sum(text.count(separator) for separator in (".", "?", "!"))


def _has_negated_relation_phrase(text: str) -> bool:
    lowered_text = text.lower()
    return any(phrase in lowered_text for phrase in _NEGATED_RELATION_PHRASES)


__all__ = [
    "FixtureCoverage",
    "FixtureValidationIssue",
    "fixture_coverage",
    "validate_fixture_file",
    "validate_fixture_payload",
]
