"""Evidence-quality grade inference from source metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from artana_evidence_api.types.common import JSONObject

HIGH_EVIDENCE_GRADE: Final = "High"
MODERATE_EVIDENCE_GRADE: Final = "Moderate"
LIMITED_EVIDENCE_GRADE: Final = "Limited"
MECHANISM_CONTEXT_EVIDENCE_GRADE: Final = "Limited (mechanism/context only)"
PROVISIONAL_LIMITED_EVIDENCE_GRADE: Final = "Limited (provisional)"
TRIAL_EXISTENCE_EVIDENCE_GRADE: Final = "Provisional (trial-existence only)"
_LIMITED_SAMPLE_SIZE_THRESHOLD: Final = 20

_CANONICAL_GRADES: Final[tuple[str, ...]] = (
    HIGH_EVIDENCE_GRADE,
    MODERATE_EVIDENCE_GRADE,
    LIMITED_EVIDENCE_GRADE,
    MECHANISM_CONTEXT_EVIDENCE_GRADE,
    PROVISIONAL_LIMITED_EVIDENCE_GRADE,
    TRIAL_EXISTENCE_EVIDENCE_GRADE,
)
_GRADE_ALIASES: Final[dict[str, str]] = {
    "high": HIGH_EVIDENCE_GRADE,
    "moderate": MODERATE_EVIDENCE_GRADE,
    "limited": LIMITED_EVIDENCE_GRADE,
    "limited mechanism context only": MECHANISM_CONTEXT_EVIDENCE_GRADE,
    "limited mechanism/context only": MECHANISM_CONTEXT_EVIDENCE_GRADE,
    "limited provisional": PROVISIONAL_LIMITED_EVIDENCE_GRADE,
    "provisional": TRIAL_EXISTENCE_EVIDENCE_GRADE,
    "provisional trial existence only": TRIAL_EXISTENCE_EVIDENCE_GRADE,
    "provisional trial-existence only": TRIAL_EXISTENCE_EVIDENCE_GRADE,
}


def normalize_evidence_grade(value: str | None) -> str | None:
    """Return one display-safe evidence grade label."""
    if not isinstance(value, str):
        return None
    stripped = " ".join(value.strip().split())
    if stripped == "":
        return None
    grade_key = _normalized_text(stripped)
    return _GRADE_ALIASES.get(grade_key) or next(
        (grade for grade in _CANONICAL_GRADES if _normalized_text(grade) == grade_key),
        stripped,
    )


def infer_evidence_grade_from_metadata(
    metadata: Mapping[str, object],
    *,
    source_type: str | None = None,
) -> str | None:
    """Infer a patient-facing evidence-quality grade from source metadata."""
    existing_grade = _string_value(metadata.get("evidence_grade"))
    normalized_existing_grade = normalize_evidence_grade(existing_grade)
    if normalized_existing_grade is not None:
        return normalized_existing_grade

    source_text = _normalized_text(
        " ".join(
            text
            for text in (
                source_type,
                _string_value(metadata.get("source")),
                _string_value(metadata.get("source_type")),
                _string_value(metadata.get("source_key")),
            )
            if text is not None
        ),
    )
    publication_types = _publication_types_from_metadata(metadata)
    source_grade = _grade_from_source_text(
        source_text=source_text,
        publication_types=publication_types,
        metadata=metadata,
    )
    if source_grade is not None:
        return source_grade

    sample_size = _sample_size_from_metadata(metadata)
    if sample_size is not None and sample_size < _LIMITED_SAMPLE_SIZE_THRESHOLD:
        return LIMITED_EVIDENCE_GRADE

    return _grade_from_publication_types(publication_types)


def _grade_from_source_text(
    *,
    source_text: str,
    publication_types: Sequence[str],
    metadata: Mapping[str, object],
) -> str | None:
    if (
        "clinicaltrials gov" in source_text or "clinical trials gov" in source_text
    ) and not _has_trial_results(metadata):
        return TRIAL_EXISTENCE_EVIDENCE_GRADE
    joined_publication_types = _normalized_text(" ".join(publication_types))
    if "preprint" in source_text or "preprint" in joined_publication_types:
        return PROVISIONAL_LIMITED_EVIDENCE_GRADE
    return None


def _grade_from_publication_types(publication_types: Sequence[str]) -> str | None:
    if not publication_types:
        return None
    joined_publication_types = _normalized_text(" ".join(publication_types))
    if _has_any_phrase(
        joined_publication_types,
        (
            "randomized controlled trial",
            "randomised controlled trial",
            "meta analysis",
            "phase iii",
        ),
    ):
        return HIGH_EVIDENCE_GRADE
    if _has_any_phrase(
        joined_publication_types,
        (
            "phase ii",
            "non randomized",
            "nonrandomized",
            "clinical trial",
            "observational",
            "retrospective",
            "case control",
        ),
    ):
        return MODERATE_EVIDENCE_GRADE
    if _has_any_phrase(
        joined_publication_types,
        ("case report", "case series"),
    ):
        return LIMITED_EVIDENCE_GRADE
    if "review" in joined_publication_types:
        return MECHANISM_CONTEXT_EVIDENCE_GRADE
    return None


def _has_any_phrase(text: str, phrases: Sequence[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def evidence_grade_for_document(document: object) -> str | None:
    """Infer an evidence grade from a document-like record."""
    metadata = getattr(document, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    source_type = getattr(document, "source_type", None)
    return infer_evidence_grade_from_metadata(
        metadata,
        source_type=source_type if isinstance(source_type, str) else None,
    )


def metadata_with_evidence_grade(
    metadata: JSONObject,
    evidence_grade: str | None,
) -> JSONObject:
    """Return metadata with a grade hint when a grade is known."""
    normalized_grade = normalize_evidence_grade(evidence_grade)
    if normalized_grade is None:
        return dict(metadata)
    return {**metadata, "evidence_grade": normalized_grade}


def _publication_types_from_metadata(metadata: Mapping[str, object]) -> list[str]:
    collected: list[str] = []
    _extend_unique(collected, _string_list(metadata.get("publication_types")))
    _extend_unique(collected, _string_list(metadata.get("publication_type")))
    for key in (
        "pubmed",
        "article",
        "selected_record",
        "normalized_record",
        "source_capture",
        "source_metadata",
    ):
        nested = metadata.get(key)
        if isinstance(nested, Mapping):
            _extend_unique(collected, _publication_types_from_metadata(nested))
    return collected


def _has_trial_results(metadata: Mapping[str, object]) -> bool:
    for value in (
        metadata.get("has_results"),
        metadata.get("results_available"),
        metadata.get("published_results"),
    ):
        if isinstance(value, bool):
            return value
    clinical_trial = metadata.get("clinical_trial")
    if isinstance(clinical_trial, Mapping):
        return _has_trial_results(clinical_trial)
    return False


def _sample_size_from_metadata(metadata: Mapping[str, object]) -> int | None:
    for key in ("sample_size", "n", "participant_count", "enrollment"):
        parsed = _int_value(metadata.get(key))
        if parsed is not None:
            return parsed
    for key in ("study", "clinical_trial", "cohort"):
        nested = metadata.get(key)
        if isinstance(nested, Mapping):
            parsed = _sample_size_from_metadata(nested)
            if parsed is not None:
                return parsed
    return None


def _extend_unique(target: list[str], values: Sequence[str]) -> None:
    seen = {_normalized_text(value) for value in target}
    for value in values:
        key = _normalized_text(value)
        if key != "" and key not in seen:
            target.append(value)
            seen.add(key)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() != "" else []
    if not isinstance(value, Sequence):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip() != ""]


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _normalized_text(value: str) -> str:
    normalized = value.casefold().replace("_", " ")
    return " ".join(
        normalized.replace("(", " ")
        .replace(")", " ")
        .replace(",", " ")
        .replace(".", " ")
        .replace(":", " ")
        .split(),
    )
