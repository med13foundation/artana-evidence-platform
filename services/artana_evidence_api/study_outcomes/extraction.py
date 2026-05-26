"""Pattern-backed extraction of quantitative trial outcomes from PubMed documents."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from artana_evidence_api.study_outcomes.contracts import StudyOutcomeDraft
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord

_TRIAL_PUBLICATION_MARKERS = (
    "clinical trial",
    "randomized controlled trial",
    "randomised controlled trial",
)
_ARM_PATTERN = re.compile(
    r"(?P<intervention>[A-Z][A-Za-z0-9+/\-(), ]{2,120}?)\s+"
    r"(?:vs\.?|versus|compared with|compared to)\s+"
    r"(?P<comparator>[A-Za-z0-9+/\-(), ]{2,120}?)"
    r"(?=\s+(?:median|[0-9]+[- ](?:year|yr)|HR\b|hazard ratio|"
    r"objective response rate|ORR)|[;,.]|$)",
    re.IGNORECASE,
)
_MEDIAN_PATTERN = re.compile(
    r"\bmedian\s+"
    r"(?P<metric>overall survival|progression[- ]free survival|OS|PFS)\s*"
    r"(?:was|were|of|:)?\s*"
    r"(?P<first>[0-9]+(?:\.[0-9]+)?)\s*"
    r"(?P<unit>months?|mo)?\s*"
    r"(?:vs\.?|versus|compared with|compared to)\s*"
    r"(?P<second>[0-9]+(?:\.[0-9]+)?)\s*"
    r"(?P<unit_after>months?|mo)?",
    re.IGNORECASE,
)
_SURVIVAL_RATE_PATTERN = re.compile(
    r"\b(?P<year>[0-9]+)[- ](?:year|yr)\s+"
    r"(?P<metric>OS|overall survival)\s*"
    r"(?:was|were|of|:)?\s*"
    r"(?P<first>[0-9]+(?:\.[0-9]+)?)\s*%\s*"
    r"(?:vs\.?|versus|compared with|compared to)\s*"
    r"(?P<second>[0-9]+(?:\.[0-9]+)?)\s*%",
    re.IGNORECASE,
)
_HAZARD_RATIO_PATTERN = re.compile(
    r"\b(?:HR|hazard ratio)\b\s*(?:=|of|:)?\s*"
    r"(?P<value>[0-9]+(?:\.[0-9]+)?)"
    r"(?:\s*\((?:95%\s*)?CI\s*"
    r"(?P<low>[0-9]+(?:\.[0-9]+)?)\s*(?:-|to)\s*"
    r"(?P<high>[0-9]+(?:\.[0-9]+)?)\))?",
    re.IGNORECASE,
)
_ORR_PATTERN = re.compile(
    r"\b(?:objective response rate|ORR)\b\s*"
    r"(?:was|were|of|:)?\s*"
    r"(?P<first>[0-9]+(?:\.[0-9]+)?)\s*%"
    r"(?:\s*(?:vs\.?|versus|compared with|compared to)\s*"
    r"(?P<second>[0-9]+(?:\.[0-9]+)?)\s*%)?",
    re.IGNORECASE,
)
_POPULATION_PATTERN = re.compile(
    r"\bin\s+(?P<population>[^.;:]{2,90}?"
    r"(?:subgroup|population|patients|cohort))\b",
    re.IGNORECASE,
)
_N_PATTERN = re.compile(r"\b[Nn]\s*=\s*(?P<n>[0-9]{1,6})\b")


def document_supports_study_outcome_extraction(
    document: HarnessDocumentRecord,
) -> bool:
    """Return true when a document is a PubMed clinical-trial record."""

    if document.source_type != "pubmed":
        return False
    publication_types = _publication_types_from_metadata(document.metadata)
    if not publication_types:
        return False
    joined = " ".join(publication_types).casefold()
    return any(marker in joined for marker in _TRIAL_PUBLICATION_MARKERS)


def extract_study_outcome_drafts(
    document: HarnessDocumentRecord,
) -> tuple[StudyOutcomeDraft, ...]:
    """Extract structured quantitative outcomes from one eligible document."""

    if not document_supports_study_outcome_extraction(document):
        return ()
    source_pmid = _source_pmid(document.metadata)
    drafts: list[StudyOutcomeDraft] = []
    for sentence in _sentences(document.text_content):
        arms = _arms_for_sentence(sentence)
        population = _population_from_sentence(sentence)
        n_value = _n_from_sentence(sentence)
        drafts.extend(
            _median_outcomes(
                sentence=sentence,
                arms=arms,
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
            ),
        )
        drafts.extend(
            _survival_rate_outcomes(
                sentence=sentence,
                arms=arms,
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
            ),
        )
        drafts.extend(
            _orr_outcomes(
                sentence=sentence,
                arms=arms,
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
            ),
        )
        drafts.extend(
            _hazard_ratio_outcomes(
                sentence=sentence,
                arms=arms,
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
            ),
        )
    return tuple(drafts)


def _publication_types_from_metadata(metadata: Mapping[str, object]) -> list[str]:
    publication_types: list[str] = []
    _append_string_values(publication_types, metadata.get("publication_types"))
    nested_pubmed = metadata.get("pubmed")
    if isinstance(nested_pubmed, Mapping):
        _append_string_values(publication_types, nested_pubmed.get("publication_types"))
    source_capture = metadata.get("source_capture")
    if isinstance(source_capture, Mapping):
        _append_string_values(publication_types, source_capture.get("publication_types"))
    return publication_types


def _append_string_values(target: list[str], value: object) -> None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized != "":
            target.append(normalized)
        return
    if not isinstance(value, Sequence):
        return
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized != "":
            target.append(normalized)


def _source_pmid(metadata: Mapping[str, object]) -> str:
    for key in ("pmid", "pubmed_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    nested_pubmed = metadata.get("pubmed")
    if isinstance(nested_pubmed, Mapping):
        for key in ("pmid", "pubmed_id"):
            value = nested_pubmed.get(key)
            if isinstance(value, str) and value.strip() != "":
                return value.strip()
    return ""


def _sentences(text: str) -> tuple[str, ...]:
    normalized = " ".join(text.replace("\n", " ").split())
    if normalized == "":
        return ()
    return tuple(
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip() != ""
    )


def _arms_for_sentence(sentence: str) -> tuple[str, str] | None:
    match = _ARM_PATTERN.search(sentence)
    if match is None:
        return None
    intervention = _clean_arm(match.group("intervention"))
    comparator = _clean_arm(match.group("comparator"))
    if intervention == "" or comparator == "":
        return None
    return intervention, comparator


def _clean_arm(value: str) -> str:
    normalized = " ".join(value.split()).strip(" ,.;:")
    if "," in normalized:
        normalized = normalized.rsplit(",", maxsplit=1)[-1].strip()
    return normalized


def _population_from_sentence(sentence: str) -> str:
    match = _POPULATION_PATTERN.search(sentence)
    if match is None:
        return "reported trial population"
    population = " ".join(match.group("population").split()).strip(" ,.;:")
    if population.casefold().startswith("the "):
        population = population[4:].strip()
    return population or "reported trial population"


def _n_from_sentence(sentence: str) -> int | None:
    match = _N_PATTERN.search(sentence)
    if match is None:
        return None
    return int(match.group("n"))


def _median_metric(raw_metric: str) -> str:
    normalized = raw_metric.casefold().replace("-", " ")
    if normalized in {"os", "overall survival"}:
        return "median_overall_survival"
    return "median_progression_free_survival"


def _month_unit(raw_unit: str | None) -> str:
    del raw_unit
    return "months"


def _year_metric(raw_year: str) -> str:
    if raw_year == "2":
        return "two_year_overall_survival_rate"
    if raw_year == "5":
        return "five_year_overall_survival_rate"
    return f"{raw_year}_year_overall_survival_rate"


def _base_metadata() -> JSONObject:
    return {"extraction_method": "pattern_v1"}


def _paired_outcomes(
    *,
    arms: tuple[str, str] | None,
    outcome_metric: str,
    first_value: float,
    second_value: float | None,
    unit: str,
    population: str,
    n_value: int | None,
    source_pmid: str,
    source_quote: str,
) -> list[StudyOutcomeDraft]:
    intervention = arms[0] if arms is not None else "reported intervention"
    comparator = arms[1] if arms is not None else None
    outcomes = [
        StudyOutcomeDraft(
            intervention=intervention,
            comparator=comparator,
            outcome_metric=outcome_metric,
            value=first_value,
            unit=unit,
            confidence_interval_low=None,
            confidence_interval_high=None,
            population=population,
            n=n_value,
            source_pmid=source_pmid,
            source_quote=source_quote,
            metadata=_base_metadata(),
        ),
    ]
    if second_value is not None and arms is not None:
        outcomes.append(
            StudyOutcomeDraft(
                intervention=arms[1],
                comparator=arms[0],
                outcome_metric=outcome_metric,
                value=second_value,
                unit=unit,
                confidence_interval_low=None,
                confidence_interval_high=None,
                population=population,
                n=n_value,
                source_pmid=source_pmid,
                source_quote=source_quote,
                metadata=_base_metadata(),
            ),
        )
    return outcomes


def _median_outcomes(
    *,
    sentence: str,
    arms: tuple[str, str] | None,
    population: str,
    n_value: int | None,
    source_pmid: str,
) -> list[StudyOutcomeDraft]:
    outcomes: list[StudyOutcomeDraft] = []
    for match in _MEDIAN_PATTERN.finditer(sentence):
        unit = _month_unit(match.group("unit") or match.group("unit_after"))
        outcomes.extend(
            _paired_outcomes(
                arms=arms,
                outcome_metric=_median_metric(match.group("metric")),
                first_value=float(match.group("first")),
                second_value=float(match.group("second")),
                unit=unit,
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
                source_quote=sentence,
            ),
        )
    return outcomes


def _survival_rate_outcomes(
    *,
    sentence: str,
    arms: tuple[str, str] | None,
    population: str,
    n_value: int | None,
    source_pmid: str,
) -> list[StudyOutcomeDraft]:
    outcomes: list[StudyOutcomeDraft] = []
    for match in _SURVIVAL_RATE_PATTERN.finditer(sentence):
        outcomes.extend(
            _paired_outcomes(
                arms=arms,
                outcome_metric=_year_metric(match.group("year")),
                first_value=float(match.group("first")),
                second_value=float(match.group("second")),
                unit="percent",
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
                source_quote=sentence,
            ),
        )
    return outcomes


def _orr_outcomes(
    *,
    sentence: str,
    arms: tuple[str, str] | None,
    population: str,
    n_value: int | None,
    source_pmid: str,
) -> list[StudyOutcomeDraft]:
    outcomes: list[StudyOutcomeDraft] = []
    for match in _ORR_PATTERN.finditer(sentence):
        raw_second_value = match.group("second")
        outcomes.extend(
            _paired_outcomes(
                arms=arms,
                outcome_metric="objective_response_rate",
                first_value=float(match.group("first")),
                second_value=(
                    float(raw_second_value) if raw_second_value is not None else None
                ),
                unit="percent",
                population=population,
                n_value=n_value,
                source_pmid=source_pmid,
                source_quote=sentence,
            ),
        )
    return outcomes


def _hazard_ratio_outcomes(
    *,
    sentence: str,
    arms: tuple[str, str] | None,
    population: str,
    n_value: int | None,
    source_pmid: str,
) -> list[StudyOutcomeDraft]:
    outcomes: list[StudyOutcomeDraft] = []
    for match in _HAZARD_RATIO_PATTERN.finditer(sentence):
        intervention = arms[0] if arms is not None else "reported intervention"
        comparator = arms[1] if arms is not None else None
        low = match.group("low")
        high = match.group("high")
        outcomes.append(
            StudyOutcomeDraft(
                intervention=intervention,
                comparator=comparator,
                outcome_metric="hazard_ratio",
                value=float(match.group("value")),
                unit="ratio",
                confidence_interval_low=float(low) if low is not None else None,
                confidence_interval_high=float(high) if high is not None else None,
                population=population,
                n=n_value,
                source_pmid=source_pmid,
                source_quote=sentence,
                metadata=_base_metadata(),
            ),
        )
    return outcomes


__all__ = [
    "document_supports_study_outcome_extraction",
    "extract_study_outcome_drafts",
]
