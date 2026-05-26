"""Deterministic live ClinicalTrials.gov trial matching."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from artana_evidence_api.source_enrichment_bridges import GatewayFetchResultProtocol

from .contracts import (
    TrialMatchingQuery,
    TrialMatchingResponse,
    TrialMatchLocation,
    TrialMatchResponse,
)

_AGE_PATTERN = re.compile(r"(\d+)")
_US_COUNTRY_VALUES = {"us", "usa", "u.s.", "u.s.a.", "united states"}
_TREATMENT_SYNONYMS = {
    "tmz": ("temozolomide",),
}


class TrialMatchingGatewayProtocol(Protocol):
    """ClinicalTrials.gov gateway shape needed by request-time matching."""

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
        condition: str | None = None,
        overall_statuses: tuple[str, ...] = (),
        location: str | None = None,
        geo_filter: str | None = None,
    ) -> GatewayFetchResultProtocol: ...


class TrialMatchingGatewayUnavailableError(RuntimeError):
    """Raised when the live ClinicalTrials.gov gateway cannot serve a match."""


async def match_clinical_trials(
    *,
    space_id: UUID,
    query: TrialMatchingQuery,
    gateway: TrialMatchingGatewayProtocol,
) -> TrialMatchingResponse:
    """Fetch live CT.gov records and rank them against patient context."""

    try:
        fetch_result = await gateway.fetch_records_async(
            query=_gateway_query(query),
            condition=query.condition,
            overall_statuses=query.statuses,
            location=_location_query(query),
            geo_filter=_geo_filter(query),
            max_results=query.max_results,
        )
    except RuntimeError as exc:
        msg = f"ClinicalTrials.gov trial matching failed: {exc}"
        raise TrialMatchingGatewayUnavailableError(msg) from exc

    matches = [
        match
        for record in fetch_result.records
        if (match := _match_record(record, query)) is not None
    ]
    matches.sort(
        key=lambda match: (
            match.relevance_score,
            _status_priority(match.status),
            match.nct_id,
        ),
        reverse=True,
    )
    return TrialMatchingResponse(
        space_id=space_id,
        query=query,
        trial_matches=matches,
        total=len(matches),
        generated_at=datetime.now(UTC),
    )


def parse_list_parameter(value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated query parameter into normalized terms."""

    if value is None:
        return ()
    return tuple(
        dict.fromkeys(
            " ".join(part.replace("_", " ").split())
            for part in value.split(",")
            if " ".join(part.replace("_", " ").split())
        ),
    )


def parse_status_parameter(value: str | None) -> tuple[str, ...]:
    """Parse a pipe- or comma-separated status query parameter."""

    if value is None:
        return ("RECRUITING", "NOT_YET_RECRUITING")
    return tuple(
        dict.fromkeys(
            " ".join(part.split()).upper()
            for part in value.replace(",", "|").split("|")
            if " ".join(part.split())
        ),
    ) or ("RECRUITING", "NOT_YET_RECRUITING")


def _match_record(
    record: Mapping[str, object],
    query: TrialMatchingQuery,
) -> TrialMatchResponse | None:
    nct_id = _string(record, "nct_id")
    if not nct_id:
        return None
    status = _string(record, "overall_status")
    if query.statuses and status.upper() not in query.statuses:
        return None
    if query.age is not None and not _age_matches_record(
        age=query.age,
        record=record,
    ):
        return None

    locations = _locations(record=record, query=query)
    matched_terms = _matched_terms(record=record, query=query)
    relevance_score, relevance_reasons = _score_record(
        record=record,
        query=query,
        locations=locations,
        matched_terms=matched_terms,
    )
    return TrialMatchResponse(
        nct_id=nct_id,
        title=_string(record, "brief_title") or _string(record, "official_title"),
        status=status,
        phase=_string_list(record, "phases"),
        conditions=_string_list(record, "conditions"),
        intervention_names=_intervention_names(record),
        eligibility_summary=_summary(_string(record, "eligibility_criteria")),
        minimum_age=_optional_string(record, "minimum_age"),
        maximum_age=_optional_string(record, "maximum_age"),
        sex=_optional_string(record, "sex"),
        locations=locations,
        primary_investigator=_primary_investigator(record),
        contact_email=_contact_email(record=record, locations=locations),
        relevance_score=relevance_score,
        relevance_reasons=relevance_reasons,
        matched_terms=matched_terms,
        source_url=f"https://clinicaltrials.gov/study/{nct_id}",
    )


def _gateway_query(query: TrialMatchingQuery) -> str:
    terms = [*query.molecular_markers, *query.prior_treatments]
    return " ".join(terms) if terms else query.condition


def _location_query(query: TrialMatchingQuery) -> str | None:
    values = [value for value in (query.reference_city, query.country) if value]
    return ", ".join(values) if values else None


def _geo_filter(query: TrialMatchingQuery) -> str | None:
    if (
        query.reference_latitude is None
        or query.reference_longitude is None
        or query.within_miles is None
    ):
        return None
    return (
        f"distance({query.reference_latitude:g},"
        f"{query.reference_longitude:g},{query.within_miles}mi)"
    )


def _score_record(
    *,
    record: Mapping[str, object],
    query: TrialMatchingQuery,
    locations: list[TrialMatchLocation],
    matched_terms: list[str],
) -> tuple[float, list[str]]:
    score = 0.2
    reasons = ["active recruitment status"]
    if _condition_matches(record=record, condition=query.condition):
        score += 0.15
        reasons.append("condition match")
    if query.age is not None:
        score += 0.1
        reasons.append("age within eligibility bounds")
    if locations and (query.reference_city or query.country):
        score += 0.1
        reasons.append("location match")
    if matched_terms:
        score += min(0.4, 0.1 * len(matched_terms))
        reasons.append("patient-context term match")
    return min(1.0, round(score, 3)), reasons


def _condition_matches(*, record: Mapping[str, object], condition: str) -> bool:
    condition_text = condition.casefold()
    return any(condition_text in item.casefold() for item in _string_list(record, "conditions"))


def _age_matches_record(*, age: int, record: Mapping[str, object]) -> bool:
    minimum_age = _age_years(_string(record, "minimum_age"))
    maximum_age = _age_years(_string(record, "maximum_age"))
    if minimum_age is not None and age < minimum_age:
        return False
    return not (maximum_age is not None and age > maximum_age)


def _age_years(value: str) -> int | None:
    match = _AGE_PATTERN.search(value)
    if match is None:
        return None
    return int(match.group(1))


def _matched_terms(
    *,
    record: Mapping[str, object],
    query: TrialMatchingQuery,
) -> list[str]:
    haystack = _record_search_text(record)
    terms = [*query.molecular_markers, *query.prior_treatments]
    matched: list[str] = []
    for term in terms:
        candidates = (term, *_TREATMENT_SYNONYMS.get(term.casefold(), ()))
        if any(candidate.casefold() in haystack for candidate in candidates):
            matched.append(term)
    return list(dict.fromkeys(matched))


def _record_search_text(record: Mapping[str, object]) -> str:
    values = [
        _string(record, "brief_title"),
        _string(record, "official_title"),
        _string(record, "brief_summary"),
        _string(record, "eligibility_criteria"),
        " ".join(_string_list(record, "conditions")),
        " ".join(_intervention_names(record)),
    ]
    return " ".join(values).casefold()


def _locations(
    *,
    record: Mapping[str, object],
    query: TrialMatchingQuery,
) -> list[TrialMatchLocation]:
    location_records = _mapping_list(record, "locations")
    matches = [
        location
        for location in (
            _location_response(location_record)
            for location_record in location_records
        )
        if location is not None and _location_matches(location=location, query=query)
    ]
    if matches:
        return matches[:10]
    fallback = [
        location
        for location in (
            _location_response(location_record)
            for location_record in location_records
        )
        if location is not None
    ]
    return fallback[:10]


def _location_response(
    location_record: Mapping[str, object],
) -> TrialMatchLocation | None:
    facility = _string(location_record, "facility")
    city = _string(location_record, "city")
    country = _string(location_record, "country")
    if not any((facility, city, country)):
        return None
    contact = _first_contact(_mapping_list(location_record, "contacts"))
    geo_point = _mapping_value(location_record.get("geo_point"))
    return TrialMatchLocation(
        facility=facility,
        status=_string(location_record, "status"),
        city=city,
        state=_string(location_record, "state"),
        zip=_string(location_record, "zip"),
        country=country,
        contact_name=_string(contact, "name") or None,
        contact_email=_string(contact, "email") or None,
        contact_phone=_string(contact, "phone") or None,
        latitude=_float_value(geo_point.get("lat")) if geo_point is not None else None,
        longitude=_float_value(geo_point.get("lon")) if geo_point is not None else None,
    )


def _location_matches(
    *,
    location: TrialMatchLocation,
    query: TrialMatchingQuery,
) -> bool:
    if query.reference_city and query.reference_city.casefold() not in location.city.casefold():
        return False
    return not (query.country and not _countries_match(location.country, query.country))


def _countries_match(left: str, right: str) -> bool:
    left_key = left.casefold()
    right_key = right.casefold()
    if left_key == right_key:
        return True
    return left_key in _US_COUNTRY_VALUES and right_key in _US_COUNTRY_VALUES


def _intervention_names(record: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    for intervention in _mapping_list(record, "interventions"):
        name = _string(intervention, "name")
        if name:
            names.append(name)
    return list(dict.fromkeys(names))


def _primary_investigator(record: Mapping[str, object]) -> str | None:
    for official in _mapping_list(record, "overall_officials"):
        role = _string(official, "role")
        if role.casefold() == "principal_investigator":
            return _string(official, "name") or None
    return None


def _contact_email(
    *,
    record: Mapping[str, object],
    locations: list[TrialMatchLocation],
) -> str | None:
    for location in locations:
        if location.contact_email:
            return location.contact_email
    for contact in _mapping_list(record, "central_contacts"):
        email = _string(contact, "email")
        if email:
            return email
    return None


def _first_contact(
    contacts: list[Mapping[str, object]],
) -> Mapping[str, object]:
    for contact in contacts:
        if _string(contact, "email") or _string(contact, "phone") or _string(contact, "name"):
            return contact
    return {}


def _summary(value: str, *, max_length: int = 500) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def _status_priority(status: str) -> int:
    priority = {
        "RECRUITING": 3,
        "NOT_YET_RECRUITING": 2,
        "AVAILABLE": 1,
    }
    return priority.get(status.upper(), 0)


def _string(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _optional_string(record: Mapping[str, object], key: str) -> str | None:
    value = _string(record, key)
    return value or None


def _string_list(record: Mapping[str, object], key: str) -> list[str]:
    value = record.get(key)
    if not isinstance(value, list | tuple):
        return []
    return [" ".join(item.split()) for item in value if isinstance(item, str) and item.strip()]


def _mapping_list(record: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = record.get(key)
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _mapping_value(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


__all__ = [
    "TrialMatchingGatewayUnavailableError",
    "match_clinical_trials",
    "parse_list_parameter",
    "parse_status_parameter",
]
